"""packages/voice_pipeline/src/jarvis_voice_pipeline/terminal_app.py

Unified Terminal & Desktop Voice Engine:
Direct Google Gemini Live Bidirectional WebSocket Audio Streaming with:
- 8-Key Seamless Circular Auto-Rotation on Rate Limits (429 / Quota)
- Spectral EchoGuard Cancellation for Natural Speaker Feedback Filtering
- Zero Dead-Air Earcon Chimes and 178 Plugins & Tools
- Simultaneous PyQt6 Mark XXXIX Desktop HUD and Terminal Console Input/Output
"""

# ruff: noqa: E402

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import socket
import sys
import threading
import time
import warnings
from collections import deque
from pathlib import Path
from typing import Any, Callable

# Filter noisy non-critical warnings
warnings.filterwarnings("ignore", message=".*there are non-data parts in the response.*")
warnings.filterwarnings("ignore", category=FutureWarning, message=".*grpcio.*")
warnings.filterwarnings("ignore", category=RuntimeWarning, message=".*duckduckgo_search.*")
warnings.filterwarnings("ignore", category=RuntimeWarning, message=".*ddgs.*")
warnings.filterwarnings("ignore", message=".*This package.*duckduckgo_search.*")
warnings.filterwarnings("ignore", category=ResourceWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning, module="sounddevice")
warnings.filterwarnings(
    "ignore", message=".*Setting the shape on a NumPy array has been deprecated.*"
)

BASE_DIR = Path(__file__).resolve().parents[4]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import numpy as np
import sounddevice as sd

# Upstream sounddevice 0.5.x NumPy 2.5+ compatibility patch (zero-copy view without deprecated in-place shape mutation)
if hasattr(sd, "_array"):

    def _safe_sd_array(buffer, channels, dtype):
        return np.frombuffer(buffer, dtype=dtype).reshape(-1, channels)

    sd._array = _safe_sd_array
from google import genai  # type: ignore
from google.genai import types  # type: ignore
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from jarvis_audio_core.audio_cues import TOOL_CHIME_BYTES
from jarvis_desktop.tool_declarations import TOOL_DECLARATIONS as _BASE_TOOL_DECLARATIONS
from jarvis_desktop.tool_pipeline import execute_desktop_action, prepare_tool_arguments
from jarvis_desktop.vad_engine import EnergyVADEngine
from jarvis_net_policy import enable_resilient_dns
from jarvis_sdk.loader import load_all_plugins_from_workspace
from src.agents.sessions.tools import create_coding_tools
from src.agents.task.session_transcript_store import SessionTranscriptStore
from src.agents.tool_loop_detection import (
    detect_tool_call_loop,
    record_tool_call,
    record_tool_call_outcome,
)
from src.agents.tools_effective_inventory import ToolExecutor, build_effective_tool_inventory
from src.gateway.server import start_jarvis_gateway_server
from src.storage.sqlite_broker import initialize_canonical_databases

from .echo import EchoGuard
from .key_rotator import get_default_key_rotator
from .outcome import unwrap
from .pipeline_builder import (
    build_jarvis_system_prompt,
    clean_gemini_declarations,
)
from .nepali_romanizer import romanize_nepali_text
from .viseme import pcm_level

# Silence noisy logging
logging.getLogger("google").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("websockets").setLevel(logging.CRITICAL)
logging.getLogger("websockets.server").setLevel(logging.CRITICAL)
logging.getLogger("asyncio").setLevel(logging.ERROR)

logger = logging.getLogger("jarvis.terminal.app")
console = Console(force_terminal=True)

# Voice turns can run long autonomous ladders, so trip points sit well above
# the channel loop: six identical no-progress calls, ten per turn overall.
_VOICE_LOOP_CONFIG: dict[str, Any] = {
    "enabled": True,
    "historySize": 40,
    "warningThreshold": 3,
    "unknownToolThreshold": 3,
    "criticalThreshold": 6,
    "globalCircuitBreakerThreshold": 10,
}


SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE = 1024
AUDIO_SLICE = 2400  # ~50ms slices at 24kHz 16-bit mono for instant barge-in
# Native-audio (speech-to-speech) Live model. It hears, answers, and calls tools
# in one real-time session; half-cascade Live models answer text-first and stall
# the voice loop, so they stay fallbacks only.
DEFAULT_MODEL = (
    os.environ.get("JARVIS_LIVE_MODEL") or "models/gemini-2.5-flash-native-audio-preview-12-2025"
)
FALLBACK_MODELS = (
    "models/gemini-2.5-flash-native-audio-latest",
)


def _resolve_credentials() -> tuple[str, str, str, str]:
    """Compatibility helper for existing unit tests."""
    rotator = get_default_key_rotator()
    gemini_key = rotator.get_current_key()
    return "wss://127.0.0.1:7433", "key", "secret", gemini_key


class JarvisTerminalHUDState:
    """Reactive state model for the rich terminal display & GUI bridge."""

    def __init__(self, ui: Any = None) -> None:
        self.ui = ui
        self.status: str = "INITIALIZING"
        self.agent_state: str = "STANDBY"
        self.room_name: str = "jarvis-local"
        self.livekit_url: str = "native-gemini-live"
        self.mic_active: bool = True
        self.transcripts: deque[tuple[str, str, str]] = deque(maxlen=30)
        self.tool_events: deque[tuple[str, str, str]] = deque(maxlen=20)
        self.last_speech_time: float = 0.0
        self.transcript_store: Any = None

    def set_agent_state(self, new_state: str) -> None:
        self.agent_state = new_state
        if self.ui and hasattr(self.ui, "set_state"):
            try:
                self.ui.set_state(new_state)
            except Exception:
                pass

    def add_transcript(self, role: str, text: str) -> None:
        ts = time.strftime("%H:%M:%S")
        self.transcripts.append((ts, role, text))
        color = "bold green" if role.lower() == "user" else "bold cyan"
        console.print(f"[{ts}] [{color}]{role}:[/{color}] {text}")

        if self.ui and hasattr(self.ui, "set_live_transcript"):
            try:
                self.ui.set_live_transcript(f"{role}: {text}")
            except Exception:
                pass

        if self.transcript_store:
            try:
                et = "user_speech" if role.lower() == "user" else "assistant_speech"
                self.transcript_store.append_entry("desktop:hud", et, {"text": text})
            except Exception:
                pass

    def add_tool_event(self, tool_name: str, details: str) -> None:
        ts = time.strftime("%H:%M:%S")
        self.tool_events.append((ts, tool_name, details))
        console.print(f"[{ts}] [bold magenta]⚡ {tool_name}:[/bold magenta] {details}")

        if self.ui and hasattr(self.ui, "write_log"):
            try:
                self.ui.write_log(f"⚡ {tool_name} {details}")
            except Exception:
                pass

        if self.transcript_store:
            try:
                self.transcript_store.append_entry(
                    "desktop:hud", "tool_event", {"tool": tool_name, "details": details}
                )
            except Exception:
                pass


class _MockRoom:
    def __init__(self):
        self._events: dict[str, list[Callable]] = {}

    def on(self, event: str):
        def decorator(func: Callable):
            self._events.setdefault(event, []).append(func)
            return func

        return decorator

    async def connect(self, *args, **kwargs):
        pass

    async def disconnect(self):
        pass


class JarvisTerminalRTCClient:
    """Mock/Compatibility RTC client stub for backward compatible test suites."""

    def __init__(
        self,
        url: str,
        token: str,
        room_name: str,
        state: JarvisTerminalHUDState,
    ) -> None:
        self.url = url
        self.token = token
        self.room_name = room_name
        self.state = state
        self.room = _MockRoom()
        self.running = False

        @self.room.on("data_received")
        def _on_data(pkt: Any):
            try:
                data_bytes = getattr(pkt, "data", b"")
                if isinstance(data_bytes, str):
                    data_bytes = data_bytes.encode("utf-8")
                msg = json.loads(data_bytes.decode("utf-8"))
                msg_type = msg.get("type")
                payload = msg.get("payload", {})
                if msg_type == "tool_start":
                    name = payload.get("name", "tool")
                    args = payload.get("args", {})
                    self.state.set_agent_state("THINKING")
                    self.state.add_tool_event(name, f"Executing: {args}")
                elif msg_type == "tool_end":
                    self.state.set_agent_state("SPEAKING")
            except Exception:
                pass

    async def _setup_microphone(self) -> None:
        pass

    async def start(self) -> None:
        self.running = True
        await self.room.connect()
        await self._setup_microphone()
        self.state.status = "CONNECTED"
        self.state.set_agent_state("LISTENING")

    async def close(self) -> None:
        self.running = False
        await self.room.disconnect()


def print_terminal_banner(url: str = "", room_name: str = "", has_gui: bool = True) -> None:
    """Prints the futuristic Stark-tech console banner."""
    rotator = get_default_key_rotator()
    banner = Text()
    banner.append(
        "╔═══════════════════════════════════════════════════════════════════════════╗\n",
        style="cyan",
    )
    banner.append(
        "║                 ✦ J.A.R.V.I.S. UNIFIED VOICE & HUD ENGINE ✦               ║\n",
        style="bold cyan",
    )
    banner.append(
        "║      Google Gemini Live Realtime Audio  ●  8-Key Pool  ●  JARVIS Core      ║\n",
        style="cyan",
    )
    banner.append(
        "╚═══════════════════════════════════════════════════════════════════════════╝\n",
        style="cyan",
    )
    banner.append(
        "● [SYSTEM] Canonical SQLite DBs & JSON-RPC Gateway (127.0.0.1:7433) Online\n",
        style="green",
    )
    banner.append(
        f"● [GEMINI LIVE] Key #{rotator.current_index + 1} Active ({rotator.masked_key()}) | Pool Size: {rotator.pool_size}\n",
        style="green",
    )
    banner.append(
        f"● [MODEL] Bidirectional WebSocket: {DEFAULT_MODEL}\n",
        style="green",
    )
    active_voice = os.environ.get("JARVIS_VOICE_NAME", "Puck").strip() or "Puck"
    banner.append(
        f"● [VOICE] {active_voice} (Single Stream) ● 16kHz Mic In (EchoGuard Active) ● 24kHz Speaker Out\n",
        style="green",
    )
    banner.append(
        "● [PERSISTENCE] SQLite Session Transcripts & Rolling Dialogue History Active\n",
        style="green",
    )
    gui_status = "MARK XXXIX Arc Reactor HUD Online" if has_gui else "Headless Terminal Mode"
    banner.append(f"● [HUD UI] {gui_status}\n\n", style="green")
    banner.append(
        "🎙️  Listening... Speak naturally or type commands below (e.g. 'Jarvis, Chrome kholera YouTube ma lofi bajau')\n",
        style="bold yellow",
    )
    banner.append("    [Press Ctrl+C to shutdown]\n", style="dim white")
    console.print(Panel(banner, border_style="cyan"))


class NativeGeminiLiveEngine:
    """Core Realtime Voice Engine using Google GenAI Live WebSocket with circular key rotation."""

    _ACTIVE_VOICE_ENGINE: NativeGeminiLiveEngine | None = None

    @classmethod
    def get_active_engine(cls) -> NativeGeminiLiveEngine | None:
        """Acquire active singleton instance of NativeGeminiLiveEngine."""
        return cls._ACTIVE_VOICE_ENGINE

    def post_system_notification(self, text: str) -> None:
        """Push an urgent system notification into text queue for spoken delivery."""
        try:
            self.text_in_queue.put_nowait(text)
        except Exception:
            pass

    def __init__(self, state: JarvisTerminalHUDState, ui: Any = None) -> None:
        NativeGeminiLiveEngine._ACTIVE_VOICE_ENGINE = self
        self.state = state
        self.ui = ui
        self.rotator = get_default_key_rotator()
        self.echo_guard = EchoGuard()
        self.active_session: Any = None
        self.session_resumption_handle: str | None = None

        self.audio_out_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=30)
        self.audio_in_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=4000)
        self.text_in_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=100)

        self.stop_event = asyncio.Event()
        self._turn_done_event = asyncio.Event()
        self._turn_done_event.set()
        self._is_speaking = False
        self._speaking_lock = threading.Lock()
        self._rx_deadline: float | None = None
        self._last_spk_time: float = 0.0
        self._last_server_activity: float = time.monotonic()
        self._boot_greeted: bool = False
        self._consecutive_fails: int = 0
        self._network_fails: int = 0
        enable_resilient_dns()
        self._ws_send_lock = asyncio.Lock()

        self.user_speaking = False
        self.loop: asyncio.AbstractEventLoop | None = None
        self._tail_until: float = 0.0
        self._tool_call_in_flight: bool = False
        self._pending_tool_response: bool = False
        self._tool_loop_state: dict[str, Any] = {}
        self._assistant_generating: bool = False
        self._turn_complete_received: bool = True
        self.prefer_devanagari: bool = False
        self._active_goal: str | None = None
        self._primary_active_goal: str | None = None
        self._task_in_progress: bool = False
        self._turn_tool_executed: bool = False
        self._ghost_nudge_count: int = 0
        self._last_user_prompt: str | None = None
        self._announced_subagent_runs: set[str] = set()

        # Load workspace plugins & tools cleanly
        import contextlib
        import io

        with contextlib.redirect_stdout(io.StringIO()):
            self.plugin_result = load_all_plugins_from_workspace(BASE_DIR)

        # Load JARVIS canonical host coding tools (ls, read, write, edit, exec, process, etc.)
        try:
            tools_list = create_coding_tools(str(BASE_DIR))
            self._coding_tools = {t["name"]: t for t in tools_list}
        except Exception as e:
            logger.warning("Failed to load host coding tools: %s", e)
            self._coding_tools = {}

        control_executors = self._voice_control_executors()
        self.tool_surface = build_effective_tool_inventory(
            base_declarations=_BASE_TOOL_DECLARATIONS,
            plugin_tools=self.plugin_result.tool_decls,
            plugin_dispatch=getattr(self.plugin_result, "plugin_dispatch", {}) or {},
            host_tools=self._coding_tools,
            control_executors=control_executors,
            executor_overrides={"computer": control_executors["computer"]},
        )
        self.tool_declarations = clean_gemini_declarations(self.tool_surface.declarations())
        self.system_prompt = build_jarvis_system_prompt(BASE_DIR, self.plugin_result.skills)
        self.active_model = DEFAULT_MODEL

        # JARVIS Task Continuity & Persistent SQLite Transcript Store
        self._transcript_store = SessionTranscriptStore()
        self.state.transcript_store = self._transcript_store

        # Acoustic Energy VAD & High-pass filter engine
        speech_thresh = int(os.environ.get("JARVIS_SPEECH_THRESHOLD", "250"))
        self.vad = EnergyVADEngine(
            speech_threshold=speech_thresh,
            hangover_frames=8,
            pre_roll_frames=5,
        )

        self._restore_prior_chat_history()

        # Start in-process CronRunner so scheduled automations actively tick
        try:
            from src.agents.sessions.tools.automations_tool import _get_shared_runner

            runner = _get_shared_runner()
            if runner and getattr(runner, "_thread", None) is None:
                runner.start(tick_seconds=15.0)
                logger.info("CronRunner background scheduler active (15s tick)")
        except Exception as cron_err:
            logger.debug("Could not initialize CronRunner on startup: %s", cron_err)

        # Register subagent completion listener to deliver spoken announcements on finish
        try:
            from src.agents.sessions.tools.subagent_tools import get_default_spawner

            spawner = get_default_spawner()
            spawner.register_completion_listener(self._on_subagent_finished)
        except Exception as spawner_err:
            logger.debug("Could not register subagent completion listener: %s", spawner_err)

        # Wire UI text handler
        if self.ui and hasattr(self.ui, "on_text_command"):
            self.ui.on_text_command = self._queue_user_text

    def _on_subagent_finished(self, record: Any, findings: str | None = None) -> None:
        """Deliver child subagent completion announcement to console and voice engine."""
        run_id = getattr(record, "run_id", "")
        if run_id and run_id in self._announced_subagent_runs:
            return
        if run_id:
            self._announced_subagent_runs.add(run_id)

        task_label = getattr(record, "label", None) or getattr(record, "task", "background task")
        status_val = getattr(getattr(record, "status", None), "value", str(getattr(record, "status", "completed")))
        res_text = getattr(record, "result_text", "") or getattr(record, "error", "") or ""
        short_res = res_text[:300].strip()

        # 1. Print visual HUD announcement
        console.print(
            f"\n[bold green]✦ [SUBAGENT {status_val.upper()}] '{task_label}' finished.[/bold green]\n"
            f"[dim cyan]{short_res}[/dim cyan]"
        )

        # 2. Record to persistent SQLite transcript store
        try:
            self._transcript_store.add_turn(
                "system",
                f"[SUBAGENT COMPLETED] Task: '{task_label}'. Status: {status_val}. Findings: {short_res}",
            )
        except Exception:
            pass

        # 3. Deliver spoken notification to Sir via Gemini Live
        if not self.stop_event.is_set():
            prompt = (
                f"[SYSTEM NOTIFICATION: Background subagent finished. Task: '{task_label}'. "
                f"Status: {status_val}. Findings: {short_res}. "
                f"Briefly inform Sir in 1 warm, natural sentence in Nepali that this background task has finished and summarize what was found.]"
            )
            self.post_system_notification(prompt)

    def _voice_control_executors(self) -> dict[str, ToolExecutor]:
        """Core control tools whose behaviour is owned by the voice engine."""

        async def shutdown(_args: dict[str, Any], _call_id: str) -> str:
            self.state.set_agent_state("IDLE")
            self.stop_event.set()
            return "Shutting down JARVIS. Goodbye Sir."

        async def standby(_args: dict[str, Any], _call_id: str) -> str:
            self.state.set_agent_state("STANDBY")
            return "Entering standby sleep mode. Say 'Hey Jarvis' to wake me up."

        async def save_memory(args: dict[str, Any], _call_id: str) -> str:
            from jarvis_desktop.memory_bridge import update_memory

            category = str(args.get("category") or "notes")
            key = str(args.get("key") or "")
            value = str(args.get("value") or "")
            if not key or not value:
                return "Memory not saved: missing key or value."
            update_memory({category: {key: {"value": value}}})
            return "Fact saved to long-term memory."

        async def recall_memory(args: dict[str, Any], _call_id: str) -> str:
            from jarvis_desktop.memory_bridge import hybrid_search_memory

            query = str(args.get("query") or args.get("q") or "").strip()
            if not query:
                return "Query cannot be empty."
            limit = int(args.get("limit") or 8)
            hits = await asyncio.to_thread(
                hybrid_search_memory,
                query=query,
                limit=limit,
                category=args.get("category"),
                workspace_dir=BASE_DIR,
            )
            if not hits:
                return f"No memories found matching '{query}'."
            lines = [f"Found {len(hits)} relevant memory records:"]
            lines.extend(
                f"- [{hit.get('category', 'general')}] {hit.get('key')}: {hit.get('value')}"
                for hit in hits[:limit]
            )
            return "\n".join(lines)

        async def computer(args: dict[str, Any], _call_id: str) -> str:
            # Voice owns native desktop control through the host pipeline. The CUA
            # plugin's coordinate backend (jarvis_sdk.input_backend) is not shipped
            # yet, and it has no window-level actions such as minimize.
            return await execute_desktop_action(args)

        return {
            "shutdown_jarvis": shutdown,
            "standby_jarvis": standby,
            "save_memory": save_memory,
            "recall_memory": recall_memory,
            "computer": computer,
        }

    def set_speaking(self, value: bool) -> None:
        """Thread-safe toggle for speaking state with echo tail calculation."""
        with self._speaking_lock:
            self._is_speaking = value
        if value:
            self._tail_until = 0.0
            self.state.set_agent_state("SPEAKING")
        else:
            self._tail_until = time.monotonic() + 0.08
            self.state.set_agent_state("LISTENING")

    @property
    def is_speaking(self) -> bool:
        with self._speaking_lock:
            return self._is_speaking

    @is_speaking.setter
    def is_speaking(self, value: bool) -> None:
        self.set_speaking(value)

    def _arm_stall(self) -> None:
        """Arms watchdog deadline when a user turn (voice or text) is in flight."""
        if getattr(self, "_rx_deadline", None) is None:
            self._rx_deadline = time.monotonic() + 25.0

    def _clear_stall(self) -> None:
        """Clears watchdog deadline once server starts responding."""
        self._rx_deadline = None

    def _drain_queues(self) -> None:
        """Drains audio queues on reconnect so stale audio is not carried over."""
        while not self.audio_out_queue.empty():
            try:
                self.audio_out_queue.get_nowait()
            except Exception:
                break
        while not self.audio_in_queue.empty():
            try:
                self.audio_in_queue.get_nowait()
            except Exception:
                break
        self.set_speaking(False)
        self._tool_call_in_flight = False
        self._pending_tool_response = False
        self._assistant_generating = False
        self._turn_complete_received = True
        self._turn_done_event.set()
        self._rx_deadline = None
        self._turn_tool_executed = False
        self._ghost_nudge_count = 0
        if hasattr(self, "vad") and self.vad is not None:
            self.vad.reset()

    def _queue_user_text(self, text: str) -> None:
        if not text or not text.strip():
            return
        cleaned = text.strip()
        self.state.add_transcript("User", cleaned)

        # Handle local /goal slash commands immediately in HUD without waiting for model turn
        if cleaned.lower().startswith("/goal"):
            try:
                from src.agents.sessions.tools.goal_tools import handle_goal_command

                reply = handle_goal_command(cleaned)
                self.state.add_transcript("JARVIS", reply)
                self.state.set_agent_state("LISTENING")
                return
            except Exception as e:
                self.state.add_transcript("JARVIS", f"⚠️ Goal command error: {e}")
                self.state.set_agent_state("LISTENING")
                return

        self.state.set_agent_state("THINKING")

        # Drain buffered mic audio so text command takes immediate precedence
        while not self.audio_out_queue.empty():
            try:
                self.audio_out_queue.get_nowait()
            except Exception:
                break

        def _push_text():
            try:
                if self.text_in_queue.full():
                    try:
                        self.text_in_queue.get_nowait()
                    except Exception:
                        pass
                self.text_in_queue.put_nowait(cleaned)
            except Exception:
                pass

        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(_push_text)
        else:
            _push_text()

    def _restore_prior_chat_history(self, session_id: str = "desktop:hud", limit: int = 30) -> None:
        """Restore recent conversation turns from persistent SQLite transcripts into HUD and console."""
        try:
            entries = self._transcript_store.get_recent_entries(session_id, limit=limit)
            if not entries:
                return
            restored = 0
            for entry in entries:
                et = entry.get("entry_type", "")
                data = entry.get("data", {})
                txt = str(data.get("text", "")).strip()
                if not txt:
                    continue
                created_ts = entry.get("created_at", time.time())
                ts = time.strftime("%H:%M:%S", time.localtime(created_ts))
                if et in ("user_turn", "user_speech"):
                    self.state.transcripts.append((ts, "User", txt))
                    restored += 1
                elif et in ("assistant_speech", "model_turn"):
                    self.state.transcripts.append((ts, "JARVIS", txt))
                    restored += 1
            if restored > 0:
                console.print(
                    f"[dim green]● [PERSISTENT CONTEXT] Restored {restored} dialogue turns from SQLite session store ({self._transcript_store.db_path})[/dim green]"
                )
                if self.ui and hasattr(self.ui, "write_log"):
                    try:
                        self.ui.write_log(
                            f"SYS: Restored {restored} dialogue turns from session archive."
                        )
                    except Exception:
                        pass
        except Exception as e:
            logger.debug("Could not restore conversation history: %s", e)

    def _get_pending_task_from_store(self, session_id: str = "desktop:hud") -> str | None:
        """Inspect recent transcript store entries to determine if an unfinished user command exists."""
        try:
            entries = self._transcript_store.get_recent_entries(session_id, limit=8)
            if not entries:
                return None
            # Check latest task_state if recorded
            for entry in reversed(entries):
                et = entry.get("entry_type", "")
                data = entry.get("data", {})
                if et == "task_state":
                    if data.get("status") == "in_progress":
                        return str(data.get("task", "")).strip() or None
                    elif data.get("status") == "completed":
                        return None
            # If no explicit task_state, inspect the last turn
            last_entry = entries[-1]
            last_et = last_entry.get("entry_type", "")
            last_data = last_entry.get("data", {})
            last_text = str(last_data.get("text", "")).strip()
            # If last turn was user speech, it is unfulfilled
            if last_et in ("user_turn", "user_speech") and len(last_text) > 3:
                return last_text
            # If last turn was assistant speech that promised an action, find the user prompt before it
            if last_et in ("assistant_speech", "model_turn"):
                lower_as = last_text.lower()
                action_keywords = ["khoj", "search", "check", "open", "khol", "gar", "run", "chala"]
                if any(kw in lower_as for kw in action_keywords):
                    for entry in reversed(entries[:-1]):
                        if entry.get("entry_type") in ("user_turn", "user_speech"):
                            u_text = str(entry.get("data", {}).get("text", "")).strip()
                            if len(u_text) > 3:
                                return u_text
            return None
        except Exception:
            return None

    def _build_resume_context(self, session_id: str = "desktop:hud", limit: int = 15) -> str | None:
        """Build context summary from previous SQLite transcript turns for system prompt injection."""
        try:
            entries = self._transcript_store.get_recent_entries(session_id, limit=limit)
            if not entries:
                return None
            lines: list[str] = [
                "## Recent Conversation History (Persisted Across Restarts)\n"
                "The following dialogue turns are from the active persistent session for context and continuity. "
                "Maintain full continuity with this conversation history. If an active task was in progress, seamlessly continue it.\n"
            ]
            for entry in entries:
                et = entry.get("entry_type", "")
                data = entry.get("data", {})
                txt = str(data.get("text", "")).strip()
                if not txt:
                    continue
                if et in ("user_turn", "user_speech"):
                    lines.append(f"• User: {txt[:350]}")
                elif et in ("assistant_speech", "model_turn"):
                    lines.append(f"• JARVIS: {txt[:350]}")
            active_task = self._active_goal or self._get_pending_task_from_store(session_id)
            if active_task:
                lines.append(
                    f"\n## Active In-Flight Task (CRITICAL RESUMPTION)\n"
                    f"User goal in progress: \"{active_task}\". "
                    f"Seamlessly resume and fulfill this task now without asking the user to repeat the command.\n"
                )
            if len(lines) <= 1:
                return None
            return "\n".join(lines) + "\n"
        except Exception as e:
            logger.debug("Failed building resume context: %s", e)
            return None

    def _is_status_inquiry(self, text: str) -> bool:
        """Check if user speech is a progress or status check on the active task."""
        t = text.lower()
        return any(
            kw in t
            for kw in (
                "gariyo", "k vo", "k bho", "k gardai", "ke gardai", "garidiyau",
                "bhyayo", "sakiyo", "what are you doing", "did you do", "status",
                "k bhayo", "ke bhayo", "garchhau", "garyo"
            )
        )

    def _detect_ghost_action_promise(self, speech_text: str, active_goal: str) -> bool:
        """Detect if JARVIS verbally promised an action or claimed progress without calling a tool."""
        st = speech_text.lower()
        ag = active_goal.lower()

        # Action promise indicators in Nepali (Latin/Devanagari) or English
        action_promise_keywords = (
            "khoj", "khol", "her", "wishleshan", "analys", "search", "check",
            "open", "run", "start", "gardai", "garchhu", "finding", "looking",
            "banaudai", "banaun", "inspect", "chalau", "dekhau", "padh", "read",
            "खोज्", "खोल्", "हेर्", "विश्लेषण", "गर्दै", "गर्छु"
        )
        has_promise = any(kw in st for kw in action_promise_keywords)

        # Actionable goal keywords in user command
        goal_action_keywords = (
            "drive", "folder", "file", "jaau", "go", "open", "khol", "search",
            "khoj", "check", "her", "read", "padh", "click", "type", "banau",
            "create", "run", "chalau", "delete", "metau", "stonic", "dir", "ls",
            "chatgpt", "youtube", "browser", "desktop", "application"
        )
        is_actionable_goal = any(kw in ag for kw in goal_action_keywords)

        return has_promise or is_actionable_goal

    async def _nudge_tool_execution(self, session: Any, goal: str, promise_text: str) -> None:
        """JARVIS Action-Enforcement Nudge: Forces model to execute tools if it made empty verbal promises."""
        try:
            await asyncio.sleep(0.25)
            if self.stop_event.is_set():
                return

            if hasattr(self, "_arm_stall"):
                self._arm_stall()
            self._assistant_generating = True
            self._turn_complete_received = False
            if hasattr(self, "_turn_done_event"):
                self._turn_done_event.clear()
            if hasattr(self, "state") and self.state and hasattr(self.state, "set_agent_state"):
                self.state.set_agent_state("THINKING")

            nudge_prompt = (
                f"[SYSTEM ACTION-ENFORCEMENT (JARVIS INVARIANT)]: You just verbally promised: '{promise_text[:120]}' "
                f"in response to '{goal[:200]}', but you called NO tools! "
                f"DO NOT CHAT, DO NOT APOLOGIZE, AND DO NOT MAKE ANOTHER VERBAL PROMISE. "
                f"You MUST call the required tool right now in this turn (e.g. ls(path='...'), exec(command='...'), "
                f"browser(action='...'), computer(action='...'), sessions_spawn(task='...')) to actually execute this task on the host PC."
            )
            logger.info("Sending JARVIS execution nudge to session: %s", nudge_prompt[:80])

            async with self._ws_send_lock:
                await session.send_client_content(
                    turns=types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=nudge_prompt)],
                    ),
                    turn_complete=True,
                )
        except Exception as exc:
            logger.warning("Failed to send JARVIS execution nudge: %s", exc)
            if hasattr(self, "state") and self.state and hasattr(self.state, "set_agent_state"):
                self.state.set_agent_state("LISTENING")
            self._assistant_generating = False
            self._turn_complete_received = True
            if hasattr(self, "_turn_done_event"):
                self._turn_done_event.set()

    def _tail_active(self) -> bool:
        return time.monotonic() < self._tail_until

    def _build_live_config(self) -> types.LiveConnectConfig:
        clean_tools = [
            {
                "name": str(td.get("name", "")),
                "description": (
                    " ".join(str(x) for x in td["description"])
                    if isinstance(td.get("description"), (list, tuple))
                    else str(td.get("description", "") or "")
                ),
                "parameters": td.get("parameters", {"type": "object", "properties": {}}),
            }
            for td in self.tool_declarations
            if td.get("name")
        ]
        vad_silence_ms = int(os.environ.get("JARVIS_VAD_SILENCE_MS", "320"))
        vad_prefix_ms = int(os.environ.get("JARVIS_VAD_PREFIX_MS", "80"))
        ric = types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(
                start_of_speech_sensitivity=types.StartSensitivity.START_SENSITIVITY_HIGH,
                end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_HIGH,
                silence_duration_ms=vad_silence_ms,
                prefix_padding_ms=vad_prefix_ms,
            )
        )
        # Regenerate system prompt so current local time and date are always fresh
        try:
            active_prompt = build_jarvis_system_prompt(BASE_DIR, self.plugin_result.skills)
        except Exception:
            active_prompt = self.system_prompt

        resume_ctx = self._build_resume_context()
        if resume_ctx:
            active_prompt = f"{active_prompt}\n\n{resume_ctx}"

        return types.LiveConnectConfig(
            response_modalities=[types.Modality.AUDIO],
            output_audio_transcription=types.AudioTranscriptionConfig(),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            system_instruction=active_prompt,
            tools=[{"function_declarations": clean_tools}],
            realtime_input_config=ric,
            session_resumption=(
                types.SessionResumptionConfig(handle=self.session_resumption_handle)
                if self.session_resumption_handle
                else None
            ),
            context_window_compression=types.ContextWindowCompressionConfig(
                sliding_window=types.SlidingWindow()
            ),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=os.environ.get("JARVIS_VOICE_NAME", "Puck").strip() or "Puck"
                    )
                )
            ),
        )

    def _play_earcon_chime(self) -> None:
        """Plays non-blocking 140ms earcon chime to notify user a tool has engaged when not speaking."""
        try:
            # Do not hijack or collide with the active speaker audio stream if assistant is speaking
            if self.is_speaking or not self.audio_in_queue.empty():
                return
            if TOOL_CHIME_BYTES:
                chime_samples = np.frombuffer(TOOL_CHIME_BYTES, dtype=np.int16)
                sd.play(chime_samples, samplerate=24000, blocking=False)
        except Exception:
            pass

    @staticmethod
    def _sanitize_tool_payload(result_str: str, max_chars: int = 8000) -> str:
        """Sanitize and bound tool response payloads for Gemini Live WebSocket frames.

        Prevents RFC 6455 1007 'invalid frame payload data' caused by oversized text,
        binary/base64 blobs, or runaway command output.
        """
        cleaned = unwrap(result_str)
        if "image_base64" in cleaned or "data:image/" in cleaned:
            cleaned = re.sub(
                r'("image_base64"\s*:\s*)"[^"]+"', r'\1"[omitted for live transport]"', cleaned
            )
            cleaned = re.sub(
                r"data:image\/[a-zA-Z]+;base64,[A-Za-z0-9+/=]+", "[image data omitted]", cleaned
            )

        if len(cleaned) > max_chars:
            cleaned = f"{cleaned[:max_chars]}... [truncated {len(cleaned) - max_chars} chars for live voice transport]"
        return cleaned

    async def _handle_tool_call(self, session: Any, tool_call: Any) -> None:
        """Execute tool calls concurrently without blocking the receive loop and synchronize response delivery."""
        self._tool_call_in_flight = True
        self._pending_tool_response = True
        self._assistant_generating = True
        self._turn_complete_received = False
        self._turn_done_event.clear()
        self.state.set_agent_state("THINKING")

        # Drain buffered mic audio so room noise is not queued during tool execution
        while not self.audio_out_queue.empty():
            try:
                self.audio_out_queue.get_nowait()
            except Exception:
                break

        try:
            fcs = getattr(tool_call, "function_calls", [])
            fn_responses = []
            for fc in fcs:
                try:
                    fr = await asyncio.wait_for(self._execute_tool_call(fc), timeout=25.0)
                except asyncio.TimeoutError:
                    fc_name = getattr(fc, "name", "tool")
                    logger.warning("Tool '%s' timed out after 25.0s", fc_name)
                    fr = types.FunctionResponse(
                        id=getattr(fc, "id", None),
                        name=fc_name,
                        response={"error": f"Tool '{fc_name}' timed out after 25.0s."},
                    )
                fn_responses.append(fr)

            # CRITICAL SYNCHRONIZATION POINT:
            # Send tool response to session and hold audio lock until server emits turn_complete.
            async with self._ws_send_lock:
                await session.send_tool_response(function_responses=fn_responses)
            self._tool_response_pending_turn = True
            self._assistant_generating = True
        except Exception as e:
            logger.error("Error executing background tool call: %s", e)
        finally:
            self._tool_call_in_flight = False
            # If no tool response was delivered (or error occurred), clear pending flag
            if not getattr(self, "_tool_response_pending_turn", False):
                self._pending_tool_response = False
                if not self.is_speaking and self.audio_in_queue.empty():
                    self._turn_done_event.set()
                    if self.state.agent_state == "THINKING":
                        self.state.set_agent_state("LISTENING")

    def _record_tool_transcript(self, name: str, args: dict[str, Any], result: str) -> None:
        """Persist one tool execution for session continuity."""
        store = getattr(self, "_transcript_store", None)
        if store is None:
            return
        try:
            store.append_entry(
                "desktop:hud",
                "tool_execution",
                {"tool": name, "args": args, "result": result[:500]},
            )
        except Exception:
            pass

    async def _execute_tool_call(self, fc: Any) -> types.FunctionResponse:
        name = getattr(fc, "name", "")
        call_id = getattr(fc, "id", None)
        raw_args = dict(getattr(fc, "args", {}) or {})

        self.state.add_tool_event(name, f"Executing with args: {raw_args}")
        self._play_earcon_chime()

        # Control tools live in the shared surface.
        if name in ("shutdown_jarvis", "standby_jarvis", "save_memory", "recall_memory"):
            invocation = await self.tool_surface.invoke(name, dict(raw_args), call_id or "call")
            res_text = self._sanitize_tool_payload(invocation.result_text)
            self._record_tool_transcript(name, raw_args, res_text)
            return types.FunctionResponse(
                id=call_id,
                name=name,
                response={"result": res_text} if invocation.ok else {"error": res_text},
            )

        # 5. Execute through JARVIS tool pipeline
        try:
            # JARVIS 5-Stage Capability Ladder Tool & Argument Aliasing
            canonical_name = name.lower().strip()
            effective_raw_args = dict(raw_args)

            if canonical_name == "sleep_jarvis":
                canonical_name = "standby_jarvis"
            elif canonical_name in ("memory_search", "search_memory"):
                canonical_name = "recall_memory"

            # Stage 2: Universal Host Execution Aliases
            if canonical_name in (
                "powershell",
                "pwsh",
                "bash",
                "cmd",
                "terminal",
                "run_command",
                "shell",
                "command_line",
            ):
                canonical_name = "exec"
                if "cmd" in effective_raw_args and "command" not in effective_raw_args:
                    effective_raw_args["command"] = effective_raw_args["cmd"]
                elif "script" in effective_raw_args and "command" not in effective_raw_args:
                    effective_raw_args["command"] = effective_raw_args["script"]
                elif (
                    "action" in effective_raw_args
                    and "command" not in effective_raw_args
                    and str(effective_raw_args["action"]).lower() not in ("exec", "run")
                ):
                    effective_raw_args["command"] = effective_raw_args["action"]

            elif canonical_name in ("python", "py", "eval", "code_interpreter", "run_python"):
                canonical_name = "exec"
                py_code = (
                    effective_raw_args.get("code")
                    or effective_raw_args.get("script")
                    or effective_raw_args.get("command")
                    or ""
                )
                if py_code and "command" not in effective_raw_args:
                    escaped_code = py_code.replace('"', '\\"')
                    effective_raw_args["command"] = f'python -c "{escaped_code}"'

            # Stage 3: Desktop UI Automation Aliases
            elif canonical_name in (
                "pause",
                "pause_music",
                "pause_song",
                "pause_video",
                "stop_music",
                "stop_song",
                "resume_music",
                "resume_song",
                "resume_video",
                "play_pause",
                "toggle_play",
            ):
                canonical_name = "browser"
                effective_raw_args["action"] = "pause"

            elif canonical_name in ("play_song", "play_music", "youtube_play"):
                canonical_name = "browser"
                effective_raw_args["action"] = "youtube_play"

            elif canonical_name in ("open_app", "launch_app", "start_app", "open", "launch"):
                target = (
                    effective_raw_args.get("app_name")
                    or effective_raw_args.get("application")
                    or effective_raw_args.get("target")
                    or effective_raw_args.get("name")
                    or effective_raw_args.get("path")
                )
                t_str = str(target or "").lower().strip()
                web_targets = {
                    "youtube": "https://www.youtube.com",
                    "yt": "https://www.youtube.com",
                    "google": "https://www.google.com",
                    "chatgpt": "https://chatgpt.com",
                    "openai": "https://chatgpt.com",
                    "facebook": "https://www.facebook.com",
                    "fb": "https://www.facebook.com",
                    "twitter": "https://x.com",
                    "x": "https://x.com",
                    "instagram": "https://www.instagram.com",
                    "reddit": "https://www.reddit.com",
                    "linkedin": "https://www.linkedin.com",
                    "github": "https://github.com",
                    "gmail": "https://mail.google.com",
                }
                if (
                    t_str in web_targets
                    or t_str in ("browser", "chrome", "edge")
                    or t_str.startswith(("http://", "https://", "www."))
                    or any(
                        t_str.endswith(ext)
                        for ext in (".com", ".org", ".net", ".io", ".ai", ".app")
                    )
                ):
                    canonical_name = "browser"
                    effective_raw_args["action"] = "open"
                    effective_raw_args["url"] = web_targets.get(t_str) or (
                        f"https://{target}"
                        if not str(target).startswith(("http://", "https://"))
                        else str(target)
                    )
                    if t_str in web_targets:
                        effective_raw_args["label"] = t_str
                else:
                    canonical_name = "desktop"
                    effective_raw_args.setdefault("action", "open_app")
                    if target:
                        effective_raw_args["app_name"] = str(target)
                        effective_raw_args["target"] = str(target)

            elif canonical_name in ("focus_app", "bring_to_front"):
                canonical_name = "desktop"
                effective_raw_args.setdefault("action", "focus_app")
                target = (
                    effective_raw_args.get("target")
                    or effective_raw_args.get("app_name")
                    or effective_raw_args.get("application")
                    or effective_raw_args.get("name")
                )
                if target:
                    effective_raw_args["target"] = str(target)
                    effective_raw_args["app_name"] = str(target)

            elif canonical_name in ("list_apps", "running_apps"):
                canonical_name = "desktop"
                effective_raw_args["action"] = "list_apps"

            elif canonical_name in (
                "click",
                "mouse_click",
                "left_click",
                "right_click",
                "double_click",
            ):
                canonical_name = "desktop"
                effective_raw_args.setdefault("action", canonical_name)

            elif canonical_name in ("type", "type_text", "send_keys", "press", "hotkey"):
                canonical_name = "desktop"
                effective_raw_args.setdefault("action", canonical_name)

            elif canonical_name in ("screenshot", "take_screenshot"):
                canonical_name = "desktop"
                effective_raw_args.setdefault("action", "screenshot")

            # Stage 1: File & Code Editing Aliases
            elif canonical_name in ("read_file", "cat", "view_file"):
                canonical_name = "read"

            elif canonical_name in ("write_file", "create_file", "save_file"):
                canonical_name = "write"

            elif canonical_name in ("edit_file",):
                canonical_name = "edit"

            elif canonical_name in (
                "read_pdf",
                "pdf_read",
                "extract_pdf",
                "view_pdf",
                "create_pdf",
                "pdf_create",
                "convert_pdf",
                "convert_to_pdf",
                "txt_to_pdf",
                "html_to_pdf",
                "make_pdf",
                "generate_pdf",
            ):
                canonical_name = "pdf"

            # Stage 4: Web Research & Information Gathering Aliases
            elif canonical_name in ("search_web", "google_search", "ddg_search", "internet_search"):
                canonical_name = "web_search"

            elif canonical_name in (
                "fetch_web",
                "fetch_url",
                "web_get",
                "scrape_url",
                "fetch_page",
            ):
                canonical_name = "web_fetch"

            # Stage 5: Dynamic Tool & Skill Workshop Aliases
            elif canonical_name in ("create_skill", "save_skill", "author_skill", "workshop"):
                canonical_name = "skill_workshop"

            elif canonical_name in ("subagent", "subagents_spawn"):
                canonical_name = "sessions_spawn"

            args = prepare_tool_arguments(canonical_name, effective_raw_args)
            if canonical_name == "pdf":
                target_path = (
                    effective_raw_args.get("file_path")
                    or effective_raw_args.get("pdf")
                    or effective_raw_args.get("path")
                    or effective_raw_args.get("file")
                    or effective_raw_args.get("input_path")
                    or effective_raw_args.get("source")
                )
                if target_path:
                    args["file_path"] = str(target_path)
                    args["pdf"] = str(target_path)
                out_path = (
                    effective_raw_args.get("output_path")
                    or effective_raw_args.get("destination")
                    or effective_raw_args.get("target")
                )
                if out_path:
                    args["output_path"] = str(out_path)
                if any(k in name.lower() for k in ("create", "convert", "make", "generate")):
                    args["action"] = "convert"
            # Ensure canonical agentId (default 'main')
            if "agentId" not in args or not args["agentId"] or args["agentId"] == "default":
                args["agentId"] = "main"

            # Single dispatch: the same inventory that produced the declarations.
            # ``desktop``/``desktop_action``/``auto_control`` are legacy aliases
            # of the declared ``computer`` tool.
            dispatch_name = (
                "computer"
                if canonical_name in ("desktop", "desktop_action", "auto_control")
                else canonical_name
            )
            verdict = detect_tool_call_loop(
                self._tool_loop_state,
                dispatch_name,
                args,
                config=_VOICE_LOOP_CONFIG,
                scope={"runId": "voice"},
            )
            if verdict.get("level") == "critical":
                logger.warning(
                    "Voice tool loop blocked (%s) for %s",
                    verdict.get("detector"),
                    dispatch_name,
                )
                res_text = self._sanitize_tool_payload(
                    str(verdict.get("message") or "Tool loop detected.")
                )
                self._record_tool_transcript(name, raw_args, res_text)
                return types.FunctionResponse(
                    id=call_id,
                    name=name,
                    response={"result": res_text},
                )
            record_tool_call(
                self._tool_loop_state,
                dispatch_name,
                args,
                call_id,
                config=_VOICE_LOOP_CONFIG,
                scope={"runId": "voice"},
            )

            invocation = await self.tool_surface.invoke(dispatch_name, args, call_id or "call")
            record_tool_call_outcome(
                self._tool_loop_state,
                {
                    "toolName": dispatch_name,
                    "toolParams": args,
                    "result": invocation.output if invocation.ok else invocation.error,
                    "toolCallId": call_id,
                    "config": _VOICE_LOOP_CONFIG,
                    "runId": "voice",
                },
            )
            if not invocation.ok:
                clean_error = self._sanitize_tool_payload(invocation.result_text)
                self._record_tool_transcript(name, raw_args, clean_error)
                return types.FunctionResponse(
                    id=call_id,
                    name=name,
                    response={"error": clean_error},
                )

            clean_res = self._sanitize_tool_payload(invocation.result_text)
            if verdict.get("stuck"):
                clean_res = f"{verdict.get('message')}\n\n{clean_res}"
            self._record_tool_transcript(name, raw_args, clean_res)
            return types.FunctionResponse(
                id=call_id,
                name=name,
                response={"result": clean_res},
            )
        except Exception as exc:
            logger.error("Tool '%s' execution failed: %s", name, exc)
            return types.FunctionResponse(
                id=call_id,
                name=name,
                response={"error": self._sanitize_tool_payload(f"Tool '{name}' failed: {exc}")},
            )

    async def _mic_stream_task(self, loop: asyncio.AbstractEventLoop) -> None:
        """Capture microphone input and send via audio_out_queue with zero onset latency, VAD gating & Digital Silence Gate."""
        barge_in_thresh = int(os.environ.get("JARVIS_BARGE_IN_THRESHOLD", "120"))
        speech_thresh = int(os.environ.get("JARVIS_SPEECH_THRESHOLD", "250"))
        silence_bytes = b"\x00" * (CHUNK_SIZE * 2)  # 1024 samples * 2 bytes = 2048 bytes
        was_speaking = False
        post_speech_silence_frames = 0

        def _enqueue_chunk(chunk: bytes) -> None:
            def _push():
                try:
                    if self.audio_out_queue.full():
                        try:
                            self.audio_out_queue.get_nowait()
                        except Exception:
                            pass
                    self.audio_out_queue.put_nowait(chunk)
                except Exception:
                    pass

            loop.call_soon_threadsafe(_push)

        def callback(indata, frames, time_info, status):
            nonlocal was_speaking, post_speech_silence_frames
            try:
                if status:
                    pass
                pcm_bytes = indata.tobytes()
                level = pcm_level(indata)

                # Update HUD waveform
                if self.ui and hasattr(self.ui, "set_audio_level"):
                    try:
                        self.ui.set_audio_level(level)
                    except Exception:
                        pass

                # While JARVIS is actively speaking, filter speaker feedback via EchoGuard
                if self.is_speaking:
                    # If a tool call is in flight or assistant is announcing, do not barge-in
                    if self._tool_call_in_flight or getattr(self, "_pending_tool_response", False):
                        return

                    # Check if this input is genuine user speech distinct from speaker echo
                    is_user = self.echo_guard.is_user_speech(indata, SEND_SAMPLE_RATE, level)
                    peak = (
                        int(np.max(np.abs(indata)))
                        if hasattr(indata, "size") and indata.size > 0
                        else 0
                    )
                    # Genuine barge-in requires: verified by spectral EchoGuard + high voice energy (peak > 2800 and level > 0.15)
                    effective_thresh = max(barge_in_thresh, 2800)
                    if is_user and (peak >= effective_thresh and level > 0.15):
                        # Conversational barge-in: user spoke loudly over assistant!
                        self.set_speaking(False)
                        self._assistant_generating = False
                        self._turn_complete_received = True
                        self._turn_done_event.set()
                        # Flush assistant audio queue immediately
                        while not self.audio_in_queue.empty():
                            try:
                                self.audio_in_queue.get_nowait()
                            except Exception:
                                break
                        self.state.set_agent_state("HEARING")
                    else:
                        return

                # Echo tail cancellation: filter speaker feedback right after playback
                if self._tail_active():
                    if not self.echo_guard.is_user_speech(indata, SEND_SAMPLE_RATE, level):
                        return
                    self._tail_until = 0.0
                elif self.echo_guard._hist:
                    self.echo_guard.reset()

                # Suppress audio capture during tool execution or while in THINKING state
                if (
                    self._tool_call_in_flight
                    or getattr(self, "_pending_tool_response", False)
                    or self.state.agent_state == "THINKING"
                ):
                    return

                # Acoustic Energy VAD & High-pass filter
                filtered_pcm = self.vad.filter_audio(pcm_bytes)
                samples = np.frombuffer(filtered_pcm, dtype=np.int16)
                peak = int(np.max(np.abs(samples))) if samples.size > 0 else 0

                is_speech = self.vad.is_speech(filtered_pcm) or (peak >= speech_thresh)

                if is_speech:
                    post_speech_silence_frames = 0
                    if not was_speaking:
                        was_speaking = True
                        # Speech onset: flush pre-roll buffer so initial phonemes are never clipped
                        flushed_pre_roll = self.vad.flush_pre_roll()
                        for pr_chunk in flushed_pre_roll:
                            _enqueue_chunk(pr_chunk)
                    _enqueue_chunk(pcm_bytes)
                else:
                    if was_speaking and post_speech_silence_frames < 4:
                        # Digital Silence Gate: emit ~250ms silence so Gemini Live server VAD
                        # immediately detects end-of-turn with near-instant conversational turn-taking
                        post_speech_silence_frames += 1
                        _enqueue_chunk(silence_bytes)
                    else:
                        was_speaking = False
                        # Pure idle room audio/music: store in pre-roll buffer only, DO NOT flood WebSocket!
                        self.vad.pre_roll_buffer.append(pcm_bytes)

            except Exception as cb_exc:
                logger.debug("Mic callback exception suppressed: %s", cb_exc)

        while not self.stop_event.is_set():
            try:
                with sd.InputStream(
                    samplerate=SEND_SAMPLE_RATE,
                    channels=1,
                    dtype="int16",
                    blocksize=CHUNK_SIZE,
                    callback=callback,
                ):
                    while not self.stop_event.is_set():
                        await asyncio.sleep(0.1)
            except Exception as e:
                if not self.stop_event.is_set():
                    logger.error("Microphone input stream failed: %s. Reconnecting mic...", e)
                    await asyncio.sleep(1.0)

    async def _spk_stream_task(self) -> None:
        """Play incoming audio from audio_in_queue to speakers with chunk batching."""
        try:
            with sd.RawOutputStream(
                samplerate=RECEIVE_SAMPLE_RATE,
                channels=1,
                dtype="int16",
                blocksize=CHUNK_SIZE,
            ) as stream:
                while not self.stop_event.is_set():
                    try:
                        # Playback streams concurrently with background tool execution.
                        # Audio in audio_in_queue is never purged on tool calls so assistant speech is never clipped.

                        # Playback must never wait for turn_complete: native-audio streams
                        # PCM while the model is still generating. Buffering here until the
                        # turn ends made the HUD show SPEAKING seconds before any sound.
                        chunk = await asyncio.wait_for(self.audio_in_queue.get(), timeout=0.04)
                    except asyncio.TimeoutError:
                        now = time.monotonic()
                        idle_time = now - self._last_spk_time

                        # Release the speaking lock only after a real inter-packet gap so the
                        # HUD does not flicker SPEAKING <-> THINKING between streamed chunks.
                        if self.is_speaking and self.audio_in_queue.empty():
                            if idle_time > 0.25:
                                self.set_speaking(False)

                        # If speaker is NOT speaking and queue is empty, ensure state transitions safely
                        if not self.is_speaking and self.audio_in_queue.empty():
                            self._turn_done_event.set()
                            if (
                                getattr(self, "_turn_complete_received", False)
                                and not getattr(self, "_tool_call_in_flight", False)
                                and not getattr(self, "_pending_tool_response", False)
                                and not getattr(self, "_tool_response_pending_turn", False)
                            ):
                                self._assistant_generating = False
                                if self.state.agent_state not in (
                                    "LISTENING",
                                    "STANDBY",
                                ):
                                    self.state.set_agent_state("LISTENING")
                            elif (
                                not getattr(self, "_turn_complete_received", True)
                                and not getattr(self, "_tool_call_in_flight", False)
                                and not getattr(self, "_pending_tool_response", False)
                                and not getattr(self, "_tool_response_pending_turn", False)
                            ):
                                if self.state.agent_state not in ("THINKING", "STANDBY"):
                                    self.state.set_agent_state("THINKING")
                                # Fallback only after 2.5s of absolute silence if server dropped turn_complete
                                if idle_time > 2.5:
                                    self._turn_complete_received = True
                                    self._assistant_generating = False
                                    self.state.set_agent_state("LISTENING")
                        continue

                    if chunk:
                        # Adaptive jitter buffer: when starting a new speech burst,
                        # pre-buffer at least ~100ms (4800 bytes) or up to 0.10s to absorb network jitter
                        # and prevent PortAudio buffer starvation clicks / stuttering
                        batch = bytearray(chunk)
                        if not self.is_speaking:
                            prebuffer_deadline = time.monotonic() + 0.10
                            while len(batch) < 4800 and time.monotonic() < prebuffer_deadline:
                                try:
                                    extra = await asyncio.wait_for(self.audio_in_queue.get(), timeout=0.03)
                                    batch.extend(extra)
                                except asyncio.TimeoutError:
                                    break
                            self.set_speaking(True)

                        # While playing, gather any immediately available chunks up to ~4800 bytes (~100ms)
                        while len(batch) < 4800:
                            try:
                                batch.extend(self.audio_in_queue.get_nowait())
                            except asyncio.QueueEmpty:
                                break

                        pcm_batch = np.frombuffer(batch, dtype=np.int16)
                        level = pcm_level(pcm_batch)
                        self.echo_guard.note_output(bytes(batch), RECEIVE_SAMPLE_RATE, level)

                        # Update HUD waveform
                        if self.ui and hasattr(self.ui, "set_audio_level"):
                            try:
                                self.ui.set_audio_level(level)
                            except Exception:
                                pass

                        await asyncio.to_thread(stream.write, bytes(batch))
                        self._last_spk_time = time.monotonic()
                        self._tail_until = time.monotonic() + 0.08
        except Exception as e:
            logger.error("Speaker output stream failed: %s", e)

    async def _send_audio_task(self, session: Any) -> None:
        """Send captured PCM chunks to Gemini Live WebSocket with dynamic batch draining and zero-latency freshness."""
        while not self.stop_event.is_set():
            try:
                chunk = await asyncio.wait_for(self.audio_out_queue.get(), timeout=0.05)
            except asyncio.TimeoutError:
                continue

            # ZERO AUDIO LEAK DURING TOOL EXECUTION, GENERATING, OR THINKING STATES:
            # Under the Gemini Live protocol, streaming realtime audio while the assistant is generating,
            # executing a tool, or waiting for a tool response causes the Gemini backend to reject the frame
            # with RFC 1007 error: "The audio content type (CONTENT_TYPE_AUDIO) is not supported for this model configuration."
            # Therefore, audio chunks must be STRICTLY SUPPRESSED until turn_complete is received from the server.
            if (
                self._tool_call_in_flight
                or getattr(self, "_pending_tool_response", False)
                or getattr(self, "_tool_response_pending_turn", False)
                or getattr(self, "_assistant_generating", False)
                or not getattr(self, "_turn_complete_received", True)
                or not self._turn_done_event.is_set()
                or self.is_speaking
                or not self.audio_in_queue.empty()
                or self.state.agent_state in ("THINKING", "SPEAKING")
            ):
                while not self.audio_out_queue.empty():
                    try:
                        self.audio_out_queue.get_nowait()
                    except Exception:
                        break
                continue

            # Realtime freshness gate: if backlog built up (>8 chunks = ~512ms), drop stale frames to keep audio live (<80ms)
            q_depth = self.audio_out_queue.qsize()
            if q_depth > 8:
                while self.audio_out_queue.qsize() > 2:
                    try:
                        self.audio_out_queue.get_nowait()
                    except Exception:
                        break

            # Fast chunk dispatch (1-2 chunks = ~64-128ms) for near-instant conversational turn-taking
            batch = [chunk]
            while not self.audio_out_queue.empty() and len(batch) < 2:
                try:
                    batch.append(self.audio_out_queue.get_nowait())
                except Exception:
                    break

            combined = b"".join(batch)

            # While assistant is generating or speaking, drop low-energy mic noise (<0.04)
            # to prevent acoustic feedback / spurious mic packets from confusing server VAD
            if self._assistant_generating or self.is_speaking:
                try:
                    level = pcm_level(np.frombuffer(combined, dtype=np.int16))
                except Exception:
                    level = 0.0
                if level < 0.04:
                    continue

            try:
                async with self._ws_send_lock:
                    if (
                        self._tool_call_in_flight
                        or getattr(self, "_pending_tool_response", False)
                        or getattr(self, "_tool_response_pending_turn", False)
                        or getattr(self, "_assistant_generating", False)
                        or self.is_speaking
                        or not self.audio_in_queue.empty()
                        or self.state.agent_state in ("THINKING", "SPEAKING")
                    ):
                        continue
                    # CRITICAL: Always use media= with audio/pcm;rate=16000 for Gemini Live native-audio models.
                    # Never use audio=, which generates CONTENT_TYPE_AUDIO causing WebSocket 1007 rejection!
                    await session.send_realtime_input(
                        media=types.Blob(data=combined, mime_type="audio/pcm;rate=16000")
                    )
            except Exception as e:
                if not self.stop_event.is_set():
                    err_msg = str(e)
                    if "1007" in err_msg or "content_type_audio" in err_msg.lower():
                        logger.warning(
                            "1007 audio rejected during model state transition: %s. Recovering stream...",
                            err_msg,
                        )
                        self.session_resumption_handle = None
                        while not self.audio_out_queue.empty():
                            try:
                                self.audio_out_queue.get_nowait()
                            except Exception:
                                break
                        await asyncio.sleep(0.2)
                        self._assistant_generating = False
                        self._turn_complete_received = True
                        self._turn_done_event.set()
                        self.state.set_agent_state("LISTENING")
                    else:
                        logger.warning("Send audio error (WebSocket closed): %s", e)
                        raise

    async def _send_text_task(self, session: Any) -> None:
        """Send queued text commands from console or HUD."""
        while not self.stop_event.is_set():
            try:
                text = await asyncio.wait_for(self.text_in_queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                continue

            if text:
                try:
                    # Wait briefly if audio from a prior turn or tool call is active (cap at 2.0s max)
                    wait_count = 0
                    while (
                        (self.is_speaking or self._tool_call_in_flight)
                        and not self.stop_event.is_set()
                        and wait_count < 40
                    ):
                        await asyncio.sleep(0.05)
                        wait_count += 1

                    self._last_user_prompt = text
                    is_inquiry = self._is_status_inquiry(text)
                    if not (self._task_in_progress and self._active_goal and is_inquiry):
                        self._active_goal = text
                        self._primary_active_goal = text
                        self._ghost_nudge_count = 0
                    self._task_in_progress = True
                    self._turn_tool_executed = False

                    self._turn_done_event.clear()
                    self._assistant_generating = True
                    self._turn_complete_received = False
                    self._arm_stall()
                    async with self._ws_send_lock:
                        try:
                            # Stream text directly via realtime input to preserve pure full-duplex live session
                            await session.send_realtime_input(text=text)
                        except (TypeError, AttributeError):
                            # Fallback only if SDK version doesn't support text keyword in send_realtime_input
                            await session.send_client_content(
                                turns=types.Content(
                                    role="user",
                                    parts=[types.Part.from_text(text=text)],
                                ),
                                turn_complete=True,
                            )
                except Exception as e:
                    if not self.stop_event.is_set():
                        logger.warning("Send text command error (WebSocket closed): %s", e)
                        raise

    async def _receive_task(self, session: Any) -> None:
        """Receive audio, transcripts, and tool calls from Gemini Live WebSocket."""
        user_buf: list[str] = []
        jarvis_buf: list[str] = []
        last_speech_jarvis: str = ""
        streaming_started = False

        while not self.stop_event.is_set():
            try:
                async for response in session.receive():
                    if self.stop_event.is_set():
                        break

                    # Server return path confirmed alive: clear stall deadline
                    self._clear_stall()
                    self._last_server_activity = time.monotonic()

                    # 1. Capture session resumption handle
                    sru = getattr(response, "session_resumption_update", None)
                    if sru is not None and getattr(sru, "resumable", False):
                        self.session_resumption_handle = getattr(sru, "new_handle", None)

                    # 2. Audio playback stream
                    audio_bytes = b""
                    sc = getattr(response, "server_content", None)
                    if sc and sc.model_turn and sc.model_turn.parts:
                        pcm_chunks = []
                        for part in sc.model_turn.parts:
                            if getattr(part, "inline_data", None) and getattr(
                                part.inline_data, "data", None
                            ):
                                pcm_chunks.append(part.inline_data.data)
                        if pcm_chunks:
                            audio_bytes = b"".join(pcm_chunks)
                    elif hasattr(response, "data") and response.data:
                        audio_bytes = response.data

                    if audio_bytes:
                        self._assistant_generating = True
                        self._turn_complete_received = False
                        self._turn_done_event.clear()
                        self.set_speaking(True)
                        # Slice into 50ms chunks for smooth queuing and responsive barge-in
                        for i in range(0, len(audio_bytes), AUDIO_SLICE):
                            slice_chunk = audio_bytes[i : i + AUDIO_SLICE]
                            try:
                                self.audio_in_queue.put_nowait(slice_chunk)
                            except asyncio.QueueFull:
                                await self.audio_in_queue.put(slice_chunk)

                    # 3. Transcripts & Server Content
                    if response.server_content:
                        sc = response.server_content

                        # When the model produces ANY content (thinking, transcription, parts),
                        # the turn is actively in-flight on the server.
                        # Clear _turn_done_event and mark assistant active to prevent sending audio chunks!
                        if sc.model_turn or sc.output_transcription or sc.grounding_metadata:
                            self._turn_done_event.clear()
                            self._assistant_generating = True
                            self._turn_complete_received = False

                        # Handle barge-in interruption from user
                        if getattr(sc, "interrupted", False):
                            self.set_speaking(False)
                            self._tool_call_in_flight = False
                            self._assistant_generating = False
                            self._turn_complete_received = True
                            while not self.audio_in_queue.empty():
                                try:
                                    self.audio_in_queue.get_nowait()
                                except Exception:
                                    break
                            self._turn_done_event.set()
                            self.state.set_agent_state("LISTENING")

                        if sc.output_transcription and sc.output_transcription.text:
                            txt = sc.output_transcription.text
                            clean_txt = re.sub(r"<ctrl\d+>", "", txt)
                            if clean_txt:
                                jarvis_buf.append(clean_txt)

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = sc.input_transcription.text
                            if txt:
                                user_buf.append(txt)
                                self._arm_stall()
                                self.state.set_agent_state("HEARING")
                                ui = getattr(self, "ui", None)
                                if ui and hasattr(ui, "set_live_transcript"):
                                    try:
                                        raw_user = "".join(user_buf)
                                        disp_live = raw_user if getattr(self, "prefer_devanagari", False) else romanize_nepali_text(raw_user)
                                        ui.set_live_transcript(f"You: {disp_live}")
                                    except Exception:
                                        pass

                        if sc.turn_complete:
                            if streaming_started:
                                console.print()  # Flush newline
                                streaming_started = False

                            if user_buf:
                                full_user = "".join(user_buf).strip()
                                full_user = re.sub(r"[ \t]+", " ", full_user)
                                if full_user:
                                    # Detect explicit script preference request
                                    user_lower = full_user.lower()
                                    if "नेपालीमै लेख" in user_lower or "देवनागरीमा लेख" in user_lower or "devanagari" in user_lower:
                                        self.prefer_devanagari = True
                                    elif "इङ्लिस लेटर" in user_lower or "रोमन" in user_lower or "roman" in user_lower or "english letter" in user_lower:
                                        self.prefer_devanagari = False

                                    display_user = full_user if getattr(self, "prefer_devanagari", False) else romanize_nepali_text(full_user)
                                    self.state.add_transcript("User", display_user)
                                    self._last_user_prompt = full_user
                                    if len(full_user.strip()) > 3:
                                        is_inquiry = self._is_status_inquiry(full_user)
                                        if not (self._task_in_progress and self._active_goal and is_inquiry):
                                            self._active_goal = full_user.strip()
                                            self._primary_active_goal = full_user.strip()
                                            self._ghost_nudge_count = 0
                                        self._task_in_progress = True
                                        self._turn_tool_executed = False
                                        if getattr(self.state, "transcript_store", None):
                                            try:
                                                self.state.transcript_store.append_entry(
                                                    "desktop:hud",
                                                    "task_state",
                                                    {"task": self._active_goal, "status": "in_progress"},
                                                )
                                            except Exception:
                                                pass
                                user_buf = []

                            if jarvis_buf:
                                full_jarvis = "".join(jarvis_buf).strip()
                                full_jarvis = re.sub(r"<ctrl\d+>", "", full_jarvis).strip()
                                if full_jarvis:
                                    ts = time.strftime("%H:%M:%S")
                                    display_jarvis = full_jarvis if getattr(self, "prefer_devanagari", False) else romanize_nepali_text(full_jarvis)
                                    last_speech_jarvis = display_jarvis
                                    console.print(
                                        f"[{ts}] [bold cyan]JARVIS:[/bold cyan] {display_jarvis}"
                                    )
                                    ui = getattr(self, "ui", None)
                                    if ui and hasattr(ui, "set_live_transcript"):
                                        try:
                                            ui.set_live_transcript(f"JARVIS: {display_jarvis}")
                                        except Exception:
                                            pass
                                    if response.tool_call is None:
                                        self.state.transcripts.append((ts, "JARVIS", display_jarvis))
                                        if getattr(self.state, "transcript_store", None):
                                            try:
                                                self.state.transcript_store.append_entry(
                                                    "desktop:hud",
                                                    "assistant_speech",
                                                    {"text": display_jarvis},
                                                )
                                            except Exception:
                                                pass
                                jarvis_buf = []
                            elif streaming_started:
                                console.print()
                            streaming_started = False

                            # JARVIS Invariant: Check for Ghost-Chatter (Action promised verbally, but 0 tools called)
                            effective_goal = self._primary_active_goal or self._active_goal or ""
                            is_ghost = (
                                response.tool_call is None
                                and self._task_in_progress
                                and bool(effective_goal)
                                and not self._turn_tool_executed
                                and not self._tool_call_in_flight
                                and not getattr(self, "_tool_response_pending_turn", False)
                                and self._detect_ghost_action_promise(last_speech_jarvis, effective_goal)
                                and self._ghost_nudge_count < 2
                            )

                            if is_ghost:
                                self._ghost_nudge_count += 1
                                logger.warning(
                                    "[GHOST-CHATTER DETECTED] JARVIS promised action without calling a tool. Firing JARVIS nudge #%d for goal: %s",
                                    self._ghost_nudge_count,
                                    effective_goal[:80],
                                )
                                self._turn_complete_received = False
                                self._assistant_generating = True
                                self._turn_done_event.clear()
                                self.state.set_agent_state("THINKING")
                                asyncio.create_task(
                                    self._nudge_tool_execution(
                                        session,
                                        effective_goal,
                                        last_speech_jarvis,
                                    )
                                )
                            else:
                                if response.tool_call is None:
                                    self._turn_complete_received = True
                                    self._assistant_generating = False
                                    # If tool execution just concluded and model delivered its final answer, mark task completed
                                    if getattr(self, "_tool_response_pending_turn", False):
                                        if self._active_goal and getattr(self.state, "transcript_store", None):
                                            try:
                                                self.state.transcript_store.append_entry(
                                                    "desktop:hud",
                                                    "task_state",
                                                    {"task": self._active_goal, "status": "completed"},
                                                )
                                            except Exception:
                                                pass
                                        self._active_goal = None
                                        self._primary_active_goal = None
                                        self._task_in_progress = False
                                        self._ghost_nudge_count = 0
                                    self._tool_response_pending_turn = False
                                    self._pending_tool_response = False
                                if (
                                    response.tool_call is None
                                    and not self._tool_call_in_flight
                                    and not getattr(self, "_tool_response_pending_turn", False)
                                ):
                                    if not self.is_speaking and self.audio_in_queue.empty():
                                        self._turn_done_event.set()
                                        self.state.set_agent_state("LISTENING")
                            self._tail_until = time.monotonic() + 0.08

                    # 4. Tool calls (executed concurrently in background task without blocking receive loop)
                    if response.tool_call:
                        self._turn_tool_executed = True
                        self._ghost_nudge_count = 0
                        if jarvis_buf:
                            full_ack = "".join(jarvis_buf).strip()
                            full_ack = re.sub(r"<ctrl\d+>", "", full_ack).strip()
                            if full_ack:
                                ts = time.strftime("%H:%M:%S")
                                display_ack = full_ack if getattr(self, "prefer_devanagari", False) else romanize_nepali_text(full_ack)
                                console.print(
                                    f"[{ts}] [bold cyan]JARVIS:[/bold cyan] {display_ack}"
                                )
                                ui = getattr(self, "ui", None)
                                if ui and hasattr(ui, "set_live_transcript"):
                                    try:
                                        ui.set_live_transcript(f"JARVIS: {display_ack}")
                                    except Exception:
                                        pass
                            jarvis_buf.clear()
                        if streaming_started:
                            console.print()
                            streaming_started = False
                        self._tool_call_in_flight = True
                        self._pending_tool_response = True
                        self._task_in_progress = True
                        self._assistant_generating = True
                        self._turn_complete_received = False
                        self._turn_done_event.clear()
                        self.state.set_agent_state("THINKING")
                        asyncio.create_task(self._handle_tool_call(session, response.tool_call))

                    # 5. Tool call cancellations
                    if getattr(response, "tool_call_cancellation", None):
                        self._tool_call_in_flight = False
                        self._pending_tool_response = False
                        self._assistant_generating = False
                        self._turn_complete_received = True
                        self._turn_done_event.set()
                        self.state.set_agent_state("LISTENING")

            except asyncio.CancelledError:
                break
            except Exception as e:
                if not self.stop_event.is_set():
                    if streaming_started:
                        console.print()
                        streaming_started = False
                    err_msg = f"{type(e).__name__}: {e}" if str(e) else repr(e)
                    logger.warning("Receive loop terminated: %s", err_msg)
                    if "1007" in err_msg or "content_type_audio" in err_msg.lower():
                        self.session_resumption_handle = None
                        self._turn_complete_received = True
                        self._assistant_generating = False
                    raise

    async def _keepalive_ping_task(self, session: Any) -> None:
        """Passive connection health monitor; avoids blocking ping/pong waiters that cause 1011 keepalive timeouts."""
        try:
            while not self.stop_event.is_set():
                await asyncio.sleep(10.0)
                # Keep server activity fresh during active tool execution to prevent spurious timeouts
                if (
                    self._tool_call_in_flight
                    or getattr(self, "_pending_tool_response", False)
                    or getattr(self, "_tool_response_pending_turn", False)
                ):
                    self._last_server_activity = time.monotonic()
        except asyncio.CancelledError:
            pass

    async def _watch_stall_task(self) -> None:
        """Monitors for stalled turns and unfreezes state gracefully before resorting to reconnect."""
        while not self.stop_event.is_set():
            await asyncio.sleep(1.0)
            now = time.monotonic()
            deadline = self._rx_deadline

            # In normal idle listening mode (no in-flight turn, not speaking or generating),
            # or during active tool execution, keep server activity timestamp fresh
            # so normal room silence or legitimate tool operations (e.g. browser navigation, video playback)
            # do not trigger an infinite reconnect loop or premature 45s stall disconnect
            if self._tool_call_in_flight or (
                deadline is None
                and not self._assistant_generating
                and self.state.agent_state in ("LISTENING", "STANDBY")
            ):
                self._last_server_activity = now

            # If agent_state remained in HEARING after user speech ended and no turn generation started within 2.5s,
            # gracefully return to LISTENING so the state is never stuck and mic audio continues streaming freely
            if (
                self.state.agent_state == "HEARING"
                and deadline is None
                and not self._assistant_generating
                and not self.is_speaking
                and (now - getattr(self, "_last_server_activity", now)) > 2.5
            ):
                self.state.set_agent_state("LISTENING")
                self._turn_done_event.set()
                self._last_server_activity = now

            if deadline is not None and now > deadline:
                self._clear_stall()
                # Unfreeze state immediately so mic audio and conversation resumes without disconnect
                self._turn_complete_received = True
                self._assistant_generating = False
                self._tool_call_in_flight = False
                self._turn_done_event.set()
                self.state.set_agent_state("LISTENING")
                logger.debug(
                    "Turn response deadline passed; gracefully resetting state to LISTENING."
                )

            # Only reconnect if server socket has had zero return packets for >45 seconds during an active turn or hung state.
            # Normal idle waiting in LISTENING mode is completely healthy and MUST NEVER trigger stall disconnects!
            is_hung_turn = (
                deadline is not None
                or self._assistant_generating
                or self.state.agent_state == "THINKING"
            )
            idle_sec = now - getattr(self, "_last_server_activity", now)
            if is_hung_turn and idle_sec > 45.0:
                self._clear_stall()
                self.session_resumption_handle = None
                logger.warning(
                    "Live session stall timeout: no server packets for %.1fs during active turn. Reconnecting fresh...",
                    idle_sec,
                )
                if self.ui and hasattr(self.ui, "write_log"):
                    try:
                        self.ui.write_log(
                            "SYS: Model unresponsive during turn — auto-reconnecting fresh session."
                        )
                    except Exception:
                        pass
                raise TimeoutError(
                    f"Live session stall timeout: no server packets for {idle_sec:.1f}s."
                )

    async def _watch_subagents_task(self, session: Any) -> None:
        """Monitor subagent runs and announce completions if not already handled by callback."""
        from src.agents.subagents.registry import SubagentRegistry
        from src.agents.subagents.types import SubagentStatus

        registry = SubagentRegistry.get_instance()

        while not self.stop_event.is_set():
            try:
                await asyncio.sleep(2.0)
                all_runs = registry.list_runs()
                for rec in all_runs:
                    if rec.run_id in self._announced_subagent_runs:
                        continue
                    if rec.status in (
                        SubagentStatus.COMPLETED,
                        SubagentStatus.FAILED,
                        SubagentStatus.TIMED_OUT,
                    ):
                        self._announced_subagent_runs.add(rec.run_id)
                        if rec.metadata.get("expects_completion_message", True):
                            task_label = rec.label or rec.task or "background task"
                            status_val = rec.status.value
                            res_text = (rec.result_text or rec.error or "")[:300].strip()
                            prompt = (
                                f"[SYSTEM NOTIFICATION: Background subagent finished. Task: '{task_label}'. "
                                f"Status: {status_val}. Findings: {res_text}. "
                                f"Briefly inform Sir in 1 warm, natural sentence in Nepali that this background task has finished and summarize what was found.]"
                            )
                            self.post_system_notification(prompt)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug("Subagent watcher loop error: %s", e)

    async def run(self) -> None:
        """Main resilient execution loop with 8-key circular auto-rotation."""
        self.loop = asyncio.get_running_loop()

        # Start microphone and speaker threads
        mic_task = asyncio.create_task(self._mic_stream_task(self.loop))
        spk_task = asyncio.create_task(self._spk_stream_task())

        while not self.stop_event.is_set():
            active_key = self.rotator.get_current_key()
            current_idx = self.rotator.current_index
            self._drain_queues()

            try:
                self.state.set_agent_state("CONNECTING")
                client = genai.Client(
                    api_key=active_key,
                    http_options={"api_version": "v1beta"},
                )
                config = self._build_live_config()

                resuming = bool(self.session_resumption_handle)
                status_msg = "Resuming" if resuming else "Connecting"
                console.print(
                    f"[dim cyan]{status_msg} Gemini Live using Key #{current_idx + 1} "
                    f"({self.rotator.masked_key()})...[/dim cyan]"
                )

                async with client.aio.live.connect(
                    model=self.active_model,
                    config=config,
                ) as session:
                    self.active_session = session
                    self.state.set_agent_state("LISTENING")
                    self.state.status = "CONNECTED"
                    self._last_server_activity = time.monotonic()
                    self._clear_stall()
                    self._consecutive_fails = 0
                    self._network_fails = 0

                    if resuming:
                        console.print(
                            f"[bold green]✔ Live Engine Restored on Key #{current_idx + 1} ({self.rotator.masked_key()})[/bold green]"
                        )
                        if self.ui and hasattr(self.ui, "write_log"):
                            self.ui.write_log(
                                f"SYS: Live Session Restored on Key #{current_idx + 1} (context preserved)."
                            )
                    else:
                        console.print(
                            f"[bold green]✔ Live Engine Connected on Key #{current_idx + 1} ({self.rotator.masked_key()})[/bold green]"
                        )
                        if self.ui and hasattr(self.ui, "write_log"):
                            self.ui.write_log(
                                f"SYS: Live Engine Active on Key #{current_idx + 1} ({self.rotator.masked_key()})."
                            )

                    # Immediate greeting turn only on initial process boot
                    if not self._boot_greeted:
                        self._boot_greeted = True
                        try:
                            self._turn_done_event.clear()
                            self._assistant_generating = True
                            self._turn_complete_received = False
                            async with self._ws_send_lock:
                                await session.send_client_content(
                                    turns=types.Content(
                                        role="user",
                                        parts=[
                                            types.Part.from_text(
                                                text="Say a brief greeting in 1 short sentence: 'Online and ready, Sir. All systems fully functional.'"
                                            )
                                        ],
                                    ),
                                    turn_complete=True,
                                )
                        except Exception as e:
                            logger.debug("Initial greeting error: %s", e)
                    else:
                        # RECONNECTION AUTO-RESUMPTION:
                        # If a user task or command was interrupted, immediately prompt model to seamlessly complete it!
                        pending_task = self._active_goal or self._get_pending_task_from_store()
                        if pending_task:
                            logger.info("Auto-resuming interrupted task on reconnect: %s", pending_task)
                            resume_prompt = (
                                f"[SYSTEM NOTIFICATION: Connection was momentarily interrupted and has now reconnected. "
                                f"You were actively executing the user's task: '{pending_task}'. "
                                f"Seamlessly resume and complete this task now for the user. Do not ask the user to repeat the command or start from scratch.]"
                            )
                            try:
                                self._turn_done_event.clear()
                                self._assistant_generating = True
                                async with self._ws_send_lock:
                                    await session.send_client_content(
                                        turns=types.Content(
                                            role="user",
                                            parts=[types.Part.from_text(text=resume_prompt)],
                                        ),
                                        turn_complete=True,
                                    )
                            except Exception as resume_err:
                                logger.warning("Failed sending task continuation on reconnect: %s", resume_err)

                    # Gather send, receive, keepalive, stall watchdog & subagents completion tasks
                    send_audio = asyncio.create_task(self._send_audio_task(session))
                    send_text = asyncio.create_task(self._send_text_task(session))
                    receive_task = asyncio.create_task(self._receive_task(session))
                    watch_stall = asyncio.create_task(self._watch_stall_task())
                    keepalive_task = asyncio.create_task(self._keepalive_ping_task(session))
                    watch_subagents = asyncio.create_task(self._watch_subagents_task(session))

                    done, pending = await asyncio.wait(
                        [send_audio, send_text, receive_task, watch_stall, keepalive_task, watch_subagents],
                        return_when=asyncio.FIRST_COMPLETED,
                    )

                    for p in pending:
                        p.cancel()
                    if pending:
                        await asyncio.gather(*pending, return_exceptions=True)

                    for d in done:
                        exc = d.exception()
                        if exc:
                            raise exc

            except asyncio.CancelledError:
                break
            except Exception as e:
                console.print()  # Ensure newline after any in-flight streaming
                err_str = f"{type(e).__name__}: {e}" if str(e) else repr(e)
                logger.warning("Session disconnected: %s", err_str)

                # Always invalidate session resumption handle on any disconnect to guarantee a clean reconnect
                if self.session_resumption_handle:
                    console.print(
                        "[dim yellow]Resumption handle discarded; reconnecting with fresh clean session and SQLite context.[/dim yellow]"
                    )
                self.session_resumption_handle = None
                self._turn_complete_received = True
                self._assistant_generating = False
                self._consecutive_fails = 0

                # 1. Classify error type
                is_network_error = isinstance(
                    e,
                    (
                        socket.gaierror,
                        socket.herror,
                        TimeoutError,
                        ConnectionRefusedError,
                        ConnectionResetError,
                    ),
                ) or any(
                    x in err_str.lower()
                    for x in [
                        "getaddrinfo",
                        "11001",
                        "10051",
                        "10054",
                        "10060",
                        "10061",
                        "10065",
                        "network is unreachable",
                        "connection reset",
                        "connection refused",
                        "dns",
                        "timed out",
                        "timeout",
                        "name or service not known",
                        "temporary failure in name resolution",
                    ]
                )

                is_rate_limit = any(
                    x in err_str.lower()
                    for x in [
                        "429",
                        "resource_exhausted",
                        "quota",
                        "rate limit",
                        "too many requests",
                    ]
                )
                is_auth_error = any(
                    x in err_str.lower()
                    for x in [
                        "401",
                        "403",
                        "unauthenticated",
                        "permission_denied",
                        "api_key_invalid",
                        "api key not valid",
                    ]
                )

                # Model fallback check ONLY on genuine 404 NOT_FOUND
                is_model_not_found = (
                    ("404" in err_str and "model" in err_str.lower())
                    or "model not found" in err_str.lower()
                    or "model does not exist" in err_str.lower()
                )
                if is_model_not_found:
                    remaining_fallbacks = [
                        model for model in FALLBACK_MODELS if model != self.active_model
                    ]
                    if remaining_fallbacks:
                        console.print(
                            f"[bold yellow]⚠️ Live model {self.active_model} not found. Switching to fallback {remaining_fallbacks[0]}...[/bold yellow]"
                        )
                        self.active_model = remaining_fallbacks[0]
                    else:
                        self.active_model = DEFAULT_MODEL
                elif self.active_model not in (DEFAULT_MODEL, *FALLBACK_MODELS):
                    # Auto-heal back to canonical native audio model
                    self.active_model = DEFAULT_MODEL

                if is_rate_limit or is_auth_error:
                    # Definitive API key issue: rotate to next key
                    self.session_resumption_handle = None
                    self._consecutive_fails = 0
                    self._network_fails = 0
                    _, new_idx = self.rotator.rotate(f"Rate-limit/Auth: {err_str[:40]}")
                    console.print(
                        f"[bold yellow]⚡ Rotating to Gemini Key #{new_idx + 1} ({self.rotator.masked_key(new_idx)})...[/bold yellow]"
                    )
                    if self.ui and hasattr(self.ui, "write_log"):
                        self.ui.write_log(
                            f"SYS: ⚡ Rotating to Gemini Key #{new_idx + 1} ({self.rotator.masked_key(new_idx)})."
                        )
                    await asyncio.sleep(0.5)
                    continue

                elif is_network_error:
                    # Network or DNS glitch: NEVER rotate API keys on network failure!
                    self._network_fails += 1
                    # Jittered exponential backoff: 1.0s, 1.8s, 3.2s, 5.8s, capped at 8.0s
                    delay = min(1.0 * (1.8 ** min(self._network_fails - 1, 4)), 8.0)
                    console.print(
                        f"[dim yellow]⚡ Network/DNS unreachable ({type(e).__name__}). Retrying on Key #{current_idx + 1} in {delay:.1f}s...[/dim yellow]"
                    )
                    if self.ui and hasattr(self.ui, "write_log"):
                        self.ui.write_log(
                            f"SYS: Network unreachable ({type(e).__name__}). Retrying in {delay:.1f}s."
                        )
                    await asyncio.sleep(delay)
                    continue

                else:
                    self._consecutive_fails += 1
                    if self._consecutive_fails >= 3:
                        self.session_resumption_handle = None
                        self._consecutive_fails = 0
                        _, new_idx = self.rotator.rotate(f"Repeated errors: {err_str[:40]}")
                        console.print(
                            f"[bold yellow]⚡ Rotating to Gemini Key #{new_idx + 1} ({self.rotator.masked_key(new_idx)})...[/bold yellow]"
                        )
                        if self.ui and hasattr(self.ui, "write_log"):
                            self.ui.write_log(
                                f"SYS: ⚡ Rotating to Gemini Key #{new_idx + 1} ({self.rotator.masked_key(new_idx)})."
                            )
                        await asyncio.sleep(0.5)
                        continue
                    else:
                        console.print(
                            f"[dim yellow]⚡ Auto-reconnecting Live session on Key #{current_idx + 1}...[/dim yellow]"
                        )
                        await asyncio.sleep(1.0)
                        continue

        # Cleanup
        mic_task.cancel()
        spk_task.cancel()


def _start_console_stdin_listener(engine: NativeGeminiLiveEngine) -> None:
    """Read user console text input in background thread."""

    def _reader():
        while not engine.stop_event.is_set():
            try:
                line = sys.stdin.readline()
                if not line:
                    break
                stripped = line.strip()
                if stripped:
                    engine._queue_user_text(stripped)
            except Exception:
                break

    t = threading.Thread(target=_reader, daemon=True, name="jarvis-stdin-reader")
    t.start()


def _terminate_conflicting_voice_processes() -> None:
    """Terminates rogue background voice assistants (e.g. Pipecat) to prevent dual voices / audio interference."""
    try:
        import subprocess

        if sys.platform == "win32":
            cmd = (
                'powershell -NoProfile -Command "'
                "Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | "
                "Where-Object { ($_.CommandLine -like '*pipecat*' -or $_.CommandLine -like '*bot.py*') -and $_.ProcessId -ne $PID } | "
                'Select-Object -ExpandProperty ProcessId"'
            )
            out = subprocess.check_output(
                cmd, shell=True, text=True, timeout=3, stderr=subprocess.DEVNULL
            ).strip()
            if out:
                for pid_str in out.splitlines():
                    pid_str = pid_str.strip()
                    if pid_str and pid_str.isdigit():
                        subprocess.run(
                            f'powershell -NoProfile -Command "Stop-Process -Id {pid_str} -Force -ErrorAction SilentlyContinue"',
                            shell=True,
                            timeout=3,
                            capture_output=True,
                        )
                logger.info(
                    "Terminated conflicting background audio process (PIDs: %s)",
                    out.replace("\n", ", "),
                )
    except Exception:
        pass


async def run_unified_voice_engine(ui: Any = None) -> None:
    """Starts JSON-RPC gateway, loads plugins, and runs the Native Gemini Live Engine."""
    # 0. Clean any rogue conflicting background assistants and engage resilient DNS
    _terminate_conflicting_voice_processes()
    enable_resilient_dns()

    # 1. Initialize SQLite state DBs
    try:
        await initialize_canonical_databases()
    except Exception as e:
        logger.debug("Database bootstrap: %s", e)

    # 2. Start JARVIS Gateway on port 7433 if not already running
    try:

        async def _safe_start_gateway():
            try:
                await start_jarvis_gateway_server(host="127.0.0.1", port=7433)
            except Exception:
                pass

        asyncio.create_task(_safe_start_gateway())
    except Exception as e:
        logger.debug("Gateway server init: %s", e)

    state = JarvisTerminalHUDState(ui=ui)
    print_terminal_banner(has_gui=(ui is not None))

    engine = NativeGeminiLiveEngine(state=state, ui=ui)
    _start_console_stdin_listener(engine)

    # 3. Auto-start configured external channels (Telegram, WhatsApp, etc.)
    try:
        from src.channels.channel_manager import ChannelManager

        cm = ChannelManager.get_instance()
        cm.auto_start_enabled_channels(live_host=engine)
    except Exception as exc:
        logger.debug("Channel auto-start error: %s", exc)

    await engine.run()


def main() -> int:
    """CLI Entry point for single-command `uv run jarvis`."""
    import os

    has_gui = False
    ui = None
    force_headless = "--headless" in sys.argv or os.environ.get("JARVIS_HEADLESS") == "1"

    if not force_headless:
        try:
            from jarvis_desktop.ui import JarvisUI

            ui = JarvisUI()
            has_gui = True
        except Exception as e:
            logger.info("Running in headless terminal mode (PyQt6 not loaded: %s)", e)

    def _voice_thread_runner():
        asyncio.run(run_unified_voice_engine(ui=ui))

    t = threading.Thread(target=_voice_thread_runner, daemon=True, name="jarvis-voice-thread")
    t.start()

    if has_gui and ui is not None and hasattr(ui, "root"):
        try:
            ui.root.mainloop()
        except KeyboardInterrupt:
            pass
        return 0
    else:
        try:
            t.join()
        except KeyboardInterrupt:
            print("\n[JARVIS] Shutting down...")
        return 0


if __name__ == "__main__":
    sys.exit(main())
