"""Canvas extension package."""

from __future__ import annotations

from .a2ui_jsonl import format_a2ui_jsonl, parse_a2ui_jsonl
from .board_widget import generate_board_widget
from .config import CanvasConfig, CanvasHostConfig, resolve_canvas_config
from .doctor import handle_canvas_cli, repair_canvas_config
from .plugin import CanvasPlugin, canvas_plugin, entry
from .tool import execute_canvas_tool, register_canvas_tool

__all__ = [
    "CanvasConfig",
    "CanvasHostConfig",
    "CanvasPlugin",
    "canvas_plugin",
    "entry",
    "execute_canvas_tool",
    "format_a2ui_jsonl",
    "generate_board_widget",
    "handle_canvas_cli",
    "parse_a2ui_jsonl",
    "register_canvas_tool",
    "repair_canvas_config",
    "resolve_canvas_config",
]
