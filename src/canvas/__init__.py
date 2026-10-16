"""jarvis.canvas — OpenClaw ``src/canvas/`` parity.

The Python port mirrors the OpenClaw ``src/canvas/`` subdir.
Sub-modules land incrementally per the migration plan.

Phase N — canvas host core:
  - constants   (CANVAS_DOCUMENTS_PATH, URL helpers)
  - documents   (create_canvas_document, manifest, pruning)
  - wrap        (buildWidgetDocument — four security bridges)
  - widget_tool (createShowWidgetTool factory)
"""
from __future__ import annotations

from .constants import CANVAS_DOCUMENTS_PATH, is_canvas_document_http_path
from .documents import (
    CanvasDocumentAsset,
    CanvasDocumentCreateInput,
    CanvasDocumentEntrypointHtml,
    CanvasDocumentEntrypointPath,
    CanvasDocumentEntrypointUrl,
    CanvasDocumentManifest,
    create_canvas_document,
    resolve_canvas_http_path_to_local_path,
    resolve_retention_scope,
)
from .wrap import WIDGET_BASE_STYLES, WIDGET_THEME_TOKENS, build_widget_document
from .widget_tool import (
    SHOW_WIDGET_REQUIRED_CLIENT_CAPS,
    WIDGET_CODE_MAX_CHARS,
    WIDGET_MAX_PER_SCOPE,
    WidgetHtmlInputError,
    create_show_widget_tool,
)

__all__ = [
    # constants
    "CANVAS_DOCUMENTS_PATH",
    "is_canvas_document_http_path",
    # documents
    "CanvasDocumentAsset",
    "CanvasDocumentCreateInput",
    "CanvasDocumentEntrypointHtml",
    "CanvasDocumentEntrypointPath",
    "CanvasDocumentEntrypointUrl",
    "CanvasDocumentManifest",
    "create_canvas_document",
    "resolve_canvas_http_path_to_local_path",
    "resolve_retention_scope",
    # wrap
    "WIDGET_BASE_STYLES",
    "WIDGET_THEME_TOKENS",
    "build_widget_document",
    # widget_tool
    "SHOW_WIDGET_REQUIRED_CLIENT_CAPS",
    "WIDGET_CODE_MAX_CHARS",
    "WIDGET_MAX_PER_SCOPE",
    "WidgetHtmlInputError",
    "create_show_widget_tool",
]
