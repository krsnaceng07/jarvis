"""Audio device management, real-time streaming, and capture pipeline for JARVIS."""

from dataclasses import dataclass

from .audio_cues import (
    SLEEP_CHIME_BYTES,
    TOOL_CHIME_BYTES,
    WAKE_CHIME_BYTES,
    create_sleep_chime,
    create_tool_chime,
    create_wake_chime,
)


@dataclass
class AudioFormat:
    sample_rate: int = 16000
    channels: int = 1
    sample_width: int = 2


class AudioPipeline:
    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self.is_running = False

    def start(self) -> None:
        self.is_running = True

    def stop(self) -> None:
        self.is_running = False


__all__ = [
    "AudioFormat",
    "AudioPipeline",
    "SLEEP_CHIME_BYTES",
    "TOOL_CHIME_BYTES",
    "WAKE_CHIME_BYTES",
    "create_sleep_chime",
    "create_tool_chime",
    "create_wake_chime",
]
