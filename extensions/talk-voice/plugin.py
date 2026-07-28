"""Talk Voice infra plugin definition.

OpenClaw parity: mirrors the OpenClaw ``talk-voice`` infra
extension (4 files in the OpenClaw source).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin


@dataclass(frozen=True, slots=True)
class TalkVoicePlugin(Plugin):
    """Talk Voice infra descriptor."""

    id: str = "talk-voice"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "Voice talk session (push-to-talk)."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook. Stub in Phase 5.15."""
        return None


talk_voice_plugin = TalkVoicePlugin()
entry = talk_voice_plugin
