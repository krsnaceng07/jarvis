"""Voice Activity Detection (VAD) and High-Pass Audio Filtering for JARVIS."""

from __future__ import annotations

from collections import deque
import numpy as np


def apply_highpass_filter(
    signal: np.ndarray,
    alpha: float = 0.95,
    prev_x: float = 0.0,
    prev_y: float = 0.0,
) -> tuple[np.ndarray, float, float]:
    """Apply first-order IIR high-pass filter: y[n] = alpha * (y[n-1] + x[n] - x[n-1]).

    Attenuates low-frequency noise (e.g. laptop fan rumble <100Hz) while preserving vocal energy (>300Hz).
    """
    if signal.size == 0:
        return signal, prev_x, prev_y

    out = np.empty_like(signal, dtype=np.float32)
    curr_x = float(prev_x)
    curr_y = float(prev_y)

    for i in range(len(signal)):
        x_val = float(signal[i])
        curr_y = alpha * (curr_y + x_val - curr_x)
        curr_x = x_val
        out[i] = curr_y

    return out, curr_x, curr_y


def filter_pcm_highpass(pcm_bytes: bytes, alpha: float = 0.95) -> bytes:
    """Filter 16-bit PCM bytes with first-order IIR high-pass filter, removing DC offset."""
    if not pcm_bytes:
        return b""
    try:
        samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)
        init_x = float(samples[0]) if len(samples) > 0 else 0.0
        filtered, _, _ = apply_highpass_filter(samples, alpha=alpha, prev_x=init_x)
        clipped = np.clip(filtered, -32768, 32767).astype(np.int16)
        return clipped.tobytes()
    except Exception:
        return pcm_bytes


class EnergyVADEngine:
    """Acoustic energy VAD engine with highpass filtering, speech hangover tail, and pre-roll onset buffer."""

    def __init__(
        self,
        speech_threshold: int = 120,
        hangover_frames: int = 8,
        pre_roll_frames: int = 12,
    ) -> None:
        import os
        env_threshold = os.environ.get("JARVIS_SPEECH_THRESHOLD")
        if env_threshold is not None:
            try:
                speech_threshold = int(env_threshold)
            except ValueError:
                pass
        env_hangover = os.environ.get("JARVIS_VAD_HANGOVER_FRAMES")
        if env_hangover is not None:
            try:
                hangover_frames = int(env_hangover)
            except ValueError:
                pass
        self.speech_threshold = speech_threshold
        self.hangover_frames = max(1, hangover_frames)
        self.speech_hangover_counter = 0
        self.pre_roll_buffer: deque[bytes] = deque(maxlen=pre_roll_frames)

    def is_speech(self, pcm_chunk: bytes, buffer_preroll: bool = True) -> bool:
        """Return True if chunk contains speech energy or is in speech hangover tail."""
        if not pcm_chunk:
            return False
        try:
            filtered = self.filter_audio(pcm_chunk)
            samples = np.frombuffer(filtered, dtype=np.int16)
            if samples.size == 0:
                return False
            max_amp = int(np.max(np.abs(samples)))
            if max_amp >= self.speech_threshold:
                self.speech_hangover_counter = self.hangover_frames
                return True
            if self.speech_hangover_counter > 0:
                self.speech_hangover_counter -= 1
                return True
            if buffer_preroll:
                self.pre_roll_buffer.append(pcm_chunk)
            return False
        except Exception:
            return False

    def flush_pre_roll(self) -> list[bytes]:
        """Flush and return all buffered pre-roll chunks on speech onset."""
        flushed = list(self.pre_roll_buffer)
        self.pre_roll_buffer.clear()
        return flushed

    def filter_audio(self, pcm_chunk: bytes) -> bytes:
        """High-pass filter audio chunk to eliminate rumble and DC offset before peak computation."""
        return filter_pcm_highpass(pcm_chunk)

    def reset(self) -> None:
        """Reset internal hangover counter and pre-roll buffer."""
        self.pre_roll_buffer.clear()
        self.speech_hangover_counter = 0

    def process_chunk(self, pcm_chunk: bytes) -> bool:
        return self.is_speech(pcm_chunk)


class SimpleVADEngine(EnergyVADEngine):
    """Backwards-compatible alias for EnergyVADEngine."""
    pass


def create_vad_engine(threshold: int = 250) -> EnergyVADEngine:
    """Factory creating VAD engine."""
    return EnergyVADEngine(speech_threshold=threshold)


__all__ = [
    "EnergyVADEngine",
    "SimpleVADEngine",
    "apply_highpass_filter",
    "create_vad_engine",
    "filter_pcm_highpass",
]
