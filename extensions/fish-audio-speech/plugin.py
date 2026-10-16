"""Fish Audio speech provider plugin entry point."""

from __future__ import annotations

from typing import Any

from .src.speech_provider import build_fish_audio_speech_provider


def _register(api: Any) -> None:
    if hasattr(api, "register_speech_provider"):
        api.register_speech_provider(build_fish_audio_speech_provider())


def get_plugin_entry() -> dict[str, Any]:
    return {
        "id": "fish-audio-speech",
        "name": "Fish Audio",
        "speechProviders": [build_fish_audio_speech_provider()],
        "register": _register,
    }


entry = get_plugin_entry()

