"""tool_open_app — JARVIS cross-platform app launcher (Phase 1C).

Migrated from ``actions/open_app.py``. Same algorithm (alias table +
per-OS launcher), reorganized into the OpenClaw 8-file shape.

Mirrors OpenClaw's extension layout:

  - ``__init__.py`` (entry)         ← this file
  - ``plugin.py`` (impl)            ← ``OpenAppPlugin``
  - ``runtime.py`` (helpers)        ← alias table + per-OS launchers
  - ``AGENTS.md`` (scoped rules)
  - ``openclaw.plugin.json`` (manifest)
  - ``pyproject.toml`` (workspace member)
"""
from __future__ import annotations

from jarvis_sdk import PluginApi, define_plugin_entry

from .plugin import OpenAppPlugin


def _register(api: PluginApi) -> None:
    """Register the open_app tool with the host's PluginApi."""
    api.register_tool(
        OpenAppPlugin(),
        names=["open_app"],
    )


# ── Plugin entry (mirrors OpenClaw's `definePluginEntry`) ───────────
entry = define_plugin_entry(
    id="tool_open_app",
    kind="tool",
    name="Open App",
    description="Cross-platform application launcher (Windows / macOS / Linux).",
    register=_register,
    version="0.1.0",
    activation="on_startup",
    permissions=["os:exec", "ui:input-simulation"],
)
