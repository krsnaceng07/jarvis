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

import logging
import asyncio
import os
import threading
import json
import sys
import traceback
from pathlib import Path
from typing import Any

import sounddevice as sd
from google import genai
from google.genai import types
from .ui import JarvisUI
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
from jarvis_sdk import DEFAULT_AGENT_ID, normalize_agent_id
from jarvis_sdk.loader import load_all_plugins_from_workspace

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


TOOL_DECLARATIONS = [
    # Phase 2: legacy action tools (browser_control, file_controller,
    # file_processor, screen_process, computer_settings, desktop_control,
    # code_helper, dev_agent, computer_control, game_updater, flight_finder)
    # have been removed (the actions/ directory is gone). The 3 tools
    # below are JARVIS-internal and stay. The 6 + 5 plugin tools
    # (weather, reminder, open_app, web_search, send_message, youtube_video,
    # memory_search, memory_get, cron_schedule, cron_list, cron_cancel)
    # are loaded dynamically by the SDK loader.
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
TOOL_DECLARATIONS.extend(_PLUGIN_TOOL_DECLS)

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
        # Plugin dispatch is built once at import time by the SDK loader.
        # The UI handle is passed to each plugin lazily inside
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
        self._submit_text_turn(text)

    def _submit_text_turn(self, text: str) -> None:
        """Submit a text turn using the Live API's typed content contract."""
        future = asyncio.run_coroutine_threadsafe(self._send_text_turn(text), self._loop)

        def report_failure(done) -> None:
            error = done.exception()
            if error is not None:
                print(f"[JARVIS] ❌ Text send: {type(error).__name__}: {error}")

        future.add_done_callback(report_failure)

    async def _send_text_turn(self, text: str) -> None:
        async with self._ws_send_lock:
            await self.session.send_client_content(
                turns=types.Content(
                    role="user",
                    parts=[types.Part(text=text)],
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
            self._is_speaking = value
        if value:
            self.ui.set_state("SPEAKING")
        elif not self.ui.muted:
            self.ui.set_state("LISTENING")

    def speak(self, text: str):
        if not self._loop or not self.session:
            return
        self._submit_text_turn(text)

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
        from jarvis_hooks import fire_sync

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
            if name == "shutdown_jarvis":
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
                mime = msg.get("mime_type") or f"audio/pcm;rate={SEND_SAMPLE_RATE}"
                if mime == "audio/pcm":
                    mime = f"audio/pcm;rate={SEND_SAMPLE_RATE}"
                async with self._ws_send_lock:
                    await self.session.send_realtime_input(
                        audio=types.Blob(
                            data=msg.get("data"),
                            mime_type=mime,
                        )
                    )
            else:
                async with self._ws_send_lock:
                    await self.session.send_realtime_input(audio=msg)

    async def _listen_audio(self):
        print("[JARVIS] 🎤 Mic started")
        loop = asyncio.get_event_loop()

        def callback(indata, frames, time_info, status):
            with self._speaking_lock:
                jarvis_speaking = self._is_speaking
            if not jarvis_speaking and not self.ui.muted:
                data = indata.tobytes()
                frame = {"data": data, "mime_type": f"audio/pcm;rate={SEND_SAMPLE_RATE}"}
                try:
                    loop.call_soon_threadsafe(self.out_queue.put_nowait, frame)
                except Exception:
                    # Queue full during network back-pressure — silently drop frame.
                    pass

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
                            from jarvis_hooks import fire_sync

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
                        async with self._ws_send_lock:
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
                    self._ws_send_lock = asyncio.Lock()

                    print(f"[JARVIS] ✅ Connected ({active_model}).")
                    self.ui.set_state("LISTENING")
                    self.ui.write_log(f"SYS: JARVIS online ({active_model}).")

                    tg.create_task(self._send_realtime())
                    tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())

            except Exception as e:
                print(f"[JARVIS] ⚠️ {e}")
                if isinstance(e, BaseExceptionGroup):
                    for child in e.exceptions:
                        print(f"[JARVIS]   task failure: {type(child).__name__}: {child}")
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
