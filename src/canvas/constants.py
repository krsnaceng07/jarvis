"""jarvis.canvas.constants — stable canvas paths and capability surfaces.

OpenClaw parity: mirrors ``openclaw-main/src/canvas/constants.ts``.
"""
from __future__ import annotations

# Stable Gateway path used by chat clients for hosted Canvas content.
_CANVAS_HOST_PATH = "/__jarvis__/canvas"
CANVAS_DOCUMENTS_PATH = f"{_CANVAS_HOST_PATH}/documents"


def is_canvas_document_http_path(pathname: str) -> bool:
    """Returns True only for the core-owned Canvas document subtree."""
    return pathname.startswith(f"{CANVAS_DOCUMENTS_PATH}/")


__all__ = [
    "CANVAS_DOCUMENTS_PATH",
    "is_canvas_document_http_path",
]
