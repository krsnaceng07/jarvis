"""Audio earcon chimes and cues for JARVIS voice interactions.

Generates 24kHz 16-bit mono PCM buffers for zero dead-air feedback:
- TOOL_CHIME_BYTES: 140ms earcon chime played when tools execute (6720 bytes)
- WAKE_CHIME_BYTES: 180ms chime played when waking from standby (8640 bytes)
- SLEEP_CHIME_BYTES: 180ms chime played when entering standby (8640 bytes)
"""

from __future__ import annotations

import math
import struct


def _generate_pcm_chime(
    frequencies: list[float],
    duration_s: float,
    sample_rate: int = 24000,
    volume: float = 0.25,
) -> bytes:
    """Generate 16-bit mono PCM sine wave chime with smooth cosine envelope."""
    total_samples = int(duration_s * sample_rate)
    pcm = bytearray()
    if total_samples <= 0:
        return b""

    for i in range(total_samples):
        t = i / sample_rate
        # Smooth attack (first 10ms) and decay (last 30ms) envelope
        attack_s = 0.010
        decay_s = 0.030
        if t < attack_s:
            env = t / attack_s
        elif t > (duration_s - decay_s):
            env = max(0.0, (duration_s - t) / decay_s)
        else:
            env = 1.0

        val = 0.0
        for freq in frequencies:
            val += math.sin(2.0 * math.pi * freq * t)
        val = (val / len(frequencies)) * env * volume
        sample = max(-32768, min(32767, int(val * 32767)))
        pcm.extend(struct.pack("<h", sample))

    return bytes(pcm)


def create_tool_chime(sample_rate: int = 24000) -> bytes:
    """Create 140ms rising chime (880Hz -> 1320Hz) for tool execution start."""
    return _generate_pcm_chime([880.0, 1320.0], duration_s=0.14, sample_rate=sample_rate)


def create_wake_chime(sample_rate: int = 24000) -> bytes:
    """Create 180ms pleasant rising chime (523.25Hz -> 659.25Hz -> 783.99Hz, C Major triad)."""
    return _generate_pcm_chime([523.25, 659.25, 783.99], duration_s=0.18, sample_rate=sample_rate)


def create_sleep_chime(sample_rate: int = 24000) -> bytes:
    """Create 180ms descending chime (783.99Hz -> 523.25Hz) for sleep / standby."""
    return _generate_pcm_chime([783.99, 659.25, 523.25], duration_s=0.18, sample_rate=sample_rate)


# Canonical pre-computed 24kHz 16-bit mono buffers
TOOL_CHIME_BYTES: bytes = create_tool_chime(24000)
WAKE_CHIME_BYTES: bytes = create_wake_chime(24000)
SLEEP_CHIME_BYTES: bytes = create_sleep_chime(24000)

__all__ = [
    "SLEEP_CHIME_BYTES",
    "TOOL_CHIME_BYTES",
    "WAKE_CHIME_BYTES",
    "create_sleep_chime",
    "create_tool_chime",
    "create_wake_chime",
]
