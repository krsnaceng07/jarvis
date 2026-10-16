"""OC Path infra plugin definition.

OpenClaw parity: mirrors the OpenClaw ``oc-path`` infra
extension (84 files in the OpenClaw source).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin


@dataclass(frozen=True, slots=True)
class OCPathPlugin(Plugin):
    """OC Path infra descriptor."""

    id: str = "oc-path"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "OpenClaw workspace path utilities."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook. Stub in Phase 5.15."""
        return None


oc_path_plugin = OCPathPlugin()
entry = oc_path_plugin
