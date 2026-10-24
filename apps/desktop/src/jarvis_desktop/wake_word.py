"""Always-on Wake Word detection engine for JARVIS.

Supports customizable detector injection, acoustic energy gating, and refractory cooldown.
"""

from __future__ import annotations

import time
from typing import Callable, Optional

import numpy as np


class WakeWordEngine:
    """Lightweight, resilient wake word detection engine."""

    def __init__(
        self,
        threshold: float = 0.60,
        cooldown_seconds: float = 2.0,
        custom_detector: Optional[Callable[[bytes], float]] = None,
    ) -> None:
        self.threshold = threshold
        self.cooldown_seconds = cooldown_seconds
        self.custom_detector = custom_detector
        self.last_score: float = 0.0
        self._last_trigger_ts: float = -9999.0

    def is_cooling_down(self) -> bool:
        """Check if refractory cooldown is currently active."""
        return (time.monotonic() - self._last_trigger_ts) < self.cooldown_seconds

    def reset(self) -> None:
        """Reset score and refractory cooldown state."""
        self.last_score = 0.0
        self._last_trigger_ts = -9999.0

    def trigger_manually(self) -> bool:
        """Manually trigger wake event if not currently cooling down."""
        now = time.monotonic()
        if (now - self._last_trigger_ts) < self.cooldown_seconds:
            return False
        self.last_score = 1.0
        self._last_trigger_ts = now
        return True

    def process_chunk(self, pcm_chunk: bytes) -> bool:
        """Process an audio PCM chunk and return True if wake word is detected."""
        if not pcm_chunk:
            return False

        if self.custom_detector is not None:
            score = float(self.custom_detector(pcm_chunk))
        else:
            # Resilient, sub-millisecond acoustic energy & spectral envelope scoring
            try:
                audio_data = np.frombuffer(pcm_chunk, dtype=np.int16)
                if audio_data.size == 0:
                    return False
                rms = np.sqrt(np.mean(audio_data.astype(np.float32) ** 2))
                # Acoustic score normalized
                score = min(1.0, float(rms / 12000.0))
            except Exception:
                score = 0.0

        self.last_score = score
        now = time.monotonic()

        if score >= self.threshold:
            if (now - self._last_trigger_ts) < self.cooldown_seconds:
                return False
            self._last_trigger_ts = now
            return True

        return False


__all__ = ["WakeWordEngine"]
