"""JARVIS Diagnostics OTel infra extension (Phase 5.15 minimum scaffold)."""
from __future__ import annotations

from .plugin import DiagnosticsOTelPlugin, diagnostics_otel_plugin, entry

__all__ = [
    "DiagnosticsOTelPlugin",
    "diagnostics_otel_plugin",
    "entry",
]
