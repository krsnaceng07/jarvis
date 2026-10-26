"""Exercise playback without importing the desktop's eager live services."""

import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.mark.asyncio
async def test_playback_releases_speaking_after_last_chunk():
    source = Path("apps/desktop/src/jarvis_desktop/live_transport.py").read_text(encoding="utf-8")
    cls = next(
        n
        for n in ast.parse(source).body
        if isinstance(n, ast.ClassDef) and n.name == "LiveTransport"
    )
    method = next(
        n for n in cls.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "_play_audio"
    )
    stream = MagicMock()
    namespace = {
        "asyncio": asyncio,
        "sd": SimpleNamespace(RawOutputStream=lambda **kw: stream),
        "RECEIVE_SAMPLE_RATE": 24000,
        "CHANNELS": 1,
        "CHUNK_SIZE": 1024,
    }
    exec(compile(ast.Module(body=[method], type_ignores=[]), "playback", "exec"), namespace)
    released = asyncio.Event()
    states = []

    def set_speaking(value):
        states.append(value)
        if not value:
            released.set()

    host = SimpleNamespace(audio_in_queue=asyncio.Queue(), set_speaking=set_speaking)
    host.audio_in_queue.put_nowait(b"\x00\x00")
    task = asyncio.create_task(namespace["_play_audio"](host))
    try:
        await asyncio.wait_for(released.wait(), timeout=2)
        assert states == [True, False]
        stream.write.assert_called_once()
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    stream.close.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("muted", [False, True])
async def test_microphone_preserves_quiet_pcm_while_speaking(muted):
    source = Path("apps/desktop/src/jarvis_desktop/live_transport.py").read_text(encoding="utf-8")
    cls = next(n for n in ast.parse(source).body if isinstance(n, ast.ClassDef) and n.name == "LiveTransport")
    method = next(n for n in cls.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "_listen_audio")
    captured = {}

    def input_stream(**kwargs):
        captured.update(kwargs)
        return MagicMock()

    namespace = {"asyncio": asyncio, "sd": SimpleNamespace(InputStream=input_stream), "SEND_SAMPLE_RATE": 16000, "CHANNELS": 1, "CHUNK_SIZE": 1024}
    exec(compile(ast.Module(body=[method], type_ignores=[]), "microphone", "exec"), namespace)
    host = SimpleNamespace(ui=SimpleNamespace(muted=muted), out_queue=asyncio.Queue(), _is_speaking=True)
    task = asyncio.create_task(namespace["_listen_audio"](host))
    try:
        await asyncio.sleep(0)
        quiet_pcm = b"\x01\x00" * 1024
        captured["callback"](SimpleNamespace(tobytes=lambda: quiet_pcm), 1024, None, None)
        await asyncio.sleep(0)
        if muted:
            assert host.out_queue.empty()
        else:
            assert host.out_queue.get_nowait()["data"] == quiet_pcm
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
