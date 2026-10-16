"""Tests for src/plugins/cli_backend.py.

Mirrors tests of src/plugins/cli-backend.types.ts in OpenClaw.
"""

from __future__ import annotations


from src.plugins.cli_backend import (
    CLI_FRESH_WATCHDOG_DEFAULTS,
    CLI_RESUME_WATCHDOG_DEFAULTS,
    resolve_cli_backend_plugin,
)


def test_cli_backend_constants():
    assert CLI_FRESH_WATCHDOG_DEFAULTS["initialSilenceTimeoutMs"] == 120000
    assert CLI_RESUME_WATCHDOG_DEFAULTS["initialSilenceTimeoutMs"] == 180000


def test_resolve_cli_backend_plugin_defaults():
    plugin = resolve_cli_backend_plugin(None)
    assert plugin.id == "custom-cli"
    assert plugin.config.command == "custom-cli"
    assert plugin.config.output == "jsonl"
    assert plugin.config.jsonlDialect == "gemini-stream-json"
    assert plugin.bundleMcp is False
    assert plugin.ownsNativeCompaction is False
    assert plugin.nativeToolMode == "absent"


def test_resolve_cli_backend_plugin_custom():
    custom_raw = {
        "id": "acme-cli",
        "config": {
            "command": "acme",
            "args": ["chat", "--output-format", "stream-json"],
            "output": "jsonl",
            "jsonlDialect": "claude-stream-json",
            "modelAliases": {"large": "acme-large-2026"},
        },
        "bundleMcp": True,
        "bundleMcpMode": "codex-config-overrides",
        "ownsNativeCompaction": True,
        "nativeToolMode": "selectable",
    }
    plugin = resolve_cli_backend_plugin(custom_raw)
    assert plugin.id == "acme-cli"
    assert plugin.config.command == "acme"
    assert plugin.config.args == ["chat", "--output-format", "stream-json"]
    assert plugin.config.jsonlDialect == "claude-stream-json"
    assert plugin.config.modelAliases == {"large": "acme-large-2026"}
    assert plugin.bundleMcp is True
    assert plugin.bundleMcpMode == "codex-config-overrides"
    assert plugin.ownsNativeCompaction is True
    assert plugin.nativeToolMode == "selectable"
