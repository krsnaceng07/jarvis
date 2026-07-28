"""File Transfer infra plugin definition.

OpenClaw parity: mirrors the OpenClaw ``file-transfer`` infra
extension (43 files in the OpenClaw source).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin


@dataclass(frozen=True, slots=True)
class FileTransferPlugin(Plugin):
    """File Transfer infra descriptor."""

    id: str = "file-transfer"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "P2P file transfer (LAN + remote)."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook. Stub in Phase 5.15."""
        return None


file_transfer_plugin = FileTransferPlugin()
entry = file_transfer_plugin
