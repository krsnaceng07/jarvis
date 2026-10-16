"""Tests for src/plugins/memory_wiki.py.

Mirrors tests of extensions/memory-wiki/src/config.ts in OpenClaw.
"""

from __future__ import annotations

import pytest

from src.plugins.memory_wiki import (
    MEMORY_WIKI_PLUGIN_ID,
    WIKI_AGENT_TOOLS,
    WIKI_REPORTS,
    WIKI_RPC_METHODS,
    WIKI_SEARCH_MODES,
    resolve_memory_wiki_config,
)


def test_memory_wiki_constants():
    assert MEMORY_WIKI_PLUGIN_ID == "memory-wiki"
    assert "wiki_status" in WIKI_AGENT_TOOLS
    assert "wiki_search" in WIKI_AGENT_TOOLS
    assert len(WIKI_AGENT_TOOLS) == 5
    assert len(WIKI_RPC_METHODS) == 3
    assert len(WIKI_REPORTS) == 9
    assert "find-person" in WIKI_SEARCH_MODES


def test_resolve_memory_wiki_config_defaults():
    cfg = resolve_memory_wiki_config(None)
    assert cfg.vaultMode == "isolated"
    assert cfg.vaultScope == "global"
    assert cfg.vaultPath == "~/.jarvis/wiki/main"
    assert cfg.renderMode == "native"
    assert cfg.searchBackend == "shared"
    assert cfg.searchCorpus == "wiki"
    assert cfg.includeCompiledDigestPrompt is False
    assert cfg.createBacklinks is True
    assert cfg.createDashboards is True


def test_resolve_memory_wiki_config_agent_scope():
    raw_cfg = {
        "vaultMode": "bridge",
        "vault": {"scope": "agent"},
    }
    cfg = resolve_memory_wiki_config(raw_cfg)
    assert cfg.vaultMode == "bridge"
    assert cfg.vaultScope == "agent"
    assert cfg.vaultPath == "~/.jarvis/wiki"


def test_resolve_memory_wiki_config_invalid_combination():
    raw_cfg = {
        "vaultMode": "unsafe-local",
        "vault": {"scope": "agent"},
    }
    with pytest.raises(ValueError, match="cannot be combined with 'unsafe-local'"):
        resolve_memory_wiki_config(raw_cfg)
