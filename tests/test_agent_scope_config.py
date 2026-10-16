"""Tests for src/agents/agent_scope_config.py.

Mirrors the behavioral contracts from ``src/agents/agent-scope-config.ts``
test surface:
- list_agent_entries / list_agent_ids
- resolve_default_agent_id (single, first, missing, multiple-defaults)
- resolve_agent_config (merge, modelPolicy, contextLimits)
- resolve_agent_workspace_dir cascade
- resolve_agent_dir cascade
"""

from __future__ import annotations

import pytest

from src.agents.agent_scope_config import (
    list_agent_entries,
    list_agent_ids,
    resolve_agent_config,
    resolve_agent_context_limits,
    resolve_agent_dir,
    resolve_agent_workspace_dir,
    resolve_default_agent_id,
)
from src.agents.agent_dir_registry import clear_agent_dir_registry


@pytest.fixture(autouse=True)
def _reset_registry():
    """Ensure the dir registry is clean for each test."""
    yield
    clear_agent_dir_registry()


# ---------------------------------------------------------------------------
# list_agent_entries
# ---------------------------------------------------------------------------


def test_list_agent_entries_empty_cfg():
    assert list_agent_entries({}) == []


def test_list_agent_entries_no_agents_key():
    assert list_agent_entries({"channels": {}}) == []


def test_list_agent_entries_list_is_not_list():
    assert list_agent_entries({"agents": {"list": "bad"}}) == []


def test_list_agent_entries_filters_none():
    cfg = {"agents": {"list": [None, {"id": "alice"}, None, {"id": "bob"}]}}
    entries = list_agent_entries(cfg)
    assert len(entries) == 2
    assert entries[0]["id"] == "alice"


# ---------------------------------------------------------------------------
# list_agent_ids
# ---------------------------------------------------------------------------


def test_list_agent_ids_empty_returns_default():
    assert list_agent_ids({}) == ["main"]


def test_list_agent_ids_deduplication():
    cfg = {"agents": {"list": [{"id": "alice"}, {"id": "ALICE"}, {"id": "bob"}]}}
    ids = list_agent_ids(cfg)
    assert ids == ["alice", "bob"]


def test_list_agent_ids_skips_invalid_id():
    cfg = {"agents": {"list": [{"id": ""}, {"id": "alice"}]}}
    ids = list_agent_ids(cfg)
    assert "alice" in ids
    assert "" not in ids


# ---------------------------------------------------------------------------
# resolve_default_agent_id
# ---------------------------------------------------------------------------


def test_resolve_default_agent_id_no_agents():
    assert resolve_default_agent_id({}) == "main"


def test_resolve_default_agent_id_first_entry():
    cfg = {"agents": {"list": [{"id": "alice"}, {"id": "bob"}]}}
    assert resolve_default_agent_id(cfg) == "alice"


def test_resolve_default_agent_id_explicit_default():
    cfg = {
        "agents": {
            "list": [
                {"id": "alice"},
                {"id": "bob", "default": True},
            ]
        }
    }
    assert resolve_default_agent_id(cfg) == "bob"


def test_resolve_default_agent_id_uppercase_normalized():
    cfg = {"agents": {"list": [{"id": "MAIN"}]}}
    assert resolve_default_agent_id(cfg) == "main"


# ---------------------------------------------------------------------------
# resolve_agent_config
# ---------------------------------------------------------------------------


def test_resolve_agent_config_missing_returns_none():
    cfg = {"agents": {"list": [{"id": "alice"}]}}
    assert resolve_agent_config(cfg, "bob") is None


def test_resolve_agent_config_basic_fields():
    cfg = {
        "agents": {
            "list": [{"id": "alice", "name": "Alice", "model": "gpt-4"}]
        }
    }
    resolved = resolve_agent_config(cfg, "alice")
    assert resolved is not None
    assert resolved["name"] == "Alice"
    assert resolved["model"] == "gpt-4"


def test_resolve_agent_config_merges_defaults_context_tokens():
    cfg = {
        "agents": {
            "defaults": {"contextTokens": 8000},
            "list": [{"id": "alice"}],
        }
    }
    resolved = resolve_agent_config(cfg, "alice")
    assert resolved["contextTokens"] == 8000


def test_resolve_agent_config_per_agent_overrides_defaults():
    cfg = {
        "agents": {
            "defaults": {"contextTokens": 8000},
            "list": [{"id": "alice", "contextTokens": 4000}],
        }
    }
    resolved = resolve_agent_config(cfg, "alice")
    assert resolved["contextTokens"] == 4000


def test_resolve_agent_config_context_limits_merge():
    cfg = {
        "agents": {
            "defaults": {"contextLimits": {"maxHistory": 20}},
            "list": [{"id": "alice", "contextLimits": {"maxOutput": 5000}}],
        }
    }
    resolved = resolve_agent_config(cfg, "alice")
    limits = resolved["contextLimits"]
    assert limits["maxHistory"] == 20
    assert limits["maxOutput"] == 5000


def test_resolve_agent_config_model_policy_excluded_when_no_allow():
    cfg = {
        "agents": {
            "list": [
                {
                    "id": "alice",
                    "modelPolicy": {"deny": ["bad-model"]},
                }
            ]
        }
    }
    resolved = resolve_agent_config(cfg, "alice")
    assert "modelPolicy" not in resolved or resolved.get("modelPolicy") is None


def test_resolve_agent_config_model_policy_included_when_allow():
    cfg = {
        "agents": {
            "list": [
                {
                    "id": "alice",
                    "modelPolicy": {"allow": ["gpt-4", "claude"]},
                }
            ]
        }
    }
    resolved = resolve_agent_config(cfg, "alice")
    assert resolved.get("modelPolicy") == {"allow": ["gpt-4", "claude"]}


# ---------------------------------------------------------------------------
# resolve_agent_workspace_dir
# ---------------------------------------------------------------------------


def test_resolve_agent_workspace_dir_per_agent_key(tmp_path):
    cfg = {
        "agents": {
            "list": [{"id": "alice", "workspace": str(tmp_path / "alice-ws")}]
        }
    }
    d = resolve_agent_workspace_dir(cfg, "alice")
    assert d.endswith("alice-ws")


def test_resolve_agent_workspace_dir_default_agent_gets_stateDir_workspace(tmp_path):
    env = {"JARVIS_STATE_DIR": str(tmp_path / "state")}
    cfg = {"agents": {"list": [{"id": "main"}]}}
    d = resolve_agent_workspace_dir(cfg, "main", env)
    assert d == str(tmp_path / "state" / "workspace")


def test_resolve_agent_workspace_dir_non_default_gets_suffixed(tmp_path):
    env = {"JARVIS_STATE_DIR": str(tmp_path / "state")}
    cfg = {"agents": {"list": [{"id": "main"}, {"id": "alice"}]}}
    d = resolve_agent_workspace_dir(cfg, "alice", env)
    assert d == str(tmp_path / "state" / "workspace-alice")


def test_resolve_agent_workspace_dir_defaults_workspace_used(tmp_path):
    env = {"JARVIS_STATE_DIR": str(tmp_path)}
    cfg = {
        "agents": {
            "defaults": {"workspace": str(tmp_path / "shared")},
            "list": [{"id": "main"}, {"id": "alice"}],
        }
    }
    d_alice = resolve_agent_workspace_dir(cfg, "alice", env)
    assert d_alice == str(tmp_path / "shared" / "alice")


# ---------------------------------------------------------------------------
# resolve_agent_dir
# ---------------------------------------------------------------------------


def test_resolve_agent_dir_default_path(tmp_path):
    env = {"JARVIS_STATE_DIR": str(tmp_path)}
    cfg = {"agents": {"list": [{"id": "main"}]}}
    d = resolve_agent_dir(cfg, "main", env)
    import os
    assert os.path.normpath(d) == os.path.normpath(str(tmp_path / "agents" / "main" / "agent"))


def test_resolve_agent_dir_configured_override(tmp_path):
    custom = str(tmp_path / "custom-dir")
    cfg = {"agents": {"list": [{"id": "alice", "agentDir": custom}]}}
    d = resolve_agent_dir(cfg, "alice")
    assert d == custom


# ---------------------------------------------------------------------------
# resolve_agent_context_limits
# ---------------------------------------------------------------------------


def test_resolve_agent_context_limits_none_cfg():
    assert resolve_agent_context_limits(None) is None


def test_resolve_agent_context_limits_defaults_only():
    cfg = {"agents": {"defaults": {"contextLimits": {"maxHistory": 10}}}}
    assert resolve_agent_context_limits(cfg)["maxHistory"] == 10


def test_resolve_agent_context_limits_agent_overrides():
    cfg = {
        "agents": {
            "defaults": {"contextLimits": {"maxHistory": 10}},
            "list": [{"id": "alice", "contextLimits": {"maxHistory": 5}}],
        }
    }
    result = resolve_agent_context_limits(cfg, "alice")
    assert result["maxHistory"] == 5
