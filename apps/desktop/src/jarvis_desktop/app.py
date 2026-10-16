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
import time
import traceback
from pathlib import Path
from typing import Any

import numpy as np
import sounddevice as sd
from google import genai
from google.genai import types
from .ui import JarvisUI
from .visual_stream import VisualFrameStreamer
from .memory_bridge import (
    load_memory,
    update_memory,
    format_memory_for_prompt,
)
from .host import (
    create_doctor_runner,
    create_gateway,
    skills_to_prompt_section,
    start_gateway,
)
from jarvis_sdk.loader import load_all_plugins_from_workspace
from .tool_declarations import (
    CODING_TOOL_DECLARATIONS,
    TOOL_DECLARATIONS as _BASE_TOOL_DECLARATIONS,
    normalize_model_tool_declaration,
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
# Primary Live API model: Gemini 2.5 Flash Native Audio
LIVE_MODEL = (
    os.environ.get("JARVIS_LIVE_MODEL")
    or "models/gemini-2.5-flash-native-audio-latest"
)
# Fallback chain: Gemini Live models
LIVE_MODEL_FALLBACKS: list[str] = [
    "models/gemini-2.5-flash-native-audio-latest",
    "models/gemini-3.1-flash-live-preview",
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
        if "result" in result:
            return str(result["result"])
        if "output" in result:
            return str(result["output"])
    return str(result)


def _emit_canonical_event(
    event_type: str,
    priority: str = "P2_NORMAL",
    tool_name: str = "",
    args: dict[str, Any] | None = None,
    turn_id: str = "",
    task_generation: int = 0,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Non-blocking event emission to the canonical event bus (INV-P9-HOST-001, INV-P9-DEP-001)."""
    try:
        from jarvis_learning.evaluation.event_bus import get_global_event_bus  # pyright: ignore[reportMissingImports]
        from jarvis_learning.evaluation.event_envelope import create_event_envelope  # pyright: ignore[reportMissingImports]

        envelope = create_event_envelope(
            event_type=event_type,
            priority=priority,
            tool_name=tool_name,
            sanitized_arguments=args or {},
            turn_id=turn_id,
            task_generation=task_generation,
            metadata=metadata or {},
        )
        get_global_event_bus().publish_nonblocking(envelope)
    except Exception:
        # Non-critical: failure in event emission must NEVER disrupt active runtime
        pass


__all__ = [
    "CODING_TOOL_DECLARATIONS",
    "TOOL_DECLARATIONS",
    "_extract_tool_output",
    "_emit_canonical_event",
    "JarvisLive",
]


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

# ── Phase 2: wire skills / hooks / cron / doctor into host subsystems ───
# Skills augment the system prompt (one block per skill). Hooks fire
# at agent-loop boundaries (before_agent_start, agent_end, etc.).
# Cron is started in a background thread by the host on first use;
# the doctor runner is exposed for the CLI (jarvis doctor).
from jarvis_hooks import HookBus  # noqa: E402

_PLUGIN_HOOK_BUS = HookBus()
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


def _open_input_stream(callback: Any) -> tuple[sd.InputStream | None, int, int]:
    """Find and open an available audio input stream.

    Prioritizes the system default recording device directly at 16000Hz mono.
    Gracefully falls back to querying DirectSound, MME, or WASAPI devices,
    resampling cleanly to 16000Hz.
    Returns (stream, sample_rate, channels) or (None, 0, 0) if unavailable.
    """
    # 1. Primary: open the OS default recording device directly at 16000Hz mono
    try:
        s = sd.InputStream(
            samplerate=16000,
            channels=1,
            dtype="int16",
            blocksize=1024,
            callback=callback,
        )
        s.start()
        dev_idx = sd.default.device[0] if sd.default.device is not None else None
        dev_name = "Default Microphone"
        if dev_idx is not None and dev_idx >= 0:
            try:
                dev_name = sd.query_devices(dev_idx).get("name", dev_name)
            except Exception:
                pass
        print(f"[JARVIS] 🎤 Mic stream open: '{dev_name}' (system default, 16000Hz, 1ch)")
        return s, 16000, 1
    except Exception as def_err:
        print(
            f"[JARVIS] ⚠️ Default input device open failed ({def_err}), searching other devices..."
        )

    # 2. Fallback: enumerate available input devices
    try:
        all_devs = sd.query_devices()
    except Exception as e:
        print(f"[JARVIS] ⚠️ Cannot query audio devices: {e}")
        return None, 0, 0

    def _priority(dev_tuple: tuple[int, Any]) -> int:
        idx, d = dev_tuple
        name = str(d.get("name", "")).lower()
        try:
            hostapi = sd.query_hostapis(d.get("hostapi", 0))["name"].lower()
        except Exception:
            hostapi = ""
        score = 0
        if "wdm-ks" in hostapi:
            # WDM-KS exclusive mode often fails or blocks on Windows desktops
            score -= 100
        elif "directsound" in hostapi:
            score += 40
        elif "mme" in hostapi:
            score += 30
        elif "wasapi" in hostapi:
            score += 20
        if "microphone" in name:
            score += 50
        return -score

    candidates = [
        idx
        for idx, d in sorted(enumerate(all_devs), key=_priority)
        if d.get("max_input_channels", 0) > 0
    ]

    for dev_idx in candidates:
        try:
            d_info = sd.query_devices(dev_idx)
            max_ch = int(d_info.get("max_input_channels", 1))
            native_sr = int(d_info.get("default_samplerate", 16000))
        except Exception:
            continue

        for sr in (16000, native_sr, 48000, 44100):
            for ch in (1, min(2, max_ch)):
                bs = 1024 * (sr // 16000) if sr % 16000 == 0 and sr >= 16000 else 1024
                try:
                    s = sd.InputStream(
                        device=dev_idx,
                        samplerate=sr,
                        channels=ch,
                        dtype="int16",
                        blocksize=bs,
                        callback=callback,
                    )
                    s.start()
                    dev_name = d_info.get("name", f"Device {dev_idx}")
                    print(
                        f"[JARVIS] 🎤 Mic stream open: '{dev_name}' (device {dev_idx}, {sr}Hz, {ch}ch)"
                    )
                    return s, sr, ch
                except Exception:
                    continue

    return None, 0, 0


def _prepare_audio_for_output(
    pcm_bytes: bytes,
    target_sr: int = RECEIVE_SAMPLE_RATE,
    target_ch: int = CHANNELS,
) -> bytes:
    """Resample and adapt mono 24kHz int16 PCM to match output stream format."""
    if not pcm_bytes:
        return b""
    if target_sr == RECEIVE_SAMPLE_RATE and target_ch == CHANNELS:
        return pcm_bytes

    samples = np.frombuffer(pcm_bytes, dtype=np.int16)
    if target_sr == 48000 and RECEIVE_SAMPLE_RATE == 24000:
        # Fast 2x linear interpolation for exact 24kHz -> 48kHz conversion
        samples = samples.repeat(2)
    elif target_sr != RECEIVE_SAMPLE_RATE:
        num_target = int(len(samples) * target_sr / RECEIVE_SAMPLE_RATE)
        x_orig = np.linspace(0, len(samples) - 1, len(samples))
        x_target = np.linspace(0, len(samples) - 1, num_target)
        samples = np.interp(x_target, x_orig, samples).astype(np.int16)

    if target_ch == 2:
        samples = np.column_stack((samples, samples)).flatten()

    return samples.astype(np.int16).tobytes()


def _open_output_stream(
    sample_rate: int = RECEIVE_SAMPLE_RATE, channels: int = CHANNELS
) -> tuple[sd.RawOutputStream | None, int, int]:
    """Find and open an optimal audio output stream without scratch or buffer underrun.

    Prioritizes the OS default audio output device (e.g. Speakers / Headphones) directly
    at 24000Hz. Gracefully falls back to other enumerated devices if needed.
    Returns (stream, sample_rate, channels) or (None, 0, 0) if unavailable.
    """
    # 1. Primary: open the OS default output device directly
    try:
        def_idx = sd.default.device[1] if sd.default.device is not None else None
        dev_name = "Default Speaker"
        max_ch = 2
        native_sr = 44100
        if def_idx is not None and def_idx >= 0:
            try:
                d_info = sd.query_devices(def_idx)
                dev_name = d_info.get("name", dev_name)
                max_ch = int(d_info.get("max_output_channels", 2))
                native_sr = int(d_info.get("default_samplerate", 44100))
            except Exception:
                pass

        for sr in (sample_rate, native_sr, 48000, 44100):
            for ch in (channels, min(2, max_ch)):
                try:
                    s = sd.RawOutputStream(
                        device=def_idx,
                        samplerate=sr,
                        channels=ch,
                        dtype="int16",
                        blocksize=1024,
                    )
                    s.start()
                    print(
                        f"[JARVIS] 🔊 Speaker stream open: '{dev_name}' (system default, device {def_idx}, {sr}Hz, {ch}ch)"
                    )
                    return s, sr, ch
                except Exception:
                    continue
    except Exception as def_err:
        print(f"[JARVIS] ⚠️ Default output stream open failed ({def_err}), searching other devices...")

    # 2. Fallback: enumerate available output devices
    try:
        all_devs = sd.query_devices()
    except Exception as e:
        print(f"[JARVIS] ⚠️ Cannot query audio output devices: {e}")
        all_devs = []

    def _out_priority(dev_tuple: tuple[int, Any]) -> int:
        idx, d = dev_tuple
        name = str(d.get("name", "")).lower()
        try:
            hostapi = sd.query_hostapis(d.get("hostapi", 0))["name"].lower()
        except Exception:
            hostapi = ""
        score = 0
        if "wdm-ks" in hostapi:
            score -= 100
        elif "wasapi" in hostapi:
            score += 40
        elif "directsound" in hostapi:
            score += 30
        elif "mme" in hostapi:
            score += 20
        if "speaker" in name or "headphone" in name:
            score += 20
        return -score

    candidates = [
        idx
        for idx, d in sorted(enumerate(all_devs), key=_out_priority)
        if d.get("max_output_channels", 0) > 0
    ]

    for dev_idx in candidates:
        try:
            d_info = sd.query_devices(dev_idx)
            max_ch = int(d_info.get("max_output_channels", 2))
            native_sr = int(d_info.get("default_samplerate", 48000))
        except Exception:
            continue

        for sr in (sample_rate, native_sr, 48000, 44100):
            for ch in (channels, min(2, max_ch)):
                try:
                    s = sd.RawOutputStream(
                        device=dev_idx,
                        samplerate=sr,
                        channels=ch,
                        dtype="int16",
                        blocksize=1024,
                    )
                    s.start()
                    dev_name = d_info.get("name", f"Device {dev_idx}")
                    print(
                        f"[JARVIS] 🔊 Speaker stream open: '{dev_name}' (device {dev_idx}, {sr}Hz, {ch}ch)"
                    )
                    return s, sr, ch
                except Exception:
                    continue

    # Fallback: system default output stream
    try:
        s = sd.RawOutputStream(
            samplerate=sample_rate,
            channels=channels,
            dtype="int16",
            blocksize=1024,
        )
        s.start()
        print(f"[JARVIS] 🔊 Speaker stream open: default output ({sample_rate}Hz, {channels}ch)")
        return s, sample_rate, channels
    except Exception as def_err:
        print(f"[JARVIS] ⚠️ Default output stream open failed: {def_err}")
        return None, 0, 0


class JarvisLive:
    def _open_output_stream(
        self, sample_rate: int = RECEIVE_SAMPLE_RATE, channels: int = CHANNELS
    ) -> tuple[sd.RawOutputStream | None, int, int]:
        return _open_output_stream(sample_rate, channels)

    def _open_input_stream(self, callback: Any) -> tuple[sd.InputStream | None, int, int]:
        return _open_input_stream(callback)

    def _prepare_audio_for_output(self, pcm_bytes: bytes, target_sr: int, target_ch: int) -> bytes:
        return _prepare_audio_for_output(pcm_bytes, target_sr, target_ch)

    def __init__(self, ui: JarvisUI):
        self.ui = ui
        self.session = None
        self.audio_in_queue = None
        self.out_queue = None
        self._loop = None
        self._is_speaking = False
        self._last_speaking_ended_at: float = 0.0
        self._speaking_lock = threading.Lock()
        self._ws_send_lock = asyncio.Lock()
        self._current_out_stream: Any = None
        self.ui.on_text_command = self._on_text_command

        # ── Task Continuity & SQLite Transcripts (OpenClaw parity) ──
        from src.agents.task.session_transcript_store import SessionTranscriptStore

        self._transcript_store = SessionTranscriptStore()
        self._restore_prior_chat_history()

        # ── Built-in coding & system tools (OpenClaw parity) ──
        from src.agents.sessions.tools import create_coding_tools
        from src.agents.sessions.tools.channel_tools import (
            create_configure_channel_tool,
            create_channel_status_tool,
        )

        self._coding_tools = {t["name"]: t for t in create_coding_tools(str(BASE_DIR))}
        conf_ch = create_configure_channel_tool(self)
        status_ch = create_channel_status_tool()
        self._coding_tools[conf_ch["name"]] = conf_ch
        self._coding_tools[status_ch["name"]] = status_ch

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

    def _on_text_command(self, text: str):
        if not self._loop:
            return
        # Phase 1C: route slash commands to plugin-registered handlers
        # BEFORE the LLM. Free text falls through unchanged.
        if text.lstrip().startswith("/"):
            asyncio.run_coroutine_threadsafe(self._handle_slash_command(text), self._loop)
            return
        self._submit_text_turn(text)

    def _submit_text_turn(self, text: str) -> None:
        """Submit a text turn using the Live API's typed content contract."""
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

        return types.LiveConnectConfig(
            response_modalities=[types.Modality.AUDIO],
            output_audio_transcription=types.AudioTranscriptionConfig(),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            system_instruction="\n".join(parts),
            tools=[types.Tool(function_declarations=TOOL_DECLARATIONS)],
            thinking_config=thinking_cfg,
            session_resumption=(
                types.SessionResumptionConfig(handle=self._session_resumption_handle)
                if self._session_resumption_handle
                else None
            ),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Charon")
                )
            ),
            realtime_input_config=types.RealtimeInputConfig(
                turn_coverage=types.TurnCoverage.TURN_INCLUDES_AUDIO_ACTIVITY_AND_ALL_VIDEO,
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
            return types.FunctionResponse(id=fc.id, name=name, response=res_dict)

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
                    import time
                    import os

                    time.sleep(1)
                    os._exit(0)

                threading.Thread(target=_shutdown, daemon=True).start()
                result = "Shutdown initiated."

            elif name in ("desktop", "desktop_action", "auto_control"):
                from .tool_pipeline import execute_desktop_action

                result = await execute_desktop_action(args)

            elif name.startswith("youtube_"):
                from src.application_automation.tools.youtube_tools import dispatch_youtube_tool

                result = await dispatch_youtube_tool(name, args)

            elif name == "set_task_goal":
                goal = str(args.get("goal") or args.get("description") or "")
                result = f"Task goal set to: {goal}"

            elif hasattr(self, "_coding_tools") and (
                name in self._coding_tools
                or (
                    name == "process"
                    and args.get("action") in ("open", "open_path", "start", "launch")
                )
            ):
                active_tool_name = name
                active_args = dict(args)
                if name == "process" and args.get("action") in (
                    "open",
                    "open_path",
                    "start",
                    "launch",
                ):
                    target_val = (
                        args.get("session_id")
                        or args.get("target")
                        or args.get("path")
                        or args.get("app")
                        or ""
                    )
                    if "open_path" in self._coding_tools:
                        active_tool_name = "open_path"
                        active_args = {"target": target_val}

                tool_entry = self._coding_tools[active_tool_name]
                execute_fn = tool_entry.get("execute")
                if execute_fn:
                    raw_res = await execute_fn(fc.id or "call", active_args)
                    result = _extract_tool_output(raw_res)
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
            result = f"Tool '{name}' failed: {e}"
            traceback.print_exc()
            self.speak_error(name, str(e))

        if not self.ui.muted:
            self.ui.set_state("LISTENING")

        print(f"[JARVIS] 📤 {name} → {str(result)[:80]}")

        return _make_response({"result": result})

    async def _send_realtime(self):
        """Continuously stream mic PCM chunks to the Live API session."""
        if not self.out_queue:
            return

        while True:
            msg = await self.out_queue.get()
            if isinstance(msg, dict):
                data = msg.get("data")
                raw_mime = msg.get("mime_type")
                mime = str(raw_mime) if raw_mime else f"audio/pcm;rate={SEND_SAMPLE_RATE}"
            else:
                data = msg
                mime = f"audio/pcm;rate={SEND_SAMPLE_RATE}"

            if not data or not self.session:
                continue

            async with self._ws_send_lock:
                try:
                    await self.session.send_realtime_input(
                        audio=types.Blob(
                            data=data,
                            mime_type=mime,
                        )
                    )
                except Exception as send_err:
                    msg_s = str(send_err).lower()
                    if any(
                        k in msg_s for k in ("closed", "not connected", "connection", "abnormal")
                    ):
                        break

    async def _send_visual_stream(self):
        """Continuously stream screen visual frames to the Gemini Live session."""
        print("[JARVIS] 👁️ Visual stream started")
        streamer = VisualFrameStreamer()
        try:
            async for frame in streamer.frames():
                if not self.session:
                    continue
                async with self._ws_send_lock:
                    try:
                        await self.session.send_realtime_input(
                            video=types.Blob(
                                data=frame.data,
                                mime_type=frame.mime_type,
                            )
                        )
                    except Exception as e:
                        msg_s = str(e).lower()
                        if any(
                            k in msg_s
                            for k in ("closed", "not connected", "connection", "abnormal")
                        ):
                            break
                        # Temporary congestion or frame drop: sleep briefly and keep stream alive
                        await asyncio.sleep(0.2)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            print(f"[JARVIS] visual stream ended: {exc}")
        finally:
            print("[JARVIS] 👁️ Visual stream stopped")

    async def _keepalive_ping(self):
        """Send periodic WebSocket keepalive pings (every 15s) to prevent idle TCP/NAT/proxy dropouts."""
        try:
            while True:
                await asyncio.sleep(15)
                if not self.session:
                    continue
                ws = getattr(self.session, "_ws", None)
                if ws and hasattr(ws, "ping"):
                    try:
                        res = ws.ping()
                        if asyncio.iscoroutine(res) or hasattr(res, "__await__"):
                            await res
                    except Exception:
                        pass
        except asyncio.CancelledError:
            pass

    async def _listen_audio(self):
        print("[JARVIS] 🎤 Mic started")
        import os
        import time
        import numpy as np

        loop = asyncio.get_event_loop()

        def _safe_put(q: object, item: object) -> None:
            if q is None:
                return
            try:
                q.put_nowait(item)
            except Exception:
                pass

        stream_info = {"sr": 16000, "ch": 1}
        # Echo suppression: mute mic while JARVIS is speaking + holdoff
        # after speech ends to let speaker audio decay. Without this,
        # the mic picks up JARVIS's own speaker output and Gemini treats
        # it as new user input → duplicate hearing/speaking/feedback loops.
        echo_suppression_hold_sec = float(os.environ.get("JARVIS_ECHO_HOLD_SEC", "0.08"))

        def callback(indata: object, frames: int, time_info: object, status: object) -> None:
            # Suppress mic while JARVIS speaks to prevent echo feedback.
            # Set JARVIS_MIC_MUTE_WHILE_SPEAKING=0 to force full-duplex
            # (only useful with hardware echo cancellation).
            mute_during_speech = os.environ.get("JARVIS_MIC_MUTE_WHILE_SPEAKING", "1") != "0"
            if mute_during_speech:
                now = time.monotonic()
                speaking_lock = getattr(self, "_speaking_lock", None)
                if speaking_lock is not None:
                    with speaking_lock:
                        is_speaking = getattr(self, "_is_speaking", False)
                        last_ended = getattr(self, "_last_speaking_ended_at", 0.0)
                        if is_speaking or (now - last_ended < echo_suppression_hold_sec):
                            return

            if not getattr(self.ui, "muted", False):
                if hasattr(indata, "ndim"):
                    actual_sr = stream_info["sr"]
                    if indata.ndim > 1 and indata.shape[1] > 1:
                        mono = (indata[:, 0].astype(np.int32) + indata[:, 1].astype(np.int32)) // 2
                    else:
                        mono = indata.flatten().astype(np.int32)

                    # Digital microphone boost for far-field capture (default 3.5x boost)
                    mic_gain = float(os.environ.get("JARVIS_MIC_GAIN", "3.5"))
                    if mic_gain != 1.0:
                        mono = np.clip(mono.astype(np.float32) * mic_gain, -32768, 32767).astype(
                            np.int32
                        )

                    if actual_sr == 16000:
                        pcm = mono.astype(np.int16).tobytes()
                    elif actual_sr == 48000:
                        pcm = mono[::3].astype(np.int16).tobytes()
                    elif actual_sr == 44100:
                        indices = np.round(
                            np.linspace(0, len(mono) - 1, int(len(mono) * 16000 / 44100))
                        ).astype(int)
                        pcm = mono[indices].astype(np.int16).tobytes()
                    else:
                        indices = np.round(
                            np.linspace(0, len(mono) - 1, int(len(mono) * 16000 / actual_sr))
                        ).astype(int)
                        pcm = mono[indices].astype(np.int16).tobytes()
                elif hasattr(indata, "tobytes"):
                    pcm = indata.tobytes()
                else:
                    return

                frame = {"data": pcm, "mime_type": f"audio/pcm;rate={SEND_SAMPLE_RATE}"}
                try:
                    loop.call_soon_threadsafe(_safe_put, self.out_queue, frame)
                except Exception:
                    pass

        mic_warned = False
        try:
            while True:
                open_fn = getattr(self, "_open_input_stream", None)
                if open_fn is not None:
                    stream, sr, ch = open_fn(callback)
                else:
                    try:
                        stream = sd.InputStream(
                            samplerate=SEND_SAMPLE_RATE,
                            channels=CHANNELS,
                            dtype="int16",
                            blocksize=CHUNK_SIZE,
                            callback=callback,
                        )
                        stream.start()
                        sr, ch = SEND_SAMPLE_RATE, CHANNELS
                    except Exception:
                        stream, sr, ch = None, 0, 0

                if stream is not None:
                    stream_info["sr"] = sr
                    stream_info["ch"] = ch
                    mic_warned = False
                    try:
                        while True:
                            await asyncio.sleep(0.5)
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        print(f"[JARVIS] ⚠️ Mic stream error: {e}")
                    finally:
                        try:
                            stream.stop()
                            stream.close()
                        except Exception:
                            pass
                else:
                    if not mic_warned:
                        print(
                            "[JARVIS] ⚠️ Microphone unavailable. "
                            "Running in channels/text/vision mode. "
                            "Will retry checking for mic in background."
                        )
                        mic_warned = True
                    await asyncio.sleep(2.0)
        except asyncio.CancelledError:
            raise

    async def _receive_audio(self):
        print("[JARVIS] 👂 Recv started")
        out_buf, in_buf = [], []

        if not self.session:
            return

        try:
            while True:
                async for response in self.session.receive():
                    # 1. Update session resumption handle if provided by Google server
                    sru = getattr(response, "session_resumption_update", None)
                    if (
                        sru
                        and getattr(sru, "resumable", False)
                        and getattr(sru, "new_handle", None)
                    ):
                        self._session_resumption_handle = sru.new_handle
                        self._consecutive_reconnect_failures = 0

                    # 2. Check for server GoAway signal (graceful server rotation)
                    go_away = getattr(response, "go_away", None)
                    if go_away:
                        time_left = getattr(go_away, "time_left", None) or "soon"
                        print(
                            f"[JARVIS] ℹ️ Live API Server rotation notice: server disconnecting in {time_left}. Resumption handle is ready."
                        )

                    # 3. Capture audio bytes from either response.data or model_turn inline_data
                    audio_bytes = response.data
                    if not audio_bytes and response.server_content and response.server_content.model_turn:
                        for p in response.server_content.model_turn.parts:
                            if getattr(p, "inline_data", None) and p.inline_data.data:
                                audio_bytes = p.inline_data.data
                                break

                    if audio_bytes and self.audio_in_queue:
                        try:
                            self.audio_in_queue.put_nowait(audio_bytes)
                        except Exception:
                            pass

                    if response.server_content:
                        sc = response.server_content

                        if getattr(sc, "interrupted", False):
                            if self.audio_in_queue:
                                while not self.audio_in_queue.empty():
                                    try:
                                        self.audio_in_queue.get_nowait()
                                    except Exception:
                                        pass
                                # Sentinel: _play_audio checks for None and
                                # breaks immediately instead of waiting 800ms.
                                self.audio_in_queue.put_nowait(None)
                            self.set_speaking(False)

                        if sc.output_transcription and sc.output_transcription.text:
                            # Speaking state is owned exclusively by _play_audio;
                            # do NOT call set_speaking(True) here — audio hasn't
                            # reached the speaker yet.
                            txt = sc.output_transcription.text.strip()
                            if txt:
                                out_buf.append(txt)

                        if sc.model_turn and sc.model_turn.parts:
                            for part in sc.model_turn.parts:
                                if getattr(part, "text", None) and not getattr(
                                    part, "thought", False
                                ):
                                    t = part.text.strip()
                                    if t and t not in out_buf:
                                        out_buf.append(t)

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = sc.input_transcription.text.strip()
                            if txt:
                                in_buf.append(txt)

                        if sc.turn_complete:
                            # Signal _play_audio that Gemini has finished
                            # sending audio. _play_audio will drain remaining
                            # queued chunks then end speech instantly.
                            tc_sig = getattr(self, "_turn_complete_signal", None)
                            if tc_sig is not None:
                                tc_sig.set()

                            full_in = " ".join(in_buf).strip()
                            if full_in:
                                self.ui.write_log(f"You: {full_in}")
                                if hasattr(self, "_transcript_store"):
                                    self._transcript_store.append_entry(
                                        "desktop:hud", "user_speech", {"text": full_in}
                                    )
                            in_buf = []

                            full_out = " ".join(out_buf).strip()
                            if full_out:
                                self.ui.write_log(f"Jarvis: {full_out}")
                                if hasattr(self, "_transcript_store"):
                                    self._transcript_store.append_entry(
                                        "desktop:hud", "assistant_speech", {"text": full_out}
                                    )
                            out_buf = []

                            # Phase 3.5: background LLM-based memory
                            # extraction is gone; the model calls
                            # `save_memory` directly when it wants
                            # to remember something.

                            # Phase 3: fire `agent_end` hook after each
                            # complete turn. Plugins can persist state
                            # (memory flush, metric emission, etc.).
                            from jarvis_hooks import fire_sync

                            fire_sync(
                                _PLUGIN_HOOK_BUS,
                                "agent_end",
                                {"input": full_in, "output": full_out},
                            )
                            _emit_canonical_event(
                                "TurnCompleted",
                                priority="P2_NORMAL",
                                metadata={"input": full_in, "output": full_out},
                            )

                    if response.tool_call:
                        fn_responses = []
                        for fc in response.tool_call.function_calls:
                            print(f"[JARVIS] 📞 {fc.name}")
                            fr = await self._execute_tool(fc)
                            fn_responses.append(fr)
                        if self.session:
                            async with self._ws_send_lock:
                                await self.session.send_tool_response(
                                    function_responses=fn_responses
                                )

        except asyncio.CancelledError:
            pass
        except Exception as e:
            msg_str = str(e).lower()
            if any(
                k in msg_str
                for k in (
                    "connectionclosed",
                    "closed",
                    "1000",
                    "1001",
                    "1006",
                    "1011",
                    "eof",
                    "abnormal",
                    "reset by peer",
                    "internal error",
                    "connection reset",
                )
            ):
                print(
                    f"[JARVIS] ℹ️ Live API connection closed by server/peer ({type(e).__name__}): {e}"
                )
            else:
                print(f"[JARVIS] ❌ Recv: {e}")
                traceback.print_exc()
            raise

    async def _play_audio(self):
        print("[JARVIS] 🔊 Play started")

        stream = None
        out_sr = RECEIVE_SAMPLE_RATE
        out_ch = CHANNELS

        open_fn = getattr(self, "_open_output_stream", None)
        if open_fn is not None:
            stream, out_sr, out_ch = open_fn(RECEIVE_SAMPLE_RATE, CHANNELS)
        else:
            try:
                stream = sd.RawOutputStream(
                    samplerate=RECEIVE_SAMPLE_RATE,
                    channels=CHANNELS,
                    dtype="int16",
                    blocksize=1024,
                )
                stream.start()
            except Exception as e:
                print(f"[JARVIS] ⚠️ Audio output stream unavailable: {e}")

        self._current_out_stream = stream

        if not self.audio_in_queue:
            return
        audio_q = self.audio_in_queue
        leftover = b""
        is_speaking = False

        prep_fn = getattr(self, "_prepare_audio_for_output", None)

        try:
            while True:
                # Wait indefinitely for the first chunk of a new speech segment
                chunk = await audio_q.get()

                # None sentinel = barge-in interrupt from _receive_audio
                if chunk is None:
                    if is_speaking:
                        is_speaking = False
                        self.set_speaking(False)
                    continue

                if not is_speaking:
                    is_speaking = True
                    self.set_speaking(True)
                    # Clear turn_complete from previous turn so we don't
                    # falsely end this new speech segment early.
                    tc_sig = getattr(self, "_turn_complete_signal", None)
                    if tc_sig is not None:
                        tc_sig.clear()

                # Minimal jitter buffer: ~30ms (1440 bytes at 24kHz int16)
                buffer_chunks = [chunk]
                accumulated = len(chunk)
                target_bytes = int(RECEIVE_SAMPLE_RATE * 2 * 0.03)
                deadline = asyncio.get_running_loop().time() + 0.025

                while accumulated < target_bytes:
                    now = asyncio.get_running_loop().time()
                    if now >= deadline:
                        break
                    try:
                        next_c = await asyncio.wait_for(
                            audio_q.get(), timeout=max(0.005, deadline - now)
                        )
                        if next_c is None:
                            buffer_chunks.clear()
                            break
                        buffer_chunks.append(next_c)
                        accumulated += len(next_c)
                    except (asyncio.TimeoutError, Exception):
                        break

                if not buffer_chunks:
                    if is_speaking:
                        is_speaking = False
                        self.set_speaking(False)
                    continue

                # Write jitter-buffered chunk
                raw_bytes = leftover + b"".join(buffer_chunks)
                remainder = len(raw_bytes) % 2
                if remainder != 0:
                    pcm_to_play = raw_bytes[:-remainder]
                    leftover = raw_bytes[-remainder:]
                else:
                    pcm_to_play = raw_bytes
                    leftover = b""

                if stream is not None and pcm_to_play:
                    if prep_fn is not None:
                        prepared = prep_fn(pcm_to_play, out_sr, out_ch)
                    else:
                        prepared = pcm_to_play
                    try:
                        await asyncio.to_thread(stream.write, prepared)
                    except Exception as play_err:
                        print(f"[JARVIS] ⚠️ Audio playback error: {play_err}")

                # Continuous streaming loop with instant turn-complete detection.
                # Primary: end speech as soon as queue is empty AND Gemini
                # signaled turn_complete (0ms dead time).
                # Fallback: 500ms timeout for edge cases (disconnect, etc).
                tc_sig = getattr(self, "_turn_complete_signal", None)
                while True:
                    # Instant end: Gemini finished and no more audio queued
                    if audio_q.empty() and tc_sig is not None and tc_sig.is_set():
                        tc_sig.clear()
                        if is_speaking:
                            is_speaking = False
                            self.set_speaking(False)
                        break

                    try:
                        next_chunk = await asyncio.wait_for(audio_q.get(), timeout=0.5)
                    except asyncio.TimeoutError:
                        if is_speaking:
                            is_speaking = False
                            self.set_speaking(False)
                        break

                    if next_chunk is None:
                        if is_speaking:
                            is_speaking = False
                            self.set_speaking(False)
                        break

                    # Batch-drain: grab everything available right now
                    more = [next_chunk]
                    interrupted = False
                    while not audio_q.empty():
                        try:
                            item = audio_q.get_nowait()
                            if item is None:
                                interrupted = True
                                break
                            more.append(item)
                        except Exception:
                            break

                    if interrupted:
                        if is_speaking:
                            is_speaking = False
                            self.set_speaking(False)
                        break

                    raw_bytes = leftover + b"".join(more)
                    remainder = len(raw_bytes) % 2
                    if remainder != 0:
                        pcm_to_play = raw_bytes[:-remainder]
                        leftover = raw_bytes[-remainder:]
                    else:
                        pcm_to_play = raw_bytes
                        leftover = b""

                    if stream is not None and pcm_to_play:
                        if prep_fn is not None:
                            prepared = prep_fn(pcm_to_play, out_sr, out_ch)
                        else:
                            prepared = pcm_to_play
                        try:
                            await asyncio.to_thread(stream.write, prepared)
                        except Exception as play_err:
                            print(f"[JARVIS] ⚠️ Audio playback error: {play_err}")

        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[JARVIS] ❌ Play error: {e}")
        finally:
            self._current_out_stream = None
            if is_speaking:
                is_speaking = False
                self.set_speaking(False)
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass

    def _is_server_internal_error(self, error: BaseException) -> bool:
        """Return True when error indicates a 1011 or 5xx server-side internal error."""
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

        while True:
            try:
                print(f"[JARVIS] 🔌 Connecting ({active_model})...")
                self.ui.set_state("THINKING")
                config = self._build_config(active_model)

                async with (
                    client.aio.live.connect(model=active_model, config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session = session
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
                    if self._session_resumption_handle:
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
                print(f"[JARVIS] ⚠️ {e}")
                if isinstance(e, BaseExceptionGroup):
                    for child in e.exceptions:
                        print(f"[JARVIS]   task failure: {type(child).__name__}: {child}")

                # If server had an internal error (1011) or a resumption failure,
                # the session on Google's backend is corrupted or dead.
                # Invalidate the resumption handle immediately so reconnect starts fresh!
                is_internal_err = self._is_server_internal_error(e)
                if self._session_resumption_handle and (
                    is_internal_err or self._consecutive_reconnect_failures > 0
                ):
                    print(
                        "[JARVIS] ℹ️ Invalidating session resumption handle to establish a fresh session."
                    )
                    self._session_resumption_handle = None

                is_not_found = self._is_model_not_found_error(e)
                is_repeated_internal_err = (
                    is_internal_err and self._consecutive_reconnect_failures >= 2
                )

                if is_not_found or is_repeated_internal_err:
                    reason = (
                        "returned not found"
                        if is_not_found
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
                            "known-good model like 'models/gemini-3.1-flash-live-preview'."
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

                if not self._is_connection_closed_error(e):
                    traceback.print_exc()

            self.set_speaking(False)
            self.ui.set_state("THINKING")
            self._consecutive_reconnect_failures += 1
            if self._session_resumption_handle and self._consecutive_reconnect_failures <= 1:
                reconnect_delay = 0.5
                print(f"[JARVIS] 🔄 Seamlessly resuming Live session in {reconnect_delay}s...")
            else:
                reconnect_delay = min(
                    10.0, 1.0 * (1.5 ** min(self._consecutive_reconnect_failures, 5))
                )
                print(
                    f"[JARVIS] 🔄 Reconnecting in {reconnect_delay:.1f}s (attempt {self._consecutive_reconnect_failures})..."
                )
            await asyncio.sleep(reconnect_delay)


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
