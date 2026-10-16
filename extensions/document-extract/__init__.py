"""Document Extract extension root entrypoint."""

from __future__ import annotations

from .src.extractor import (
    MAX_EXTRACTED_TEXT_CHARS,
    MAX_RENDER_DIMENSION,
    DocumentExtractedImage,
    DocumentExtractionRequest,
    DocumentExtractionResult,
    PdfDocumentExtractor,
    PdfEngineProtocol,
    PdfPasswordError,
    create_pdf_document_extractor,
    get_default_pdf_engine,
    set_default_pdf_engine,
)
from .src.plugin import DocumentExtractPlugin, entry, document_extract_plugin

__all__ = [
    "DocumentExtractPlugin",
    "DocumentExtractedImage",
    "DocumentExtractionRequest",
    "DocumentExtractionResult",
    "MAX_EXTRACTED_TEXT_CHARS",
    "MAX_RENDER_DIMENSION",
    "PdfDocumentExtractor",
    "PdfEngineProtocol",
    "PdfPasswordError",
    "create_pdf_document_extractor",
    "document_extract_plugin",
    "entry",
    "get_default_pdf_engine",
    "set_default_pdf_engine",
]
