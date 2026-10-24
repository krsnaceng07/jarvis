"""Re-export audio cues from jarvis_audio_core for backward compatibility."""

from jarvis_audio_core.audio_cues import (
    SLEEP_CHIME_BYTES,
    TOOL_CHIME_BYTES,
    WAKE_CHIME_BYTES,
    create_sleep_chime,
    create_tool_chime,
    create_wake_chime,
)

__all__ = [
    "SLEEP_CHIME_BYTES",
    "TOOL_CHIME_BYTES",
    "WAKE_CHIME_BYTES",
    "create_sleep_chime",
    "create_tool_chime",
    "create_wake_chime",
]
