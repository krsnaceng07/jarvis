"""TTS Local CLI infra plugin definition.

OpenClaw parity: mirrors the OpenClaw ``tts-local-cli`` infra
extension (6 files in the OpenClaw source).
The Python port ships a focused ``Plugin`` stub so the
extension is loadable + discoverable; the full surface
lands in Phase 5.16+.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin


@dataclass(frozen=True, slots=True)
class TTSLocalCLIPlugin(Plugin):
    """TTS Local CLI infra descriptor."""

    id: str = "tts-local-cli"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "Local TTS via system CLI (espeak, say, etc.)."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook. Stub in Phase 5.15."""
        return None


tts_local_cli_plugin = TTSLocalCLIPlugin()
entry = tts_local_cli_plugin
