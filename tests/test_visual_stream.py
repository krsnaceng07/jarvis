"""tests.test_visual_stream — Tests for Desktop Visual Streaming & Live Vision Parity.

Covers:
- VisualStreamConfig defaults and environment overrides.
- VisualFrameStreamer frame generator and JPEG compression constraints.
- Windows desktop attachment helper _ensure_input_desktop.
- _grab_screen mss capture and ImageGrab fallback.
- JarvisLive._send_visual_stream integration with WebSocket lock and send_realtime_input.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from PIL import Image
import pytest

from jarvis_desktop.visual_stream import (
    VisualFrame,
    VisualFrameStreamer,
    VisualStreamConfig,
    load_visual_stream_config,
    _ensure_input_desktop,
    _grab_screen,
)


def test_visual_stream_config_defaults(monkeypatch):
    monkeypatch.delenv("JARVIS_VISUAL_STREAM", raising=False)
    monkeypatch.delenv("JARVIS_VISUAL_SOURCE", raising=False)
    monkeypatch.delenv("JARVIS_VISUAL_STREAM_FPS", raising=False)
    monkeypatch.delenv("JARVIS_VISUAL_MAX_EDGE", raising=False)

    cfg = load_visual_stream_config()
    assert cfg.enabled is True
    assert cfg.source == "screen"
    assert cfg.fps == 1.0
    assert cfg.max_edge == 1024


def test_visual_stream_config_env_overrides(monkeypatch):
    monkeypatch.setenv("JARVIS_VISUAL_STREAM", "0")
    cfg = load_visual_stream_config()
    assert cfg.enabled is False

    monkeypatch.setenv("JARVIS_VISUAL_STREAM", "1")
    monkeypatch.setenv("JARVIS_VISUAL_SOURCE", "camera")
    monkeypatch.setenv("JARVIS_VISUAL_STREAM_FPS", "0.5")
    monkeypatch.setenv("JARVIS_VISUAL_MAX_EDGE", "640")
    cfg = load_visual_stream_config()
    assert cfg.enabled is True
    assert cfg.source == "camera"
    assert cfg.fps == 0.5
    assert cfg.max_edge == 640


@pytest.mark.asyncio
async def test_visual_streamer_screen_frames_generator():
    cfg = VisualStreamConfig(enabled=True, source="screen", fps=10.0, max_edge=320)
    streamer = VisualFrameStreamer(cfg)

    dummy_img = Image.new("RGB", (640, 480), color="blue")
    with patch("jarvis_desktop.visual_stream._grab_screen", return_value=dummy_img):
        frames: list[VisualFrame] = []
        async for frame in streamer.frames():
            frames.append(frame)
            if len(frames) >= 2:
                break

        assert len(frames) == 2
        for f in frames:
            assert f.source == "screen"
            assert f.mime_type == "image/jpeg"
            assert len(f.data) > 0


def test_ensure_input_desktop_tolerates_errors():
    with patch("sys.platform", "win32"), patch("ctypes.windll") as mock_windll:
        mock_user32 = MagicMock()
        mock_windll.user32 = mock_user32
        mock_user32.OpenInputDesktop.side_effect = RuntimeError("Access Denied")
        # Must not raise
        _ensure_input_desktop()


def test_grab_screen_fallback_to_imagegrab():
    dummy_img = Image.new("RGB", (200, 200), color="red")
    with (
        patch("mss.MSS", side_effect=Exception("BitBlt error")),
        patch("PIL.ImageGrab.grab", return_value=dummy_img),
    ):
        result = _grab_screen(1)
        assert result.size == (200, 200)


@pytest.mark.asyncio
async def test_jarvis_live_send_visual_stream():
    from jarvis_desktop.app import JarvisLive

    mock_ui = MagicMock()
    mock_session = AsyncMock()
    app = JarvisLive(mock_ui)
    app.session = mock_session
    app._ws_send_lock = asyncio.Lock()

    dummy_img = Image.new("RGB", (400, 300), color="green")
    with patch("jarvis_desktop.visual_stream._grab_screen", return_value=dummy_img):
        task = asyncio.create_task(app._send_visual_stream())
        await asyncio.sleep(0.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        call_kwargs = mock_session.send_realtime_input.call_args.kwargs
        blob = call_kwargs.get("media") or call_kwargs.get("video")
        assert blob is not None
        assert blob.mime_type == "image/jpeg"
