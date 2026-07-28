"""LLM Task infra plugin definition.

OpenClaw parity: mirrors the OpenClaw ``llm-task`` infra
extension (9 files in the OpenClaw source).
The Python port ships a focused ``Plugin`` stub so the
extension is loadable + discoverable; the full surface
lands in Phase 5.16+.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin


@dataclass(frozen=True, slots=True)
class LLMTaskPlugin(Plugin):
    """LLM Task infra descriptor."""

    id: str = "llm-task"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "Standalone LLM task executor for batch operations."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook. Stub in Phase 5.15."""
        return None


llm_task_plugin = LLMTaskPlugin()
entry = llm_task_plugin
