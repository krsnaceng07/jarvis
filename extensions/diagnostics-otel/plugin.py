"""Diagnostics OTel infra plugin definition.

OpenClaw parity: mirrors the OpenClaw ``diagnostics-otel`` infra
extension (28 files in the OpenClaw source).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin


@dataclass(frozen=True, slots=True)
class DiagnosticsOTelPlugin(Plugin):
    """Diagnostics OTel infra descriptor."""

    id: str = "diagnostics-otel"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "OpenTelemetry diagnostics exporter."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook. Stub in Phase 5.15."""
        return None


diagnostics_otel_plugin = DiagnosticsOTelPlugin()
entry = diagnostics_otel_plugin
