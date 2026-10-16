"""Canvas plugin entrypoint.

Registers the canvas agent tool and host.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin
from .tool import register_canvas_tool


@dataclass(frozen=True, slots=True)
class CanvasPlugin(Plugin):
    """Canvas plugin."""

    id: str = "canvas"
    kind: str = "tools"
    version: str = "0.1.0"
    description: str = "Presents hosted widget documents on paired panels."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Register canvas tool."""
        register_canvas_tool(ctx)


canvas_plugin = CanvasPlugin()
entry = canvas_plugin
