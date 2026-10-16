"""jarvis.canvas.widget_tool — show_widget agent tool.

OpenClaw parity: mirrors ``openclaw-main/src/canvas/widget-tool.ts``.

``createShowWidgetTool`` factory pattern:
  - Requires the ``inline-widgets`` client capability on the Gateway connection.
  - Validates ``widget_code`` is non-empty and within the 262,144-character limit.
  - Detects SVG vs HTML and selects the right body class.
  - Delegates document materialization to ``create_canvas_document``.
  - Returns a structured Canvas preview handle identical to OpenClaw's
    ``jsonResult({ kind: "canvas", presentation, view, text })``.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from .documents import (
    CanvasDocumentCreateInput,
    CanvasDocumentEntrypointHtml,
    create_canvas_document,
    resolve_retention_scope,
)
from .wrap import build_widget_document

SHOW_WIDGET_REQUIRED_CLIENT_CAPS: list[str] = ["inline-widgets"]
WIDGET_CODE_MAX_CHARS = 262_144
WIDGET_MAX_PER_SCOPE = 32


class WidgetHtmlInputError(ValueError):
    """Input error for oversized or invalid widget HTML."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.name = "ToolInputError"


def _assert_widget_html_size(html: str, max_chars: int, input_name: str = "widget_code") -> None:
    """Mirror assertWidgetHtmlSize from plugin-sdk/widget-html.ts."""
    if len(html) > max_chars:
        raise WidgetHtmlInputError(
            f"{input_name} exceeds maximum size ({max_chars} characters)"
        )


def create_show_widget_tool(
    *,
    session_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    state_dir: Optional[str] = None,
) -> dict:
    """Create the show_widget agent tool.

    OpenClaw parity: mirrors ``createShowWidgetTool`` in ``widget-tool.ts``.

    Returns an AgentTool-compatible dict with name, label, description,
    parameters (JSON Schema), requiredClientCaps, and execute coroutine.
    """
    retention_scope = resolve_retention_scope(session_id, agent_id)

    parameters = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Short title shown with the inline preview and in the hosted document title.",
            },
            "widget_code": {
                "type": "string",
                "description": (
                    "Self-contained HTML or SVG. Input beginning with <svg is rendered "
                    "in SVG mode. Maximum 262,144 characters."
                ),
            },
        },
        "required": ["title", "widget_code"],
    }

    async def _execute(
        tool_call_id: str,
        args: dict,
        signal: Any = None,
        on_update: Any = None,
    ) -> Any:
        title = (args.get("title") or "").strip()
        raw_widget_code = args.get("widget_code") or ""

        if not title:
            raise WidgetHtmlInputError("title required")

        if not raw_widget_code.strip():
            raise WidgetHtmlInputError("widget_code required")

        _assert_widget_html_size(raw_widget_code, WIDGET_CODE_MAX_CHARS)

        widget_code = raw_widget_code.strip()

        input_doc = CanvasDocumentCreateInput(
            kind="html_bundle",
            title=title,
            entrypoint=CanvasDocumentEntrypointHtml(
                type="html",
                value=build_widget_document(title, widget_code),
            ),
            surface="assistant_message",
            retention_scope=retention_scope,
            # Direct navigation must not run widget script as the host origin.
            csp_sandbox="scripts",
        )

        document = create_canvas_document(
            input_doc,
            state_dir=state_dir,
            max_documents_per_scope=WIDGET_MAX_PER_SCOPE,
        )

        result = {
            "kind": "canvas",
            "presentation": {
                "target": "assistant_message",
                "title": title,
                "sandbox": "scripts",
            },
            "view": {
                "id": document.id,
                "url": document.entry_url,
            },
            "text": f"Widget hosted at {document.entry_url}",
        }
        return {"content": [{"type": "text", "text": json.dumps(result)}]}

    return {
        "name": "show_widget",
        "label": "Show Widget",
        "description": (
            "Show interactive self-contained HTML or SVG widget on the user's current surface. "
            "Inline everything; no external resources. "
            "Pre-themed: bare button, input, select, textarea, table, code, h1-h3 already styled. "
            "Helper classes: .card, .badge (.ok/.warn/.danger/.info), .metric, .muted, .row; "
            "button.primary = the one main action. "
            "Theme vars (auto light/dark, live host sync): "
            "--surface --card --elevated --text --text-strong --muted --border --border-strong "
            "--accent (links/focus/highlight) --accent-fill (primary bg) --accent-fg "
            "--ok --warn --danger --info (each with -subtle tint) --radius --font-body --font-mono. "
            "Colors ONLY via these vars — never hex/rgb/hsl. "
            "Page background stays transparent. "
            "Web chat: sendPrompt(text) sends text as the user's message — wire to buttons; "
            "works only after a real click inside the widget (never call automatically; "
            "slash commands rejected).",
        ),
        "parameters": parameters,
        "required_client_caps": SHOW_WIDGET_REQUIRED_CLIENT_CAPS,
        "execute": _execute,
    }


__all__ = [
    "SHOW_WIDGET_REQUIRED_CLIENT_CAPS",
    "WIDGET_CODE_MAX_CHARS",
    "WIDGET_MAX_PER_SCOPE",
    "WidgetHtmlInputError",
    "create_show_widget_tool",
]
