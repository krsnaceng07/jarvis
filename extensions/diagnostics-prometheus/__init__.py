"""JARVIS Diagnostics Prometheus infra extension (Phase 5.15 minimum scaffold)."""

from __future__ import annotations

from .plugin import DiagnosticsPrometheusPlugin, diagnostics_prometheus_plugin, entry

__all__ = [
    "DiagnosticsPrometheusPlugin",
    "diagnostics_prometheus_plugin",
    "entry",
]
