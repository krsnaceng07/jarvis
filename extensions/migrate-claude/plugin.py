"""Migrate Claude infra plugin definition.

OpenClaw parity: mirrors the OpenClaw ``migrate-claude`` infra
extension (14 files in the OpenClaw source).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin


@dataclass(frozen=True, slots=True)
class MigrateClaudePlugin(Plugin):
    """Migrate Claude infra descriptor."""

    id: str = "migrate-claude"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "Claude artifacts migration tool."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook. Stub in Phase 5.15."""
        return None


migrate_claude_plugin = MigrateClaudePlugin()
entry = migrate_claude_plugin
