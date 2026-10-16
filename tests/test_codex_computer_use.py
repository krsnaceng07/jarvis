"""Tests for src/plugins/codex_computer_use.py.

Mirrors tests of computer-use.ts in OpenClaw.
"""

from __future__ import annotations



from src.plugins.codex_computer_use import (
    DEFAULT_COMPUTER_USE_MCP_SERVER_NAME,
    DEFAULT_COMPUTER_USE_PLUGIN_NAME,
    resolve_codex_computer_use_config,
)


def test_resolve_codex_computer_use_config_defaults():
    cfg = resolve_codex_computer_use_config(None)
    assert cfg.enabled is False
    assert cfg.autoInstall is False
    assert cfg.pluginName == DEFAULT_COMPUTER_USE_PLUGIN_NAME
    assert cfg.mcpServerName == DEFAULT_COMPUTER_USE_MCP_SERVER_NAME
    assert cfg.pluginCacheMode == "independent"


def test_resolve_codex_computer_use_config_inferred_enabled():
    custom_plugin_cfg = {"computerUse": {"autoInstall": True}}
    cfg = resolve_codex_computer_use_config(custom_plugin_cfg)
    assert cfg.enabled is True
    assert cfg.autoInstall is True


def test_resolve_codex_computer_use_config_env_override(monkeypatch):
    monkeypatch.setenv("OPENCLAW_CODEX_COMPUTER_USE", "true")
    monkeypatch.setenv("OPENCLAW_CODEX_COMPUTER_USE_AUTO_INSTALL", "1")
    monkeypatch.setenv("OPENCLAW_CODEX_COMPUTER_USE_PLUGIN_CACHE_MODE", "shared")

    cfg = resolve_codex_computer_use_config(None)
    assert cfg.enabled is True
    assert cfg.autoInstall is True
    assert cfg.pluginCacheMode == "shared"
