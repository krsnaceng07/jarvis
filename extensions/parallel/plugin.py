"""Parallel infra plugin definition.

OpenClaw parity: mirrors the OpenClaw ``parallel`` infra
extension (21 files in the OpenClaw source).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin


@dataclass(frozen=True, slots=True)
class ParallelPlugin(Plugin):
    """Parallel infra descriptor."""

    id: str = "parallel"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "Parallel web search + extract API."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook. Stub in Phase 5.15."""
        return None


parallel_plugin = ParallelPlugin()
entry = parallel_plugin
