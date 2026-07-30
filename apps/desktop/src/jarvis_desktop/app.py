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
import os
import threading
import json
import sys
import traceback
from pathlib import Path

import sounddevice as sd
from google import genai
from google.genai import types
from .ui import JarvisUI
from .memory_bridge import (
    load_memory,
    update_memory,
    format_memory_for_prompt,
)

# Phase 2: the legacy `actions/` directory has been removed entirely.
# All 17 actions have been migrated to `extensions/<id>/` (Phases 1A-1C)
# or are dropped (Phase 2 deprecates them — see OPENCLAW_MIGRATION_PLAN.md
# §24 for the new OpenClaw feature roadmap).
#
# Current tool surface (5 tools from OpenClaw-parity extensions, loaded dynamically):
#   - extensions/memory_core/   (memory_search, memory_get)
#   - extensions/cron/          (cron_schedule, cron_list, cron_cancel)
#
# Phase 4.3h: removed 6 JARVIS-original tools (tool_weather, tool_reminder,
# tool_open_app, tool_web_search, tool_send_message, tool_youtube_video)
# per the "same to same" architect rule — none of these exist in OpenClaw.


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
# Primary Live API model. Mirrors OpenClaw's
# ``GOOGLE_REALTIME_DEFAULT_MODEL`` in
# ``extensions/google/realtime-voice-provider.ts``.
# The previous ``gemini-2.5-flash-native-audio-preview-12-2025``
# was deprecated in 2026-Q1 and now returns
# ``1008 None. Requested entity was not found`` on connect
# (see Google's Live API deprecation notice + the
# ``google-gemini/gemini-skills`` Live API guide).
# Override at runtime with ``JARVIS_LIVE_MODEL``.
LIVE_MODEL = (
    os.environ.get("JARVIS_LIVE_MODEL")
    or "models/gemini-3.1-flash-live-preview"
)
# Fallback chain used when the primary model returns
# 1008 / "Requested entity was not found". The runtime
# walks the chain left-to-right and stops at the first
# model that accepts the WebSocket handshake. Mirrors
# OpenClaw's pattern of cycling through model versions
# before failing the session.
LIVE_MODEL_FALLBACKS: list[str] = [
    "models/gemini-2.5-flash-native-audio-preview-12-2025",
    "models/gemini-2.5-flash-native-audio-preview-09-2025",
    "models/gemini-live-2.5-flash-preview",
]
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


# ─────────────────────────────────────────────────────────────────────
# Phase 3.5: background memory extraction is gone. The legacy
# ``_update_memory_async`` path used a separate LLM call to decide
# whether a turn was worth remembering; in Phase 3.5 the model is
# the curator — the ``save_memory`` tool (in TOOL_DECLARATIONS below)
# is called inline when the model wants to remember something. This
# matches OpenClaw's memory-core flow and removes the `or_client`
# dependency from the host.
#
# Plugin manifest loader (PR 1B — full SDK-driven plugin loader)
#
# Reads every `extensions/*/openclaw.plugin.json` and returns the tool
# declarations declared in each manifest. Used to extend TOOL_DECLARATIONS
# below. Mirrors OpenClaw's `src/plugins/loader.ts`. Phase 1C hardens
# the SDK with strict `PluginManifest` typed schema (Phase 4.3h
# removed the original 2 consumer-feedback tools, but the contract
# itself is unchanged).
# ─────────────────────────────────────────────────────────────────────
def _load_plugins() -> (
    tuple[
        "list[dict]",  # tool_decls
        "dict[str, tuple]",  # plugin_dispatch
        "list",  # commands (list[CommandDecl])
        "list[tuple]",  # cli_handlers
        "list",  # skills (list[SkillDecl])
        "list",  # hooks (list[HookRegistration])
        "list",  # cron_jobs (list[CronDecl])
        "list[dict]",  # doctor_contracts (raw dicts)
        "list[dict]",  # http_handlers (Phase 3, raw dicts)
        "dict | None",  # channel (Phase 3, single-active-slot)
    ]
):
    """Discover + register every extension's plugin entry via the SDK.

    Mirrors OpenClaw's `src/plugins/loader.ts` pattern. For each
    ``extensions/<id>/openclaw.plugin.json``:
      1. dynamically import ``extensions.<id>``
      2. call ``entry.register(api)`` with a real ``PluginApi``
      3. collect tools / commands / cli / skills / hooks / cron /
         doctor contracts / http_handlers / channel

    Returns the 10-tuple
    ``(tool_decls, dispatch, commands, cli, skills, hooks, cron,
    doctor, http_handlers, channel)``. ``channel`` is single-slot
    (the last plugin to register wins; matches OpenClaw).
    """
    import json as _json
    import importlib
    from pathlib import Path as _Path

    from jarvis_sdk import PluginApi, PluginContext, Result  # noqa: F401

    workspace = _Path(__file__).resolve().parents[4]  # jarvis_desktop/src/jarvis_desktop/app.py
    extensions_dir = workspace / "extensions"
    if not extensions_dir.exists():
        return [], {}, [], [], [], [], [], [], [], None

    tool_decls: "list[dict]" = []
    plugin_dispatch: "dict[str, tuple]" = {}
    commands: list = []  # list[CommandDecl]
    cli_handlers: "list[tuple]" = []
    skills: list = []  # list[SkillDecl]
    hooks: list = []  # list[HookRegistration]
    cron_jobs: list = []  # list[CronDecl]
    doctor_contracts: "list[dict]" = []
    http_handlers: "list[dict]" = []  # Phase 3
    channel: "dict | None" = None  # Phase 3, single-active-slot

    for manifest_path in sorted(extensions_dir.glob("*/openclaw.plugin.json")):
        ext_name = manifest_path.parent.name
        try:
            manifest_obj = _json.loads(manifest_path.read_text(encoding="utf-8"))
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
        # Wire the manifest's `contracts.tools` declaration so the API
        # can validate plugin tool registrations against the declared
        # tool names. Mirrors the OpenClaw SDK ``PluginContext.set_manifest``
        # contract: tools not in ``contracts.tools`` are skipped at
        # ``register_tool`` time (4.3h contract).
        try:
            api.set_manifest(manifest_obj)
        except Exception as e:
            print(f"[WARN] {ext_name} set_manifest() failed: {e}")
        try:
            entry.register(api)
        except Exception as e:
            print(f"[WARN] {ext_name}.register() failed: {e}")
            continue

        for tool_inst in api.tool_instances:
            decls = getattr(tool_inst, "tools", [tool_inst] if hasattr(tool_inst, "name") else [])
            for tool_decl in decls:
                if not hasattr(tool_decl, "name") or not hasattr(tool_decl, "parameters"):
                    continue
                params: dict = {
                    "type": "OBJECT",
                    "properties": {},
                    "required": [],
                }
                for p in getattr(tool_decl, "parameters", []):
                    params["properties"][p.name] = {
                        "type": getattr(p, "type", "string").upper(),
                        "description": getattr(p, "description", ""),
                    }
                    if getattr(p, "required", False):
                        params["required"].append(p.name)
                tool_decls.append(
                    {
                        "name": tool_decl.name,
                        "description": getattr(tool_decl, "description", ""),
                        "parameters": params,
                    }
                )
                plugin_dispatch[tool_decl.name] = (tool_inst, tool_decl.name)

        commands.extend(api.commands)
        cli_handlers.extend(api.cli_handlers)
        skills.extend(api.skills)
        hooks.extend(api.hooks)
        cron_jobs.extend(api.cron_jobs)
        doctor_contracts.extend(api.doctor_contracts)
        http_handlers.extend(api.http_handlers)
        # Channel is single-active-slot (last writer wins, matches
        # OpenClaw's behavior). We keep the surface small: one
        # channel per process, the gateway and host route to it.
        if api.channel is not None:
            channel = api.channel

    return (
        tool_decls,
        plugin_dispatch,
        commands,
        cli_handlers,
        skills,
        hooks,
        cron_jobs,
        doctor_contracts,
        http_handlers,
        channel,
    )


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
    # Phase 2: legacy action tools (browser_control, file_controller,
    # file_processor, screen_process, computer_settings, desktop_control,
    # code_helper, dev_agent, computer_control, game_updater, flight_finder)
    # have been removed (the actions/ directory is gone). The 3 tools
    # below are JARVIS-internal and stay. The 6 + 5 plugin tools
    # (weather, reminder, open_app, web_search, send_message, youtube_video,
    # memory_search, memory_get, cron_schedule, cron_list, cron_cancel)
    # are loaded dynamically by _load_plugins().
    {
        "name": "agent_task",
        "description": (
            "Queue a long-running task for background execution. "
            "Returns the task id; poll via the same id."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "goal": {"type": "STRING", "description": "What the task should accomplish."},
                "priority": {
                    "type": "STRING",
                    "description": "low | normal | high (default: normal)",
                },
            },
            "required": ["goal"],
        },
    },
    {
        "name": "shutdown_jarvis",
        "description": "Shuts down the JARVIS session cleanly.",
        "parameters": {"type": "OBJECT", "properties": {}},
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
(
    _PLUGIN_TOOL_DECLS,
    _PLUGIN_DISPATCH,
    _PLUGIN_COMMANDS,
    _PLUGIN_CLI,
    _PLUGIN_SKILLS,
    _PLUGIN_HOOKS,
    _PLUGIN_CRON_JOBS,
    _PLUGIN_DOCTOR_CONTRACTS,
    _PLUGIN_HTTP_HANDLERS,  # Phase 3
    _PLUGIN_CHANNEL,  # Phase 3, single-active-slot
) = _load_plugins()
TOOL_DECLARATIONS.extend(_PLUGIN_TOOL_DECLS)

# ── Phase 2: wire skills / hooks / cron / doctor into host subsystems ───
# Skills augment the system prompt (one block per skill). Hooks fire
# at agent-loop boundaries (before_agent_start, agent_end, etc.).
# Cron is started in a background thread by the host on first use;
# the doctor runner is exposed for the CLI (jarvis doctor).
from src.hooks import HookBus  # noqa: E402
from src.doctor import DoctorRunner  # noqa: E402

_PLUGIN_HOOK_BUS = HookBus()
_PLUGIN_HOOK_BUS.register_all(_PLUGIN_HOOKS)
_PLUGIN_DOCTOR = DoctorRunner()
_PLUGIN_DOCTOR.add_raws(_PLUGIN_DOCTOR_CONTRACTS)

# ── Phase 3: gateway + channel wiring ────────────────────────────
# The gateway exposes plugin-registered HTTP routes on
# 127.0.0.1:7433. We register routes eagerly (so the plugin's
# `api.register_http_handler` call is honored), then start the
# server in a background thread. If the port is busy, we log a
# warning and skip — the desktop host shouldn't refuse to start
# just because another JARVIS instance is already running.
from src.gateway import Gateway, GatewayLockError  # noqa: E402

_GATEWAY = Gateway()
for _raw in _PLUGIN_HTTP_HANDLERS:
    try:
        _GATEWAY.add_raw(_raw)
    except (ValueError, TypeError) as e:
        print(f"[WARN] gateway: bad route {_raw.get('path', '?')!r}: {e}")

try:
    _GATEWAY.start()
except GatewayLockError as e:
    # Another JARVIS instance is already holding 7433 — that's
    # fine; the operator can route to that one instead. We do not
    # crash the host for this.
    print(f"[WARN] gateway: {e}")

# Phase 3 channel framework (simplified): if a plugin registered
# a channel, we expose it as a class-level singleton the slash
# command router can call. We don't auto-start a long-polling
# listener — that's opt-in via the CLI (`jarvis telegram setup`
# configures the bot; a future Phase 3.5 will add a "start
# channel" hook). For now the channel surface is wired so
# `api.register_channel({...})` is honored, but the listener is
# not spun up implicitly.
_PLUGIN_CHANNELS: dict[str, dict] = {}
if _PLUGIN_CHANNEL is not None:
    _PLUGIN_CHANNELS[_PLUGIN_CHANNEL.get("id", "default")] = _PLUGIN_CHANNEL
    print(
        f"[INFO] channel: registered {_PLUGIN_CHANNEL.get('id', '?')!r} "
        f"(send + listen available; listener not auto-started)"
    )


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

        # Phase 3: fire `before_agent_start` hook. Plugins can mutate
        # the system prompt (e.g. inject a skill, add context) before
        # the LLM session opens. Fire-and-forget — we don't block the
        # build on plugin hooks.
        from src.hooks import fire_sync

        fire_sync(
            _PLUGIN_HOOK_BUS,
            "before_agent_start",
            {"timestamp": datetime.now().isoformat()},
        )

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

        # ── Phase 2: inject skill bodies into the system prompt ────
        # Each skill's body becomes a labeled section. This is
        # the same one-shot the OpenClaw host does before
        # ``client.aio.live.connect``.
        from src.skills import skills_to_prompt_section

        skills_section = skills_to_prompt_section(_PLUGIN_SKILLS)

        parts = [time_ctx]
        if mem_str:
            parts.append(mem_str)
        parts.append(sys_prompt)
        if skills_section:
            parts.append(skills_section)

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

        # ── Host-owned tool context ────────────────────────────────
        # Mirrors OpenClaw's ``buildToolContext`` in
        # ``src/agents/agent-tools.before-tool-call.ts``: the host
        # injects ``agentId`` (and the per-agent memorySearch
        # override) into the tool call so the LLM never has to
        # pass it. Without this, plugins like
        # ``memory_recall`` / ``memory_store`` / ``memory_forget``
        # reject calls with ``Err("memory_recall requires an
        # enabled agentId.")`` because the LLM doesn't know what
        # agent it is running for. OpenClaw's pattern: the host
        # owns ``agentId``; the tool reads it from the context
        # (``ctx.agentId``), not from the LLM's args.
        from src.routing.agent_id import DEFAULT_AGENT_ID, normalize_agent_id

        # Only inject if the LLM didn't already pass one. If the
        # LLM DID pass one (e.g. via ``memory_recall(agentId="x",
        # query=...)``), trust it — but normalize it so the
        # plugin doesn't have to.
        if "agentId" in args and args["agentId"]:
            args["agentId"] = normalize_agent_id(args["agentId"])
        else:
            args.setdefault("agentId", DEFAULT_AGENT_ID)

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
            if name == "agent_task":
                # Phase 3.5: the legacy ``agent/task_queue.py`` is
                # gone (not in OpenClaw). The ``agent_task`` tool
                # stays in TOOL_DECLARATIONS for LLM compatibility
                # but always returns a clear "not yet available"
                # answer; the user-facing answer is what the model
                # surfaces to the operator.
                result = (
                    "The agent_task system has been removed in Phase 3.5. "
                    "It was a legacy JARVIS feature with no OpenClaw "
                    "equivalent; use `cron_schedule` for delayed jobs, "
                    "`reminder` for short-term nudges, or describe the "
                    "goal as a fresh prompt."
                )

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
                # Phase 2: the 11 legacy action tools (browser_control,
                # file_controller, file_processor, screen_process,
                # computer_settings, desktop_control, code_helper,
                # dev_agent, computer_control, game_updater,
                # flight_finder) have been removed. If the LLM asks
                # for one, we tell it the tool is gone rather than
                # throwing — this gives the model a chance to pick
                # a working alternative from the OpenClaw-parity
                # extension tools (memory_search, memory_get,
                # cron_schedule, etc.).
                result = (
                    f"Tool {name!r} is no longer available in JARVIS. "
                    "It was part of the legacy `actions/` layer that "
                    "was removed in Phase 2. Use an OpenClaw-parity "
                    "extension tool instead (memory_search, memory_get, "
                    "cron_schedule, etc.)."
                )

        except Exception as e:
            result = f"Tool '{name}' failed: {e}"
            traceback.print_exc()
            self.speak_error(name, e)

        if not self.ui.muted:
            self.ui.set_state("LISTENING")

        print(f"[JARVIS] 📤 {name} → {str(result)[:80]}")

        return types.FunctionResponse(id=fc.id, name=name, response={"result": result})

    async def _send_realtime(self):
        """Pump mic PCM chunks to the Live API.

        Matches the OLD JARVIS pattern that worked before
        the SDK / model upgrade: each chunk in
        ``self.out_queue`` is a ``{"data": bytes,
        "mime_type": "audio/pcm"}`` dict produced by
        ``_listen_audio``. The new SDK's
        ``send_realtime_input`` requires ``audio=``
        (not the deprecated ``media=``) so we wrap
        the dict in a ``types.Blob``.
        """
        while True:
            msg = await self.out_queue.get()
            if isinstance(msg, dict):
                await self.session.send_realtime_input(
                    audio=types.Blob(
                        data=msg.get("data"),
                        mime_type=msg.get("mime_type") or "audio/pcm",
                    )
                )
            else:
                # Defensive: pass the dict / Blob straight
                # through if the producer was already a
                # Blob (future-proof).
                await self.session.send_realtime_input(audio=msg)

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

                            # Phase 3.5: background LLM-based memory
                            # extraction is gone; the model calls
                            # `save_memory` directly when it wants
                            # to remember something.

                            # Phase 3: fire `agent_end` hook after each
                            # complete turn. Plugins can persist state
                            # (memory flush, metric emission, etc.).
                            from src.hooks import fire_sync

                            fire_sync(
                                _PLUGIN_HOOK_BUS,
                                "agent_end",
                                {"input": full_in, "output": full_out},
                            )

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

    def _is_model_not_found_error(self, error: BaseException) -> bool:
        """Return True when ``error`` looks like a deprecated / unknown model.

        The Gemini Live API closes the WebSocket with code
        1008 + reason "Requested entity was not found" when
        the model name is deprecated, revoked, or the API
        key doesn't have access to it. We use this signal
        to walk the ``LIVE_MODEL_FALLBACKS`` chain.
        """
        msg = str(error).lower()
        if "1008" in msg and "not found" in msg:
            return True
        if "requested entity was not found" in msg:
            return True
        return False

    def _is_transient_error(self, error: BaseException) -> bool:
        """True for reconnect-worthy failures (network blip, 5xx)."""
        msg = str(error).lower()
        if "1008" in msg:
            return False  # model_not_found, not transient
        return True

    async def _try_connect(
        self,
        client: "genai.Client",
        config: Any,
        model: str,
    ) -> Any:
        """Open a Live API session on ``model``; raise the raw error otherwise.

        Mirrors OpenClaw's pattern of cycling through model
        versions on 1008. Returns the session context
        manager; the caller enters it.
        """
        return client.aio.live.connect(model=model, config=config)

    async def run(self):
        client = genai.Client(api_key=_get_api_key(), http_options={"api_version": "v1beta"})

        # Active model: starts at LIVE_MODEL, falls back on
        # 1008 "Requested entity was not found". Persists
        # across reconnect cycles so a successful model is
        # not retried on every reconnect.
        active_model: str = LIVE_MODEL

        while True:
            try:
                print(f"[JARVIS] 🔌 Connecting ({active_model})...")
                self.ui.set_state("THINKING")
                config = self._build_config()

                async with (
                    client.aio.live.connect(model=active_model, config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session = session
                    self._loop = asyncio.get_event_loop()
                    self.audio_in_queue = asyncio.Queue()
                    self.out_queue = asyncio.Queue(maxsize=10)

                    print(f"[JARVIS] ✅ Connected ({active_model}).")
                    self.ui.set_state("LISTENING")
                    self.ui.write_log(f"SYS: JARVIS online ({active_model}).")

                    tg.create_task(self._send_realtime())
                    tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())

            except Exception as e:
                print(f"[JARVIS] ⚠️ {e}")
                if self._is_model_not_found_error(e):
                    # Walk the fallback chain. If we already
                    # used it, give up with a clear message.
                    tried = [active_model]
                    for fallback in LIVE_MODEL_FALLBACKS:
                        if fallback in tried:
                            continue
                        print(
                            f"[JARVIS] 🔁 Model {active_model} returned 1008 "
                            f"(not found). Trying fallback: {fallback}"
                        )
                        active_model = fallback
                        tried.append(fallback)
                        break
                    else:
                        print(
                            "[JARVIS] ❌ All Live API model fallbacks exhausted. "
                            "Common causes:\n"
                            "  1. The Gemini API key in config/api_keys.json "
                            "is invalid, revoked, or doesn't have Live API access.\n"
                            "  2. The current model is no longer available in "
                            "your region / tier.\n"
                            "Fix: rotate the Gemini key (see AGENTS.md security "
                            "section) or set JARVIS_LIVE_MODEL env var to a "
                            "known-good model like 'models/gemini-3.1-flash-live-preview'."
                        )
                        self.ui.write_log(
                            "SYS: ❌ Live API model not found. Rotate the "
                            "Gemini key or set JARVIS_LIVE_MODEL."
                        )
                        self.ui.set_state("IDLE")
                        await asyncio.sleep(30)
                        continue
                    # Don't sleep the full 3s on fallback; reconnect immediately.
                    continue
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
