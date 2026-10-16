"""Tests for src/plugins/codex_plugins.py.

Mirrors tests of command-plugins-management.ts in OpenClaw.
"""

from __future__ import annotations


from src.plugins.codex_plugins import (
    POLICY_REFRESH_HINT,
    parse_codex_plugins_config,
)


def test_policy_refresh_hint():
    assert "New Codex conversations pick this up automatically" in POLICY_REFRESH_HINT


def test_parse_codex_plugins_config_defaults():
    block = parse_codex_plugins_config(None)
    assert block.enabled is False
    assert block.allow_all_plugins is False
    assert block.allow_destructive_actions is True
    assert block.plugins == {}


def test_parse_codex_plugins_config_custom():
    custom_cfg = {
        "codexPlugins": {
            "enabled": True,
            "allow_all_plugins": True,
            "allow_destructive_actions": "auto",
            "plugins": {
                "google-calendar": {
                    "enabled": True,
                    "marketplaceName": "openai-curated",
                    "pluginName": "google-calendar",
                    "allow_destructive_actions": "ask",
                }
            },
        }
    }

    block = parse_codex_plugins_config(custom_cfg)
    assert block.enabled is True
    assert block.allow_all_plugins is True
    assert block.allow_destructive_actions == "auto"
    assert "google-calendar" in block.plugins
    entry = block.plugins["google-calendar"]
    assert entry.enabled is True
    assert entry.marketplace_name == "openai-curated"
    assert entry.plugin_name == "google-calendar"
    assert entry.allow_destructive_actions == "ask"
