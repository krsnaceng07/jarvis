"""jarvis.config.talk_defaults — talk/voice turn-segmentation defaults.

OpenClaw parity: mirrors ``openclaw-main/src/config/talk-defaults.ts``.
"""
from __future__ import annotations

#: Platform-specific silence windows for talk/voice turn segmentation.
TALK_SILENCE_TIMEOUT_MS_BY_PLATFORM: dict = {
    "macos": 700,
    "android": 700,
    "ios": 900,
}


def describe_talk_silence_timeout_defaults() -> str:
    """Format the talk silence defaults for config help text.

    Mirrors :func:`describeTalkSilenceTimeoutDefaults`
    (``shared/config/talk-defaults.ts`).
    """
    macos = TALK_SILENCE_TIMEOUT_MS_BY_PLATFORM["macos"]
    ios = TALK_SILENCE_TIMEOUT_MS_BY_PLATFORM["ios"]
    return f"{macos} ms on macOS and Android, {ios} ms on iOS"


__all__ = [
    "TALK_SILENCE_TIMEOUT_MS_BY_PLATFORM",
    "describe_talk_silence_timeout_defaults",
]
