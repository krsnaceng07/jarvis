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

# Phase 2: the legacy `actions/` directory has been removed entirely.
# All 17 actions have been migrated to `extensions/<id>/` (Phases 1A-1C)
# or are dropped (Phase 2 deprecates them — see OPENCLAW_MIGRATION_PLAN.md
# §24 for the new OpenClaw feature roadmap).
#
# Current tool surface (6 tools, all loaded dynamically):
#   - extensions/tool_weather/   (PR 1A)
#   - extensions/tool_reminder/  (PR 1B)
#   - extensions/tool_open_app/       (PR 1C)
#   - extensions/tool_web_search/     (PR 1C)
#   - extensions/tool_send_message/   (PR 1C)
#   - extensions/tool_youtube_video/  (PR 1C)
#
# Plus Phase 2 plugins:
#   - extensions/memory_core/   (memory_search, memory_get)
#   - extensions/cron/          (cron_schedule, cron_list, cron_cancel)


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
        "list[dict]",  # tool_decls
        "dict[str, tuple]",  # plugin_dispatch
        "list",  # commands (list[CommandDecl])
        "list[tuple]",  # cli_handlers
        "list",  # skills (list[SkillDecl])
        "list",  # hooks (list[HookRegistration])
        "list",  # cron_jobs (list[CronDecl])
        "list[dict]",  # doctor_contracts (raw dicts)
    ]
):
    """Discover + register every extension's plugin entry via the SDK.

    Mirrors OpenClaw's `src/plugins/loader.ts` pattern. For each
    ``extensions/<id>/openclaw.plugin.json``:
      1. dynamically import ``extensions.<id>``
      2. call ``entry.register(api)`` with a real ``PluginApi``
      3. collect tools / commands / cli / skills / hooks / cron /
         doctor contracts

    Returns the 8-tuple
    ``(tool_decls, dispatch, commands, cli, skills, hooks, cron, doctor)``.
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
    skills: list = []  # list[SkillDecl]
    hooks: list = []  # list[HookRegistration]
    cron_jobs: list = []  # list[CronDecl]
    doctor_contracts: "list[dict]" = []

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
        skills.extend(api.skills)
        hooks.extend(api.hooks)
        cron_jobs.extend(api.cron_jobs)
        doctor_contracts.extend(api.doctor_contracts)

    return (
        tool_decls,
        plugin_dispatch,
        commands,
        cli_handlers,
        skills,
        hooks,
        cron_jobs,
        doctor_contracts,
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
) = _load_plugins()
TOOL_DECLARATIONS.extend(_PLUGIN_TOOL_DECLS)

# ── Phase 2: wire skills / hooks / cron / doctor into host subsystems ───
# Skills augment the system prompt (one block per skill). Hooks fire
# at agent-loop boundaries (before_agent_start, agent_end, etc.).
# Cron is started in a background thread by the host on first use;
# the doctor runner is exposed for the CLI (jarvis doctor).
from jarvis.hooks import HookBus  # noqa: E402
from jarvis.doctor import DoctorRunner  # noqa: E402

_PLUGIN_HOOK_BUS = HookBus()
_PLUGIN_HOOK_BUS.register_all(_PLUGIN_HOOKS)
_PLUGIN_DOCTOR = DoctorRunner()
_PLUGIN_DOCTOR.add_raws(_PLUGIN_DOCTOR_CONTRACTS)


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
            if name == "agent_task":
                # Phase 2: ``agent_task`` is now owned by the
                # ``agent`` extension (a Phase 2.5 deliverable). For
                # now we keep a stub here so the LLM's tool surface
                # is unchanged; the stub returns a clear "not yet
                # implemented" error.
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
                # a working alternative (e.g. tool_open_app for
                # "open browser").
                result = (
                    f"Tool {name!r} is no longer available in JARVIS. "
                    "It was part of the legacy `actions/` layer that "
                    "was removed in Phase 2. Use an extension tool "
                    "instead (e.g. tool_open_app, tool_web_search, "
                    "tool_send_message, memory_search)."
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
