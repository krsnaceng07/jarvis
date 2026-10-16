"""OpenShell infra plugin definition.

OpenClaw parity: mirrors the OpenClaw ``openshell`` infra
extension (17 files in the OpenClaw source).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin


@dataclass(frozen=True, slots=True)
class OpenShellPlugin(Plugin):
    """OpenShell infra descriptor."""

    id: str = "openshell"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "OpenShell sandboxed shell execution."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook. Stub in Phase 5.15."""
        return None


openshell_plugin = OpenShellPlugin()
entry = openshell_plugin
