"""Tests for src/plugins/zalouser.py.

Mirrors tests of extensions/zalouser/src/config-schema.ts in OpenClaw.
"""

from __future__ import annotations


from src.plugins.zalouser import (
    ZALOUSER_CHANNEL_ID,
    ZALOUSER_PLUGIN_ID,
    ZALOUSER_TOOL_ACTIONS,
    ZALOUSER_TOOL_NAME,
    resolve_zalouser_config,
)


def test_zalouser_constants():
    assert ZALOUSER_PLUGIN_ID == "zalouser"
    assert ZALOUSER_CHANNEL_ID == "zalouser"
    assert ZALOUSER_TOOL_NAME == "zalouser"
    assert "send" in ZALOUSER_TOOL_ACTIONS
    assert "image" in ZALOUSER_TOOL_ACTIONS
    assert "friends" in ZALOUSER_TOOL_ACTIONS
    assert "groups" in ZALOUSER_TOOL_ACTIONS
    assert len(ZALOUSER_TOOL_ACTIONS) == 7


def test_resolve_zalouser_config_defaults():
    cfg = resolve_zalouser_config(None)
    assert cfg.enabled is True
    assert cfg.dmPolicy == "pairing"
    assert cfg.groupPolicy == "allowlist"
    assert cfg.allowFrom == []


def test_resolve_zalouser_config_custom():
    channels = {
        "zalouser": {
            "enabled": True,
            "dmPolicy": "allowlist",
            "allowFrom": ["user_123", "user_456"],
            "groupPolicy": "open",
            "messagePrefix": "[Zalo]",
        }
    }
    cfg = resolve_zalouser_config(channels)
    assert cfg.enabled is True
    assert cfg.dmPolicy == "allowlist"
    assert cfg.allowFrom == ["user_123", "user_456"]
    assert cfg.groupPolicy == "open"
    assert cfg.messagePrefix == "[Zalo]"
