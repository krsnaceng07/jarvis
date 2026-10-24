from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace

import pytest

from jarvis_voice_pipeline import terminal_app
from jarvis_voice_pipeline.pipeline_builder import build_openclaw_gemini_tools


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
    tools = build_openclaw_gemini_tools(
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
