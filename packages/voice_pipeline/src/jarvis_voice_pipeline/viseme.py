"""packages/voice_pipeline/src/jarvis_voice_pipeline/viseme.py

Audio spectrum and RMS loudness level analysis for HUD visualizers and terminal bars.
"""

from __future__ import annotations

import numpy as np

_LEVEL_FLOOR = 60.0
_LEVEL_FULL = 2600.0


def pcm_level(samples) -> float:
    """Map a block of int16 PCM samples to a 0.0–1.0 loudness level."""
    try:
        x = np.asarray(samples, dtype=np.float32)
        if x.size == 0:
            return 0.0
        rms = float(np.sqrt(np.mean(x * x)))
    except Exception:
        return 0.0
    if rms <= _LEVEL_FLOOR:
        return 0.0
    return min(1.0, (rms - _LEVEL_FLOOR) / (_LEVEL_FULL - _LEVEL_FLOOR))
