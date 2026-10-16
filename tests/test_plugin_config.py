"""Tests for src/plugins/plugin_config.py.

Mirrors tests of plugins/config-state.ts in OpenClaw.
"""

from __future__ import annotations


from src.plugins.plugin_config import (
    is_plugin_enabled,
    normalize_plugins_config,
)


def test_normalize_plugins_config_defaults():
    cfg = normalize_plugins_config(None)
    assert cfg.enabled is True
    assert cfg.allow is None
    assert cfg.deny == []
    assert cfg.slots == {}
    assert cfg.entries == {}


def test_normalize_plugins_config_custom():
    raw = {
        "plugins": {
            "enabled": True,
            "allow": ["voice-call", "memory-core"],
            "deny": ["untrusted-plugin"],
            "slots": {"memory": "memory-core"},
            "entries": {
                "voice-call": {
                    "enabled": True,
                    "config": {"provider": "twilio"},
                }
            },
        }
    }

    norm = normalize_plugins_config(raw)
    assert norm.enabled is True
    assert norm.allow == ["voice-call", "memory-core"]
    assert norm.deny == ["untrusted-plugin"]
    assert norm.slots == {"memory": "memory-core"}
    assert norm.entries["voice-call"].config == {"provider": "twilio"}


def test_is_plugin_enabled_deny_wins():
    raw = {
        "plugins": {
            "allow": ["voice-call"],
            "deny": ["voice-call"],
        }
    }
    norm = normalize_plugins_config(raw)
    assert is_plugin_enabled("voice-call", norm) is False


def test_is_plugin_enabled_allowlist_restriction():
    raw = {
        "plugins": {
            "allow": ["voice-call"],
        }
    }
    norm = normalize_plugins_config(raw)
    assert is_plugin_enabled("voice-call", norm) is True
    assert is_plugin_enabled("other-plugin", norm) is False


def test_is_plugin_enabled_slot_selection_force_activates():
    raw = {
        "plugins": {
            "allow": ["voice-call"],  # memory-core not in allow
            "slots": {"memory": "memory-core"},
        }
    }
    norm = normalize_plugins_config(raw)
    # Memory slot selection force activates memory-core even if not in allow list
    assert is_plugin_enabled("memory-core", norm) is True
