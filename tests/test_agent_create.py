"""Tests for src/agents/agent_create.py.

Covers the full create_agent contract: name validation, reserved-id check,
duplicate detection, config mutation, workspace creation, and bootstrap files.
"""

from __future__ import annotations

import pytest

from src.agents.agent_create import create_agent
from src.agents.agent_dir_registry import clear_agent_dir_registry


@pytest.fixture(autouse=True)
def _clean():
    yield
    clear_agent_dir_registry()


def _env(tmp_path) -> dict:
    return {"JARVIS_STATE_DIR": str(tmp_path)}


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_create_agent_success(tmp_path):
    cfg: dict = {}
    result = create_agent(name="Alice Bot", cfg=cfg, env=_env(tmp_path))
    assert result["status"] == "created"
    assert result["agent_id"] == "alice-bot"
    assert result["name"] == "Alice Bot"
    assert "agents" in cfg
    assert any(e["id"] == "alice-bot" for e in cfg["agents"]["list"])


def test_create_agent_workspace_created(tmp_path):
    import os
    cfg: dict = {}
    result = create_agent(name="My Agent", cfg=cfg, env=_env(tmp_path))
    assert result["status"] == "created"
    assert os.path.isdir(result["workspace"])


def test_create_agent_bootstrap_files_written(tmp_path):
    import os
    cfg: dict = {}
    result = create_agent(name="Helper Bot", cfg=cfg, env=_env(tmp_path))
    assert result["status"] == "created"
    ws = result["workspace"]
    assert os.path.isfile(os.path.join(ws, "AGENTS.md"))
    assert os.path.isfile(os.path.join(ws, "SOUL.md"))


def test_create_agent_no_bootstrap_when_disabled(tmp_path):
    import os
    cfg: dict = {}
    result = create_agent(name="Ghost", cfg=cfg, env=_env(tmp_path), write_bootstrap=False)
    assert result["status"] == "created"
    ws = result["workspace"]
    assert not os.path.exists(os.path.join(ws, "AGENTS.md"))


def test_create_agent_with_explicit_workspace(tmp_path):
    ws = str(tmp_path / "custom-ws")
    cfg: dict = {}
    result = create_agent(name="Custom", cfg=cfg, workspace=ws, env=_env(tmp_path))
    assert result["status"] == "created"
    assert result["workspace"] == ws


def test_create_agent_with_model(tmp_path):
    cfg: dict = {}
    result = create_agent(name="Smart", cfg=cfg, model="gpt-4", env=_env(tmp_path))
    assert result["status"] == "created"
    assert result["model"] == "gpt-4"
    entry = next(e for e in cfg["agents"]["list"] if e["id"] == "smart")
    assert entry["model"] == "gpt-4"


def test_create_agent_is_default_flag(tmp_path):
    cfg: dict = {}
    create_agent(name="Alice", cfg=cfg, env=_env(tmp_path), is_default=True)
    entry = next(e for e in cfg["agents"]["list"] if e["id"] == "alice")
    assert entry.get("default") is True


# ---------------------------------------------------------------------------
# Slug derivation
# ---------------------------------------------------------------------------


def test_name_slug_lowercase():
    cfg: dict = {}
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        result = create_agent(name="My Cool Agent", cfg=cfg, env={"JARVIS_STATE_DIR": td})
    assert result["agent_id"] == "my-cool-agent"


def test_name_with_special_chars():
    cfg: dict = {}
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        result = create_agent(name="O'Brien", cfg=cfg, env={"JARVIS_STATE_DIR": td})
    assert result["status"] == "created"


# ---------------------------------------------------------------------------
# Name validation
# ---------------------------------------------------------------------------


def test_empty_name_rejected():
    cfg: dict = {}
    result = create_agent(name="", cfg=cfg)
    assert result["status"] == "error"
    assert result["reason"] == "invalid-name"


def test_whitespace_only_name_rejected():
    cfg: dict = {}
    result = create_agent(name="   ", cfg=cfg)
    assert result["status"] == "error"
    assert result["reason"] == "invalid-name"


def test_name_too_long_rejected():
    cfg: dict = {}
    result = create_agent(name="A" * 65, cfg=cfg)
    assert result["status"] == "error"
    assert result["reason"] == "invalid-name"


def test_name_starts_with_invalid_char_rejected():
    cfg: dict = {}
    result = create_agent(name="-bad", cfg=cfg)
    assert result["status"] == "error"
    assert result["reason"] == "invalid-name"


# ---------------------------------------------------------------------------
# Reserved ids
# ---------------------------------------------------------------------------


def test_reserved_agent_id_rejected():
    cfg: dict = {}
    result = create_agent(name="System", cfg=cfg)
    assert result["status"] == "error"
    assert result["reason"] == "reserved-id"
    assert result["agent_id"] == "system"


def test_jarvis_reserved():
    cfg: dict = {}
    result = create_agent(name="Jarvis", cfg=cfg)
    assert result["status"] == "error"
    assert result["reason"] == "reserved-id"


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------


def test_duplicate_agent_rejected(tmp_path):
    cfg: dict = {}
    create_agent(name="Alice", cfg=cfg, env=_env(tmp_path))
    result = create_agent(name="Alice", cfg=cfg, env=_env(tmp_path))
    assert result["status"] == "error"
    assert result["reason"] == "already-exists"


# ---------------------------------------------------------------------------
# Binding spec validation
# ---------------------------------------------------------------------------


def test_invalid_binding_spec_rejected(tmp_path):
    cfg: dict = {}
    result = create_agent(
        name="Alice",
        cfg=cfg,
        env=_env(tmp_path),
        binding_specs=[""],
    )
    assert result["status"] == "error"
    assert result["reason"] == "invalid-bindings"
