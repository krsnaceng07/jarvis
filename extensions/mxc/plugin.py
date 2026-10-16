"""MXC infra plugin definition.

OpenClaw parity: mirrors the OpenClaw ``mxc`` infra
extension (31 files in the OpenClaw source).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin


@dataclass(frozen=True, slots=True)
class MXCPlugin(Plugin):
    """MXC infra descriptor."""

    id: str = "mxc"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "MXC data layer bridge."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook. Stub in Phase 5.15."""
        return None


mxc_plugin = MXCPlugin()
entry = mxc_plugin
