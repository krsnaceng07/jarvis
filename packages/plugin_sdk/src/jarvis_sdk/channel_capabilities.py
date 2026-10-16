"""Static channel capability flags advertised by channel plugins.

Mirrors OpenClaw's ``ChannelCapabilities``
(``src/channels/plugins/types.core.ts``). Capabilities are static
metadata: the host reads them once at discovery time and never
freshness-polls the transport for them.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ChannelTtsVoiceDeliveryCapabilities:
    """Voice delivery capabilities for a channel (TTS)."""

    synthesis_target: str | None = None
    transcodes_audio: bool = False
    audio_file_formats: tuple[str, ...] = field(default_factory=tuple)
    captioned_final_text: bool = False
    prefer_audio_file_format: str | None = None


@dataclass(frozen=True, slots=True)
class ChannelCapabilities:
    """Static capability flags for one channel plugin.

    All flags default to absent so a minimal transport-only channel
    stays honest about what it cannot render.
    """

    chat_types: tuple[str, ...] = field(default_factory=tuple)
    polls: bool = False
    reactions: bool = False
    edit: bool = False
    unsend: bool = False
    reply: bool = False
    effects: bool = False
    group_management: bool = False
    threads: bool = False
    media: bool = False
    native_commands: bool = False
    block_streaming: bool = False
    tts: ChannelTtsVoiceDeliveryCapabilities | None = None


__all__ = ["ChannelCapabilities", "ChannelTtsVoiceDeliveryCapabilities"]
