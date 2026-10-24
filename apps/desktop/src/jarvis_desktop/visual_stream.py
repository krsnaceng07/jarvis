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
from dataclasses import dataclass, replace
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
    idle_interval: float = 8.0
    change_threshold: float = 0.02


@dataclass(frozen=True, slots=True)
class VisualFrame:
    data: bytes
    mime_type: str
    source: VisualSource
    captured_at: float


def load_visual_stream_config() -> VisualStreamConfig:
    """Load startup visual stream settings from environment variables."""
    enabled_raw = os.environ.get("JARVIS_VISUAL_STREAM", "1").strip().lower()
    source_raw = os.environ.get("JARVIS_VISUAL_SOURCE", "screen").strip().lower()
    source: VisualSource = source_raw if source_raw in ("off", "screen", "camera") else "screen"

    enabled = enabled_raw not in {"0", "false", "no", "off"} and source != "off"
    fps = _read_float_env("JARVIS_VISUAL_STREAM_FPS", 1.0)
    max_edge = _read_int_env("JARVIS_VISUAL_MAX_EDGE", 1024)
    jpeg_quality = _read_int_env("JARVIS_VISUAL_JPEG_QUALITY", 72)
    camera_index = _read_int_env("JARVIS_VISUAL_CAMERA_INDEX", 0)
    monitor_index = _read_int_env("JARVIS_VISUAL_MONITOR_INDEX", 1)
    idle_interval = _read_float_env("JARVIS_VISUAL_IDLE_INTERVAL", 8.0)
    change_threshold = _read_float_env("JARVIS_VISUAL_CHANGE_THRESHOLD", 0.02)

    return VisualStreamConfig(
        enabled=enabled,
        source=source,
        fps=max(0.1, min(fps, 1.0)),
        max_edge=max(320, min(max_edge, 1920)),
        jpeg_quality=max(35, min(jpeg_quality, 90)),
        camera_index=max(0, camera_index),
        monitor_index=max(0, monitor_index),
        idle_interval=max(1.0, min(idle_interval, 30.0)),
        change_threshold=max(0.001, min(change_threshold, 0.1)),
    )


class VisualFrameStreamer:
    """Long-lived screen or camera frame producer with differential change streaming."""

    def __init__(
        self,
        config: VisualStreamConfig | None = None,
        fps: float | None = None,
    ) -> None:
        base_cfg = config or load_visual_stream_config()
        if fps is not None:
            self.config = replace(base_cfg, fps=max(0.1, min(fps, 30.0)))
        else:
            self.config = base_cfg

    async def stream_to_livekit(self, video_source: Any) -> None:
        """Stream captured visual frames into a LiveKit rtc.VideoSource."""
        try:
            from livekit import rtc

            async for frame in self.frames():
                if not frame or not frame.data:
                    continue
                try:
                    img = Image.open(io.BytesIO(frame.data)).convert("RGBA")
                    raw_bytes = img.tobytes()
                    vk_frame = rtc.VideoFrame(
                        img.width,
                        img.height,
                        rtc.VideoBufferType.RGBA,
                        raw_bytes,
                    )
                    video_source.capture_frame(vk_frame)
                except Exception as stream_err:
                    print(f"[JARVIS] visual frame push to livekit error: {stream_err}")
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            print(f"[JARVIS] stream_to_livekit aborted: {exc}")

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
        min_interval = 1.0 / max(0.1, self.config.fps)
        idle_interval = max(min_interval, self.config.idle_interval)
        last_sent_time = 0.0
        last_thumb: bytes | None = None

        consecutive_denied = 0
        while True:
            start = time.monotonic()
            try:
                image = await asyncio.to_thread(_grab_screen, self.config.monitor_index)
                if consecutive_denied > 0:
                    print("[JARVIS] 👁️ Visual stream screen capture resumed.")
                    consecutive_denied = 0

                # Fast perceptual difference detection via 32x32 grayscale thumbnail (~2ms)
                thumb = image.resize((32, 32), Image.Resampling.NEAREST).convert("L").tobytes()

                has_changed = True
                if last_thumb is not None:
                    total_diff = sum(abs(a - b) for a, b in zip(thumb, last_thumb))
                    diff_ratio = total_diff / (1024.0 * 255.0)
                    has_changed = diff_ratio >= self.config.change_threshold

                now = time.monotonic()
                time_since_last_sent = now - last_sent_time

                # Stream frame immediately if visual content changed OR idle keepalive interval expired
                if has_changed or time_since_last_sent >= idle_interval:
                    last_thumb = thumb
                    last_sent_time = now
                    jpeg_bytes = await asyncio.to_thread(_encode_jpeg, image, self.config)
                    yield VisualFrame(
                        data=jpeg_bytes,
                        mime_type="image/jpeg",
                        source="screen",
                        captured_at=time.time(),
                    )
            except Exception as exc:
                err_str = str(exc)
                if "Access is denied" in err_str or "BitBlt" in err_str:
                    consecutive_denied += 1
                    if consecutive_denied == 1:
                        print(f"[JARVIS] visual stream screen capture paused (UAC/secure desktop active): {exc}")
                    await asyncio.sleep(1.0)
                else:
                    print(f"[JARVIS] visual stream screen capture paused: {exc}")
                    await asyncio.sleep(2.0)

            elapsed = time.monotonic() - start
            await asyncio.sleep(max(0.05, min_interval - elapsed))

    async def _camera_frames(self):
        import cv2

        min_interval = 1.0 / max(0.1, self.config.fps)
        idle_interval = max(min_interval, self.config.idle_interval)
        last_sent_time = 0.0
        last_thumb: bytes | None = None

        capture = cv2.VideoCapture(self.config.camera_index)
        try:
            while True:
                start = time.monotonic()
                ok, frame = await asyncio.to_thread(capture.read)
                if ok:
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    image = Image.fromarray(rgb)

                    thumb = image.resize((32, 32), Image.Resampling.NEAREST).convert("L").tobytes()
                    has_changed = True
                    if last_thumb is not None:
                        total_diff = sum(abs(a - b) for a, b in zip(thumb, last_thumb))
                        diff_ratio = total_diff / (1024.0 * 255.0)
                        has_changed = diff_ratio >= max(0.015, self.config.change_threshold)

                    now = time.monotonic()
                    if has_changed or (now - last_sent_time) >= idle_interval:
                        last_thumb = thumb
                        last_sent_time = now
                        jpeg_bytes = await asyncio.to_thread(_encode_jpeg, image, self.config)
                        yield VisualFrame(
                            data=jpeg_bytes,
                            mime_type="image/jpeg",
                            source="camera",
                            captured_at=time.time(),
                        )
                else:
                    print("[JARVIS] visual stream camera frame unavailable")
                    await asyncio.sleep(2.0)

                elapsed = time.monotonic() - start
                await asyncio.sleep(max(0.05, min_interval - elapsed))
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
