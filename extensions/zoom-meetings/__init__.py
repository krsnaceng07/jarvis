"""JARVIS Zoom Meetings infra extension (Phase 5.15 minimum scaffold)."""
from __future__ import annotations

from .plugin import ZoomMeetingsPlugin, zoom_meetings_plugin, entry

__all__ = [
    "ZoomMeetingsPlugin",
    "zoom_meetings_plugin",
    "entry",
]
