"""packages/voice_pipeline/src/jarvis_voice_pipeline/echo.py

Echo Guard: Distinguishes user speech from speaker feedback via spectral subtraction.
Prevents JARVIS from hearing its own voice while allowing immediate user barge-in.
"""

from __future__ import annotations

import time
import numpy as np

_BAND_EDGES = (200, 400, 700, 1100, 1700, 2600, 3800, 5200, 7000)
_HISTORY_S = 1.5
_MIN_LEVEL = 0.06
_MIN_USER = 0.15
_HEAD_Q = 97
_HEAD_MULT = 1.15
_UNRELIABLE_FLOOR = 0.22
_BLOCKS_NORMAL = 5
_BLOCKS_NOISY = 12
_FLOOR_WINDOW = 60
_FLOOR_Q = 35
_WARMUP = 16
_RELEARN_RUN = 28


def band_energies(pcm, sr: int) -> np.ndarray:
    """Raw energy per speech band — spectral fingerprint."""
    x = np.asarray(pcm, dtype=np.float32)
    if x.size < 64:
        return np.zeros(len(_BAND_EDGES) - 1, dtype=np.float32)
    x = x - x.mean()
    n = 1 << (int(x.size) - 1).bit_length()
    mag = np.abs(np.fft.rfft(x * np.hanning(x.size), n=n))
    freqs = np.fft.rfftfreq(n, 1.0 / sr)
    out = np.empty(len(_BAND_EDGES) - 1, dtype=np.float32)
    for i in range(len(_BAND_EDGES) - 1):
        m = (freqs >= _BAND_EDGES[i]) & (freqs < _BAND_EDGES[i + 1])
        out[i] = float(mag[m].sum())
    return out


class EchoGuard:
    """Classifies microphone blocks while the assistant is speaking."""

    def __init__(self) -> None:
        self._hist: list[tuple[float, np.ndarray, float]] = []
        self._gain = 0.6
        self._seen = 0
        self._last_sim = 0.0
        self._residuals: list[float] = []
        self._floor = 0.10
        self._run = 0
        self._head = 0.13

    @property
    def gain(self) -> float:
        return self._gain

    @property
    def floor(self) -> float:
        return self._floor

    @property
    def reliable(self) -> bool:
        return self._floor < _UNRELIABLE_FLOOR

    @property
    def threshold(self) -> float:
        return max(_MIN_USER, self._head * _HEAD_MULT)

    @property
    def last_similarity(self) -> float:
        return self._last_sim

    def reset(self) -> None:
        self._hist.clear()
        self._last_sim = 0.0

    def note_output(self, pcm, sr: int, level: float, when: float | None = None) -> None:
        try:
            t = time.monotonic() if when is None else when
            self._hist.append((t, band_energies(pcm, sr), float(level)))
            cutoff = t - _HISTORY_S
            if len(self._hist) > 8:
                self._hist = [h for h in self._hist if h[0] >= cutoff]
        except Exception:
            pass

    def note_input(self, pcm, sr: int, level: float, when: float | None = None) -> None:
        """Safe input observation hook for microphone audio frames."""
        pass

    def is_user_speech(self, pcm, sr: int, level: float, when: float | None = None) -> bool:
        try:
            if level < _MIN_LEVEL:
                if self._hist and max(h[2] for h in self._hist) > 0.15:
                    self._residuals.append(0.0)
                    if len(self._residuals) > _FLOOR_WINDOW:
                        del self._residuals[:-_FLOOR_WINDOW]
                    if len(self._residuals) >= _WARMUP:
                        self._floor = float(np.percentile(self._residuals, _FLOOR_Q))
                        self._head = float(np.percentile(self._residuals, _HEAD_Q))
                self._run = 0
                return False
            if not self._hist:
                return True

            t = time.monotonic() if when is None else when
            bands = band_energies(pcm, sr)
            total = float(bands.sum())
            if total <= 1e-9:
                return False

            best_res, best_level = 1.0, 0.0
            for ts, ref, ref_level in self._hist:
                if ts > t or t - ts > _HISTORY_S:
                    continue
                denom = float(np.dot(ref, ref))
                if denom < 1e-12:
                    continue
                alpha = max(0.0, float(np.dot(bands, ref)) / denom)
                residual = np.maximum(bands - alpha * ref, 0.0)
                ratio = float(residual.sum()) / total
                if ratio < best_res:
                    best_res, best_level = ratio, ref_level
            self._last_sim = 1.0 - best_res

            if best_level <= 0.0:
                return True

            warming = len(self._residuals) < _WARMUP
            thr = self.threshold
            speech = (not warming) and best_res >= thr

            if speech:
                self._run += 1
                if self._run > _RELEARN_RUN:
                    self._residuals.clear()
                    self._run = 0
                    return False
                return True

            self._run = 0
            self._residuals.append(best_res)
            if len(self._residuals) > _FLOOR_WINDOW:
                del self._residuals[:-_FLOOR_WINDOW]
            if len(self._residuals) >= _WARMUP:
                self._floor = float(np.percentile(self._residuals, _FLOOR_Q))
                self._head = float(np.percentile(self._residuals, _HEAD_Q))
            if warming:
                return False

            if best_res <= self._floor * 1.15 and best_level > 0.05:
                obs = level / max(best_level, 1e-6)
                self._gain += (min(obs, 3.0) - self._gain) * 0.08
                self._seen = min(self._seen + 1, 999)
            return False
        except Exception:
            return False
