"""Continuous visual frame streaming for the desktop Live session.

This is the host-side capture half of the OpenClaw-style ``desktop.stream``
capability. It is deliberately not exposed as a screenshot tool: the desktop
host owns a long-lived frame source and provider adapters decide how to forward
frames to the active model.
"""

from __future__ import annotations

import asyncio
import io
import os
import sys
import time
from dataclasses import dataclass
from typing import Any, Literal

from PIL import Image

VisualSource = Literal["off", "screen", "camera"]


@dataclass(frozen=True, slots=True)
class VisualStreamConfig:
    enabled: bool = True
    source: VisualSource = "screen"
    fps: float = 1.0
    max_edge: int = 1024
    jpeg_quality: int = 72
    camera_index: int = 0
    monitor_index: int = 1


@dataclass(frozen=True, slots=True)
class VisualFrame:
    data: bytes
    mime_type: str
    source: VisualSource
    captured_at: float


def load_visual_stream_config() -> VisualStreamConfig:
    """Load startup visual stream settings from environment variables."""
    enabled_raw = os.environ.get("JARVIS_VISUAL_STREAM", "0").strip().lower()
    source_raw = os.environ.get("JARVIS_VISUAL_SOURCE", "screen").strip().lower()
    source: VisualSource = source_raw if source_raw in ("off", "screen", "camera") else "screen"

    enabled = enabled_raw not in {"0", "false", "no", "off"} and source != "off"
    fps = _read_float_env("JARVIS_VISUAL_STREAM_FPS", 1.0)
    max_edge = _read_int_env("JARVIS_VISUAL_MAX_EDGE", 1024)
    jpeg_quality = _read_int_env("JARVIS_VISUAL_JPEG_QUALITY", 72)
    camera_index = _read_int_env("JARVIS_VISUAL_CAMERA_INDEX", 0)
    monitor_index = _read_int_env("JARVIS_VISUAL_MONITOR_INDEX", 1)

    return VisualStreamConfig(
        enabled=enabled,
        source=source,
        fps=max(0.1, min(fps, 1.0)),
        max_edge=max(320, min(max_edge, 1920)),
        jpeg_quality=max(35, min(jpeg_quality, 90)),
        camera_index=max(0, camera_index),
        monitor_index=max(0, monitor_index),
    )


class VisualFrameStreamer:
    """Long-lived screen or camera frame producer."""

    def __init__(self, config: VisualStreamConfig | None = None) -> None:
        self.config = config or load_visual_stream_config()

    async def frames(self):
        if not self.config.enabled:
            return
        if self.config.source == "camera":
            async for frame in self._camera_frames():
                yield frame
            return
        async for frame in self._screen_frames():
            yield frame

    async def _screen_frames(self):
        interval = 1.0 / self.config.fps
        while True:
            start = time.monotonic()
            try:
                image = await asyncio.to_thread(_grab_screen, self.config.monitor_index)
                yield VisualFrame(
                    data=_encode_jpeg(image, self.config),
                    mime_type="image/jpeg",
                    source="screen",
                    captured_at=time.time(),
                )
            except Exception as exc:
                print(f"[JARVIS] visual stream screen capture paused: {exc}")
                await asyncio.sleep(2.0)
            await asyncio.sleep(max(0.0, interval - (time.monotonic() - start)))

    async def _camera_frames(self):
        import cv2

        interval = 1.0 / self.config.fps
        capture = cv2.VideoCapture(self.config.camera_index)
        try:
            while True:
                start = time.monotonic()
                ok, frame = await asyncio.to_thread(capture.read)
                if ok:
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    image = Image.fromarray(rgb)
                    yield VisualFrame(
                        data=_encode_jpeg(image, self.config),
                        mime_type="image/jpeg",
                        source="camera",
                        captured_at=time.time(),
                    )
                else:
                    print("[JARVIS] visual stream camera frame unavailable")
                    await asyncio.sleep(2.0)
                await asyncio.sleep(max(0.0, interval - (time.monotonic() - start)))
        finally:
            capture.release()


def _read_float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _read_int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _ensure_input_desktop() -> None:
    """Attach current thread to interactive input desktop on Windows if running in a separate station."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        user32 = ctypes.windll.user32
        h_desktop = user32.OpenInputDesktop(0, False, 0x01FF)
        if h_desktop:
            user32.SetThreadDesktop(h_desktop)
    except Exception:
        pass


def _select_monitor(monitors: Any, monitor_index: int) -> Any:
    if not monitors:
        raise RuntimeError("no displays available")
    if 0 <= monitor_index < len(monitors):
        return monitors[monitor_index]
    if len(monitors) > 1:
        return monitors[1]
    return monitors[0]


def _grab_screen(monitor_index: int = 1) -> Image.Image:
    """Capture screen frame, attaching to input desktop on Windows if needed."""
    _ensure_input_desktop()
    try:
        from mss import MSS

        with MSS() as sct:
            monitor = _select_monitor(sct.monitors, monitor_index)
            shot = sct.grab(monitor)
            return Image.frombytes("RGB", shot.size, shot.rgb)
    except Exception as mss_exc:
        try:
            from PIL import ImageGrab

            img = ImageGrab.grab()
            return img.convert("RGB")
        except Exception:
            raise mss_exc


def _encode_jpeg(image: Image.Image, config: VisualStreamConfig) -> bytes:
    image = image.convert("RGB")
    image.thumbnail((config.max_edge, config.max_edge), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=config.jpeg_quality, optimize=True)
    return out.getvalue()


__all__ = [
    "VisualFrame",
    "VisualFrameStreamer",
    "VisualStreamConfig",
    "load_visual_stream_config",
]
