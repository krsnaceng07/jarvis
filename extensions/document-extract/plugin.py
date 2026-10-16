"""Document Extract infra plugin definition.

OpenClaw parity: mirrors the OpenClaw ``document-extract`` infra
extension (5 files in the OpenClaw source).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin


@dataclass(frozen=True, slots=True)
class DocumentExtractPlugin(Plugin):
    """Document Extract infra descriptor."""

    id: str = "document-extract"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "Document text + structure extraction."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook. Stub in Phase 5.15."""
        return None


document_extract_plugin = DocumentExtractPlugin()
entry = document_extract_plugin
