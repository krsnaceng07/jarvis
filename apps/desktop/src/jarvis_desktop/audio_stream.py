"""Audio stream helpers for desktop audio hardware capture and playback."""

from __future__ import annotations

from typing import Any, Optional, Tuple

try:
    import numpy as np
    import sounddevice as sd
    if hasattr(sd, "_array"):
        def _safe_sd_array(buffer, channels, dtype):
            return np.frombuffer(buffer, dtype=dtype).reshape(-1, channels)
        sd._array = _safe_sd_array
except ImportError:
    sd = None  # type: ignore


def open_input_stream(callback: Any) -> Tuple[Optional[Any], int, int]:
    """Open a default microphone input stream."""
    sample_rate = 16000
    channels = 1
    if sd is None:
        return None, sample_rate, channels
    try:
        stream = sd.InputStream(
            samplerate=sample_rate,
            channels=channels,
            dtype="int16",
            callback=callback,
        )
        return stream, sample_rate, channels
    except Exception:
        return None, sample_rate, channels


def open_output_stream(sample_rate: int = 24000, channels: int = 1) -> Tuple[Optional[Any], int, int]:
    """Open a default speaker output stream."""
    if sd is None:
        return None, sample_rate, channels
    try:
        stream = sd.RawOutputStream(
            samplerate=sample_rate,
            channels=channels,
            dtype="int16",
        )
        return stream, sample_rate, channels
    except Exception:
        return None, sample_rate, channels


def prepare_audio_for_output(
    pcm_bytes: bytes,
    target_sr: int = 24000,
    target_ch: int = 1,
) -> bytes:
    """Pass-through or align PCM bytes for output device."""
    return pcm_bytes


__all__ = [
    "open_input_stream",
    "open_output_stream",
    "prepare_audio_for_output",
]
