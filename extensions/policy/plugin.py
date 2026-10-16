"""Policy infra plugin definition.

OpenClaw parity: mirrors the OpenClaw ``policy`` infra
extension (69 files in the OpenClaw source).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin


@dataclass(frozen=True, slots=True)
class PolicyPlugin(Plugin):
    """Policy infra descriptor."""

    id: str = "policy"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "Policy enforcement (RBAC + scopes)."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook. Stub in Phase 5.15."""
        return None


policy_plugin = PolicyPlugin()
entry = policy_plugin
