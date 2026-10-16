"""Workboard plugin entrypoint.

Registers the workboard tools and commands.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin
from .store import WorkboardStore
from .tools import register_workboard_tools


@dataclass(frozen=True, slots=True)
class WorkboardPlugin(Plugin):
    """Workboard extension plugin."""

    id: str = "workboard"
    kind: str = "tools"
    version: str = "0.1.0"
    description: str = "Dashboard workboard for agent-owned issues and sessions."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Register tools and commands."""
        store = WorkboardStore()
        register_workboard_tools(ctx, store)


workboard_plugin = WorkboardPlugin()
entry = workboard_plugin
