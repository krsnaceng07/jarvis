"""Document Extract plugin entrypoint.

Registers the PDF document extractor contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin
from .extractor import create_pdf_document_extractor


@dataclass(frozen=True, slots=True)
class DocumentExtractPlugin(Plugin):
    """Document Extract infra plugin."""

    id: str = "document-extract"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "Extract text and fallback page images from local document attachments."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Register the PDF document extractor."""
        if hasattr(ctx, "register_document_extractor"):
            ctx.register_document_extractor(create_pdf_document_extractor())


document_extract_plugin = DocumentExtractPlugin()
entry = document_extract_plugin
