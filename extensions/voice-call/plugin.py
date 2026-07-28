"""Voice Call infra plugin definition.

OpenClaw parity: mirrors the OpenClaw ``voice-call`` infra
extension (129 files in the OpenClaw source).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin


@dataclass(frozen=True, slots=True)
class VoiceCallPlugin(Plugin):
    """Voice Call infra descriptor."""

    id: str = "voice-call"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "Voice call bridge (Twilio + SIP)."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook. Stub in Phase 5.15."""
        return None


voice_call_plugin = VoiceCallPlugin()
entry = voice_call_plugin
