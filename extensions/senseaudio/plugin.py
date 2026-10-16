"""SenseAudio plugin entry — registers the media-understanding provider.

Mirrors OpenClaw's ``extensions/senseaudio/index.ts``:
the plugin registers ``senseaudio_media_understanding_provider``
with the host via ``api.register_media_understanding_provider``.

The host picks which provider to use per capability
(audio/image/video) based on each provider's
``auto_priority`` + any operator override.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin, PluginApi

from .media_understanding_provider import senseaudio_media_understanding_provider


@dataclass(slots=True)
class SenseAudioPlugin(Plugin):
    """SenseAudio media-understanding provider plugin descriptor."""

    id: str = "senseaudio"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "SenseAudio audio transcription provider (OpenAI-compatible)."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook — no-op for senseaudio (provider is load-on-demand)."""
        return None

    def register(self, api: PluginApi) -> None:
        """Register the media-understanding provider with the host.

        Mirrors OpenClaw's ``register(api)`` in
        ``extensions/senseaudio/index.ts``. The host reads
        ``api.media_understanding_providers`` afterward and
        picks the right provider per capability (audio in
        this case).
        """
        api.register_media_understanding_provider(senseaudio_media_understanding_provider)


senseaudio_plugin = SenseAudioPlugin()
entry = senseaudio_plugin
