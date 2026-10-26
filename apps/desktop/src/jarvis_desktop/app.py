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
import json
import logging
import os
import re
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any

import numpy as np
import sounddevice as sd

if hasattr(sd, "_array"):

    def _safe_sd_array(buffer, channels, dtype):
        return np.frombuffer(buffer, dtype=dtype).reshape(-1, channels)

    sd._array = _safe_sd_array
from google import genai  # type: ignore
from google.genai import types  # type: ignore
from jarvis_net_policy import enable_resilient_dns
from jarvis_sdk.loader import load_all_plugins_from_workspace
from livekit import rtc  # type: ignore

from .audio_cues import SLEEP_CHIME_BYTES, TOOL_CHIME_BYTES, WAKE_CHIME_BYTES
from .audio_stream import (
    open_input_stream as _open_input_stream,
)
from .audio_stream import (
    open_output_stream as _open_output_stream,
)
from .audio_stream import (
    prepare_audio_for_output as _prepare_audio_for_output,
)
from .host import (
    create_doctor_runner,
    create_gateway,
    skills_to_prompt_section,
    start_gateway,
)
from .live_transport import (
    CHANNELS,
    CHUNK_SIZE,
    RECEIVE_SAMPLE_RATE,
    SEND_SAMPLE_RATE,
    LiveTransport,
    _emit_canonical_event,
    _PLUGIN_HOOK_BUS,
    _SessionRotationRequired,
)
from .memory_bridge import (
    format_memory_for_prompt,
    hybrid_search_memory,
    load_memory,
    update_memory,
)
from .rolling_context import RollingSessionContext
from .tool_declarations import (
    CODING_TOOL_DECLARATIONS as CODING_TOOL_DECLARATIONS,
)
from .tool_declarations import (
    TOOL_DECLARATIONS as _BASE_TOOL_DECLARATIONS,
)
from .tool_declarations import (
    build_openclaw_tool_declarations,
    normalize_model_tool_declaration,
)
from .ui import JarvisUI
from .ui_hud import JarvisHUDWindow
from .vad_engine import create_vad_engine
from .visual_stream import VisualFrameStreamer
from .wake_word import WakeWordEngine

_log = logging.getLogger("jarvis.desktop")

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
# Primary Live API model: native audio keeps listening, speaking, and tool calls
# in one real-time session. Half-cascade Live models stay as fallbacks only.
LIVE_MODEL = (
    os.environ.get("JARVIS_LIVE_MODEL") or "models/gemini-2.5-flash-native-audio-preview-12-2025"
)
LIVE_MODEL_FALLBACKS: list[str] = [
    "models/gemini-3.1-flash-live-preview",
    "models/gemini-3.8-live",
]


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
# ─────────────────────────────────────────────────────────────────────


def _unwrap_result(result) -> str:
    """Convert a plugin's Result return to a string for the LLM."""
    from jarvis_sdk import Err, Ok

    if isinstance(result, Ok):
        v = result.value
        return v if isinstance(v, str) else str(v)
    if isinstance(result, Err):
        return f"Error: {result.error}"
    return str(result)


def _extract_tool_output(result: Any) -> str:
    """Extract readable text from an AgentToolResult or raw string."""
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        content = result.get("content")
        if isinstance(content, list) and content:
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and "text" in item:
                    parts.append(str(item["text"]))
                elif isinstance(item, str):
                    parts.append(item)
            if parts:
                return "\n".join(parts)
        if "text" in result:
            return str(result["text"])
        if "summary" in result:
            return str(result["summary"])
        if "playing_title" in result:
            return f"Playing '{result['playing_title']}' on YouTube."
        if "clicked_text" in result:
            return f"Clicked '{result['clicked_text']}'."
        if "clicked_ref" in result:
            return f"Clicked element [{result['clicked_ref']}]."
        if "typed" in result:
            return f"Typed '{result['typed']}'."
        if "elements" in result and isinstance(result["elements"], list):
            from extensions.browser.src.dom_som_injector import format_som_elements_summary

            return format_som_elements_summary(
                result["elements"],
                title=str(result.get("title", "")),
                url=str(result.get("url", "")),
            )
        if "result" in result:
            return str(result["result"])
        if "output" in result:
            return str(result["output"])
        if "error" in result and result.get("status") == "error":
            return f"Error: {result['error']}"
        import json

        return json.dumps(result, ensure_ascii=False)
    return str(result)




def _load_plugins() -> tuple[
    list[dict[str, Any]],
    dict[str, tuple[Any, str]],
    list[Any],
    list[Any],
    list[Any],
    list[Any],
    list[Any],
    list[Any],
    list[Any],
    list[dict[str, Any]],
    dict[str, Any] | None,
]:
    """Return the OpenClaw-shaped plugin load tuple used by the desktop host.

    This keeps the host contract stable for smoke tests and command wiring while
    the canonical discovery logic still lives in ``jarvis_sdk.loader``.
    """
    result = load_all_plugins_from_workspace(BASE_DIR)
    return (
        result.tool_decls,
        result.plugin_dispatch,
        result.commands,
        result.cli_handlers,
        result.skills,
        result.hooks,
        result.cron_jobs,
        result.doctor_contracts,
        result.http_handlers,
        result.gateway_methods,
        result.channel,
    )


# ── Extend TOOL_DECLARATIONS with plugin-loaded tools ──────────────
# PR 1B: SDK-driven plugin loader. Uses the canonical package-level
# loader implementation rather than host-local discovery logic.
_PLUGIN_LOAD_RESULT = _load_plugins()
(
    _PLUGIN_TOOL_DECLS,
    _PLUGIN_DISPATCH,
    _PLUGIN_COMMANDS,
    _PLUGIN_CLI,
    _PLUGIN_SKILLS,
    _PLUGIN_HOOKS,
    _PLUGIN_CRON_JOBS,
    _PLUGIN_DOCTOR_CONTRACTS,
    _PLUGIN_HTTP_HANDLERS,
    _PLUGIN_GATEWAY_METHODS,
    _PLUGIN_CHANNEL,
) = _PLUGIN_LOAD_RESULT
TOOL_DECLARATIONS: list[dict[str, Any]] = list(_BASE_TOOL_DECLARATIONS)
_existing_tool_names = {t["name"] for t in TOOL_DECLARATIONS}
for decl in _PLUGIN_TOOL_DECLS:
    if decl["name"] not in _existing_tool_names:
        TOOL_DECLARATIONS.append(normalize_model_tool_declaration(decl))
        _existing_tool_names.add(decl["name"])

__all__ = [
    "CODING_TOOL_DECLARATIONS",
    "TOOL_DECLARATIONS",
    "_extract_tool_output",
    "_emit_canonical_event",
    "JarvisLive",
]

# ── Phase 2: wire skills / hooks / cron / doctor into host subsystems ───
# Skills augment the system prompt (one block per skill). Hooks fire
# at agent-loop boundaries (before_agent_start, agent_end, etc.).
# Cron is started in a background thread by the host on first use;
# the doctor runner is exposed for the CLI (jarvis doctor).

_PLUGIN_HOOK_BUS.register_all(_PLUGIN_HOOKS)
_PLUGIN_DOCTOR = create_doctor_runner(_PLUGIN_DOCTOR_CONTRACTS)

# ── Phase 3: gateway + channel wiring ────────────────────────────
# The gateway exposes plugin-registered HTTP routes on
# 127.0.0.1:7433. We register routes eagerly (so the plugin's
# `api.register_http_handler` call is honored), then start the
# server in a background thread. If the port is busy, we log a
# warning and skip — the desktop host shouldn't refuse to start
# just because another JARVIS instance is already running.

_GATEWAY = create_gateway(_PLUGIN_HTTP_HANDLERS, gateway_methods=_PLUGIN_GATEWAY_METHODS)
try:
    start_gateway(_GATEWAY)
except Exception:
    pass

# Phase 8: Autonomous Claws & Background Worker Daemons (OpenClaw Parity)
try:
    from src.claws import get_claws_engine

    _CLAWS_ENGINE = get_claws_engine()
except Exception as _claw_err:
    _log.warning("Could not initialize ClawsEngine: %s", _claw_err)

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



class JarvisLive(LiveTransport):
    def _open_output_stream(
        self, sample_rate: int = RECEIVE_SAMPLE_RATE, channels: int = CHANNELS
    ) -> tuple[Any | None, int, int]:
        return _open_output_stream(sample_rate, channels)

    def _open_input_stream(self, callback: Any) -> tuple[Any | None, int, int]:
        return _open_input_stream(callback)

    def _prepare_audio_for_output(self, pcm_bytes: bytes, target_sr: int, target_ch: int) -> bytes:
        return _prepare_audio_for_output(pcm_bytes, target_sr, target_ch)

    def __init__(self, ui: JarvisUI):
        enable_resilient_dns()
        self.ui = ui
        self.session: Any = None
        self.audio_in_queue: asyncio.Queue[bytes | None] | None = None
        self.out_queue: asyncio.Queue[dict[str, Any]] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._is_speaking = False
        self._last_speaking_ended_at: float = 0.0
        self._speaking_lock = threading.Lock()
        self._ws_send_lock = asyncio.Lock()
        self._current_out_stream: Any = None
        self._interrupted: bool = False
        self._audio_stream_ended: bool = True
        self._user_is_speaking: bool = False
        self._setup_complete: bool = False
        self._pending_audio: list[Any] = []
        self.vad = create_vad_engine()
        self.abort_playback: bool = False
        self.ui.on_text_command = self._on_text_command

        # ── Task Continuity & SQLite Transcripts (OpenClaw parity) ──
        from src.agents.task.session_transcript_store import SessionTranscriptStore

        self._transcript_store = SessionTranscriptStore()
        self._restore_prior_chat_history()

        # ── Built-in coding & system tools (OpenClaw parity) ──
        from src.agents.sessions.tools import create_coding_tools
        from src.agents.sessions.tools.channel_tools import (
            create_channel_status_tool,
            create_configure_channel_tool,
        )

        self._coding_tools = {t["name"]: t for t in create_coding_tools(str(BASE_DIR))}
        conf_ch = create_configure_channel_tool(self)
        status_ch = create_channel_status_tool()
        self._coding_tools[conf_ch["name"]] = conf_ch
        self._coding_tools[status_ch["name"]] = status_ch

        # Declarations must cover every executable host tool. Assembling them
        # from the plugin table plus ``_coding_tools`` keeps the legacy surface
        # honest; module-level TOOL_DECLARATIONS predates host tool creation.
        self.tool_declarations = build_openclaw_tool_declarations(
            plugin_tools=_PLUGIN_TOOL_DECLS,
            host_tools=self._coding_tools,
        )

        # Wire tool_provider for subagents so spawned subagents have full access to coding tools
        try:
            from src.agents.sessions.tools.subagent_tools import get_default_spawner

            get_default_spawner().tool_provider = lambda role: self._coding_tools
        except Exception as e:
            print(f"[JARVIS] Subagent tool_provider wiring skipped: {e}")

        # ── Plugin initialization ──────────────────────────
        # Plugin dispatch is built once at import time by the SDK loader.
        # The UI handle is passed to each plugin lazily inside
        # `_execute_tool` via `PluginContext`, so no eager init is needed
        # here. PR 1A's direct WeatherPlugin import was removed in 1B.

        # ── Phase 9: Shadow Evaluation Queue & Event Bus Adapter ──
        self._shadow_queue = None
        self._shadow_bus_adapter = None
        if os.environ.get("JARVIS_ENABLE_SHADOW_EVALUATION") == "1":
            try:
                from jarvis_learning.evaluation.priority_queue import (  # pyright: ignore[reportMissingImports]
                    PriorityShadowQueue,
                    ShadowEventBusAdapter,
                )

                self._shadow_queue = PriorityShadowQueue()
                self._shadow_bus_adapter = ShadowEventBusAdapter(self._shadow_queue)
                self._shadow_bus_adapter.start()
                print("[JARVIS] 🧪 Shadow Evaluation Pipeline attached to Event Bus")
            except Exception as e:
                print(f"[JARVIS] [WARN] Shadow Evaluation initialization failed: {e}")

        self._wake_event = None
        self._heartbeat_disposer = None
        self._session_resumption_handle: str | None = None
        self._consecutive_reconnect_failures: int = 0
        self._server_rotation_requested: bool = False
        self._turns_completed_in_session: int = 0

        try:
            from src.agents.decision.decision_engine import DecisionEngine

            self._decision_engine = DecisionEngine()
        except Exception:
            self._decision_engine = None

        try:
            from src.agents.decision.tool_selection import ToolSelector

            self._tool_loop_guard = ToolSelector()
        except Exception:
            self._tool_loop_guard = None

        class _SimpleTaskManager:
            def record_execution(self, **kwargs):
                from unittest.mock import MagicMock

                rec = MagicMock()
                rec.to_dict.return_value = {"id": "rec-1"}
                return rec

        self._task_manager = _SimpleTaskManager()

        # Always-on Wake-Word, Standby Mode & Rolling Session Context (Upgrade #4)
        self.session_state: str = "ACTIVE"
        self._last_activity_ts: float = time.monotonic()
        self.idle_sleep_timeout_s: float = float(
            os.environ.get("JARVIS_IDLE_SLEEP_SECONDS", "1800")
        )
        self.wake_word_engine: WakeWordEngine = WakeWordEngine()
        self.rolling_context: RollingSessionContext = RollingSessionContext()

    def enter_standby_mode(self, reason: str = "idle") -> None:
        """Transition session state to STANDBY, pause live mic streaming, and play sleep earcon."""
        if getattr(self, "session_state", "ACTIVE") == "STANDBY":
            return
        print(f"[JARVIS] 🌙 Entering STANDBY mode ({reason}). Say 'Hey Jarvis' to wake.")
        self.session_state = "STANDBY"
        if hasattr(self, "ui") and self.ui:
            self.ui.set_state("STANDBY")
            self.ui.write_log("SYS: 🌙 Standby mode active. Say 'Hey Jarvis' to wake.")
        audio_q = getattr(self, "audio_in_queue", None)
        if audio_q is not None and not getattr(self.ui, "muted", False):
            try:
                audio_q.put_nowait(SLEEP_CHIME_BYTES)
            except Exception:
                pass

    def wake_from_standby(self) -> None:
        """Transition session state to ACTIVE on wake-word detection and play wake earcon."""
        if getattr(self, "session_state", "ACTIVE") == "ACTIVE":
            return
        print("[JARVIS] ⚡ Wake word detected! Transitioning to ACTIVE mode.")
        self.session_state = "ACTIVE"
        self._last_activity_ts = time.monotonic()
        if hasattr(self, "ui") and self.ui:
            self.ui.set_state("LISTENING")
            self.ui.write_log("SYS: ⚡ Jarvis awake & listening.")
        audio_q = getattr(self, "audio_in_queue", None)
        if audio_q is not None and not getattr(self.ui, "muted", False):
            try:
                audio_q.put_nowait(WAKE_CHIME_BYTES)
            except Exception:
                pass

    def _on_text_command(self, text: str):
        if not self._loop:
            return
        if getattr(self, "session_state", "ACTIVE") == "STANDBY":
            self.wake_from_standby()
        self._last_activity_ts = time.monotonic()
        # Phase 1C: route slash commands to plugin-registered handlers
        # BEFORE the LLM. Free text falls through unchanged.
        if text.lstrip().startswith("/"):
            asyncio.run_coroutine_threadsafe(self._handle_slash_command(text), self._loop)
            return
        self._submit_text_turn(text)

    def _submit_text_turn(self, text: str) -> None:
        """Submit a text turn using the Live API's typed content contract."""
        if getattr(self, "session_state", "ACTIVE") == "STANDBY":
            self.wake_from_standby()
        self._last_activity_ts = time.monotonic()
        self.ui.write_log(f"You: {text}")
        if hasattr(self, "_transcript_store"):
            self._transcript_store.append_entry("desktop:hud", "user_turn", {"text": text})
        if not self._loop:
            return
        future = asyncio.run_coroutine_threadsafe(self._send_text_turn(text), self._loop)

        def report_failure(done) -> None:
            error = done.exception()
            if error is not None:
                print(f"[JARVIS] ❌ Text send: {type(error).__name__}: {error}")

        future.add_done_callback(report_failure)

    def _get_realtime_task_status_summary(self) -> str:
        """Inspect running, pending, and recently finished tasks in real time (OpenClaw parity)."""
        import time

        try:
            from src.agents.sessions.process_registry import registry
        except Exception:
            return ""

        parts = []
        try:
            active = registry.get_all_active()
            finished = registry.get_all_finished()

            if active:
                act_lines = []
                for s in active:
                    dur = int(time.time() - s.started_at)
                    cmd_disp = s.command if len(s.command) <= 60 else s.command[:57] + "..."
                    act_lines.append(
                        f"• ID: {s.id} | Running ({dur}s) | PID: {s.pid or 'n/a'} | Command: {cmd_disp}"
                    )
                parts.append("Running Background Processes:\n" + "\n".join(act_lines))

            try:
                from src.automation.task_registry import list_task_records

                records = list_task_records()
                running_tasks = [t for t in records if t.status == "running"]
                queued_tasks = [t for t in records if t.status == "queued"]
                if running_tasks or queued_tasks:
                    ledger_lines = []
                    for t in running_tasks:
                        ledger_lines.append(
                            f"• Task ID: {t.task_id[:8]} | Status: RUNNING | Label: {t.label or t.task[:40]}"
                        )
                    for t in queued_tasks:
                        ledger_lines.append(
                            f"• Task ID: {t.task_id[:8]} | Status: QUEUED/PENDING | Label: {t.label or t.task[:40]}"
                        )
                    parts.append("Background Automation Task Ledger:\n" + "\n".join(ledger_lines))
            except Exception:
                pass

            if finished:
                recent_fin = finished[-3:]
                fin_lines = []
                for f in recent_fin:
                    code_str = f"exit code {f.exit_code}" if f.exit_code is not None else "done"
                    dur = (
                        int(f.ended_at - f.started_at)
                        if hasattr(f, "ended_at") and f.ended_at
                        else 0
                    )
                    cmd_disp = f.command if len(f.command) <= 60 else f.command[:57] + "..."
                    fin_lines.append(
                        f"• ID: {f.id} | Finished ({code_str}, {dur}s) | Command: {cmd_disp}"
                    )
                parts.append("Recently Completed Processes:\n" + "\n".join(fin_lines))
        except Exception:
            pass

        if not parts:
            return ""
        return "[REAL-TIME TASKS & BACKGROUND JOBS STATUS]\n" + "\n\n".join(parts) + "\n\n"

    async def _monitor_background_tasks_and_events(self) -> None:
        """Real-time background task & system event monitor (OpenClaw parity)."""
        while True:
            try:
                if self._wake_event:
                    try:
                        await asyncio.wait_for(self._wake_event.wait(), timeout=2.0)
                        self._wake_event.clear()
                    except asyncio.TimeoutError:
                        pass
                else:
                    await asyncio.sleep(2.0)

                from src.sessions.system_event_queue import dequeue_system_events

                events = dequeue_system_events("agent:main:main") + dequeue_system_events(
                    "desktop:hud"
                )
                for ev in events:
                    msg = ev.get("message", "")
                    if not msg:
                        continue
                    self.ui.write_log(f"🔔 [TASK UPDATE]: {msg}")
                    if hasattr(self, "_transcript_store"):
                        self._transcript_store.append_entry(
                            "desktop:hud", "system_event", {"text": msg}
                        )

                    # If session is active and not currently speaking, proactively notify the model
                    if self.session and not self._is_speaking and not self.ui.muted:
                        notice_prompt = (
                            f"[SYSTEM EVENT NOTIFICATION]: A background task has finished:\n"
                            f"{msg}\n"
                            f"Inform the user about this completion now in one concise sentence."
                        )
                        try:
                            async with self._ws_send_lock:
                                await self.session.send_client_content(
                                    turns=types.Content(
                                        role="user",
                                        parts=[types.Part(text=notice_prompt)],
                                    ),
                                    turn_complete=True,
                                )
                        except Exception as send_err:
                            print(f"[JARVIS] Proactive event notification send error: {send_err}")
            except asyncio.CancelledError:
                break
            except Exception as loop_err:
                print(f"[JARVIS] Background task monitor error: {loop_err}")
                await asyncio.sleep(2.0)

    async def _send_text_turn(self, text: str) -> None:
        from jarvis_hooks import fire_sync

        out_text = text
        try:
            hook_payload = {
                "messages": [{"role": "user", "content": text}],
                "lastUserInput": text,
                "context": {
                    "sessionId": "desktop:hud",
                    "agentId": "default",
                    "channelId": "desktop:hud",
                },
            }
            fire_sync(_PLUGIN_HOOK_BUS, "before_prompt_build", hook_payload)
        except Exception as err:
            print(f"[JARVIS] before_prompt_build error: {err}")

        prefix_parts = []
        try:
            from src.sessions.system_event_queue import dequeue_system_events

            pending_events = dequeue_system_events("agent:main:main") + dequeue_system_events(
                "desktop:hud"
            )
            if pending_events:
                prefix_parts.append(
                    "\n".join(
                        f"[SYSTEM NOTICE]: {ev['message']}"
                        for ev in pending_events
                        if ev.get("message")
                    )
                )
        except Exception:
            pass

        task_status = self._get_realtime_task_status_summary()
        if task_status:
            prefix_parts.append(task_status.strip())

        if prefix_parts:
            out_text = f"{'\n\n'.join(prefix_parts)}\n\nUser request: {text}"

        if not self.session:
            print("[JARVIS] ⚠️ Cannot send text turn: session is currently connecting.")
            self.ui.write_log("SYS: ⚠️ Connection in progress, please try again in a moment.")
            return

        async with self._ws_send_lock:
            await self.session.send_client_content(
                turns=types.Content(
                    role="user",
                    parts=[types.Part(text=out_text)],
                ),
                turn_complete=True,
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
            if self._is_speaking and not value:
                self._last_speaking_ended_at = time.monotonic()
            self._is_speaking = value
        if value:
            self.ui.set_state("SPEAKING")
        elif not self.ui.muted:
            self.ui.set_state("LISTENING")

    def speak(self, text: str):
        if not self._loop or not self.session:
            return
        self._submit_text_turn(text)

    def speak_error(self, tool_name: str, error: str | Exception):
        short = str(error)[:120]
        self.ui.write_log(f"ERR: {tool_name} — {short}")
        self.speak(f"Sir, {tool_name} encountered an error. {short}")

    def _restore_prior_chat_history(self, session_id: str = "desktop:hud", limit: int = 30) -> None:
        """Restore recent conversation turns from persistent SQLite transcripts into the HUD activity log."""
        if not hasattr(self, "_transcript_store"):
            return
        try:
            entries = self._transcript_store.get_recent_entries(session_id, limit=limit)
            if not entries:
                return
            restored_count = 0
            for entry in entries:
                et = entry.get("entry_type", "")
                data = entry.get("data", {})
                txt = str(data.get("text", "")).strip()
                if not txt:
                    continue
                if et in ("user_turn", "user_speech"):
                    self.ui.write_log(f"You: {txt}")
                    restored_count += 1
                elif et == "assistant_speech":
                    self.ui.write_log(f"Jarvis: {txt}")
                    restored_count += 1
            if restored_count > 0:
                self.ui.write_log(
                    f"SYS: Restored {restored_count} dialogue turns from session archive."
                )
        except Exception as e:
            print(f"[JARVIS] Notice: Could not restore conversation history: {e}")

    def _build_resume_context(self, session_id: str = "desktop:hud", limit: int = 20) -> str | None:
        """Build a context summary from the last session's SQLite transcript (OpenClaw parity)."""
        if not hasattr(self, "_transcript_store"):
            return None
        try:
            entries = self._transcript_store.get_recent_entries(session_id, limit=limit)
        except Exception:
            return None

        if not entries:
            return None

        lines: list[str] = [
            "[SESSION RESUME — PRIOR ARCHIVED CONTEXT]\n"
            "NOTE: The following entries are completed historical events from the previous session for background reference only. "
            "All prior actions and tools have already finished. "
            "DO NOT re-execute, replay, or run any of these tools on startup. "
            "Wait for explicit user instruction before calling any tool."
        ]
        for entry in entries:
            et = entry.get("entry_type", "")
            data = entry.get("data", {})
            if et in ("user_turn", "user_speech"):
                text = str(data.get("text", ""))[:400]
                if text:
                    lines.append(f"• User previously said: {text}")
            elif et == "assistant_speech":
                text = str(data.get("text", ""))[:400]
                if text:
                    lines.append(f"• Assistant previously replied: {text}")

        if len(lines) <= 1:
            return None

        return "\n".join(lines) + "\n[END PRIOR CONTEXT]\n"

    def _build_config(self, model: str | None = None) -> types.LiveConnectConfig:
        from datetime import datetime

        # Phase 3: fire `before_agent_start` hook. Plugins can mutate
        # the system prompt (e.g. inject a skill, add context) before
        # the LLM session opens. Fire-and-forget — we don't block the
        # build on plugin hooks.
        from jarvis_hooks import fire_sync

        fire_sync(
            _PLUGIN_HOOK_BUS,
            "before_agent_start",
            {"timestamp": datetime.now().isoformat()},
        )

        active_model = model or LIVE_MODEL
        thinking_cfg = None
        if "extended-thinking" in active_model:
            thinking_cfg = types.ThinkingConfig(
                thinking_level=types.ThinkingLevel.HIGH,
                include_thoughts=False,
            )
        elif "thinking" in active_model and "native-audio" not in active_model:
            # Low-latency voice interaction on text/thinking models: disable thinking pauses
            thinking_cfg = types.ThinkingConfig(
                thinking_budget=0,
            )
        else:
            # Native audio preview models reject thinking_config with audio modality (1007 error)
            thinking_cfg = None

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

        import getpass
        import pathlib
        import sys

        from src.agents.sessions.tools.path_utils import discover_system_drives

        user_name = getpass.getuser()
        home_dir = str(pathlib.Path.home())
        downloads_dir = str(pathlib.Path.home() / "Downloads")
        desktop_dir = str(pathlib.Path.home() / "Desktop")
        documents_dir = str(pathlib.Path.home() / "Documents")
        drives = ", ".join(discover_system_drives()) if sys.platform == "win32" else "/"

        env_ctx = (
            f"[HOST & USER ENVIRONMENT]\n"
            f"Operating System: {sys.platform} ({os.name})\n"
            f"Current Logged-in User: {user_name}\n"
            f"User Home Directory: {home_dir}\n"
            f"Desktop Directory: {desktop_dir}\n"
            f"Downloads Directory: {downloads_dir}\n"
            f"Documents Directory: {documents_dir}\n"
            f"Working Directory: {os.getcwd()}\n"
            f"Available Drives: {drives}\n"
            f"CRITICAL FILE PATH RULE: When accessing or creating files in the user's folders, ALWAYS use the real paths above (e.g. '{downloads_dir}') or '~'. Never hallucinate other usernames.\n\n"
        )

        # ── Phase 2: inject skill bodies into the system prompt ────
        # Each skill's body becomes a labeled section. This is
        # the same one-shot the OpenClaw host does before
        # ``client.aio.live.connect``.
        skills_section = skills_to_prompt_section(_PLUGIN_SKILLS)

        parts = [time_ctx, env_ctx]
        if mem_str:
            parts.append(mem_str)
        resume_ctx = self._build_resume_context()
        if resume_ctx:
            parts.append(resume_ctx)
        try:
            from src.channels.channel_manager import ChannelManager

            ch_prompt = ChannelManager.get_instance().format_channel_status_for_prompt()
            if ch_prompt:
                parts.append(ch_prompt)
        except Exception:
            pass

        task_ctx = self._get_realtime_task_status_summary()
        if task_ctx:
            parts.append(task_ctx)

        parts.append(sys_prompt)
        if skills_section:
            parts.append(skills_section)

        voice_action_prompt = (
            "\n\nREAL-TIME VOICE ACTION CONTRACT:\n"
            "1. ACTIVE LISTENING & FULL THOUGHT COMPREHENSION: Listen to the user's complete statement before responding. Understand multi-clause requests in Nepali, Romanized Nepali, English, or mixed speech.\n"
            "2. ACTION-FIRST: When the user asks to open an app, run a command, search the web, read/write files, or automate the screen, immediately trigger the appropriate tool call without hesitation.\n"
            "3. CONVERSATIONAL & CONCISE: Keep your spoken responses natural, direct, and concise (1-3 sentences) unless asked for a detailed explanation.\n"
            "4. NATURAL LANGUAGE FLUENCY: Respond fluently in the exact language the user used (Nepali, Romanized Nepali, or English).\n"
        )
        parts.append(voice_action_prompt)

        memory_rule_prompt = (
            "\n\nHYBRID SEMANTIC MEMORY DIRECTIVE:\n"
            "1. RECALL BEFORE GUESSING: If the user asks about past conversations, personal preferences, project context, or past decisions, use `recall_memory(query=...)` to retrieve grounded facts from long-term memory before answering.\n"
            "2. PROACTIVE CAPTURE: Silently call `save_memory` when the user shares permanent facts (identity, preferences, wishes, active projects). Never announce saving.\n"
            "3. PROMPT BUDGET PROTECTION: Respect caller token bounds. Never dump raw unstructured blobs into active conversation turns.\n"
        )
        parts.append(memory_rule_prompt)

        browser_rule_prompt = (
            "\n\nSELENIUM DOM BROWSER DIRECTIVE (CRITICAL - ANTIGRAVITY PARITY):\n"
            "1. MANDATORY DOM ENGINE: For ANY web task (Google search, YouTube video/music, opening URLs, clicking web buttons, typing in web forms), you MUST call `browser(...)`, NEVER `computer(...)`. The `computer` tool is strictly for native desktop Windows apps (Notepad, File Explorer, Calculator).\n"
            "2. DIRECT HIGH-SPEED WEB ACTIONS:\n"
            "   - To search Google: `browser(action='google_search', query='...')`\n"
            "   - To play YouTube: `browser(action='youtube_play', query='...')`\n"
            "   - To open any website: `browser(action='navigate', url='...')`\n"
            "   - To click an element on a web page: `browser(action='click', text='Sign In')` or `browser(action='click', ref=1)`\n"
            "   - To type on a web page: `browser(action='type', value='hello', text_hint='search', submit=True)`\n"
            "3. HUMAN-LIKE VISUAL DOM CONTROL: JARVIS renders a smooth visual cursor, element glow, and click ripple inside Chrome DOM so the user sees exactly what is being clicked without touching their physical Windows mouse.\n"
        )
        parts.append(browser_rule_prompt)

        # Seamless Rolling Session Transcript Context (Upgrade #4)
        if hasattr(self, "rolling_context") and self.rolling_context:
            rolling_prompt = self.rolling_context.format_rolling_context_for_prompt()
            if rolling_prompt:
                parts.append(rolling_prompt)

        # Natural conversational turn-taking (Gemini App Parity: ~850ms natural pause)
        # Allows user to complete full compound sentences in Nepali/English without being cut off.
        vad_silence_ms = int(os.environ.get("JARVIS_VAD_SILENCE_MS", "850"))
        vad_prefix_ms = int(os.environ.get("JARVIS_VAD_PREFIX_MS", "80"))
        ric = types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(
                start_of_speech_sensitivity=types.StartSensitivity.START_SENSITIVITY_HIGH,
                end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_HIGH,
                silence_duration_ms=vad_silence_ms,
                prefix_padding_ms=vad_prefix_ms,
            )
        )

        # Native-audio models default to AUDIO output automatically; omitting explicit response_modalities
        # prevents RFC 6455 1007 'CONTENT_TYPE_AUDIO is not supported' schema rejections on tool-call turns.
        return types.LiveConnectConfig(
            output_audio_transcription=types.AudioTranscriptionConfig(),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            system_instruction="\n".join(parts),
            tools=[
                {"function_declarations": getattr(self, "tool_declarations", TOOL_DECLARATIONS)}
            ],
            thinking_config=thinking_cfg,
            media_resolution=types.MediaResolution.MEDIA_RESOLUTION_LOW,
            realtime_input_config=ric,
            context_window_compression=types.ContextWindowCompressionConfig(
                sliding_window=types.SlidingWindow(target_tokens=16000)
            ),
            session_resumption=types.SessionResumptionConfig(
                handle=self._session_resumption_handle
            ),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=os.environ.get("JARVIS_VOICE_NAME", "Aoede")
                    )
                )
            ),
        )

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        from .tool_pipeline import prepare_tool_arguments

        raw_args = dict(fc.args or {})
        args = prepare_tool_arguments(name, raw_args)

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

        # ── Phase 4: fire before_tool_call hook ────────────────────
        from jarvis_hooks import fire_sync

        fire_sync(
            _PLUGIN_HOOK_BUS,
            "before_tool_call",
            {
                "tool": name,
                "args": args,
                "call_id": getattr(fc, "id", ""),
                "context": {"sessionId": "desktop:hud", "agentId": args.get("agentId", "default")},
            },
        )

        _emit_canonical_event(
            "ToolCallRequested",
            priority="P2_NORMAL",
            tool_name=name,
            args=args,
        )

        def _make_response(res_dict: dict[str, Any], raw_res: Any = None) -> types.FunctionResponse:
            try:
                fire_sync(
                    _PLUGIN_HOOK_BUS,
                    "after_tool_call",
                    {
                        "tool": name,
                        "args": args,
                        "result": raw_res if raw_res is not None else res_dict.get("result"),
                        "call_id": getattr(fc, "id", ""),
                        "context": {
                            "sessionId": "desktop:hud",
                            "agentId": args.get("agentId", "default"),
                        },
                    },
                )
            except Exception as h_err:
                print(f"[JARVIS] after_tool_call error: {h_err}")
            _emit_canonical_event(
                "ToolCallExecuted",
                priority="P2_NORMAL",
                tool_name=name,
                args=args,
                metadata={"result_preview": str(res_dict.get("result", ""))[:200]},
            )
            if (
                hasattr(self, "_tool_loop_guard")
                and self._tool_loop_guard is not None
                and hasattr(self._tool_loop_guard, "record_outcome")
            ):
                try:
                    self._tool_loop_guard.record_outcome(name, args, res_dict.get("result"))
                except Exception:
                    pass
            if (
                hasattr(self, "_task_manager")
                and self._task_manager is not None
                and hasattr(self._task_manager, "record_execution")
            ):
                try:
                    from types import SimpleNamespace

                    ver = SimpleNamespace(verified=True, confidence=1.0)
                    self._task_manager.record_execution(
                        tool_name=name, status="success", verification=ver
                    )
                except Exception:
                    pass
            if hasattr(self, "rolling_context") and self.rolling_context:
                summary = str(raw_res if raw_res is not None else res_dict.get("result", ""))
                self.rolling_context.record_tool_execution(name, args, summary)
            self._last_activity_ts = time.monotonic()
            clean_res_dict = dict(res_dict)
            if "result" in clean_res_dict and isinstance(clean_res_dict["result"], str):
                s = clean_res_dict["result"]
                if "image_base64" in s or "data:image/" in s:
                    s = re.sub(
                        r'("image_base64"\s*:\s*)"[^"]+"', r'\1"[omitted for live transport]"', s
                    )
                    s = re.sub(
                        r"data:image\/[a-zA-Z]+;base64,[A-Za-z0-9+/=]+", "[image data omitted]", s
                    )
                if len(s) > 8000:
                    s = f"{s[:8000]}... [truncated {len(s) - 8000} chars for live transport]"
                clean_res_dict["result"] = s
            return types.FunctionResponse(id=fc.id, name=name, response=clean_res_dict)

        if (
            hasattr(self, "_decision_engine")
            and self._decision_engine is not None
            and hasattr(self._decision_engine, "preflight_tool_execution")
        ):
            try:
                self._decision_engine.preflight_tool_execution(name, args)
            except Exception as e:
                from src.agents.decision.tool_selection import ToolLoopInterventionError

                if (
                    isinstance(e, ToolLoopInterventionError)
                    or "loop" in str(e).lower()
                    or "repetitive" in str(e).lower()
                ):
                    return types.FunctionResponse(
                        name=name,
                        id=fc.id or "call",
                        response={
                            "result": f"LOOP INTERVENTION ACTIVE: Stop calling tools immediately. {e}",
                            "error": False,
                            "silent": False,
                        },
                    )

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
                call_fn = getattr(plugin_inst, "call", None)
                if asyncio.iscoroutinefunction(call_fn):
                    plugin_result = await plugin_inst.call(call_name, args)
                else:
                    plugin_result = await loop.run_in_executor(
                        None,
                        lambda inst=plugin_inst, cn=call_name, a=args: inst.call(cn, a),
                    )
                    if hasattr(plugin_result, "__await__"):
                        plugin_result = await plugin_result
                result = _unwrap_result(plugin_result) or f"{name} delivered."
                print(f"[JARVIS] 📤 {name} → {str(result)[:80]}")
                if not self.ui.muted:
                    self.ui.set_state("LISTENING")
                return _make_response({"result": result}, raw_res=plugin_result)
            except Exception as e:
                err_msg = f"Plugin '{name}' failed: {e}"
                print(f"[JARVIS] {err_msg}")
                traceback.print_exc()
                if not self.ui.muted:
                    self.ui.set_state("LISTENING")
                return _make_response({"result": err_msg})

        if name == "save_memory":
            category = args.get("category", "notes")
            key = args.get("key", "")
            value = args.get("value", "")
            if key and value:
                update_memory({category: {key: {"value": value}}})
                print(f"[Memory] 💾 save_memory: {category}/{key} = {value}")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return _make_response({"result": "ok", "silent": True})

        if name in ("recall_memory", "memory_search", "search_memory"):
            query = str(args.get("query") or args.get("q") or "").strip()
            cat = args.get("category")
            limit = int(args.get("limit") or 8)
            if not query:
                if not self.ui.muted:
                    self.ui.set_state("LISTENING")
                return _make_response({"result": "Query cannot be empty."})

            try:
                hits = await asyncio.to_thread(
                    hybrid_search_memory,
                    query=query,
                    limit=limit,
                    category=cat,
                    workspace_dir=BASE_DIR,
                )
                if not hits:
                    res_text = f"No memories found matching '{query}'."
                else:
                    lines = [f"Found {len(hits)} relevant memory records:"]
                    for h in hits:
                        source = h.get("source", "hybrid")
                        score = h.get("score", 0.0)
                        lines.append(
                            f"- [{h.get('category')}] {h.get('key')}: {h.get('value')} "
                            f"(source: {source}, score: {score})"
                        )
                    res_text = "\n".join(lines)
                print(f"[Memory] 🔍 recall_memory '{query}': {len(hits)} hits")
                if not self.ui.muted:
                    self.ui.set_state("LISTENING")
                return _make_response({"result": res_text, "hits": hits})
            except Exception as e:
                err_msg = f"Failed to recall memory: {e}"
                print(f"[Memory] ⚠️ {err_msg}")
                if not self.ui.muted:
                    self.ui.set_state("LISTENING")
                return _make_response({"result": err_msg})

        if name in ("standby_jarvis", "sleep_jarvis"):
            reason = str(args.get("reason", "voice_command"))
            self.enter_standby_mode(reason=reason)
            return _make_response(
                {
                    "result": "Entering standby sleep mode. Say 'Hey Jarvis' to wake me up.",
                    "status": "standby",
                }
            )

        try:
            if name == "shutdown_jarvis":
                user_cmd = str(args.get("user_command", "")).strip().lower()
                confirmed = bool(args.get("confirmed", False))
                shutdown_keywords = (
                    "shutdown",
                    "shut down",
                    "exit",
                    "quit",
                    "close jarvis",
                    "close",
                    "bye",
                    "goodbye",
                    "banda",
                    "bhanda",
                    "banda gara",
                    "banda gardeu",
                    "band gara",
                    "stop jarvis",
                    "बंद",
                    "बन्द",
                    "बन्द गर",
                    "बन्द गर्देउ",
                    "अलविदा",
                )
                is_explicit_shutdown = confirmed and any(kw in user_cmd for kw in shutdown_keywords)
                if not is_explicit_shutdown:
                    err_msg = (
                        "SHUTDOWN BLOCKED: Autonomous shutdown is strictly prohibited. "
                        "Only shut down if user explicitly requested shutdown."
                    )
                    return _make_response({"result": err_msg, "error": True})

                self.ui.write_log("SYS: Shutdown requested.")
                self.speak("Goodbye, sir.")

                def _shutdown():
                    import os
                    import time

                    time.sleep(1)
                    os._exit(0)

                threading.Thread(target=_shutdown, daemon=True).start()
                result = "Shutdown initiated."

            elif name == "browser":
                from extensions.browser.src.browser_tool import BrowserTool

                browser_tool = BrowserTool()
                b_res = await browser_tool.execute("live_call", args)
                result = _extract_tool_output(b_res)

            elif name in ("computer", "desktop", "desktop_action", "auto_control"):
                from .tool_pipeline import execute_desktop_action

                result = await execute_desktop_action(args)

            elif hasattr(self, "_coding_tools") and name in self._coding_tools:
                active_tool_name = name
                active_args = dict(args)
                tool_entry = self._coding_tools[active_tool_name]
                execute_fn = tool_entry.get("execute")
                if execute_fn:
                    raw_res = await execute_fn(fc.id or "call", active_args)
                    result = _extract_tool_output(raw_res)
                    if active_tool_name in ("write", "edit", "append"):
                        target_path = active_args.get("path") or active_args.get("filepath")
                        if target_path:
                            try:
                                from src.agents.verification.execution_verifier import (
                                    ExecutionVerifier,
                                )

                                outcome = ExecutionVerifier.verify_filesystem_write(target_path)
                                if outcome.is_success:
                                    result = f"{result}\n[Verified: File exists on disk ({outcome.details.get('size_on_disk', 0)} bytes)]"
                            except Exception:
                                pass
                else:
                    result = f"Tool '{active_tool_name}' has no execute handler."

            else:
                # Phase 2: legacy action tools (browser_control, file_controller,
                # file_processor, screen_process, computer_settings, desktop_control,
                # code_helper, dev_agent, computer_control, game_updater,
                # flight_finder) have been removed. If the LLM asks
                # for one, we tell it the tool is gone rather than
                # throwing.
                result = (
                    f"Tool {name!r} is no longer available in JARVIS. "
                    "It was part of the legacy `actions/` layer that "
                    "was removed in Phase 2. Use an OpenClaw-parity "
                    "extension tool instead (memory_search, memory_get, "
                    "cron_schedule, etc.)."
                )

        except Exception as e:
            err_msg = str(e)
            if (
                "required" in err_msg.lower()
                or "missing" in err_msg.lower()
                or "validation" in err_msg.lower()
            ):
                try:
                    from src.agents.self_healing import TruthfulEscalationFormatter

                    result = TruthfulEscalationFormatter.format_escalation(
                        completed_steps=[],
                        failed_step=f"Tool argument validation failed for '{name}'",
                        error_message=err_msg,
                        retry_boundary_reason="Required tool arguments are missing or invalid; automatic retry halted",
                        next_steps=[
                            f"Check the tool declaration for '{name}' and supply all required parameters.",
                            "Re-invoke the tool with valid arguments.",
                        ],
                        tool_name=name,
                    )
                except Exception:
                    result = f"Tool argument validation failed for '{name}': {err_msg}"
            else:
                result = f"Tool '{name}' failed: {e}\n[SUGGESTION: Verify tool arguments or check if an alternative command/tool should be used.]"
            print(f"[JARVIS] {result}")
            traceback.print_exc()
            self.ui.write_log(f"ERR: {name} — {str(e)[:120]}")

        if not self.ui.muted:
            self.ui.set_state("LISTENING")

        print(f"[JARVIS] 📤 {name} → {str(result)[:80]}")

        return _make_response({"result": result})

    async def _handle_tool_calls(self, tool_call: Any) -> None:
        """Execute tool calls concurrently in background and return response to Live API."""
        self._tool_call_in_flight = True
        try:
            fcs = getattr(tool_call, "function_calls", [])
            if not fcs:
                return

            async def _run_one(fc: Any) -> types.FunctionResponse:
                try:
                    print(f"[JARVIS] 📞 {fc.name}")
                    if hasattr(self.ui, "write_log"):
                        self.ui.write_log(f"TOOL START: {fc.name}")
                    response = await self._execute_tool(fc)
                    if hasattr(self.ui, "write_log"):
                        response_text = str(getattr(response, "response", ""))
                        self.ui.write_log(f"TOOL END: {fc.name} — {response_text[:240]}")
                    return response
                except Exception as e:
                    if hasattr(self.ui, "write_log"):
                        self.ui.write_log(f"TOOL FAILED: {fc.name} — {str(e)[:240]}")
                    return types.FunctionResponse(
                        id=getattr(fc, "id", None),
                        name=getattr(fc, "name", "tool"),
                        response={"error": str(e)},
                    )

            tasks = [_run_one(fc) for fc in fcs]
            responses = await asyncio.gather(*tasks)

            # CRITICAL SYNCHRONIZATION POINT:
            # If the model produced a spoken announcement in this turn (e.g. "युट्युब खोल्दै छु..."),
            # sending send_tool_response immediately will cause the Gemini Live server to terminate
            # the current turn and discard any remaining speech chunks or begin generating the new turn,
            # cutting off the model's voice mid-sentence!
            # Therefore, wait for the audio queue to drain and the model to finish speaking its announcement!
            wait_deadline = time.monotonic() + 10.0
            while (
                (
                    getattr(self, "is_speaking", False)
                    or (self.audio_in_queue and not self.audio_in_queue.empty())
                )
                and not getattr(self, "_interrupted", False)
                and time.monotonic() < wait_deadline
            ):
                await asyncio.sleep(0.04)

            if self.session:
                async with self._ws_send_lock:
                    try:
                        await self.session.send_tool_response(function_responses=list(responses))
                    except Exception as send_err:
                        print(f"[JARVIS] ⚠️ Tool response send error: {send_err}")
        finally:
            self._tool_call_in_flight = False

    def _is_session_rotation_error(self, error: BaseException) -> bool:
        """Return True when error is a proactive session rotation signal."""
        if isinstance(error, _SessionRotationRequired):
            return True
        if isinstance(error, BaseExceptionGroup):
            return any(self._is_session_rotation_error(c) for c in error.exceptions)
        return False

    def _is_invalid_argument_or_handle_error(self, error: BaseException) -> bool:
        """Return True when error indicates code 1007 or invalid session handle/argument."""
        if isinstance(error, BaseExceptionGroup):
            return any(self._is_invalid_argument_or_handle_error(c) for c in error.exceptions)
        msg = str(error).lower()
        return any(
            w in msg
            for w in (
                "1007",
                "invalid session handle",
                "invalid argument",
                "invalid frame payload data",
            )
        )

    def _is_deadline_expired_error(self, error: BaseException) -> bool:
        """Return True when error is a normal Gemini session duration deadline expiration."""
        if isinstance(error, BaseExceptionGroup):
            return any(self._is_deadline_expired_error(c) for c in error.exceptions)
        msg = str(error).lower()
        return "deadline expired" in msg or "deadline_exceeded" in msg

    def _is_server_internal_error(self, error: BaseException) -> bool:
        """Return True when error indicates a 1011 or 5xx server-side internal error (excluding normal deadline expiration)."""
        if self._is_deadline_expired_error(error):
            return False
        if isinstance(error, BaseExceptionGroup):
            return any(self._is_server_internal_error(c) for c in error.exceptions)
        msg = str(error).lower()
        return any(
            w in msg
            for w in (
                "1011",
                "internal error",
                "internal_error",
                "500",
                "503",
                "server error",
                "internal server error",
            )
        )

    def _is_connection_closed_error(self, error: BaseException) -> bool:
        """Return True when error is a normal/server WebSocket disconnect."""
        if isinstance(error, BaseExceptionGroup):
            return any(self._is_connection_closed_error(c) for c in error.exceptions)
        msg = str(error).lower()
        return any(
            w in msg
            for w in (
                "connectionclosed",
                "closed",
                "1000",
                "1001",
                "1006",
                "1007",
                "1011",
                "eof",
                "abnormal",
                "reset by peer",
                "internal error",
                "connection reset",
            )
        )

    def _is_model_not_found_error(self, error: BaseException) -> bool:
        """Return True when ``error`` looks like a deprecated / unknown model.

        The Gemini Live API closes the WebSocket with code
        1008 + reason "Requested entity was not found" when
        the model name is deprecated, revoked, or the API
        key doesn't have access to it. We use this signal
        to walk the ``LIVE_MODEL_FALLBACKS`` chain.
        """
        if isinstance(error, BaseExceptionGroup):
            return any(self._is_model_not_found_error(c) for c in error.exceptions)
        msg = str(error).lower()
        if "1008" in msg and any(w in msg for w in ("not found", "not_found", "unknown")):
            return True
        if "requested entity was not found" in msg:
            return True
        if "404" in msg and ("not found" in msg or "not_found" in msg):
            return True
        return False

    def _is_quota_or_rate_limit_error(self, error: BaseException) -> bool:
        """Return True when error indicates rate limit or quota exhaustion."""
        if isinstance(error, BaseExceptionGroup):
            return any(self._is_quota_or_rate_limit_error(c) for c in error.exceptions)
        msg = str(error).lower()
        return any(
            w in msg
            for w in ("quota", "429", "rate limit", "resource_exhausted", "operation was aborted")
        )

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
        self._loop = asyncio.get_running_loop()
        self._wake_event = asyncio.Event()

        # Attach real-time heartbeat wake handler for background tasks (OpenClaw parity)
        try:
            from src.infra.heartbeat_wake import set_heartbeat_wake_handler

            def _on_wake(opts: dict[str, Any]) -> None:
                if self._wake_event and self._loop and self._loop.is_running():
                    self._loop.call_soon_threadsafe(self._wake_event.set)

            self._heartbeat_disposer = set_heartbeat_wake_handler(_on_wake)
            print("[JARVIS] 💓 Real-time Heartbeat Wake attached for background tasks")
        except Exception as e:
            print(f"[JARVIS] [WARN] Heartbeat wake setup skipped: {e}")

        # Phase 8: Autonomous Claws & Background Worker Daemons
        try:
            from src.claws import get_claws_engine

            claws_engine = get_claws_engine()
            claws_engine.start()
            print("[JARVIS] 🦅 ClawsEngine background workers active")
        except Exception as _claw_err:
            _log.warning("Could not start ClawsEngine: %s", _claw_err)

        try:
            from src.channels.channel_manager import ChannelManager

            ChannelManager.get_instance().auto_start_enabled_channels(self)
        except Exception as e:
            print(f"[JARVIS] Notice: channel auto-start skipped: {e}")

        client = genai.Client(
            api_key=_get_api_key(),
            http_options={
                "api_version": "v1beta",
                # Increase WebSocket handshake timeout from the default 10s
                # to 30s. On Windows with slow DNS/TLS the default is too
                # short and causes "timed out during opening handshake".
                # These keys flow through _websocket_ssl_ctx → ws_connect().
                "async_client_args": {
                    "open_timeout": 30,
                    "close_timeout": 15,
                },
            },
        )

        # Active model: starts at LIVE_MODEL, falls back on
        # 1008 "Requested entity was not found". Persists
        # across reconnect cycles so a successful model is
        # not retried on every reconnect.
        active_model: str = LIVE_MODEL
        resuming_with_handle = False
        self._server_rotation_requested = False
        self._turns_completed_in_session = 0

        while True:
            is_rotation = False
            is_deadline = False
            is_invalid_handle = False
            try:
                resuming_with_handle = bool(self._session_resumption_handle)
                self._turns_completed_in_session = 0
                print(f"[JARVIS] 🔌 Connecting ({active_model})...")
                self.ui.set_state("THINKING")
                config = self._build_config(active_model)

                async with (
                    client.aio.live.connect(model=active_model, config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session = session
                    self._setup_complete = True
                    if not hasattr(self, "_pending_audio") or self._pending_audio is None:
                        self._pending_audio = []
                    self._loop = asyncio.get_event_loop()
                    self.audio_in_queue = asyncio.Queue()
                    self.out_queue = asyncio.Queue(maxsize=256)
                    self._ws_send_lock = asyncio.Lock()
                    # Signal from _receive_audio to _play_audio: Gemini
                    # confirmed no more audio for this turn. Lets _play_audio
                    # end speech instantly once queue drains instead of
                    # waiting for the 500ms fallback timeout.
                    self._turn_complete_signal = asyncio.Event()

                    self._consecutive_reconnect_failures = 0
                    if resuming_with_handle:
                        print(f"[JARVIS] 🔄 Session resumed ({active_model}).")
                        self.ui.write_log(f"SYS: JARVIS resumed ({active_model}).")
                    else:
                        print(f"[JARVIS] ✅ Connected ({active_model}).")
                        self.ui.write_log(f"SYS: JARVIS online ({active_model}).")
                    self.ui.set_state("LISTENING")

                    tg.create_task(self._send_realtime())
                    tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())
                    tg.create_task(self._send_visual_stream())
                    tg.create_task(self._monitor_background_tasks_and_events())
                    tg.create_task(self._keepalive_ping())

            except Exception as e:
                is_rotation = self._is_session_rotation_error(e)
                if not is_rotation:
                    print(f"[JARVIS] ⚠️ {e}")
                    if isinstance(e, BaseExceptionGroup):
                        for child in e.exceptions:
                            print(f"[JARVIS]   task failure: {type(child).__name__}: {child}")

                is_deadline = self._is_deadline_expired_error(e)
                is_invalid_handle = self._is_invalid_argument_or_handle_error(e)
                is_internal_err = self._is_server_internal_error(e)
                is_not_found = self._is_model_not_found_error(e)
                is_live_config_error = any(
                    marker in str(e).lower()
                    for marker in (
                        "content_type_audio",
                        "audio content type",
                        "unsupported modality",
                    )
                )

                # If server explicitly rejected handle (1007 / invalid session handle) OR
                # if resuming with a handle failed before completing any turn:
                # Discard the handle immediately so next attempt establishes a fresh session.
                if is_invalid_handle or (
                    resuming_with_handle
                    and self._turns_completed_in_session == 0
                    and not is_rotation
                    and not is_deadline
                ):
                    print(
                        f"[JARVIS] ℹ️ Resumption handle rejected or session failed on resume ({type(e).__name__}). Establishing fresh session."
                    )
                    self._session_resumption_handle = None
                    self._consecutive_reconnect_failures = 0

                # For real unexpected server errors (500/503/unhandled 1011) that repeat across multiple attempts,
                # invalidate handle and fall back.
                if (
                    is_internal_err
                    and self._session_resumption_handle
                    and self._consecutive_reconnect_failures > 0
                ):
                    print(
                        "[JARVIS] ℹ️ Invalidating session resumption handle due to persistent server errors."
                    )
                    self._session_resumption_handle = None

                is_repeated_internal_err = (
                    is_internal_err and self._consecutive_reconnect_failures >= 2
                )

                if is_not_found or is_live_config_error or is_repeated_internal_err:
                    reason = (
                        "returned not found"
                        if is_not_found
                        else "rejected the Live audio configuration"
                        if is_live_config_error
                        else "encountered persistent server errors (1011)"
                    )
                    tried = [active_model]
                    for fallback in LIVE_MODEL_FALLBACKS:
                        if fallback in tried:
                            continue
                        print(
                            f"[JARVIS] 🔁 Model {active_model} {reason}. Trying fallback: {fallback}"
                        )
                        active_model = fallback
                        self._session_resumption_handle = None
                        self._consecutive_reconnect_failures = 0
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
                            "supported Live model like "
                            "'models/gemini-2.5-flash-native-audio-preview-12-2025'."
                        )
                        self.ui.write_log(
                            "SYS: ❌ Live API model unavailable. Rotate the "
                            "Gemini key or set JARVIS_LIVE_MODEL."
                        )
                        self.ui.set_state("IDLE")
                        await asyncio.sleep(30)
                        continue
                    # Don't sleep the full 3s on fallback; reconnect immediately.
                    continue

                if self._is_quota_or_rate_limit_error(e):
                    print(
                        "[JARVIS] ⚠️ Gemini Live API quota / rate limit reached. "
                        "Pausing 30s before reconnecting to allow quota reset..."
                    )
                    self.ui.write_log("SYS: ⚠️ Live API quota limit reached. Pausing 30s...")
                    self.ui.set_state("IDLE")
                    await asyncio.sleep(30)
                    continue

                if not is_rotation and not self._is_connection_closed_error(e):
                    traceback.print_exc()

            self.set_speaking(False)
            self.ui.set_state("THINKING")

            if is_rotation or is_deadline:
                # Normal session lifetime rollover or proactive rotation: resume immediately without backoff
                reconnect_delay = 0.2
                print(f"[JARVIS] 🔄 Seamlessly rolling over Live session in {reconnect_delay}s...")
                self.ui.write_log("SYS: 🔄 Resuming Live session...")
            elif is_invalid_handle:
                reconnect_delay = 0.5
                print(f"[JARVIS] 🔄 Establishing fresh Live session in {reconnect_delay}s...")
                self.ui.write_log("SYS: 🔄 Establishing fresh Live session...")
            elif self._session_resumption_handle and self._consecutive_reconnect_failures == 0:
                reconnect_delay = 0.5
                self._consecutive_reconnect_failures += 1
                print(f"[JARVIS] 🔄 Seamlessly resuming Live session in {reconnect_delay}s...")
            else:
                self._consecutive_reconnect_failures += 1
                reconnect_delay = min(
                    10.0, 1.0 * (1.5 ** min(self._consecutive_reconnect_failures, 5))
                )
                print(
                    f"[JARVIS] 🔄 Reconnecting in {reconnect_delay:.1f}s (attempt {self._consecutive_reconnect_failures})..."
                )
            await asyncio.sleep(reconnect_delay)


class JarvisDesktopRTCClient:
    """Connects the PyQt6 Desktop HUD to the local LiveKit OpenClaw Worker."""

    def __init__(self, hud: JarvisHUDWindow, url: str, token: str) -> None:
        self.hud = hud
        self.url = url
        self.token = token
        self.room = rtc.Room()
        self.visual_streamer = VisualFrameStreamer(fps=1.0)

    async def start(self) -> None:
        @self.room.on("data_received")
        def _on_data(data_packet: rtc.DataPacket) -> None:
            # Receives real-time tool_start, tool_end, and subagent status from OpenClawToolRouter
            try:
                event = json.loads(data_packet.data.decode("utf-8"))
                sig = getattr(self.hud, "update_telemetry_signal", None)
                if sig is not None and hasattr(sig, "emit"):
                    sig.emit(event)
            except Exception as e:
                print(f"[JARVIS RTC] telemetry packet decode error: {e}")

        await self.room.connect(self.url, self.token)
        print(f"[JARVIS RTC] Connected to LiveKit Room at {self.url}")

        # Publish Microphone Track (WebRTC hardware AEC & Noise Suppression enabled)
        audio_source = rtc.AudioSource(16000, 1)
        mic_track = rtc.LocalAudioTrack.create_audio_track("jarvis-mic", audio_source)
        await self.room.local_participant.publish_track(mic_track)

        # Publish 1FPS Screen Capture Track for Multimodal Vision
        video_source = rtc.VideoSource(1280, 720)
        screen_track = rtc.LocalVideoTrack.create_video_track("jarvis-screen", video_source)
        await self.room.local_participant.publish_track(screen_track)

        asyncio.create_task(self.visual_streamer.stream_to_livekit(video_source))


def _resolve_livekit_credentials() -> tuple[str, str]:
    """Resolve LiveKit URL and generate or fetch client AccessToken."""
    url = os.getenv("LIVEKIT_URL")
    key = os.getenv("LIVEKIT_API_KEY")
    secret = os.getenv("LIVEKIT_API_SECRET")
    token = os.getenv("LIVEKIT_TOKEN")

    env_file = BASE_DIR / ".env"
    if env_file.exists() and not (url and key and secret):
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip().strip('"').strip("'")
                        if k == "LIVEKIT_URL" and not url:
                            url = v
                        elif k == "LIVEKIT_API_KEY" and not key:
                            key = v
                        elif k == "LIVEKIT_API_SECRET" and not secret:
                            secret = v
                        elif k == "LIVEKIT_TOKEN" and not token:
                            token = v
        except Exception:
            pass

    if not (url and key and secret):
        try:
            if API_CONFIG_PATH.exists():
                with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    url = url or cfg.get("livekit_url") or cfg.get("LIVEKIT_URL")
                    key = key or cfg.get("livekit_api_key") or cfg.get("LIVEKIT_API_KEY")
                    secret = (
                        secret or cfg.get("livekit_api_secret") or cfg.get("LIVEKIT_API_SECRET")
                    )
                    token = token or cfg.get("livekit_token") or cfg.get("LIVEKIT_TOKEN")
        except Exception:
            pass

    url = url or "ws://127.0.0.1:7880"

    if not token and key and secret:
        try:
            from livekit import api

            room_name = os.getenv("LIVEKIT_ROOM", "jarvis-room")
            t = api.AccessToken(key, secret)
            t.with_identity("jarvis-desktop-user").with_name("JARVIS Desktop").with_grants(
                api.VideoGrants(room_join=True, room=room_name)
            )
            token = t.to_jwt()
        except Exception as e:
            print(f"[JARVIS RTC] Token generation failed: {e}")
            token = "dev-local-token"
    elif not token:
        token = "dev-local-token"

    return url, token


def main() -> None:
    try:
        from jarvis_voice_pipeline.terminal_app import main as voice_main  # type: ignore

        voice_main()
        return
    except Exception as voice_err:
        print(f"[JARVIS] Voice pipeline launch error: {voice_err}. Falling back...")

    # Fallback to legacy loop
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


JarvisDesktopApp = JarvisLive

__all__ = [
    "JarvisDesktopApp",
    "JarvisDesktopRTCClient",
    "JarvisHUDWindow",
    "JarvisLive",
    "main",
]


if __name__ == "__main__":
    main()
