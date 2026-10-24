"""Test live performance, speech smoothness parameters, and web search reliability."""

import pytest
from src.system.web_search_provider import WebSearchProvider
from jarvis_desktop.vad_engine import EnergyVADEngine
from jarvis_voice_pipeline.terminal_app import DEFAULT_MODEL, FALLBACK_MODELS


def test_vad_hangover_latency_optimized() -> None:
    """Verify VAD hangover is tuned to 3 frames (~192ms) for brisk human-like turn-taking."""
    vad = EnergyVADEngine()
    assert vad.hangover_frames == 3


def test_gemini_live_models_only_native_audio() -> None:
    """Verify DEFAULT_MODEL and FALLBACK_MODELS only contain models supporting Bidi audio streaming."""
    assert "native-audio" in DEFAULT_MODEL
    for m in FALLBACK_MODELS:
        assert "native-audio" in m
        assert "3.1" not in m
        assert "3.8" not in m


def test_web_search_provider_returns_live_results() -> None:
    """Verify WebSearchProvider returns structured results with ok=True for common queries."""
    res = WebSearchProvider.search("water pump motor nepal price", count=3)
    assert res.get("ok") is True
    assert isinstance(res.get("results"), list)
    assert len(res.get("results")) > 0
    first = res["results"][0]
    assert "title" in first and "url" in first and "snippet" in first
    assert len(first["title"]) > 0


def test_web_search_format_prompt() -> None:
    """Verify WebSearchProvider format_results_for_prompt produces valid markdown."""
    sample = {
        "ok": True,
        "results": [
            {
                "title": "DC Motor Water Pump 12V",
                "url": "https://example.com/pump",
                "snippet": "High pressure 12V DC water pump.",
            }
        ],
    }
    prompt_text = WebSearchProvider.format_results_for_prompt(sample)
    assert "DC Motor Water Pump 12V" in prompt_text
    assert "https://example.com/pump" in prompt_text


def test_system_prompt_spoken_acknowledgment_and_naming_contract() -> None:
    """Verify system prompt contains spoken acknowledgment alongside tool execution and ASCII directory naming."""
    from pathlib import Path
    from jarvis_voice_pipeline.pipeline_builder import build_jarvis_system_prompt

    prompt = build_jarvis_system_prompt(Path("e:/jarvis"), [])
    assert "MANDATORY ACTION-FIRST EXECUTION WITH CONCURRENT SPOKEN ACKNOWLEDGMENT" in prompt
    assert "FOLDER & FILE NAMING CONVENTION" in prompt
    assert "English / Latin script for directory and file names" in prompt


@pytest.mark.asyncio
async def test_watch_stall_does_not_disconnect_during_idle_listening() -> None:
    """Verify that idle listening for >45s does not raise TimeoutError."""
    import asyncio
    import time
    from types import SimpleNamespace
    from jarvis_voice_pipeline import terminal_app

    engine = object.__new__(terminal_app.NativeGeminiLiveEngine)
    engine.stop_event = asyncio.Event()
    engine.state = SimpleNamespace(agent_state="LISTENING")
    engine._rx_deadline = None
    engine._assistant_generating = False
    engine._tool_call_in_flight = False
    engine._turn_done_event = asyncio.Event()
    engine._turn_done_event.set()
    # Simulate last server activity being 60 seconds ago in idle LISTENING mode
    engine._last_server_activity = time.monotonic() - 60.0
    engine.session_resumption_handle = "valid_handle"
    engine.ui = None

    task = asyncio.create_task(engine._watch_stall_task())
    await asyncio.sleep(1.2)
    engine.stop_event.set()
    await task

    # Handle must not be invalidated and stall must not have triggered
    assert engine.session_resumption_handle == "valid_handle"


def test_romanize_nepali_transcription() -> None:
    """Verify Devanagari Nepali is romanized into natural English letters while preserving Latin words."""
    from jarvis_voice_pipeline.nepali_romanizer import romanize_nepali_text

    raw1 = "नमस्ते Sir, मद्दतको लागि तयार छु।"
    rom1 = romanize_nepali_text(raw1)
    assert "Namaste Sir" in rom1
    assert "tayaar chhu" in rom1
    # Must not contain Devanagari characters
    assert not any("\u0900" <= c <= "\u097f" for c in rom1)

    raw2 = "माफ गर्नुहोस् Sir. म 'E:' ड्राइभमा 'Stonic' वा 'Stonic AI' फोल्डर खोज्छु।"
    rom2 = romanize_nepali_text(raw2)
    assert "Maaf garnuhos Sir" in rom2
    assert "'E:'" in rom2
    assert "'Stonic'" in rom2
    assert "folder khojchhu" in rom2
    assert not any("\u0900" <= c <= "\u097f" for c in rom2)


@pytest.mark.asyncio
async def test_send_audio_uses_media_chunks_not_audio_arg() -> None:
    """Verify send_realtime_input is called with media= Blob and not audio= Blob (RFC 1007 CONTENT_TYPE_AUDIO fix)."""
    import asyncio
    import threading
    from unittest.mock import AsyncMock
    from types import SimpleNamespace
    from jarvis_voice_pipeline import terminal_app

    engine = object.__new__(terminal_app.NativeGeminiLiveEngine)
    engine.stop_event = asyncio.Event()
    engine.audio_out_queue = asyncio.Queue()
    engine._ws_send_lock = asyncio.Lock()
    engine._speaking_lock = threading.Lock()
    engine._turn_done_event = asyncio.Event()
    engine._turn_done_event.set()
    engine._tool_call_in_flight = False
    engine._pending_tool_response = False
    engine._tool_response_pending_turn = False
    engine._assistant_generating = False
    engine._is_speaking = False
    engine.audio_in_queue = asyncio.Queue()
    engine.state = SimpleNamespace(agent_state="LISTENING")

    mock_session = AsyncMock()
    # Put a 50ms chunk of 16kHz int16 PCM (1600 bytes)
    engine.audio_out_queue.put_nowait(b"\x00" * 1600)

    task = asyncio.create_task(engine._send_audio_task(mock_session))
    await asyncio.sleep(0.1)
    engine.stop_event.set()
    await task

    # Verify send_realtime_input was called with media keyword, NOT audio keyword
    assert mock_session.send_realtime_input.called
    kwargs = mock_session.send_realtime_input.call_args.kwargs
    assert "media" in kwargs, "send_realtime_input must use media= parameter"
    assert "audio" not in kwargs, "send_realtime_input must never use audio= parameter (triggers RFC 1007 error)"
    blob = kwargs["media"]
    assert blob.mime_type == "audio/pcm;rate=16000"


def test_resume_context_preserves_task_and_omits_completion_override(tmp_path) -> None:
    """Verify _build_resume_context injects in-flight tasks and no longer claims all prior tasks completed."""
    from jarvis_voice_pipeline import terminal_app
    from src.agents.task.session_transcript_store import SessionTranscriptStore

    db_path = tmp_path / "test_agent.sqlite"
    store = SessionTranscriptStore(db_path)
    store.append_entry("desktop:hud", "user_speech", {"text": "E drive ma Stonic AI folder khoj"})
    store.append_entry("desktop:hud", "assistant_speech", {"text": "Hunchha sar. Ma E drivema 'Stonic' folder khojchhu"})

    engine = object.__new__(terminal_app.NativeGeminiLiveEngine)
    engine._transcript_store = store
    engine._active_goal = "E drive ma Stonic AI folder khoj"

    ctx = engine._build_resume_context("desktop:hud")
    assert ctx is not None
    # Must NOT claim that all tasks are finished
    assert "All prior tools and tasks have completed. Do not re-execute" not in ctx
    # Must explicitly instruct continuity and note the active task
    assert "Active In-Flight Task (CRITICAL RESUMPTION)" in ctx
    assert "E drive ma Stonic AI folder khoj" in ctx
    assert "Maintain full continuity" in ctx


def test_pending_task_recovery_from_store(tmp_path) -> None:
    """Verify _get_pending_task_from_store extracts incomplete tasks across disconnections."""
    from jarvis_voice_pipeline import terminal_app
    from src.agents.task.session_transcript_store import SessionTranscriptStore

    db_path = tmp_path / "test_agent.sqlite"
    store = SessionTranscriptStore(db_path)
    store.append_entry("desktop:hud", "user_speech", {"text": "ChatGPT kholera UI generate garna prompt deu"})
    store.append_entry("desktop:hud", "assistant_speech", {"text": "Hunchha sar, ma ChatGPT kholdaichhu"})

    engine = object.__new__(terminal_app.NativeGeminiLiveEngine)
    engine._transcript_store = store
    engine._active_goal = None

    pending = engine._get_pending_task_from_store("desktop:hud")
    assert pending is not None
    assert "ChatGPT kholera UI generate garna prompt deu" in pending


def test_clean_gemini_declarations_filters_to_voice_priority_tools() -> None:
    """Verify tool bloat is prevented by filtering declarations to focused voice priority tools."""
    from jarvis_voice_pipeline.pipeline_builder import (
        clean_gemini_declarations,
        VOICE_PRIORITY_TOOLS,
    )

    sample_decls = [
        {"name": "ls", "description": "old ls desc", "parameters": {}},
        {"name": "exec", "description": "old exec desc", "parameters": {}},
        {"name": "computer", "description": "desktop control", "parameters": {}},
        {"name": "honcho_search_messages", "description": "honcho noise", "parameters": {}},
        {"name": "cron_schedule", "description": "cron noise", "parameters": {}},
        {"name": "sessions_spawn", "description": "spawn noise", "parameters": {}},
    ]

    filtered = clean_gemini_declarations(sample_decls, voice_priority_only=True)
    names = {t["name"] for t in filtered}

    # Must contain voice priority tools
    assert "ls" in names
    assert "exec" in names
    assert "computer" in names
    assert "pdf" in names
    assert "sessions_spawn" in names

    # Must NOT contain non-priority background/plugin tools
    assert "honcho_search_messages" not in names
    assert "cron_schedule" not in names

    # Must adhere to Google's recommended tool budget (<= 20 tools)
    assert len(filtered) <= len(VOICE_PRIORITY_TOOLS) + 1


def test_ls_and_exec_voice_descriptions_enhanced() -> None:
    """Verify ls and exec declarations have enhanced, action-prompting descriptions."""
    from jarvis_voice_pipeline.pipeline_builder import clean_gemini_declarations

    sample_decls = [
        {"name": "ls", "description": "generic ls", "parameters": {}},
        {"name": "exec", "description": "generic exec", "parameters": {}},
    ]
    filtered = clean_gemini_declarations(sample_decls, voice_priority_only=True)
    by_name = {t["name"]: t for t in filtered}

    assert "MUST call this whenever user asks to inspect, check, explore, search, or analyze any folder or drive" in by_name["ls"]["description"]
    assert "deep recursive searches" in by_name["exec"]["description"]


def test_status_inquiry_detection() -> None:
    """Verify user follow-up questions are correctly classified as status inquiries."""
    from jarvis_voice_pipeline import terminal_app

    engine = object.__new__(terminal_app.NativeGeminiLiveEngine)

    assert engine._is_status_inquiry("chhau maile bhaneko kura gariyo.") is True
    assert engine._is_status_inquiry("k vo") is True
    assert engine._is_status_inquiry("ke gardai chhau?") is True
    assert engine._is_status_inquiry("sakiyo?") is True
    assert engine._is_status_inquiry("what are you doing?") is True
    assert engine._is_status_inquiry("did you do it?") is True

    # Non-status new commands
    assert engine._is_status_inquiry("E drive ma stonic folder khoj") is False
    assert engine._is_status_inquiry("chrome browser khola") is False


def test_ghost_action_promise_detection() -> None:
    """Verify verbal promises without tool execution are identified as ghost chatter."""
    from jarvis_voice_pipeline import terminal_app

    engine = object.__new__(terminal_app.NativeGeminiLiveEngine)
    goal = "Timi yee drivema jaau. it drivema stonik naamako folder ho. tyo pholdaramaa bhitr bhaeko sabai kura diplee enaalaaij gar"

    # Ghost promises made by model
    assert engine._detect_ghost_action_promise("Hunchha sar, Ma E: drivema 'Stonic' folder khojchhu", goal) is True
    assert engine._detect_ghost_action_promise("Ma 'E:' drivema 'Stonic' folder bhitrako sabai kura gahiro tarikaale wishleshan garchhu", goal) is True
    assert engine._detect_ghost_action_promise("Ma gardai chhu sar. wishleshan garna kehi samay laagchh.", goal) is True

    # Ordinary chat greeting
    assert engine._detect_ghost_action_promise("Namaste Sir, ma tapailai kasto maddat garna sakchhu?", "") is False


@pytest.mark.asyncio
async def test_ghost_nudge_tool_execution_dispatches_client_content() -> None:
    """Verify _nudge_tool_execution sends strict JARVIS Action-Enforcement Nudge into session."""
    import asyncio
    from unittest.mock import AsyncMock
    from jarvis_voice_pipeline import terminal_app

    engine = object.__new__(terminal_app.NativeGeminiLiveEngine)
    engine.stop_event = asyncio.Event()
    engine._ws_send_lock = asyncio.Lock()

    mock_session = AsyncMock()
    goal = "E drive ma Stonic AI folder khoj"
    promise = "Hunchha sar, ma khojchhu"

    await engine._nudge_tool_execution(mock_session, goal, promise)

    assert mock_session.send_client_content.called
    kwargs = mock_session.send_client_content.call_args.kwargs
    assert kwargs.get("turn_complete") is True
    turns = kwargs.get("turns")
    assert turns.role == "user"
    nudge_text = turns.parts[0].text
    assert "JARVIS INVARIANT" in nudge_text
    assert "You MUST call the required tool right now in this turn" in nudge_text
    assert "ls(path=" in nudge_text


def test_voice_priority_tools_contains_subagents_and_automations() -> None:
    """Verify sessions_spawn, sessions_yield, subagents, and automations are voice-enabled."""
    from jarvis_voice_pipeline.pipeline_builder import (
        VOICE_PRIORITY_TOOLS,
        VOICE_TOOL_DESCRIPTIONS,
        clean_gemini_declarations,
    )

    assert "sessions_spawn" in VOICE_PRIORITY_TOOLS
    assert "sessions_yield" in VOICE_PRIORITY_TOOLS
    assert "subagents" in VOICE_PRIORITY_TOOLS
    assert "automations" in VOICE_PRIORITY_TOOLS

    assert "sessions_spawn" in VOICE_TOOL_DESCRIPTIONS
    assert "automations" in VOICE_TOOL_DESCRIPTIONS

    # Verify clean_gemini_declarations retains them
    sample_decls = [
        {
            "name": "sessions_spawn",
            "description": "Spawn background agent",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string"},
                    "attachments": {"type": "array"},  # must have items injected
                },
            },
        },
        {
            "name": "automations",
            "description": "Cron automations",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string"},
                    "schedule": {"type": "string"},
                },
            },
        },
    ]

    cleaned = clean_gemini_declarations(sample_decls, voice_priority_only=True)
    names = [d["name"] for d in cleaned]
    assert "sessions_spawn" in names
    assert "automations" in names

    # Array parameter must have items dict (Gemini Live Protocol Invariant)
    spawn_decl = next(d for d in cleaned if d["name"] == "sessions_spawn")
    assert "items" in spawn_decl["parameters"]["properties"]["attachments"]


@pytest.mark.asyncio
async def test_automations_tool_actions_and_aliases() -> None:
    """Verify automations tool handles create/add, list, status/get, run, and delete/remove."""
    from src.agents.sessions.tools.automations_tool import create_automations_tool_definition
    from extensions.cron.runtime import CronTable

    tool_def = create_automations_tool_definition()
    execute = tool_def["execute"]
    table = CronTable.default()

    test_job_id = "test_smoke_job_42"
    # Ensure clean slate
    table.remove(test_job_id)

    # 1. Action: "add" alias for "create" with "prompt" alias for "payload"
    res_create = await execute(
        "call_1",
        {
            "action": "add",
            "job_id": test_job_id,
            "schedule": "300",
            "prompt": "Remind Sir to check deployment",
        },
    )
    assert res_create["details"]["success"] is True
    assert res_create["details"]["action"] == "create"
    assert table.get(test_job_id) is not None

    # 2. Action: "list"
    res_list = await execute("call_2", {"action": "list"})
    assert res_list["details"]["action"] == "list"
    assert any(j["id"] == test_job_id for j in res_list["details"]["jobs"])

    # 3. Action: "get" alias for "status"
    res_status = await execute("call_3", {"action": "get", "job_id": test_job_id})
    assert res_status["details"]["action"] == "status"
    assert res_status["details"]["success"] is True
    assert res_status["details"]["job"]["id"] == test_job_id

    # 4. Action: "run" triggers immediate execution
    res_run = await execute("call_4", {"action": "run", "job_id": test_job_id})
    assert res_run["details"]["action"] == "run"
    assert res_run["details"]["success"] is True

    # 5. Action: "remove" alias for "delete"
    res_delete = await execute("call_5", {"action": "remove", "job_id": test_job_id})
    assert res_delete["details"]["action"] == "delete"
    assert res_delete["details"]["deleted"] is True
    assert table.get(test_job_id) is None


@pytest.mark.asyncio
async def test_subagent_spawner_and_completion_announcement() -> None:
    """Verify subagent executes in background and notifies listener."""
    from src.agents.subagents import (
        SubagentSpawner,
        SubagentRegistry,
        SubagentRunner,
        SpawnSubagentParams,
        SubagentSpawnContextMode,
        SubagentStatus,
    )

    registry = SubagentRegistry()
    runner = SubagentRunner(registry=registry)
    spawner = SubagentSpawner(registry=registry)

    completed_records = []

    def on_complete(rec, findings):
        completed_records.append((rec, findings))

    spawner.register_completion_listener(on_complete)

    params = SpawnSubagentParams(
        task="dir",
        label="List current directory test",
        context=SubagentSpawnContextMode.ISOLATED,
        run_timeout_seconds=10.0,
    )

    spawn_res = await spawner.spawn(
        params,
        runner_factory=lambda rec, tools: runner.run(rec, tools),
    )
    assert spawn_res.status == "accepted"

    # Wait briefly for background execution
    import asyncio
    for _ in range(50):
        await asyncio.sleep(0.05)
        if completed_records:
            break

    assert len(completed_records) > 0
    rec, findings = completed_records[0]
    assert rec.status == SubagentStatus.COMPLETED
    assert "List current directory test" in (rec.label or "")
    assert findings is not None


@pytest.mark.asyncio
async def test_subagent_directory_analysis_does_not_hijack_web_search() -> None:
    """Verify subagent task analyzing directory (even with 'search' in folder name) invokes ls, NOT web_search."""
    from src.agents.subagents.runner import SubagentRunner
    from src.agents.subagents.types import SubagentRole, SubagentRunRecord, SubagentStatus

    ls_invoked = False
    web_search_invoked = False

    async def mock_ls(cid, args):
        nonlocal ls_invoked
        ls_invoked = True
        return {"content": [{"type": "text", "text": "notes-search/\nrea-analysis/"}], "entries": ["notes-search/", "rea-analysis/"]}

    async def mock_search(cid, args):
        nonlocal web_search_invoked
        web_search_invoked = True
        return {"content": [{"type": "text", "text": "Google results"}]}

    tools = {
        "ls": {"execute": mock_ls},
        "web_search": {"execute": mock_search},
    }

    runner = SubagentRunner()
    record = SubagentRunRecord(
        run_id="test_dir_not_search",
        parent_session_key="desktop:hud",
        child_session_key="subagent:test_dir",
        task="Perform a deep and comprehensive analysis of the E:\\stonic directory. Explore all subfolders ('notes-search', 'rea-analysis').",
        role=SubagentRole.LEAF,
        status=SubagentStatus.QUEUED,
    )

    summary, artifacts = await runner._default_execute(record, tools)

    assert ls_invoked is True, "ls must be invoked for local directory analysis task"
    assert web_search_invoked is False, "web_search must NEVER be invoked for directory analysis"
    assert "Directory listing" in summary
    assert "E:\\stonic" in artifacts


def test_path_utils_windows_drive_root_fallback() -> None:
    """Verify resolve_read_path and resolve_unicode_path fallback to drive root on Windows when cwd doesn't match."""
    import sys
    from src.agents.sessions.tools.path_utils import resolve_read_path, resolve_unicode_path

    if sys.platform != "win32":
        return

    # In our environment, E:\stonic exists but E:\jarvis\stonic does not
    resolved_read = resolve_read_path("Stonic", "E:\\jarvis")
    resolved_unicode = resolve_unicode_path("Stonic", "E:\\jarvis")

    assert "E:\\" in resolved_read
    assert "jarvis" not in resolved_read.lower()
    assert "stonic" in resolved_read.lower()

    assert "E:\\" in resolved_unicode
    assert "jarvis" not in resolved_unicode.lower()
    assert "stonic" in resolved_unicode.lower()


@pytest.mark.asyncio
async def test_send_audio_task_strictly_suppresses_audio_when_assistant_generating() -> None:
    """Verify _send_audio_task suppresses mic chunks and never leaks audio during assistant generation (eliminating 1007 error)."""
    import asyncio
    import threading
    from unittest.mock import AsyncMock
    from types import SimpleNamespace
    from jarvis_voice_pipeline import terminal_app

    engine = object.__new__(terminal_app.NativeGeminiLiveEngine)
    engine.stop_event = asyncio.Event()
    engine.audio_out_queue = asyncio.Queue()
    engine._ws_send_lock = asyncio.Lock()
    engine._speaking_lock = threading.Lock()
    engine._turn_done_event = asyncio.Event()
    engine._turn_done_event.clear()
    engine._tool_call_in_flight = False
    engine._pending_tool_response = False
    engine._tool_response_pending_turn = False
    engine._assistant_generating = True
    engine._turn_complete_received = False
    engine._is_speaking = False
    engine.audio_in_queue = asyncio.Queue()
    engine.state = SimpleNamespace(agent_state="THINKING")

    mock_session = AsyncMock()
    # Put multiple PCM audio chunks
    for _ in range(5):
        engine.audio_out_queue.put_nowait(b"\x00" * 1600)

    task = asyncio.create_task(engine._send_audio_task(mock_session))
    await asyncio.sleep(0.15)
    engine.stop_event.set()
    await task

    # Audio chunks must NOT be sent to the Gemini Live session while generating
    assert not mock_session.send_realtime_input.called
    assert engine.audio_out_queue.empty()


def test_audio_controller_and_brightness_controller() -> None:
    """Verify AudioController and BrightnessController work natively on Windows."""
    from src.system.audio_controller import AudioController
    from src.system.brightness_controller import BrightnessController

    ac = AudioController.get_instance()
    vol_res = ac.get_volume()
    assert isinstance(vol_res, dict)
    assert "ok" in vol_res

    bc = BrightnessController.get_instance()
    bri_res = bc.get_brightness()
    assert isinstance(bri_res, dict)
    assert "ok" in bri_res


@pytest.mark.asyncio
async def test_computer_tool_volume_and_brightness_actions() -> None:
    """Verify computer tool executes volume and brightness hardware actions natively."""
    from src.agents.sessions.tools.computer_tool import create_computer_tool

    tool = create_computer_tool()
    fn = tool.execute if hasattr(tool, "execute") else tool["execute"]

    # Test get_volume
    res_vol = await fn({"action": "get_volume"})
    assert isinstance(res_vol, dict)
    assert "ok" in res_vol

    # Test get_brightness
    res_bri = await fn({"action": "get_brightness"})
    assert isinstance(res_bri, dict)
    assert "ok" in res_bri

    # Test set_volume
    res_set = await fn({"action": "set_volume", "value": 82})
    assert isinstance(res_set, dict)
    assert res_set.get("ok") is True
    assert res_set.get("volume_percent") == 82


@pytest.mark.asyncio
async def test_exec_tool_windows_env_var_expansion() -> None:
    """Verify exec_tool expands %USERPROFILE% and ~ so Windows explorer opens the real folder."""
    import os
    import re

    cmd = r"explorer.exe %USERPROFILE%\Downloads"
    expanded = os.path.expandvars(cmd)
    assert "%USERPROFILE%" not in expanded
    assert os.environ.get("USERPROFILE", "Users") in expanded

    tilde_cmd = r"explorer.exe ~/Downloads"
    expanded_tilde = re.sub(
        r'(^|[\s"\'=])~([/\\])',
        lambda m: f"{m.group(1)}{os.path.expanduser('~')}{m.group(2)}",
        tilde_cmd,
    )
    assert "~" not in expanded_tilde


@pytest.mark.asyncio
async def test_send_audio_task_permits_audio_when_hearing() -> None:
    """Verify _send_audio_task does not drop microphone packets when agent_state is HEARING."""
    import asyncio
    import threading
    import numpy as np
    from unittest.mock import AsyncMock
    from types import SimpleNamespace
    from jarvis_voice_pipeline import terminal_app

    engine = object.__new__(terminal_app.NativeGeminiLiveEngine)
    engine.stop_event = asyncio.Event()
    engine.audio_out_queue = asyncio.Queue()
    engine._ws_send_lock = asyncio.Lock()
    engine._speaking_lock = threading.Lock()
    engine._turn_done_event = asyncio.Event()
    engine._turn_done_event.set()
    engine._tool_call_in_flight = False
    engine._pending_tool_response = False
    engine._tool_response_pending_turn = False
    engine._assistant_generating = False
    engine._turn_complete_received = True
    engine._is_speaking = False
    engine.audio_in_queue = asyncio.Queue()
    # When user starts speaking, agent_state transitions to HEARING
    engine.state = SimpleNamespace(agent_state="HEARING")

    mock_session = AsyncMock()
    # Provide synthetic audio with speech energy (> 0.04 level)
    loud_pcm = (np.sin(np.linspace(0, 50, 800)) * 10000).astype(np.int16).tobytes()
    engine.audio_out_queue.put_nowait(loud_pcm)

    task = asyncio.create_task(engine._send_audio_task(mock_session))
    await asyncio.sleep(0.12)
    engine.stop_event.set()
    await task

    # Audio MUST be transmitted to Gemini Live when in HEARING state
    assert mock_session.send_realtime_input.called







