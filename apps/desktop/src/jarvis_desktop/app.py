"""JARVIS desktop app — main entry.

This is the moved `main.py` from the legacy root layout. Two changes from the
original:

1. ``from ui import JarvisUI`` → ``from .ui import JarvisUI`` (relative import
   inside the package).
2. ``get_base_dir()`` returns the workspace root (``parents[3]`` of this file)
   instead of the script's parent, so legacy paths like
   ``config/api_keys.json`` and ``core/prompt.txt`` still resolve.

The full monolithic content is preserved; HUD splitting into ``hud/`` submodules
happens in Phase 1.
"""

from __future__ import annotations

import asyncio
import threading
import json
import sys
import traceback
from pathlib import Path

import sounddevice as sd
from google import genai
from google.genai import types
from .ui import JarvisUI
from memory.memory_manager import (
    load_memory,
    update_memory,
    format_memory_for_prompt,
    should_extract_memory,
    extract_memory,
)

from actions.file_processor import file_processor
from actions.flight_finder import flight_finder

# Phase 1C: 6 actions have migrated to `extensions/<id>/` extensions
# and are now loaded dynamically via `_load_plugins()` from each
# extension's `openclaw.plugin.json` entry:
#
#   - extensions/tool_weather/   (PR 1A)
#   - extensions/tool_reminder/  (PR 1B)
#   - extensions/tool_open_app/       (PR 1C)
#   - extensions/tool_web_search/     (PR 1C)
#   - extensions/tool_send_message/   (PR 1C)
#   - extensions/tool_youtube_video/  (PR 1C)
#
# The remaining 11 actions in `actions/` migrate in Phase 2.
from actions.computer_settings import computer_settings
from actions.screen_processor import screen_process
from actions.desktop import desktop_control
from actions.browser_control import browser_control
from actions.file_controller import file_controller
from actions.code_helper import code_helper
from actions.dev_agent import dev_agent
from actions.computer_control import computer_control
from actions.game_updater import game_updater


def get_base_dir() -> Path:
    """Workspace root, not the script's directory.

    From ``apps/desktop/src/jarvis_desktop/app.py`` the workspace root is
    four parents up:
      parents[0] = jarvis_desktop/
      parents[1] = src/
      parents[2] = desktop/
      parents[3] = apps/
      parents[4] = <workspace root>

    We resolve to the workspace root so the legacy ``config/`` and
    ``core/`` directories at the workspace root continue to work.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parents[4]


BASE_DIR = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
PROMPT_PATH = BASE_DIR / "core" / "prompt.txt"
LIVE_MODEL = "models/gemini-2.5-flash-native-audio-preview-12-2025"
CHANNELS = 1
SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE = 1024


def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _load_system_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return (
            "You are JARVIS, Tony Stark's AI assistant. "
            "Be concise, direct, and always use the provided tools to complete tasks. "
            "Never simulate or guess results — always call the appropriate tool."
        )


_last_memory_input = ""


def _update_memory_async(user_text: str, jarvis_text: str) -> None:
    global _last_memory_input

    user_text = (user_text or "").strip()
    jarvis_text = (jarvis_text or "").strip()

    if len(user_text) < 5 or user_text == _last_memory_input:
        return
    _last_memory_input = user_text

    try:
        api_key = _get_api_key()
        if not should_extract_memory(user_text, jarvis_text, api_key):
            return
        data = extract_memory(user_text, jarvis_text, api_key)
        if data:
            update_memory(data)
            print(f"[Memory] ✅ {list(data.keys())}")
    except Exception as e:
        if "429" not in str(e):
            print(f"[Memory] ⚠️ {e}")


# ─────────────────────────────────────────────────────────────────────
# Plugin manifest loader (PR 1B — full SDK-driven plugin loader)
#
# Reads every `extensions/*/openclaw.plugin.json` and returns the tool
# declarations declared in each manifest. Used to extend TOOL_DECLARATIONS
# below. Mirrors OpenClaw's `src/plugins/loader.ts`. Phase 1C hardens
# the SDK with two-consumer feedback (tool_weather + tool_reminder) and
# promotes the contract to a strict `PluginManifest` typed schema.
# ─────────────────────────────────────────────────────────────────────
def _load_plugins() -> (
    tuple[
        "list[dict]",
        "dict[str, tuple]",
        "list",  # list[CommandDecl]
        "list[tuple]",
    ]
):
    """Discover + register every extension's plugin entry via the SDK.

    Mirrors OpenClaw's `src/plugins/loader.ts` pattern. For each
    ``extensions/<id>/openclaw.plugin.json``:
      1. dynamically import ``extensions.<id>``
      2. call ``entry.register(api)`` with a real ``PluginApi``
      3. collect tool decls (→ TOOL_DECLARATIONS) + a dispatch map
         (→ _execute_tool) + commands + CLI handlers (→ Phase 8+)

    Returns ``(tool_decls, plugin_dispatch, commands, cli_handlers)``.
    """
    import json as _json
    import importlib
    from pathlib import Path as _Path

    from jarvis_sdk import PluginApi, PluginContext, Result  # noqa: F401

    workspace = _Path(__file__).resolve().parents[4]  # jarvis_desktop/src/jarvis_desktop/app.py
    extensions_dir = workspace / "extensions"
    if not extensions_dir.exists():
        return [], {}, [], []

    tool_decls: "list[dict]" = []
    plugin_dispatch: "dict[str, tuple]" = {}
    commands: list = []  # list[CommandDecl]
    cli_handlers: "list[tuple]" = []

    for manifest_path in sorted(extensions_dir.glob("*/openclaw.plugin.json")):
        ext_name = manifest_path.parent.name
        try:
            _json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, _json.JSONDecodeError) as e:
            print(f"[WARN] Could not read manifest {manifest_path}: {e}")
            continue

        try:
            entry_module = importlib.import_module(f"extensions.{ext_name}")
            entry = entry_module.entry
        except (ImportError, AttributeError) as e:
            print(f"[WARN] Could not load extensions.{ext_name} entry: {e}")
            continue

        ctx = PluginContext(
            plugin_id=entry.id,
            plugin_kind=entry.kind,
            data_dir=_Path.home() / ".jarvis" / "extensions" / ext_name,
            workspace=workspace,
        )
        api = PluginApi(ctx)
        try:
            entry.register(api)
        except Exception as e:
            print(f"[WARN] {ext_name}.register() failed: {e}")
            continue

        for tool_inst in api.tool_instances:
            for tool_decl in tool_inst.tools:
                params: dict = {
                    "type": "OBJECT",
                    "properties": {},
                    "required": [],
                }
                for p in tool_decl.parameters:
                    params["properties"][p.name] = {
                        "type": p.type.upper(),
                        "description": p.description,
                    }
                    if p.required:
                        params["required"].append(p.name)
                tool_decls.append(
                    {
                        "name": tool_decl.name,
                        "description": tool_decl.description,
                        "parameters": params,
                    }
                )
                plugin_dispatch[tool_decl.name] = (tool_inst, tool_decl.name)

        commands.extend(api.commands)
        cli_handlers.extend(api.cli_handlers)

    return tool_decls, plugin_dispatch, commands, cli_handlers


def _unwrap_result(result) -> str:
    """Convert a plugin's Result return to a string for the LLM."""
    from jarvis_sdk import Err, Ok

    if isinstance(result, Ok):
        v = result.value
        return v if isinstance(v, str) else str(v)
    if isinstance(result, Err):
        return f"Error: {result.error}"
    return str(result)


TOOL_DECLARATIONS = [
    # Phase 1A + 1B + 1C: 6 tools (weather_report, reminder, open_app,
    # web_search, send_message, youtube_video) are no longer in this
    # hardcoded list — they're loaded dynamically by `_load_plugins()`
    # from each extension's `openclaw.plugin.json` entry. The remaining
    # 11 entries below are the actions still in `actions/` (Phase 2).
    {
        "name": "screen_process",
        "description": (
            "Captures and analyzes the screen or webcam image. "
            "MUST be called when user asks what is on screen, what you see, "
            "analyze my screen, look at camera, etc. "
            "You have NO visual ability without this tool. "
            "After calling this tool, stay SILENT — the vision module speaks directly."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "angle": {
                    "type": "STRING",
                    "description": "'screen' to capture display, 'camera' for webcam. Default: 'screen'",
                },
                "text": {
                    "type": "STRING",
                    "description": "The question or instruction about the captured image",
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "computer_settings",
        "description": (
            "Controls the computer: volume, brightness, window management, keyboard shortcuts, "
            "typing text on screen, closing apps, fullscreen, dark mode, WiFi, restart, shutdown, "
            "scrolling, tab management, zoom, screenshots, lock screen, refresh/reload page. "
            "Use for ANY single computer control command. NEVER route to agent_task."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "The action to perform"},
                "description": {
                    "type": "STRING",
                    "description": "Natural language description of what to do",
                },
                "value": {
                    "type": "STRING",
                    "description": "Optional value: volume level, text to type, etc.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "browser_control",
        "description": (
            "Controls the web browser. Use for: opening websites, searching the web, "
            "clicking elements, filling forms, scrolling, any web-based task."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "go_to | search | click | type | scroll | fill_form | smart_click | smart_type | get_text | press | close",
                },
                "url": {"type": "STRING", "description": "URL for go_to action"},
                "query": {"type": "STRING", "description": "Search query for search action"},
                "selector": {"type": "STRING", "description": "CSS selector for click/type"},
                "text": {"type": "STRING", "description": "Text to click or type"},
                "description": {
                    "type": "STRING",
                    "description": "Element description for smart_click/smart_type",
                },
                "direction": {"type": "STRING", "description": "up or down for scroll"},
                "key": {"type": "STRING", "description": "Key name for press action"},
                "incognito": {"type": "BOOLEAN", "description": "Open in private/incognito mode"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "file_controller",
        "description": "Manages files and folders: list, create, delete, move, copy, rename, read, write, find, disk usage.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "list | create_file | create_folder | delete | move | copy | rename | read | write | find | largest | disk_usage | organize_desktop | info",
                },
                "path": {
                    "type": "STRING",
                    "description": "File/folder path or shortcut: desktop, downloads, documents, home",
                },
                "destination": {"type": "STRING", "description": "Destination path for move/copy"},
                "new_name": {"type": "STRING", "description": "New name for rename"},
                "content": {"type": "STRING", "description": "Content for create_file/write"},
                "name": {"type": "STRING", "description": "File name to search for"},
                "extension": {
                    "type": "STRING",
                    "description": "File extension to search (e.g. .pdf)",
                },
                "count": {"type": "INTEGER", "description": "Number of results for largest"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "desktop_control",
        "description": "Controls the desktop: wallpaper, organize, clean, list, stats.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "wallpaper | wallpaper_url | organize | clean | list | stats | task",
                },
                "path": {"type": "STRING", "description": "Image path for wallpaper"},
                "url": {"type": "STRING", "description": "Image URL for wallpaper_url"},
                "mode": {"type": "STRING", "description": "by_type or by_date for organize"},
                "task": {"type": "STRING", "description": "Natural language desktop task"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "code_helper",
        "description": "Writes, edits, explains, runs, or builds code files.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "write | edit | explain | run | build | auto (default: auto)",
                },
                "description": {
                    "type": "STRING",
                    "description": "What the code should do or what change to make",
                },
                "language": {
                    "type": "STRING",
                    "description": "Programming language (default: python)",
                },
                "output_path": {"type": "STRING", "description": "Where to save the file"},
                "file_path": {
                    "type": "STRING",
                    "description": "Path to existing file for edit/explain/run/build",
                },
                "code": {"type": "STRING", "description": "Raw code string for explain"},
                "args": {"type": "STRING", "description": "CLI arguments for run/build"},
                "timeout": {
                    "type": "INTEGER",
                    "description": "Execution timeout in seconds (default: 30)",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "dev_agent",
        "description": "Builds complete multi-file projects from scratch: plans, writes files, installs deps, opens VSCode, runs and fixes errors.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "description": {"type": "STRING", "description": "What the project should do"},
                "language": {
                    "type": "STRING",
                    "description": "Programming language (default: python)",
                },
                "project_name": {"type": "STRING", "description": "Optional project folder name"},
                "timeout": {
                    "type": "INTEGER",
                    "description": "Run timeout in seconds (default: 30)",
                },
            },
            "required": ["description"],
        },
    },
    {
        "name": "agent_task",
        "description": (
            "Executes complex multi-step tasks requiring multiple different tools. "
            "Examples: 'research X and save to file', 'find and organize files'. "
            "DO NOT use for single commands. NEVER use for Steam/Epic — use game_updater."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "goal": {
                    "type": "STRING",
                    "description": "Complete description of what to accomplish",
                },
                "priority": {
                    "type": "STRING",
                    "description": "low | normal | high (default: normal)",
                },
            },
            "required": ["goal"],
        },
    },
    {
        "name": "computer_control",
        "description": "Direct computer control: type, click, hotkeys, scroll, move mouse, screenshots, find elements on screen.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "type | smart_type | click | double_click | right_click | hotkey | press | scroll | move | copy | paste | screenshot | wait | clear_field | focus_window | screen_find | screen_click | random_data | user_data",
                },
                "text": {"type": "STRING", "description": "Text to type or paste"},
                "x": {"type": "INTEGER", "description": "X coordinate"},
                "y": {"type": "INTEGER", "description": "Y coordinate"},
                "keys": {"type": "STRING", "description": "Key combination e.g. 'ctrl+c'"},
                "key": {"type": "STRING", "description": "Single key e.g. 'enter'"},
                "direction": {"type": "STRING", "description": "up | down | left | right"},
                "amount": {"type": "INTEGER", "description": "Scroll amount (default: 3)"},
                "seconds": {"type": "NUMBER", "description": "Seconds to wait"},
                "title": {"type": "STRING", "description": "Window title for focus_window"},
                "description": {
                    "type": "STRING",
                    "description": "Element description for screen_find/screen_click",
                },
                "type": {"type": "STRING", "description": "Data type for random_data"},
                "field": {"type": "STRING", "description": "Field for user_data: name|email|city"},
                "clear_first": {
                    "type": "BOOLEAN",
                    "description": "Clear field before typing (default: true)",
                },
                "path": {"type": "STRING", "description": "Save path for screenshot"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "game_updater",
        "description": (
            "THE ONLY tool for ANY Steam or Epic Games request. "
            "Use for: installing, downloading, updating games, listing installed games, "
            "checking download status, scheduling updates. "
            "ALWAYS call directly for any Steam/Epic/game request. "
            "NEVER use agent_task, browser_control, or web_search for Steam/Epic."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "update | install | list | download_status | schedule | cancel_schedule | schedule_status (default: update)",
                },
                "platform": {
                    "type": "STRING",
                    "description": "steam | epic | both (default: both)",
                },
                "game_name": {
                    "type": "STRING",
                    "description": "Game name (partial match supported)",
                },
                "app_id": {"type": "STRING", "description": "Steam AppID for install (optional)"},
                "hour": {
                    "type": "INTEGER",
                    "description": "Hour for scheduled update 0-23 (default: 3)",
                },
                "minute": {
                    "type": "INTEGER",
                    "description": "Minute for scheduled update 0-59 (default: 0)",
                },
                "shutdown_when_done": {
                    "type": "BOOLEAN",
                    "description": "Shut down PC when download finishes",
                },
            },
            "required": [],
        },
    },
    {
        "name": "flight_finder",
        "description": "Searches Google Flights and speaks the best options.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "origin": {"type": "STRING", "description": "Departure city or airport code"},
                "destination": {"type": "STRING", "description": "Arrival city or airport code"},
                "date": {"type": "STRING", "description": "Departure date (any format)"},
                "return_date": {"type": "STRING", "description": "Return date for round trips"},
                "passengers": {
                    "type": "INTEGER",
                    "description": "Number of passengers (default: 1)",
                },
                "cabin": {"type": "STRING", "description": "economy | premium | business | first"},
                "save": {"type": "BOOLEAN", "description": "Save results to Notepad"},
            },
            "required": ["origin", "destination", "date"],
        },
    },
    {
        "name": "file_processor",
        "description": (
            "Processes any file that the user has uploaded or dropped onto the interface. "
            "Use this when the user refers to an uploaded file and wants an action on it. "
            "Supports: images (describe/ocr/resize/compress/convert), "
            "PDFs (summarize/extract_text/to_word), "
            "Word docs & text files (summarize/fix/reformat/translate), "
            "CSV/Excel (analyze/stats/filter/sort/convert), "
            "JSON/XML (validate/format/analyze), "
            "code files (explain/review/fix/optimize/run/document/test), "
            "audio (transcribe/trim/convert/info), "
            "video (trim/extract_audio/extract_frame/compress/transcribe/info), "
            "archives (list/extract), "
            "presentations (summarize/extract_text). "
            "ALWAYS call this tool when a file has been uploaded and the user gives a command about it. "
            "If the user's command is ambiguous, pick the most logical action for that file type."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "file_path": {
                    "type": "STRING",
                    "description": "Full path to the uploaded file. Leave empty to use the currently uploaded file.",
                },
                "action": {
                    "type": "STRING",
                    "description": (
                        "What to do with the file. Examples by type:\n"
                        "image: describe | ocr | resize | compress | convert | info\n"
                        "pdf: summarize | extract_text | to_word | info\n"
                        "docx/txt: summarize | fix | reformat | translate_hint | word_count | to_bullet\n"
                        "csv/excel: analyze | stats | filter | sort | convert | info\n"
                        "json: validate | format | analyze | to_csv\n"
                        "code: explain | review | fix | optimize | run | document | test\n"
                        "audio: transcribe | trim | convert | info\n"
                        "video: trim | extract_audio | extract_frame | compress | transcribe | info | convert\n"
                        "archive: list | extract\n"
                        "pptx: summarize | extract_text | analyze"
                    ),
                },
                "instruction": {
                    "type": "STRING",
                    "description": "Free-form instruction if action doesn't cover it. E.g. 'translate this to Turkish', 'find all email addresses'",
                },
                "format": {
                    "type": "STRING",
                    "description": "Target format for conversion. E.g. 'mp3', 'pdf', 'csv', 'png'",
                },
                "width": {"type": "INTEGER", "description": "Target width for image resize"},
                "height": {"type": "INTEGER", "description": "Target height for image resize"},
                "scale": {
                    "type": "NUMBER",
                    "description": "Scale factor for image resize (e.g. 0.5)",
                },
                "quality": {
                    "type": "INTEGER",
                    "description": "Quality 1-100 for image/video compress",
                },
                "start": {
                    "type": "STRING",
                    "description": "Start time for trim: seconds or HH:MM:SS",
                },
                "end": {"type": "STRING", "description": "End time for trim: seconds or HH:MM:SS"},
                "timestamp": {
                    "type": "STRING",
                    "description": "Timestamp for video frame extraction HH:MM:SS",
                },
                "column": {"type": "STRING", "description": "Column name for CSV filter/sort"},
                "value": {"type": "STRING", "description": "Filter value for CSV filter"},
                "condition": {
                    "type": "STRING",
                    "description": "Filter condition: equals|contains|gt|lt",
                },
                "ascending": {
                    "type": "BOOLEAN",
                    "description": "Sort order for CSV sort (default: true)",
                },
                "save": {"type": "BOOLEAN", "description": "Save result to file (default: true)"},
                "destination": {
                    "type": "STRING",
                    "description": "Output folder for archive extract",
                },
            },
            "required": [],
        },
    },
    {
        "name": "shutdown_jarvis",
        "description": (
            "Shuts down the assistant completely. "
            "Call this when the user expresses intent to end the conversation, "
            "close the assistant, say goodbye, or stop Jarvis. "
            "The user can say this in ANY language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        },
    },
    {
        "name": "save_memory",
        "description": (
            "Save an important personal fact about the user to long-term memory. "
            "Call this silently whenever the user reveals something worth remembering: "
            "name, age, city, job, preferences, hobbies, relationships, projects, or future plans. "
            "Do NOT call for: weather, reminders, searches, or one-time commands. "
            "Do NOT announce that you are saving — just call it silently. "
            "Values must be in English regardless of the conversation language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
                    "description": (
                        "identity — name, age, birthday, city, job, language, nationality | "
                        "preferences — favorite food/color/music/film/game/sport, hobbies | "
                        "projects — active projects, goals, things being built | "
                        "relationships — friends, family, partner, colleagues | "
                        "wishes — future plans, things to buy, travel dreams | "
                        "notes — habits, schedule, anything else worth remembering"
                    ),
                },
                "key": {
                    "type": "STRING",
                    "description": "Short snake_case key (e.g. name, favorite_food, sister_name)",
                },
                "value": {
                    "type": "STRING",
                    "description": "Concise value in English (e.g. Fatih, pizza, older sister)",
                },
            },
            "required": ["category", "key", "value"],
        },
    },
]


# ── Extend TOOL_DECLARATIONS with plugin-loaded tools ──────────────
# PR 1B: SDK-driven plugin loader. Discovers extensions, imports each
# entry, calls register(api), collects tool declarations and a dispatch
# map. Phase 2+ migrates the remaining 15 actions to extensions; the
# hardcoded list below shrinks as that happens.
_PLUGIN_TOOL_DECLS, _PLUGIN_DISPATCH, _PLUGIN_COMMANDS, _PLUGIN_CLI = _load_plugins()
TOOL_DECLARATIONS.extend(_PLUGIN_TOOL_DECLS)


class JarvisLive:
    def __init__(self, ui: JarvisUI):
        self.ui = ui
        self.session = None
        self.audio_in_queue = None
        self.out_queue = None
        self._loop = None
        self._is_speaking = False
        self._speaking_lock = threading.Lock()
        self.ui.on_text_command = self._on_text_command

        # ── Plugin initialization ──────────────────────────
        # Plugin dispatch is built once at import time by `_load_plugins()`
        # (PR 1B). The UI handle is passed to each plugin lazily inside
        # `_execute_tool` via `PluginContext`, so no eager init is needed
        # here. PR 1A's direct WeatherPlugin import was removed in 1B.

    def _on_text_command(self, text: str):
        if not self._loop or not self.session:
            return
        # Phase 1C: route slash commands to plugin-registered handlers
        # BEFORE the LLM. Free text falls through unchanged.
        if text.lstrip().startswith("/"):
            asyncio.run_coroutine_threadsafe(self._handle_slash_command(text), self._loop)
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(turns={"parts": [{"text": text}]}, turn_complete=True),
            self._loop,
        )

    async def _handle_slash_command(self, text: str) -> None:
        """Dispatch a slash command via the ``CommandRouter``.

        Phase 1C: a plugin command's ``reply_text`` is spoken via
        ``self.speak(...)`` and logged; we do NOT loop back to the LLM
        (which would re-trigger tool calls). ``suppress_reply`` from
        the handler is honored.
        """
        from .commands import CommandRouter

        router = CommandRouter(_PLUGIN_COMMANDS, ui=self.ui)
        result = await router.dispatch(text)
        if result is None:
            return  # router decided not to handle; not expected for "/"
        if result.reply_text and not self.ui.muted:
            self.speak(result.reply_text)
        if not self.ui.muted:
            self.ui.set_state("LISTENING")

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            self._is_speaking = value
        if value:
            self.ui.set_state("SPEAKING")
        elif not self.ui.muted:
            self.ui.set_state("LISTENING")

    def speak(self, text: str):
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(turns={"parts": [{"text": text}]}, turn_complete=True),
            self._loop,
        )

    def speak_error(self, tool_name: str, error: str):
        short = str(error)[:120]
        self.ui.write_log(f"ERR: {tool_name} — {short}")
        self.speak(f"Sir, {tool_name} encountered an error. {short}")

    def _build_config(self) -> types.LiveConnectConfig:
        from datetime import datetime

        memory = load_memory()
        mem_str = format_memory_for_prompt(memory)
        sys_prompt = _load_system_prompt()

        now = datetime.now()
        time_str = now.strftime("%A, %B %d, %Y — %I:%M %p")
        time_ctx = (
            f"[CURRENT DATE & TIME]\n"
            f"Right now it is: {time_str}\n"
            f"Use this to calculate exact times for reminders.\n\n"
        )

        parts = [time_ctx]
        if mem_str:
            parts.append(mem_str)
        parts.append(sys_prompt)

        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction="\n".join(parts),
            tools=[{"function_declarations": TOOL_DECLARATIONS}],
            session_resumption=types.SessionResumptionConfig(),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Charon")
                )
            ),
        )

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})

        print(f"[JARVIS] 🔧 {name}  {args}")
        self.ui.set_state("THINKING")

        # Event loop handle, used by both the plugin dispatch (below)
        # and the legacy hardcoded if/elif branches further down.
        loop = asyncio.get_event_loop()
        result = "Done."

        # ── Plugin dispatch (PR 1B) ─────────────────────────────────
        # Plugin-loaded tools route through this dispatch map. The
        # plugin returns a `Result` (Ok/Err) which we unwrap to a
        # string for the LLM.
        if name in _PLUGIN_DISPATCH:
            plugin_inst, call_name = _PLUGIN_DISPATCH[name]
            try:
                # Plugins are async-call but the underlying tool may be
                # sync; we use run_in_executor to keep the audio loop alive.
                plugin_result = await loop.run_in_executor(
                    None,
                    lambda inst=plugin_inst, cn=call_name, a=args: inst.call(cn, a),
                )
                # `call` may be sync (returns Result directly) or async
                # (returns awaitable). Handle both.
                if hasattr(plugin_result, "__await__"):
                    plugin_result = await plugin_result
                result = _unwrap_result(plugin_result) or f"{name} delivered."
                print(f"[JARVIS] 📤 {name} → {str(result)[:80]}")
                if not self.ui.muted:
                    self.ui.set_state("LISTENING")
                return types.FunctionResponse(id=fc.id, name=name, response={"result": result})
            except Exception as e:
                err_msg = f"Plugin '{name}' failed: {e}"
                print(f"[JARVIS] {err_msg}")
                traceback.print_exc()
                if not self.ui.muted:
                    self.ui.set_state("LISTENING")
                return types.FunctionResponse(id=fc.id, name=name, response={"result": err_msg})

        if name == "save_memory":
            category = args.get("category", "notes")
            key = args.get("key", "")
            value = args.get("value", "")
            if key and value:
                update_memory({category: {key: {"value": value}}})
                print(f"[Memory] 💾 save_memory: {category}/{key} = {value}")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name, response={"result": "ok", "silent": True}
            )

        try:
            if name == "browser_control":
                r = await loop.run_in_executor(
                    None, lambda: browser_control(parameters=args, player=self.ui)
                )
                result = r or "Done."

            elif name == "file_controller":
                r = await loop.run_in_executor(
                    None, lambda: file_controller(parameters=args, player=self.ui)
                )
                result = r or "Done."

            elif name == "file_processor":
                if not args.get("file_path") and self.ui.current_file:
                    args["file_path"] = self.ui.current_file
                r = await loop.run_in_executor(
                    None, lambda: file_processor(parameters=args, player=self.ui, speak=self.speak)
                )
                result = r or "Done."

            elif name == "screen_process":
                threading.Thread(
                    target=screen_process,
                    kwargs={
                        "parameters": args,
                        "response": None,
                        "player": self.ui,
                        "session_memory": None,
                    },
                    daemon=True,
                ).start()
                result = "Vision module activated. Stay completely silent — vision module will speak directly."

            elif name == "computer_settings":
                r = await loop.run_in_executor(
                    None, lambda: computer_settings(parameters=args, response=None, player=self.ui)
                )
                result = r or "Done."

            elif name == "desktop_control":
                r = await loop.run_in_executor(
                    None, lambda: desktop_control(parameters=args, player=self.ui)
                )
                result = r or "Done."

            elif name == "code_helper":
                r = await loop.run_in_executor(
                    None, lambda: code_helper(parameters=args, player=self.ui, speak=self.speak)
                )
                result = r or "Done."

            elif name == "dev_agent":
                r = await loop.run_in_executor(
                    None, lambda: dev_agent(parameters=args, player=self.ui, speak=self.speak)
                )
                result = r or "Done."

            elif name == "agent_task":
                from agent.task_queue import get_queue, TaskPriority

                priority_map = {
                    "low": TaskPriority.LOW,
                    "normal": TaskPriority.NORMAL,
                    "high": TaskPriority.HIGH,
                }
                priority = priority_map.get(
                    args.get("priority", "normal").lower(), TaskPriority.NORMAL
                )
                task_id = get_queue().submit(
                    goal=args.get("goal", ""), priority=priority, speak=self.speak
                )
                result = f"Task started (ID: {task_id})."

            elif name == "computer_control":
                r = await loop.run_in_executor(
                    None, lambda: computer_control(parameters=args, player=self.ui)
                )
                result = r or "Done."

            elif name == "game_updater":
                r = await loop.run_in_executor(
                    None, lambda: game_updater(parameters=args, player=self.ui, speak=self.speak)
                )
                result = r or "Done."

            elif name == "flight_finder":
                r = await loop.run_in_executor(
                    None, lambda: flight_finder(parameters=args, player=self.ui)
                )
                result = r or "Done."
            elif name == "shutdown_jarvis":
                self.ui.write_log("SYS: Shutdown requested.")
                self.speak("Goodbye, sir.")

                def _shutdown():
                    import time
                    import os

                    time.sleep(1)
                    os._exit(0)

                threading.Thread(target=_shutdown, daemon=True).start()
            else:
                result = f"Unknown tool: {name}"

        except Exception as e:
            result = f"Tool '{name}' failed: {e}"
            traceback.print_exc()
            self.speak_error(name, e)

        if not self.ui.muted:
            self.ui.set_state("LISTENING")

        print(f"[JARVIS] 📤 {name} → {str(result)[:80]}")

        return types.FunctionResponse(id=fc.id, name=name, response={"result": result})

    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            await self.session.send_realtime_input(media=msg)

    async def _listen_audio(self):
        print("[JARVIS] 🎤 Mic started")
        loop = asyncio.get_event_loop()

        def callback(indata, frames, time_info, status):
            with self._speaking_lock:
                jarvis_speaking = self._is_speaking
            if not jarvis_speaking and not self.ui.muted:
                data = indata.tobytes()
                loop.call_soon_threadsafe(
                    self.out_queue.put_nowait, {"data": data, "mime_type": "audio/pcm"}
                )

        try:
            with sd.InputStream(
                samplerate=SEND_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK_SIZE,
                callback=callback,
            ):
                print("[JARVIS] 🎤 Mic stream open")
                while True:
                    await asyncio.sleep(0.1)
        except Exception as e:
            print(f"[JARVIS] ❌ Mic: {e}")
            raise

    async def _receive_audio(self):
        print("[JARVIS] 👂 Recv started")
        out_buf, in_buf = [], []

        try:
            while True:
                async for response in self.session.receive():
                    if response.data:
                        self.audio_in_queue.put_nowait(response.data)

                    if response.server_content:
                        sc = response.server_content

                        if sc.output_transcription and sc.output_transcription.text:
                            self.set_speaking(True)
                            txt = sc.output_transcription.text.strip()
                            if txt:
                                out_buf.append(txt)

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = sc.input_transcription.text.strip()
                            if txt:
                                in_buf.append(txt)

                        if sc.turn_complete:
                            self.set_speaking(False)

                            full_in = " ".join(in_buf).strip()
                            if full_in:
                                self.ui.write_log(f"You: {full_in}")
                            in_buf = []

                            full_out = " ".join(out_buf).strip()
                            if full_out:
                                self.ui.write_log(f"Jarvis: {full_out}")
                            out_buf = []

                            if full_in and len(full_in) > 5:
                                threading.Thread(
                                    target=_update_memory_async,
                                    args=(full_in, full_out),
                                    daemon=True,
                                ).start()

                    if response.tool_call:
                        fn_responses = []
                        for fc in response.tool_call.function_calls:
                            print(f"[JARVIS] 📞 {fc.name}")
                            fr = await self._execute_tool(fc)
                            fn_responses.append(fr)
                        await self.session.send_tool_response(function_responses=fn_responses)

        except Exception as e:
            print(f"[JARVIS] ❌ Recv: {e}")
            traceback.print_exc()
            raise

    async def _play_audio(self):
        print("[JARVIS] 🔊 Play started")
        loop = asyncio.get_event_loop()

        stream = sd.RawOutputStream(
            samplerate=RECEIVE_SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=CHUNK_SIZE,
        )
        stream.start()
        try:
            while True:
                chunk = await self.audio_in_queue.get()
                self.set_speaking(True)
                await asyncio.to_thread(stream.write, chunk)
        except Exception as e:
            print(f"[JARVIS] ❌ Play: {e}")
            raise
        finally:
            self.set_speaking(False)
            stream.stop()
            stream.close()

    async def run(self):
        client = genai.Client(api_key=_get_api_key(), http_options={"api_version": "v1beta"})

        while True:
            try:
                print("[JARVIS] 🔌 Connecting...")
                self.ui.set_state("THINKING")
                config = self._build_config()

                async with (
                    client.aio.live.connect(model=LIVE_MODEL, config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session = session
                    self._loop = asyncio.get_event_loop()
                    self.audio_in_queue = asyncio.Queue()
                    self.out_queue = asyncio.Queue(maxsize=10)

                    print("[JARVIS] ✅ Connected.")
                    self.ui.set_state("LISTENING")
                    self.ui.write_log("SYS: JARVIS online.")

                    tg.create_task(self._send_realtime())
                    tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())

            except Exception as e:
                print(f"[JARVIS] ⚠️ {e}")
                traceback.print_exc()

            self.set_speaking(False)
            self.ui.set_state("THINKING")
            print("[JARVIS] 🔄 Reconnecting in 3s...")
            await asyncio.sleep(3)


def main():
    ui = JarvisUI("face.png")

    def runner():
        ui.wait_for_api_key()
        jarvis = JarvisLive(ui)
        try:
            asyncio.run(jarvis.run())
        except KeyboardInterrupt:
            print("\n🔴 Shutting down...")

    threading.Thread(target=runner, daemon=True).start()
    ui.root.mainloop()


if __name__ == "__main__":
    main()
