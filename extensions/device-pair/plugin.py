"""Device Pairing infra plugin definition.

OpenClaw parity: mirrors the OpenClaw ``device-pair`` infra
extension (14 files in the OpenClaw source).
The Python port ships a focused ``Plugin`` stub so the
extension is loadable + discoverable; the full surface
lands in Phase 5.16+.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin


@dataclass(frozen=True, slots=True)
class DevicePairingPlugin(Plugin):
    """Device Pairing infra descriptor."""

    id: str = "device-pair"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "Local device pairing flow (QR + approval + binding)."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook. Stub in Phase 5.15."""
        return None


device_pair_plugin = DevicePairingPlugin()
entry = device_pair_plugin
