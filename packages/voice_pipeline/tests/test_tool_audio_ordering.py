from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace

import pytest

from jarvis_voice_pipeline import terminal_app
from jarvis_voice_pipeline.pipeline_builder import build_jarvis_gemini_tools


class _OutputStream:
    def __init__(self) -> None:
        self.written: list[bytes] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def write(self, data: bytes) -> None:
        self.written.append(bytes(data))


def test_host_controls_use_generic_exec_instead_of_private_model_tools() -> None:
    tools = build_jarvis_gemini_tools(
        host_tools=[
            {
                "name": "exec",
                "description": "Run a shell command on the host.",
                "parameters": {
                    "type": "object",
                    "properties": {"command": {"type": "string"}},
                    "required": ["command"],
                },
            }
        ]
    )

    names = {tool["name"] for tool in tools}
    assert "exec" in names
    assert "system_volume" not in names
    assert "system_brightness" not in names


@pytest.mark.asyncio
async def test_audio_streams_while_the_assistant_turn_is_generating(monkeypatch) -> None:
    stream = _OutputStream()
    monkeypatch.setattr(terminal_app.sd, "RawOutputStream", lambda **_kwargs: stream)
    engine = object.__new__(terminal_app.NativeGeminiLiveEngine)
    engine.stop_event = asyncio.Event()
    engine.audio_in_queue = asyncio.Queue()
    engine.audio_in_queue.put_nowait(b"\x00\x00" * 1200)
    engine._tool_call_in_flight = False
    engine._pending_tool_response = False
    engine._assistant_generating = True
    engine._turn_complete_received = False
    engine._last_spk_time = 0.0
    engine._tail_until = 0.0
    engine._speaking_lock = threading.Lock()
    engine._is_speaking = False
    engine.state = SimpleNamespace(set_agent_state=lambda *_args: None)
    engine.echo_guard = SimpleNamespace(note_output=lambda *_args, **_kwargs: None)
    engine.ui = None

    task = asyncio.create_task(engine._spk_stream_task())
    await asyncio.sleep(0.15)
    engine.stop_event.set()
    await task

    assert engine.audio_in_queue.empty()
    assert stream.written, "streamed PCM must not wait for turn_complete"


@pytest.mark.asyncio
async def test_audio_streams_concurrently_while_tool_call_in_flight(monkeypatch) -> None:
    stream = _OutputStream()
    monkeypatch.setattr(terminal_app.sd, "RawOutputStream", lambda **_kwargs: stream)
    engine = object.__new__(terminal_app.NativeGeminiLiveEngine)
    engine.stop_event = asyncio.Event()
    engine.audio_in_queue = asyncio.Queue()
    engine.audio_in_queue.put_nowait(b"\x00\x00" * 1200)
    engine._tool_call_in_flight = True
    engine._pending_tool_response = True
    engine._assistant_generating = True
    engine._turn_complete_received = False
    engine._last_spk_time = 0.0
    engine._tail_until = 0.0
    engine._speaking_lock = threading.Lock()
    engine._is_speaking = False
    engine.state = SimpleNamespace(set_agent_state=lambda *_args: None)
    engine.echo_guard = SimpleNamespace(note_output=lambda *_args, **_kwargs: None)
    engine.ui = None

    task = asyncio.create_task(engine._spk_stream_task())
    await asyncio.sleep(0.15)
    engine.stop_event.set()
    await task

    assert engine.audio_in_queue.empty()
    assert stream.written, "Assistant speech audio must play concurrently while tool is in flight"


@pytest.mark.asyncio
async def test_tool_turn_transcription_is_not_persisted_as_assistant_answer(monkeypatch) -> None:
    engine = object.__new__(terminal_app.NativeGeminiLiveEngine)
    engine.stop_event = asyncio.Event()
    engine.state = terminal_app.JarvisTerminalHUDState()
    engine.session_resumption_handle = None
    engine._rx_deadline = None
    engine._turn_done_event = asyncio.Event()
    engine._tool_call_in_flight = False
    engine._pending_tool_response = False
    engine._assistant_generating = False
    engine._turn_complete_received = True
    engine._primary_active_goal = None
    engine._active_goal = None
    engine.audio_in_queue = asyncio.Queue()

    async def finish_tool_call(_session, _tool_call) -> None:
        engine.stop_event.set()

    monkeypatch.setattr(engine, "_handle_tool_call", finish_tool_call)

    response = SimpleNamespace(
        server_content=SimpleNamespace(
            model_turn=None,
            output_transcription=SimpleNamespace(text="Brightness is now lower."),
            input_transcription=None,
            grounding_metadata=None,
            turn_complete=True,
            interrupted=False,
        ),
        tool_call=SimpleNamespace(function_calls=[]),
        session_resumption_update=None,
        data=None,
        tool_call_cancellation=None,
    )

    class _Session:
        async def receive(self):
            yield response
            await asyncio.sleep(0.01)

    await engine._receive_task(_Session())

    assert not any(role == "JARVIS" for _time, role, _text in engine.state.transcripts)


@pytest.mark.asyncio
async def test_execute_desktop_action_volume_and_brightness() -> None:
    """Verify execute_desktop_action correctly handles volume and brightness."""
    from jarvis_desktop.tool_pipeline import execute_desktop_action

    vol_res = await execute_desktop_action({"action": "set_volume", "volume": 60})
    assert "Volume set to 60%" in vol_res

    get_vol_res = await execute_desktop_action({"action": "get_volume"})
    assert "System volume is currently" in get_vol_res

    adj_vol_res = await execute_desktop_action({"action": "adjust_volume", "delta": 5})
    assert "Volume set to" in adj_vol_res

    bright_res = await execute_desktop_action({"action": "set_brightness", "brightness": 75})
    assert "Screen brightness set to" in bright_res or "executed" in bright_res

    get_bright_res = await execute_desktop_action({"action": "get_brightness"})
    assert "screen brightness" in get_bright_res.lower()


@pytest.mark.asyncio
async def test_handle_tool_call_waits_for_spoken_acknowledgment() -> None:
    """Verify _handle_tool_call does not clip spoken acknowledgment before delivering tool response."""
    from unittest.mock import AsyncMock

    engine = object.__new__(terminal_app.NativeGeminiLiveEngine)
    engine.stop_event = asyncio.Event()
    engine._turn_done_event = asyncio.Event()
    engine._speaking_lock = threading.Lock()
    engine._is_speaking = True
    engine.set_speaking = lambda v: setattr(engine, "_is_speaking", v)
    engine.audio_in_queue = asyncio.Queue()
    engine.audio_in_queue.put_nowait(b"\x00" * 400)
    engine.audio_out_queue = asyncio.Queue()
    engine._ws_send_lock = asyncio.Lock()
    engine.state = SimpleNamespace(
        agent_state="THINKING",
        set_agent_state=lambda *_a: None,
        add_tool_event=lambda *_a: None,
    )
    engine._play_earcon_chime = lambda: None
    engine._execute_tool_call = AsyncMock(return_value="tool_done")

    async def finish_speech_later():
        await asyncio.sleep(0.08)
        engine.set_speaking(False)
        while not engine.audio_in_queue.empty():
            engine.audio_in_queue.get_nowait()

    mock_session = SimpleNamespace(
        send_tool_response=AsyncMock(),
    )

    speech_task = asyncio.create_task(finish_speech_later())
    fc_call = SimpleNamespace(function_calls=[SimpleNamespace(name="computer", args={"action": "set_volume", "volume": 50})])
    await engine._handle_tool_call(mock_session, fc_call)
    await speech_task

    mock_session.send_tool_response.assert_called_once()
    assert not engine.is_speaking
    assert engine.audio_in_queue.empty()


@pytest.mark.asyncio
async def test_post_turn_silence_prevents_1007_mic_leak() -> None:
    """Verify _send_audio_task suppresses mic output during the post-turn cooldown window."""
    import time
    from unittest.mock import AsyncMock

    engine = object.__new__(terminal_app.NativeGeminiLiveEngine)
    engine.stop_event = asyncio.Event()
    engine.audio_out_queue = asyncio.Queue()
    engine.audio_in_queue = asyncio.Queue()
    engine._speaking_lock = threading.Lock()
    engine._is_speaking = False
    engine._assistant_generating = False
    engine._turn_complete_received = True
    engine._tool_call_in_flight = False
    engine._pending_tool_response = False
    engine._tool_response_pending_turn = False
    engine.state = SimpleNamespace(agent_state="LISTENING")
    engine._ws_send_lock = asyncio.Lock()

    engine._post_turn_silence_until = time.monotonic() + 1.0

    mock_session = SimpleNamespace(send_realtime_input=AsyncMock())
    engine.audio_out_queue.put_nowait(b"\x00" * 800)

    send_task = asyncio.create_task(engine._send_audio_task(mock_session))
    await asyncio.sleep(0.06)
    engine.stop_event.set()
    await send_task

    mock_session.send_realtime_input.assert_not_called()


def test_conversational_inquiries_not_treated_as_actionable_goals() -> None:
    """Verify general conversation (e.g. 'के गर्दै छौ?') does not trigger spurious Ghost-Chatter tool nudges."""
    assert not terminal_app._is_actionable_user_goal("के गर्दै छौ?")
    assert not terminal_app._is_actionable_user_goal("ke gardai chhau?")
    assert not terminal_app._is_actionable_user_goal("के हुँदैछ?")
    assert not terminal_app._is_actionable_user_goal("chutkila sunau")
    assert not terminal_app._is_actionable_user_goal("Malai hasaaun sakchhau.")
    # Real actionable commands must still return True
    assert terminal_app._is_actionable_user_goal("bholam 30% kara")
    assert terminal_app._is_actionable_user_goal("open youtube")
    assert terminal_app._is_actionable_user_goal("भोल्युम कम गर")


@pytest.mark.asyncio
async def test_tool_response_watchdog_unfreezes_state() -> None:
    """Verify that if Gemini Live stalls after send_tool_response, the >25s watchdog unfreezes the state."""
    import threading
    import time
    from unittest.mock import AsyncMock

    engine = object.__new__(terminal_app.NativeGeminiLiveEngine)
    engine.stop_event = asyncio.Event()
    engine.audio_out_queue = asyncio.Queue()
    engine.audio_in_queue = asyncio.Queue()
    engine._tool_call_in_flight = False
    engine._pending_tool_response = False
    engine._tool_response_pending_turn = True
    # Simulate a tool response sent 30 seconds ago with no server reply
    engine._tool_response_sent_at = time.monotonic() - 30.0
    engine._last_server_activity = time.monotonic() - 30.0
    engine._speaking_lock = threading.Lock()
    engine._is_speaking = False
    engine._assistant_generating = True
    engine._turn_complete_received = False
    engine._turn_done_event = asyncio.Event()
    engine.state = SimpleNamespace(agent_state="THINKING", set_agent_state=lambda s: setattr(engine.state, "agent_state", s))
    engine._ws_send_lock = asyncio.Lock()
    engine._post_turn_silence_until = 0.0

    mock_session = SimpleNamespace(send_realtime_input=AsyncMock())
    engine.audio_out_queue.put_nowait(b"\x00" * 800)

    # In _send_audio_task, the watchdog should detect sent_at > 25s with idle server and unfreeze safely
    send_task = asyncio.create_task(engine._send_audio_task(mock_session))
    await asyncio.sleep(0.06)
    engine.stop_event.set()
    await send_task

    assert engine._tool_response_pending_turn is False
    assert engine.state.agent_state == "LISTENING"
    assert engine._turn_done_event.is_set()


def test_terminate_conflicting_processes_protects_ancestors() -> None:
    """Verify _terminate_conflicting_voice_processes runs cleanly without killing the test runner or parent shells."""
    # Should run with zero exceptions and protect current pid and parents
    terminal_app._terminate_conflicting_voice_processes()


def test_sleep_command_and_wake_word_detection() -> None:
    """Verify explicit sleep mode commands and wake words are accurately classified."""
    # Sleep commands
    assert terminal_app._is_sleep_command("स्लिप मोडमा जाऊ")
    assert terminal_app._is_sleep_command("sleep mode")
    assert terminal_app._is_sleep_command("standby mode")
    assert terminal_app._is_sleep_command("स्ट्यान्डबाई")
    assert terminal_app._is_sleep_command("सुत अब")
    assert terminal_app._is_sleep_command("rest mode ma jaau")
    assert not terminal_app._is_sleep_command("bholam 30% kara")
    assert not terminal_app._is_sleep_command("ke gardai chhau?")

    # Wake words
    assert terminal_app._is_wake_word("JARVIS")
    assert terminal_app._is_wake_word("जार्विस")
    assert terminal_app._is_wake_word("hey jarvis")
    assert terminal_app._is_wake_word("हे जार्विस उठ")
    assert terminal_app._is_wake_word("hello service")
    assert terminal_app._is_wake_word("How are you charvis")
    assert terminal_app._is_wake_word("haau aar yoo jarmis")
    assert not terminal_app._is_wake_word("mero pani thikai chha")
    assert not terminal_app._is_wake_word("khana khayau?")


@pytest.mark.asyncio
async def test_proactive_session_rollover_on_idle() -> None:
    """Verify that after 12 minutes (720s) of connection age during idle state, SessionRollover is raised."""
    import time

    engine = object.__new__(terminal_app.NativeGeminiLiveEngine)
    engine._speaking_lock = threading.Lock()
    engine._is_speaking = False
    engine.stop_event = asyncio.Event()
    engine.audio_out_queue = asyncio.Queue()
    engine.audio_in_queue = asyncio.Queue()
    engine._tool_call_in_flight = False
    engine._pending_tool_response = False
    engine._tool_response_pending_turn = False
    engine._assistant_generating = False
    engine._rx_deadline = None
    engine._last_server_activity = time.monotonic()
    engine.state = SimpleNamespace(
        agent_state="LISTENING",
        set_agent_state=lambda s: setattr(engine.state, "agent_state", s),
    )
    engine.ui = None
    # Simulate connection established 730 seconds ago (12.1 minutes)
    engine._session_connected_at = time.monotonic() - 730.0

    # Running _watch_stall_task should raise SessionRollover
    watch_task = asyncio.create_task(engine._watch_stall_task())
    await asyncio.sleep(0.05)

    with pytest.raises(terminal_app.SessionRollover):
        await watch_task


@pytest.mark.asyncio
async def test_ws_keepalive_ping_sent_when_idle_no_phantom_audio(monkeypatch) -> None:
    """Verify that RFC 6455 WebSocket ping keeps the connection alive without sending phantom audio."""
    import time
    from unittest.mock import AsyncMock

    engine = object.__new__(terminal_app.NativeGeminiLiveEngine)
    engine._speaking_lock = threading.Lock()
    engine._is_speaking = False
    engine.stop_event = asyncio.Event()
    engine.audio_out_queue = asyncio.Queue()
    engine.audio_in_queue = asyncio.Queue()
    engine._tool_call_in_flight = False
    engine._pending_tool_response = False
    engine._tool_response_pending_turn = False
    engine._assistant_generating = False
    engine.state = SimpleNamespace(
        agent_state="LISTENING",
        set_agent_state=lambda s: setattr(engine.state, "agent_state", s),
    )
    engine._ws_send_lock = asyncio.Lock()
    engine._post_turn_silence_until = 0.0
    # Simulate last audio sent 30 seconds ago
    engine._last_audio_sent_at = time.monotonic() - 30.0

    mock_ws = SimpleNamespace(ping=AsyncMock())
    mock_session = SimpleNamespace(_ws=mock_ws, send_realtime_input=AsyncMock())

    # Monkeypatch asyncio.sleep in keepalive task so it doesn't wait 15 seconds in unit test
    orig_sleep = asyncio.sleep

    async def _fast_sleep(_dur):
        await orig_sleep(0.01)

    monkeypatch.setattr(asyncio, "sleep", _fast_sleep)

    keepalive_task = asyncio.create_task(engine._keepalive_ping_task(mock_session))
    await orig_sleep(0.03)
    engine.stop_event.set()
    await keepalive_task

    # RFC 6455 WebSocket ping must be sent to keep TCP/TLS session alive
    mock_ws.ping.assert_awaited()
    # Must NOT send realtime audio chunks during idle to prevent phantom user speech hallucinations
    mock_session.send_realtime_input.assert_not_called()


test_audio_silence_heartbeat_sent_when_idle = test_ws_keepalive_ping_sent_when_idle_no_phantom_audio


def test_organize_files_actionable_and_ghost_promise_detection() -> None:
    """Verify that file organization commands and empty verbal promises are accurately detected."""
    user_cmd = "jar wi downloadma bhaeko sabai sabailaaee organaaij garera ta tegorij waaij"
    assert terminal_app._is_actionable_user_goal(user_cmd) is True
    assert terminal_app._is_actionable_user_goal("downloads safaa gara") is True
    assert terminal_app._is_actionable_user_goal("डाउनलोड फोल्डर व्यवस्थित गर") is True

    jarvis_speech = "Hunchha Sir, Ma downloads pholdaramaa bhaekaa sabai phaailaharoolaaee kyaategoreeanusaar wyawasthit gardai chhu. yasakaa laagi Ma pahile phaailaharooko prakaar herchhu."
    assert terminal_app._detect_ghost_action_promise(jarvis_speech, user_cmd) is True

    # Multi-turn promised work: announcing start of moving files after inspection
    ongoing_speech = "maile downloads pholdaramaa rahekaa phaailaharoo ra pholdaraharooko soochee hereko chhu. ab Ma yinalaaee upayukt shreneeharoomaa saarn suru garchhu."
    assert terminal_app._detect_ghost_action_promise(ongoing_speech, user_cmd) is True

    # Verified task completion speech
    completed_speech = "maile sabai phaailaharoolaaee upayukt pholdaramaa saarisakeko chhu, sir."
    assert terminal_app._detect_ghost_action_promise(completed_speech, user_cmd) is False

    # Settled tool completion recognition
    settled_speech = "phaailaharoolaaee sambandhit pholdaraharoomaa wyawasthit garisaken maile. ab Tapaiko arko kaam ke chha?"
    assert terminal_app._is_task_completion_speech(settled_speech) is True
    assert terminal_app._is_task_completion_speech("downloads folder poorn roopamaa wyawasthit bhaisakeko chha sar.") is True
    assert terminal_app._is_task_completion_speech("ab Ma yinalaaee upayukt shreneeharoomaa saarn suru garchhu.") is False



def test_repair_cmd_syntax_to_powershell() -> None:
    """Verify that CMD syntax constructs are auto-translated to valid PowerShell commands."""
    from src.agents.sessions.tools.exec_tool import repair_cmd_syntax_to_powershell

    cmd = 'if not exist "~/Downloads/Videos" mkdir "~/Downloads/Videos"'
    fixed = repair_cmd_syntax_to_powershell(cmd)
    assert "-not (Test-Path" in fixed
    assert "New-Item -ItemType Directory -Force" in fixed

    cmd_exist = 'if exist "file.txt" Remove-Item "file.txt"'
    fixed_exist = repair_cmd_syntax_to_powershell(cmd_exist)
    assert 'Test-Path "file.txt"' in fixed_exist

    cmd_touch = 'type nul > "newfile.txt"'
    fixed_touch = repair_cmd_syntax_to_powershell(cmd_touch)
    assert "New-Item -ItemType File -Force" in fixed_touch


def test_error_classifier_classify_error_parity() -> None:
    """Verify that ErrorClassifier.classify_error exists and processes tool execution errors."""
    from src.agents.self_healing import ErrorClassifier, FailureEvent

    fe = ErrorClassifier.classify_error(
        "ParserError: Missing '(' after 'if'",
        context={"tool_name": "exec", "args": {"command": "if not exist dir mkdir dir"}},
        attempt_count=1,
    )
    assert isinstance(fe, FailureEvent)
    assert fe.context["tool_name"] == "exec"


def test_affirmations_and_completion_remarks_not_actionable_goals() -> None:
    """Confirmations, affirmations, and visual observations must NOT trigger actionable goals."""
    from jarvis_voice_pipeline.terminal_app import _is_actionable_user_goal

    assert _is_actionable_user_goal("अब सक्ससेसफुली देखि।") is False
    assert _is_actionable_user_goal("भयो ओपन गर्नमा सिभि") is False
    assert _is_actionable_user_goal("bhayo dekhiyo sar") is False
    assert _is_actionable_user_goal("khulisakyo") is False
    assert _is_actionable_user_goal("it's open now") is False
    assert _is_actionable_user_goal("done") is False

    # Actual commands must still be actionable
    assert _is_actionable_user_goal("a Mero sebee holaa tyo sebee open garera") is True
    assert _is_actionable_user_goal("downloads check bhan ta ke chha") is True


def test_ghost_action_promise_polite_assistance_offers() -> None:
    """Polite signoffs, assistance offers, and completed reports must not trigger ghost chatter nudges."""
    from jarvis_voice_pipeline.terminal_app import _detect_ghost_action_promise

    assistance_resp = "thik chha sar. aru kehee sahaayataa chaahiemaa bhannuholaa"
    assert _detect_ghost_action_promise(assistance_resp, "downloads check bhan ta ke chha") is False

    completed_resp = "maile CV open garisaken sar."
    assert _detect_ghost_action_promise(completed_resp, "a Mero sebee holaa tyo sebee open garera") is False


def test_desktop_action_open_file_argument_preparation() -> None:
    """Computer open_file action must properly normalize target and file_path arguments."""
    from jarvis_desktop.tool_pipeline import prepare_tool_arguments

    prep = prepare_tool_arguments("computer", {"action": "open_file", "file_path": "C:\\Users\\test\\doc.pdf"})
    assert prep["action"] == "open_file"
    assert prep["target"] == "C:\\Users\\test\\doc.pdf"
    assert prep["file_path"] == "C:\\Users\\test\\doc.pdf"


def test_criticisms_and_complaints_not_actionable_goals() -> None:
    """User complaints, criticisms, and time queries must NOT trigger actionable goals."""
    from jarvis_voice_pipeline.terminal_app import _is_actionable_user_goal

    assert _is_actionable_user_goal("sabai kura galtee nai garchhau.") is False
    assert _is_actionable_user_goal("aawashyakataa chha dherai kuraako tara Timi garnai sakdainau.") is False
    assert _is_actionable_user_goal("ke sahayog garna sakchhau bhane") is False
    assert _is_actionable_user_goal("taaim kati bhayo?") is False
    assert _is_actionable_user_goal("time kati bhayo?") is False
    assert _is_actionable_user_goal("samay kati bhayo") is False
    assert _is_actionable_user_goal("kati bajyo") is False


def test_windows_asyncio_10054_patch_installed() -> None:
    """Verify that Windows Proactor WinError 10054 patch applies safely and idempotently."""
    import sys
    from jarvis_net_policy import patch_windows_asyncio_connection_lost

    patch_windows_asyncio_connection_lost()
    if sys.platform == "win32":
        from asyncio import proactor_events

        assert getattr(proactor_events, "_PROACTOR_10054_PATCHED", False) is True


@pytest.mark.asyncio
async def test_session_rollover_respects_user_speech_recency() -> None:
    """Session rollover must NOT fire while the user is actively speaking or conversing."""
    import time
    from types import SimpleNamespace

    engine = object.__new__(terminal_app.NativeGeminiLiveEngine)
    engine._speaking_lock = threading.Lock()
    engine._is_speaking = False
    engine.stop_event = asyncio.Event()
    engine.audio_out_queue = asyncio.Queue()
    engine.audio_in_queue = asyncio.Queue()
    engine._tool_call_in_flight = False
    engine._pending_tool_response = False
    engine._tool_response_pending_turn = False
    engine._assistant_generating = False
    engine._turn_complete_received = True
    engine._rx_deadline = None
    engine._last_server_activity = time.monotonic()
    engine.state = SimpleNamespace(
        agent_state="LISTENING",
        set_agent_state=lambda s: setattr(engine.state, "agent_state", s),
    )
    engine.ui = None
    engine._active_goal = None
    engine._task_in_progress = False

    # Simulate connection established 730s ago (>12m), BUT user spoke 10s ago (<45s)
    engine._session_connected_at = time.monotonic() - 730.0
    engine._last_user_speech_time = time.monotonic() - 10.0

    # Rollover must NOT be triggered because user was actively conversing
    watch_task = asyncio.create_task(engine._watch_stall_task())
    await asyncio.sleep(0.05)
    engine.stop_event.set()
    await watch_task


@pytest.mark.asyncio
async def test_audio_sending_suppressed_when_tool_execution_in_flight() -> None:
    """When _tool_call_in_flight or _pending_tool_response is True, _send_audio_task must drop chunks and send 0 packets to session."""
    from types import SimpleNamespace

    engine = object.__new__(terminal_app.NativeGeminiLiveEngine)
    engine.stop_event = asyncio.Event()
    engine.audio_out_queue = asyncio.Queue()
    engine.audio_in_queue = asyncio.Queue()
    engine._ws_send_lock = asyncio.Lock()
    engine._speaking_lock = threading.Lock()
    engine._is_speaking = False
    engine._tool_call_in_flight = True
    engine._pending_tool_response = True
    engine._tool_response_pending_turn = False
    engine._assistant_generating = False
    engine._turn_complete_received = False
    engine.state = SimpleNamespace(
        agent_state="THINKING",
        set_agent_state=lambda s: setattr(engine.state, "agent_state", s),
    )
    engine._post_turn_silence_until = 0.0
    engine._is_speaking = False

    sent_packets: list[bytes] = []

    class MockSession:
        async def send_realtime_input(self, media=None):
            if media and hasattr(media, "data"):
                sent_packets.append(media.data)

    mock_session = MockSession()
    # Put chunks in queue
    engine.audio_out_queue.put_nowait(b"\x01\x02" * 512)
    engine.audio_out_queue.put_nowait(b"\x03\x04" * 512)

    send_task = asyncio.create_task(engine._send_audio_task(mock_session))
    await asyncio.sleep(0.08)
    engine.stop_event.set()
    await send_task

    # Queue must be drained and ZERO packets must be sent into the WebSocket!
    assert engine.audio_out_queue.empty()
    assert len(sent_packets) == 0, "No audio packets may be sent while tool execution is in flight!"


@pytest.mark.asyncio
async def test_audio_streams_freely_during_user_turn_in_hearing_state() -> None:
    """When agent_state is HEARING or LISTENING and no tool is in flight, user audio must stream freely to session."""
    import time
    from types import SimpleNamespace

    engine = object.__new__(terminal_app.NativeGeminiLiveEngine)
    engine.stop_event = asyncio.Event()
    engine.audio_out_queue = asyncio.Queue()
    engine.audio_in_queue = asyncio.Queue()
    engine._ws_send_lock = asyncio.Lock()
    engine._speaking_lock = threading.Lock()
    engine._is_speaking = False
    engine._tool_call_in_flight = False
    engine._pending_tool_response = False
    engine._tool_response_pending_turn = False
    engine._assistant_generating = False
    engine._turn_complete_received = True
    engine.state = SimpleNamespace(
        agent_state="HEARING",
        set_agent_state=lambda s: setattr(engine.state, "agent_state", s),
    )
    # User last spoke 400ms ago (>0.25s cadence between words)
    engine._last_user_speech_time = time.monotonic() - 0.40
    engine._post_turn_silence_until = 0.0
    engine._is_speaking = False

    sent_packets: list[bytes] = []

    class MockSession:
        async def send_realtime_input(self, media=None):
            if media and hasattr(media, "data"):
                sent_packets.append(media.data)

    mock_session = MockSession()
    chunk_data = b"\x05\x06" * 512
    engine.audio_out_queue.put_nowait(chunk_data)

    send_task = asyncio.create_task(engine._send_audio_task(mock_session))
    await asyncio.sleep(0.08)
    engine.stop_event.set()
    await send_task

    assert len(sent_packets) > 0, "User speech audio chunks must stream freely to session during user conversation!"




