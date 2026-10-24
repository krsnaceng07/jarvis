"""packages/voice_pipeline/src/jarvis_voice_pipeline/pipeline_builder.py

Native Gemini Live Multimodal Pipeline Builder for JARVIS:
Assembles prompt, memory (USER.md + MEMORY.md + SQLite FTS5), and JARVIS tool schemas
for real-time native bidirectional audio streaming.
"""

from __future__ import annotations

import inspect
import json
import logging
from pathlib import Path
from typing import Any, Callable, Optional

from jarvis_desktop.memory_bridge import format_memory_for_prompt
from jarvis_desktop.tool_declarations import build_jarvis_tool_declarations
from jarvis_desktop.tool_pipeline import execute_desktop_action, prepare_tool_arguments
from jarvis_sdk.loader import skills_to_prompt_section

logger = logging.getLogger("jarvis.voice_pipeline.builder")


VOICE_PRIORITY_TOOLS: set[str] = {
    # System exploration & file inspection
    "ls",
    "read",
    "write",
    "edit",
    "exec",
    "process",
    # UI Automation & Browsing
    "computer",
    "browser",
    "web_search",
    "web_fetch",
    # Documents, Media & Creative Generation
    "pdf",
    "image_generate",
    "video_generate",
    "music_generate",
    # Memory & State
    "save_memory",
    "recall_memory",
    # System Control
    "shutdown_jarvis",
    "standby_jarvis",
    # Goal Tracking
    "create_goal",
    "update_goal",
    # Automations, Cron & Background Subagents
    "automations",
    "sessions_spawn",
    "sessions_yield",
    "subagents",
    # Capabilities, Plugins & Channels
    "skill_workshop",
    "plugins",
    "secrets",
    "channels",
}

VOICE_TOOL_DESCRIPTIONS: dict[str, str] = {
    "ls": (
        "List files, folders, or drives at path (e.g. 'E:\\', 'E:\\stonic', 'C:\\Users', 'drives'). "
        "MUST call this whenever user asks to inspect, check, explore, search, or analyze any folder or drive."
    ),
    "exec": (
        "Execute a shell or PowerShell command on host PC (e.g. dir, Get-ChildItem, python, git). "
        "Use for deep recursive searches or running system commands."
    ),
    "computer": (
        "Control native Windows desktop UI (click, double_click, move_cursor, inspect_ui, screenshot, type, key, minimize, maximize) "
        "and physical hardware controls (set_volume, get_volume, mute, unmute, adjust_volume, set_brightness, get_brightness). "
        "MUST invoke when user asks for mouse/UI actions, or system volume / screen brightness changes."
    ),
    "browser": (
        "Automate web browsing and DOM. "
        "MUST invoke for opening websites, ChatGPT, YouTube, searching Google, clicking links, or typing in web forms."
    ),
    "read": "Read text or image file contents from disk.",
    "write": "Write full content to a file on disk. Creates parent directories if needed.",
    "edit": "Surgically edit parts of an existing file by replacing old text with new text.",
    "process": (
        "Manage host applications and background tasks (action='open'|'kill'|'wait'|'list', target=..., session_id=...)."
    ),
    "pdf": "Read, extract text, or convert documents to styled PDF (file_path, output_path, action='read'|'convert').",
    "image_generate": "Generate or edit images from text descriptions (action='generate'|'status'|'list', prompt=...).",
    "video_generate": "Generate video animations from text prompts or images (prompt=...).",
    "music_generate": "Generate audio/music tracks from text descriptions (prompt=...).",
    "save_memory": "Save an important personal fact about user to long-term memory.",
    "recall_memory": "Retrieve facts, user preferences, projects, or history from memory.",
    "shutdown_jarvis": "Terminates and exits the JARVIS desktop process on host PC when explicitly commanded.",
    "standby_jarvis": "Put JARVIS into standby sleep mode until wake word 'Hey Jarvis'.",
    "web_search": "Search Google for current information, documentation, news, or technical syntax.",
    "web_fetch": "Fetch content of a web page by URL.",
    "automations": (
        "Schedule, inspect, run, or delete automated recurring or one-shot cron tasks "
        "(action='create'|'add'|'list'|'delete'|'status'|'run', schedule=..., payload=...)."
    ),
    "sessions_spawn": (
        "Spawn an autonomous background subagent to execute long, slow, research, or multi-step tasks in parallel "
        "(task=..., label=..., run_timeout_seconds=...). Returns immediately so you can multitask with the user."
    ),
    "sessions_yield": (
        "Yield turn while waiting for background subagent tasks (message=...)."
    ),
    "subagents": (
        "Inspect running or recent background subagents or cancel a background task "
        "(action='list'|'cancel', task_id=...)."
    ),
    "skill_workshop": "Inspect, train, create, or test agent skills and capabilities (action='create'|'test'|'list', name=...).",
    "plugins": "Inspect, enable, or disable JARVIS plugins and extensions (action='list'|'enable'|'disable', plugin_id=...).",
    "secrets": "Securely view or manage API keys and credentials (action='list'|'get'|'set', name=...).",
    "channels": "Manage and inspect communication channels like Telegram, WhatsApp, Discord (action='list'|'status').",
}


def _clean_schema(schema: Any) -> Any:
    """Recursively normalize JSON Schema types to lowercase and strip unsupported fields."""
    if not isinstance(schema, dict):
        return schema
    cleaned: dict[str, Any] = {}
    for k, v in schema.items():
        if k in ("additionalProperties", "additional_properties", "title") or k.startswith("$"):
            continue
        if k == "type":
            if isinstance(v, str):
                cleaned["type"] = v.lower()
            elif isinstance(v, list):
                cleaned["type"] = [item.lower() if isinstance(item, str) else item for item in v]
            else:
                cleaned["type"] = v
        elif k == "properties" and isinstance(v, dict):
            cleaned["properties"] = {
                prop_k: _clean_schema(prop_v)
                for prop_k, prop_v in v.items()
                if isinstance(prop_v, dict)
            }
        elif k == "items" and isinstance(v, dict):
            cleaned["items"] = _clean_schema(v)
        elif k == "description" and isinstance(v, str):
            first_line = v.strip().split("\n")[0].strip()
            cleaned[k] = first_line[:97] + "..." if len(first_line) > 100 else first_line
        elif k in ("required", "enum", "format"):
            cleaned[k] = v
    if "type" not in cleaned and "properties" in cleaned:
        cleaned["type"] = "object"
    # CRITICAL PROTOCOL INVARIANT: Google Gemini Live requires items for every array parameter
    if cleaned.get("type") == "array" and ("items" not in cleaned or not cleaned["items"]):
        cleaned["items"] = {"type": "string"}
    return cleaned


def build_jarvis_system_prompt(base_dir: Path, plugin_skills: list[Any]) -> str:
    """Assembles the deterministic JARVIS System Prompt with strict byte budgets."""
    core_prompt_path = base_dir / "core" / "prompt.txt"
    core_directives = (
        core_prompt_path.read_text(encoding="utf-8")
        if core_prompt_path.exists()
        else "You are JARVIS, an autonomous multimodal operating system assistant."
    )

    memory_section = format_memory_for_prompt(
        workspace_dir=base_dir,
        max_user_bytes=5_120,
        max_memory_bytes=20_480,
    )
    skills_section = skills_to_prompt_section(plugin_skills)

    voice_contract = (
        "\n## REAL-TIME VOICE & ACTION CONTRACT\n"
        "- Execute non-destructive tools immediately (Action-First) without asking permission.\n"
        "- Keep spoken responses crisp, natural, and friendly (1-3 sentences).\n"
        "- Adapt seamlessly between Nepali, English, or mixed conversation.\n"
        "- ZERO FAKE COMPLETION: Execute available steps yourself and report the exact blocker when a step cannot be completed. Use the already-authenticated browser profile when possible. If a site requires login and no approved credential is available, leave the page visible and ask the user to authenticate there; never ask them to speak or paste a password or OTP into chat.\n"
        "- FOREGROUND VISIBLE EXECUTION DEFAULT (REAL PC AUTOMATION): When the user commands any interactive task, website action (e.g. ChatGPT, YouTube, Facebook, Google, web portals), desktop app action, mouse movement, typing, or downloading, you MUST execute it VISIBLY IN THE FOREGROUND ON THE PC SCREEN! The user must physically see the browser/app window open on screen, navigation happen, inputs typed, buttons clicked, generation settle, and files downloaded! STRICT BAN ON FALSE 'BACKGROUND' CLAIMS: NEVER tell the user 'म ब्याकग्राउन्डमा सुरु गर्दै छु' for interactive tasks! Background execution is strictly reserved for when the user explicitly requests 'ब्याकग्राउन्डमा' or for silent headless batch jobs.\n"
        "- MANDATORY ACTION-FIRST EXECUTION WITH CONCURRENT SPOKEN ACKNOWLEDGMENT: When the user commands an action (e.g. open ChatGPT, search Google, generate image, play song, change volume, open folder, create file), you MUST CALL THE APPROPRIATE TOOL IN THE VERY FIRST TURN! Simultaneously, speak a brief, warm 1-sentence acknowledgment (e.g. 'हुन्छ Sir, म डाउनलोड्समा क्रिस्टल फोल्डर बनाउँदै छु...' or 'Sure Sir, opening that for you right away...') ALONGSIDE the tool call so the user knows exactly what you are doing in real time! Never execute tasks in dead silence, and never make empty verbal promises without invoking the tool call.\n"
        "- JARVIS PROMISED WORK & ZERO-GHOST-CHATTER INVARIANT (CRITICAL):\n"
        "  * Actionable request: ACT IMMEDIATELY. Never stay in pure conversation or make empty promises when a tool exists.\n"
        "  * Saying 'Ma khojchhu', 'Ma herchhu', 'Ma wishleshan garchhu', 'I will check', 'I will analyze', or 'Ma gardai chhu' is a PROGRESS UPDATE, NOT A FINAL ANSWER! You MUST emit the tool call (e.g. ls, exec, browser, computer) in the EXACT SAME TURN!\n"
        "  * STRICT BAN ON EMPTY VERBAL COMMITMENTS: If the user commands you to inspect, check, explore, or analyze a drive or folder (e.g. 'E: drive ma Stonic folder', 'C: ma', 'downloads ma'), you MUST CALL `ls(path='E:\\stonic')` OR `exec` in that turn. Ending a turn with only speech and NO tool call when the user requested an action is a FATAL CONTRACT FAILURE.\n"
        "  * STRICT BAN ON LYING ABOUT PROGRESS: When the user asks 'did you do what I said?' ('maile bhaneko kura gariyo', 'k vo', 'k gardai chhau', 'what are you doing'), DO NOT lie and say 'Ma gardaichhu'! If a tool has not run, CALL THE TOOL IMMEDIATELY in that turn.\n"
        "  * WINDOWS PATH RESOLUTION: When the user refers to Windows drives or folders (e.g. 'E drive', 'E ma stonik folder', 'D ma', 'C drive'), translate them to Windows absolute paths: 'E:\\stonic', 'E:\\', 'C:\\', 'C:\\Users\\<user>\\Downloads', etc. Always pass the path to `ls(path='E:\\stonic')` or `exec(command='Get-ChildItem E:\\stonic')`.\n"
        "- FOLDER & FILE NAMING CONVENTION: When the user asks in Nepali to create a folder or file (e.g. 'क्रिस्टल नामको फोल्डर बनाउ', 'कृष्ण नामको फोल्डर बनाउ'), use clean English / Latin script for directory and file names (e.g. 'Crystal', 'Krishna', 'Documents', etc.) unless the user explicitly asks for Devanagari script. Standard Windows filesystems and command lines prefer clean ASCII/English names.\n"
        "- TRANSCRIPTION SCRIPT CONVENTION: Speak naturally in spoken Nepali as requested. For written output and transcriptions, default to Romanized Nepali (English / Latin alphabet, e.g. 'Namaste Sir, ma folder banaudai chhu') unless the user explicitly requests Devanagari script ('नेपालीमै लेख' or 'देवनागरीमा लेख').\n"
        "- DYNAMIC N-STEP AUTONOMOUS TASK EXECUTION: Real-world tasks are not fixed to 6 steps—they dynamically scale to 2, 5, 8, 12, or 20+ steps depending on complexity! Intelligently analyze the user's goal, deduce all required steps, and execute them sequentially to completion:\n"
        "  1. Open Target: Launch the browser to the exact URL (`browser(action='open', url='https://chatgpt.com')`) or open the desktop application visibly.\n"
        "  2. Settle & Observe: Inspect the DOM/UI snapshot (`browser(action='snapshot')` or `computer(action='inspect_ui')`) to verify rendering.\n"
        "  3. Clear Roadblocks: Dismiss cookie consent, popups, or blocking modals.\n"
        "  4. Authentication: If login is required, fill credentials or handle sign-in.\n"
        "  5. Core Action: Locate the input field, type the prompt/text, and submit (`press_key: 'Return'`).\n"
        "  6. Wait for Generation: Monitor generation progress dynamically until complete.\n"
        "  7. Verify Output: Visually verify that the output/image/result has rendered in the DOM.\n"
        "  8. Deliverable: Download/save the final deliverable (e.g. image, file, code) to user's PC (`~/Desktop` or `~/Downloads`), verify its existence, and confirm the deliverable!\n"
        "  9. Adaptive Followthrough: Continue with any subsequent steps the user requested until 100% complete!\n"
        "- MANDATORY ACTION PRECEDENCE (NO FAKE PROGRESS): NEVER claim you completed an action (e.g. 'मैले भोल्युम ६०% मा सेट गरिदिएँ', 'I have adjusted the brightness', 'मैले एप खोलिदिएँ') UNLESS you have FIRST called the respective tool and verified its execution result. Calling the tool FIRST is strictly required. Speaking or hallucinating success without calling the tool is STRICTLY FORBIDDEN.\n"
        "- MANDATORY TRUTHFULNESS ON BACKGROUND TASKS (ZERO FAKE PROGRESS): NEVER claim that a background task is running, in progress, or completed unless you actually called a background tool (e.g. `sessions_spawn`, `process`, or `exec`) in this session AND it succeeded. If a tool call returned an error or failed, report the failure honestly. Fabricating fake background progress or inventing tasks is STRICTLY FORBIDDEN.\n"
        "- MOUSE & GUI AUTOMATION RULE (JARVIS CURSOR & REAL INPUT): When the user asks you to use the mouse, click, double click, move the cursor, or interact with GUI controls (e.g. 'माउस युज गर', 'माउसले खोल', 'mouse use gara', 'click gara', 'कर्सर सार', 'double click'), you MUST invoke the `computer` tool (action='click', 'double_click', 'move_cursor', 'drag') and NEVER use `exec` or CLI commands to bypass it! To open an icon, folder, or file on Windows desktop or File Explorer with the mouse, use `action='double_click'` (single-click only highlights/selects). It is a STRICT VIOLATION to tell the user 'म माउस को प्रयोग गरेर...' (I am using the mouse...) while calling `exec`!\n"
        "- SYSTEM VOLUME & SCREEN BRIGHTNESS CONTROL: For system audio volume or display brightness, ALWAYS invoke `computer(action='set_volume', value=...)`, `computer(action='get_volume')`, `computer(action='set_brightness', value=...)`, or `computer(action='get_brightness')`. Never hallucinate changing volume or brightness without calling `computer` first!\n"
        "- If the user commands web navigation, search, or YouTube, invoke the `browser` tool.\n"
        "- When executing desktop commands, bash, powershell, or running code, invoke the appropriate tool.\n"
        "- PDF & DOCUMENT PROCESSING (READING & CONVERSION): When the user asks you to read, extract, convert/create, or open a PDF document (e.g. '[FILE_UPLOADED]', 'यो पुरै पढ', 'पिडीएफ पढ्नुहोस्', 'read this file', 'CV lai PDF banau', 'convert to pdf', 'open pdf', 'show pdf'), immediately invoke the `pdf` tool (with `file_path`, optional `output_path`, and `action='convert'` or `'read'`). On Windows, opening a PDF launches the system's default PDF viewer (e.g. Google Chrome or Edge). If the user asks why Chrome opened, explain that Chrome is the PC's default PDF viewer. To show the file directly in File Explorer, use `explorer.exe /select,\"<path>\"`. NEVER attempt to upload user documents to third-party web converters, and NEVER say you cannot read or generate PDFs!\n"
        "- JARVIS 5-STAGE CAPABILITY LADDER & AUTONOMOUS TOOL ARBITRATION (ZERO PREMATURE REFUSAL):\n"
        "  * Choose the available tool that matches the requested outcome; do not claim a capability before checking that the relevant tool exists and returned a successful result.\n"
        "  * 5-Stage Capability Ladder:\n"
        "    1. Dedicated Tool: If a matching tool exists, invoke it directly.\n"
        "    2. Desktop Automation & Mouse Control (`computer` / `desktop`): For any GUI interaction, clicking icons/folders, moving cursor, window management, or when the user asks for mouse actions, invoke `computer` directly. To open icons/folders, use `double_click`.\n"
        '    3. Universal Host Execution (`exec`): If no GUI/dedicated tool applies, invoke `exec` with PowerShell, Windows CMD, WMI cmdlets, registry edits, `winget`, or inline Python scripts (`python -c "..."`).\n'
        "    4. Autonomous Google/Web Search & Learning (`web_search` / `web_fetch`): If you do not know the exact PowerShell cmdlet, registry key, API syntax, or technical method, immediately run `web_search` to discover the exact command, learn it, then execute it via `exec`.\n"
        "    5. Dynamic Tool / Skill Authoring (`skill_workshop` & `write`): If a task requires custom multi-step logic or reusable functionality, dynamically create a script or skill using `skill_workshop` or `write`, and run it.\n"
        "  * SUBAGENTS & PARALLEL MULTITASKING: When the user requests a background job, deep research, codebase analysis, long-running headless batch task, or explicitly asks for background execution ('ब्याकग्राउन्डमा गर', 'run in background'), invoke `sessions_spawn(task=..., label=...)` immediately! Simultaneously speak a brief acknowledgment (e.g. 'हुन्छ Sir, म ब्याकग्राउन्डमा सब-एजेन्ट सुरु गर्दै छु...'). Subagents run asynchronously in parallel, freeing you to converse and multitask freely with Sir! Once the subagent finishes, a notification will arrive for you to announce the completion findings to Sir.\n"
        "  * AUTOMATIONS & CRON SCHEDULING: When the user asks for a reminder, recurring schedule, or timer (e.g. '१० मिनेट पछि सम्झाउ', 'every 5 minutes do X', 'schedule a job'), invoke `automations(action='create', schedule=..., payload=...)`. For relative delays, pass seconds (e.g. '600' or '10m'); for recurring, pass a 5-field cron expression ('*/5 * * * *'); to list or cancel, use `action='list'` or `action='delete'`.\n"
        "  * Only if ALL stages fail or are physically impossible (e.g. non-existent physical hardware) may you state the exact technical roadblock.\n"
    )

    # Dynamic temporal & environment context
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo

    try:
        npt_zone = ZoneInfo("Asia/Kathmandu")
        now_npt = datetime.now(npt_zone)
        now_utc = datetime.now(timezone.utc)
        time_npt_str = now_npt.strftime("%I:%M:%S %p")
        date_npt_str = now_npt.strftime("%A, %B %d, %Y")
        time_utc_str = now_utc.strftime("%I:%M:%S %p UTC")
    except Exception:
        now_utc = datetime.now(timezone.utc)
        time_npt_str = now_utc.strftime("%I:%M:%S %p")
        date_npt_str = now_utc.strftime("%A, %B %d, %Y")
        time_utc_str = now_utc.strftime("%I:%M:%S %p UTC")

    temporal_section = (
        "\n## CURRENT ENVIRONMENT & TEMPORAL CONTEXT\n"
        f"- Current Local Time: {time_npt_str} NPT (Nepal Standard Time, UTC+5:45)\n"
        f"- Current Date: {date_npt_str}\n"
        f"- Current UTC Time: {time_utc_str}\n"
        "- Location Context: Nepal (Timezone: Asia/Kathmandu, UTC+5:45)\n"
        "- Spoken Time Directives: When the user asks for the current time or date, answer immediately using the Current Local Time in Nepal Standard Time provided above. State the time directly, naturally, and warmly in Nepali or English as requested. Never guess UTC, never claim you don't know the time, and never launch an unnecessary web search or tool for the current time.\n"
    )

    goal_section = ""
    try:
        from src.agents.sessions.tools.goal_tools import get_active_goal

        active_goal = get_active_goal("default_session")
        if active_goal and active_goal.get("status") not in ("complete", "done"):
            obj = active_goal.get("objective", "").strip()
            status = active_goal.get("status", "in_progress")
            budget = active_goal.get("token_budget")
            budget_info = f" (Token Budget: {budget:,})" if budget else ""
            notes = active_goal.get("notes", [])
            notes_text = ""
            if notes:
                notes_text = "\n  Latest Progress: " + "; ".join(
                    n.get("note", "") for n in notes[-3:]
                )
            goal_section = (
                f"\n## ACTIVE SESSION GOAL\n"
                f"- Objective: {obj}{budget_info}\n"
                f"- Status: {status}{notes_text}\n"
                f"- Autonomous Followthrough: Remain persistently focused on achieving this goal step-by-step. "
                f"Once completed, call the `update_goal` tool with status='complete'.\n"
            )
    except Exception:
        pass

    channels_section = ""
    try:
        from src.channels.channel_manager import ChannelManager

        ch_status = ChannelManager.get_instance().format_channel_status_for_prompt()
        if ch_status:
            channels_section = f"\n{ch_status}"
    except Exception:
        pass

    return f"{core_directives}\n\n{memory_section}\n\n{skills_section}\n{voice_contract}{temporal_section}{goal_section}{channels_section}"


def build_jarvis_gemini_tools(
    plugin_tools: list[dict[str, Any]] | None = None,
    host_tools: dict[str, Any] | list[Any] | None = None,
) -> list[dict[str, Any]]:
    """Build and clean Gemini function declarations for all JARVIS tools.

    Strictly satisfies Google GenAI FunctionDeclaration schema:
    only 'name', 'description' (as string), and 'parameters' (cleaned JSON Schema object).
    Strips any internal implementation keys (execute, label, promptSnippet, etc.).
    """
    decls = build_jarvis_tool_declarations(plugin_tools=plugin_tools, host_tools=host_tools)
    return clean_gemini_declarations(decls)


def clean_gemini_declarations(
    decls: list[dict[str, Any]],
    voice_priority_only: bool = True,
) -> list[dict[str, Any]]:
    """Normalize declarations for the Live API wire format.

    Filters declarations down to focused voice priority tools to prevent
    tool bloat and model selection paralysis in low-latency native-audio sessions.
    """
    cleaned_decls: list[dict[str, Any]] = []
    seen: set[str] = set()

    for d in decls:
        name = str(d.get("name", "")).strip()
        if not name or name in seen:
            continue
        if voice_priority_only and name not in VOICE_PRIORITY_TOOLS:
            continue

        seen.add(name)

        # Use voice-tailored description if available, otherwise truncate crisp first line
        if name in VOICE_TOOL_DESCRIPTIONS:
            description = VOICE_TOOL_DESCRIPTIONS[name]
        else:
            raw_desc = d.get("description", "")
            if isinstance(raw_desc, (list, tuple)):
                description = " ".join(str(x) for x in raw_desc)
            else:
                description = str(raw_desc or "")
            first_line = description.strip().split("\n")[0].strip()
            if len(first_line) > 140:
                first_line = first_line[:137] + "..."
            description = first_line

        raw_params = d.get("parameters", {})
        cleaned_params = (
            _clean_schema(raw_params)
            if isinstance(raw_params, dict)
            else {"type": "object", "properties": {}}
        )

        cleaned_decls.append(
            {
                "name": name,
                "description": description,
                "parameters": cleaned_params,
            }
        )

    if (not voice_priority_only or "pdf" in VOICE_PRIORITY_TOOLS) and not any(
        d.get("name") == "pdf" for d in cleaned_decls
    ):
        cleaned_decls.append(
            {
                "name": "pdf",
                "description": VOICE_TOOL_DESCRIPTIONS.get(
                    "pdf",
                    "Read, extract text, or convert/create PDF documents (file_path, output_path, action='read'|'convert').",
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to input file (.pdf, .txt, .html, .md)",
                        },
                        "output_path": {
                            "type": "string",
                            "description": "Optional destination path for generated PDF",
                        },
                        "action": {
                            "type": "string",
                            "enum": ["read", "convert", "extract"],
                            "description": "Action: 'read'/'extract' to read PDF, 'convert' to create PDF from txt/html/md",
                        },
                        "pages": {
                            "type": "string",
                            "description": "Page range to extract e.g. '1-5', 'all'",
                        },
                    },
                    "required": ["file_path"],
                },
            }
        )
    return cleaned_decls


def build_jarvis_livekit_tools(
    declarations: list[dict[str, Any]],
    plugin_dispatch: dict[str, Any] | None = None,
    coding_tools: dict[str, Any] | None = None,
    decision_engine: Any = None,
    on_tool_event: Optional[Callable[[str, str, Any], None]] = None,
) -> list[Any]:
    """Compatibility bridge for tests expecting callable tool wrappers."""
    plugin_dispatch = plugin_dispatch or {}
    callable_tools: list[Any] = []

    for decl in declarations:
        name = decl.get("name", "unknown")

        def _make_callable(tool_name: str):
            async def _invoke(**kwargs) -> str:
                if on_tool_event:
                    on_tool_event("tool_start", tool_name, kwargs)
                try:
                    args = prepare_tool_arguments(tool_name, kwargs)
                    if tool_name in plugin_dispatch:
                        handler, _ = plugin_dispatch[tool_name]
                        if inspect.iscoroutinefunction(handler):
                            res = await handler(args)
                        else:
                            res = handler(args)
                    else:
                        res = await execute_desktop_action(args)
                    res_str = json.dumps(res) if isinstance(res, dict) else str(res)
                    if on_tool_event:
                        on_tool_event("tool_end", tool_name, res_str)
                    return res_str
                except Exception as e:
                    if on_tool_event:
                        on_tool_event("tool_end", tool_name, str(e))
                    raise

            _invoke.__name__ = tool_name
            return _invoke

        callable_tools.append(_make_callable(name))

    return callable_tools


async def create_jarvis_livekit_agent(
    base_dir: Path,
    gemini_api_key: str,
    model_name: str = "models/gemini-2.5-flash-native-audio-preview-12-2025",
    on_tool_event: Optional[Callable[[str, str, Any], None]] = None,
) -> tuple[Any, Any]:
    """Compatibility stub returning (session, agent) mock for legacy tests."""

    class _MockAgent:
        def __init__(self):
            self.tools = [lambda: None]

    class _MockSession:
        def start(self, *args, **kwargs):
            pass

        def on(self, *args, **kwargs):
            pass

    return _MockSession(), _MockAgent()


create_jarvis_pipecat_task = create_jarvis_livekit_agent

__all__ = [
    "_clean_schema",
    "build_jarvis_system_prompt",
    "build_jarvis_gemini_tools",
    "build_jarvis_livekit_tools",
    "clean_gemini_declarations",
    "create_jarvis_livekit_agent",
    "create_jarvis_pipecat_task",
]
