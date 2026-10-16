"""Tests for src/commands/binding_format.py, agents_bindings.py,
agents_list_command.py, and agents_bind_command.py.

Mirrors behavioral contracts from OpenClaw's:
  - agents.binding-format.ts
  - agents.bindings.ts
  - agents.commands.list.ts
  - agents.commands.bind.ts
"""

from __future__ import annotations

import io
import json
import pytest

from src.commands.binding_format import describe_binding
from src.commands.agents_bindings import (
    apply_agent_bindings,
    parse_binding_specs,
    remove_agent_bindings,
)
from src.commands.agents_list_command import agents_list_command
from src.commands.agents_bind_command import (
    agents_bind_command,
    agents_bindings_list_command,
    agents_unbind_command,
)
from src.agents.agent_dir_registry import clear_agent_dir_registry


@pytest.fixture(autouse=True)
def _clean_registry():
    yield
    clear_agent_dir_registry()


# ============================================================
# describe_binding
# ============================================================


def test_describe_binding_minimal():
    b = {"agentId": "alice", "match": {"channel": "discord"}}
    assert describe_binding(b) == "discord"


def test_describe_binding_with_account():
    b = {"agentId": "alice", "match": {"channel": "discord", "accountId": "support"}}
    assert describe_binding(b) == "discord accountId=support"


def test_describe_binding_with_peer():
    b = {
        "agentId": "alice",
        "match": {"channel": "slack", "peer": {"kind": "channel", "id": "C123"}},
    }
    assert describe_binding(b) == "slack peer=channel:C123"


def test_describe_binding_with_guild():
    b = {"agentId": "alice", "match": {"channel": "discord", "guildId": "GABC"}}
    assert describe_binding(b) == "discord guild=GABC"


def test_describe_binding_with_comment():
    b = {
        "agentId": "alice",
        "match": {"channel": "discord"},
        "comment": "My binding",
    }
    assert "# My binding" in describe_binding(b)


def test_describe_binding_with_roles():
    b = {"agentId": "alice", "match": {"channel": "discord", "roles": ["R1", "R2"]}}
    result = describe_binding(b)
    assert "roles=R1,R2" in result


def test_describe_binding_full():
    b = {
        "agentId": "alice",
        "match": {
            "channel": "discord",
            "accountId": "support",
            "peer": {"kind": "direct", "id": "U123"},
            "guildId": "G456",
            "teamId": "T789",
        },
    }
    result = describe_binding(b)
    assert "discord" in result
    assert "accountId=support" in result
    assert "peer=direct:U123" in result
    assert "guild=G456" in result
    assert "team=T789" in result


# ============================================================
# parse_binding_specs
# ============================================================


def test_parse_binding_spec_channel_only():
    result = parse_binding_specs(agent_id="alice", specs=["discord"])
    assert not result["errors"]
    assert len(result["bindings"]) == 1
    assert result["bindings"][0]["match"]["channel"] == "discord"


def test_parse_binding_spec_with_account():
    result = parse_binding_specs(agent_id="alice", specs=["discord/support"])
    assert not result["errors"]
    b = result["bindings"][0]
    assert b["match"]["accountId"] == "support"


def test_parse_binding_spec_with_peer():
    result = parse_binding_specs(agent_id="alice", specs=["discord/default/channel:123"])
    assert not result["errors"]
    b = result["bindings"][0]
    assert b["match"]["peer"] == {"kind": "channel", "id": "123"}


def test_parse_binding_spec_with_query_guild():
    result = parse_binding_specs(agent_id="alice", specs=["discord?guild=GABC"])
    assert not result["errors"]
    assert result["bindings"][0]["match"]["guildId"] == "GABC"


def test_parse_binding_spec_with_roles():
    result = parse_binding_specs(agent_id="alice", specs=["discord?roles=R1,R2"])
    assert not result["errors"]
    assert result["bindings"][0]["match"]["roles"] == ["R1", "R2"]


def test_parse_binding_spec_invalid_peer_kind():
    result = parse_binding_specs(agent_id="alice", specs=["discord/default/bad:123"])
    assert result["errors"]
    assert not result["bindings"]


def test_parse_binding_spec_empty_spec():
    result = parse_binding_specs(agent_id="alice", specs=[""])
    assert result["errors"]


def test_parse_binding_spec_agent_id_normalized():
    result = parse_binding_specs(agent_id="ALICE", specs=["discord"])
    assert result["bindings"][0]["agentId"] == "alice"


def test_parse_binding_spec_multiple():
    result = parse_binding_specs(agent_id="alice", specs=["discord", "slack/ws"])
    assert not result["errors"]
    assert len(result["bindings"]) == 2


# ============================================================
# apply_agent_bindings
# ============================================================


def _make_binding(agent_id: str, channel: str, account_id: str | None = None) -> dict:
    match: dict = {"channel": channel}
    if account_id:
        match["accountId"] = account_id
    return {"agentId": agent_id, "match": match}


def test_apply_agent_bindings_add_new():
    cfg: dict = {}
    b = _make_binding("alice", "discord")
    result = apply_agent_bindings(cfg, [b])
    assert result["added"] == [b]
    assert not result["conflicts"]
    assert len(result["config"]["bindings"]) == 1


def test_apply_agent_bindings_skip_duplicate():
    b = _make_binding("alice", "discord")
    cfg = {"bindings": [b]}
    result = apply_agent_bindings(cfg, [b])
    assert result["skipped"] == [b]
    assert not result["added"]


def test_apply_agent_bindings_conflict_different_agent():
    existing = _make_binding("alice", "discord")
    incoming = _make_binding("bob", "discord")
    cfg = {"bindings": [existing]}
    result = apply_agent_bindings(cfg, [incoming])
    assert len(result["conflicts"]) == 1
    assert result["conflicts"][0]["existingAgentId"] == "alice"


def test_apply_agent_bindings_upgrade_default_to_specific():
    """Adding accountId to existing default-scoped binding upgrades it."""
    existing = _make_binding("alice", "discord")  # no accountId = default scope
    incoming = _make_binding("alice", "discord", account_id="support")
    cfg = {"bindings": [existing]}
    result = apply_agent_bindings(cfg, [incoming])
    assert result["updated"] == [incoming]
    assert not result["added"]
    assert not result["conflicts"]


def test_apply_agent_bindings_preserves_non_route_bindings():
    acp_binding = {"type": "acp", "agentId": "sys", "match": {"channel": "discord", "peer": {"kind": "direct", "id": "U1"}}}
    cfg = {"bindings": [acp_binding]}
    b = _make_binding("alice", "slack")
    result = apply_agent_bindings(cfg, [b])
    bindings = result["config"]["bindings"]
    assert acp_binding in bindings
    assert b in bindings


# ============================================================
# remove_agent_bindings
# ============================================================


def test_remove_agent_bindings_removes_matching():
    b = _make_binding("alice", "discord")
    cfg = {"bindings": [b]}
    result = remove_agent_bindings(cfg, [b])
    assert result["removed"] == [b]
    assert result["config"]["bindings"] == []


def test_remove_agent_bindings_not_found():
    b = _make_binding("alice", "discord")
    cfg: dict = {}
    result = remove_agent_bindings(cfg, [b])
    assert result["not_found" if "not_found" in result else "notFound"] == [b]


def test_remove_agent_bindings_only_removes_matching():
    b1 = _make_binding("alice", "discord")
    b2 = _make_binding("alice", "slack")
    cfg = {"bindings": [b1, b2]}
    result = remove_agent_bindings(cfg, [b1])
    remaining = result["config"]["bindings"]
    assert b1 not in remaining
    assert b2 in remaining


# ============================================================
# agents_list_command
# ============================================================


def test_agents_list_command_text_output(tmp_path):
    cfg = {
        "agents": {
            "list": [
                {"id": "main", "default": True, "name": "Main"},
                {"id": "alice"},
            ]
        }
    }
    env = {"JARVIS_STATE_DIR": str(tmp_path)}
    out = io.StringIO()
    agents_list_command(cfg=cfg, env=env, out=out)
    output = out.getvalue()
    assert "main" in output
    assert "alice" in output
    assert "[default]" in output


def test_agents_list_command_json_output(tmp_path):
    cfg = {"agents": {"list": [{"id": "main", "default": True}]}}
    env = {"JARVIS_STATE_DIR": str(tmp_path)}
    out = io.StringIO()
    agents_list_command(cfg=cfg, json_output=True, env=env, out=out)
    data = json.loads(out.getvalue())
    assert isinstance(data, list)
    assert data[0]["id"] == "main"
    assert data[0]["isDefault"] is True


def test_agents_list_command_with_bindings_flag(tmp_path):
    cfg = {
        "agents": {"list": [{"id": "main", "default": True}, {"id": "alice"}]},
        "bindings": [{"agentId": "alice", "match": {"channel": "discord", "accountId": "support"}}],
    }
    env = {"JARVIS_STATE_DIR": str(tmp_path)}
    out = io.StringIO()
    agents_list_command(cfg=cfg, bindings=True, env=env, out=out)
    output = out.getvalue()
    assert "discord" in output
    assert "support" in output


def test_agents_list_command_default_gets_no_explicit_rules_label(tmp_path):
    cfg = {"agents": {"list": [{"id": "main", "default": True}]}}
    env = {"JARVIS_STATE_DIR": str(tmp_path)}
    out = io.StringIO()
    agents_list_command(cfg=cfg, bindings=True, env=env, out=out)
    output = out.getvalue()
    assert "default" in output


# ============================================================
# agents_bindings_list_command
# ============================================================


def test_agents_bindings_list_all():
    cfg = {
        "bindings": [
            {"agentId": "alice", "match": {"channel": "discord"}},
            {"agentId": "bob", "match": {"channel": "slack"}},
        ]
    }
    result = agents_bindings_list_command(cfg)
    assert len(result["bindings"]) == 2


def test_agents_bindings_list_filtered_by_agent():
    cfg = {
        "bindings": [
            {"agentId": "alice", "match": {"channel": "discord"}},
            {"agentId": "bob", "match": {"channel": "slack"}},
        ]
    }
    result = agents_bindings_list_command(cfg, agent="alice")
    assert len(result["bindings"]) == 1
    assert result["bindings"][0]["agentId"] == "alice"


def test_agents_bindings_list_empty():
    result = agents_bindings_list_command({})
    assert result["bindings"] == []
    assert any("No" in line for line in result["lines"])


# ============================================================
# agents_bind_command
# ============================================================


def test_agents_bind_command_adds_binding():
    cfg = {"agents": {"list": [{"id": "alice", "default": True}]}}
    result = agents_bind_command(cfg, agent="alice", bind_specs=["discord/support"])
    assert result["ok"]
    assert result["added"]
    assert result["config"] is not None


def test_agents_bind_command_unknown_agent():
    cfg = {"agents": {"list": [{"id": "alice"}]}}
    result = agents_bind_command(cfg, agent="ghost", bind_specs=["discord"])
    assert not result["ok"]
    assert "not found" in result["error"].lower()


def test_agents_bind_command_invalid_spec():
    cfg = {"agents": {"list": [{"id": "alice", "default": True}]}}
    result = agents_bind_command(cfg, agent="alice", bind_specs=["discord/default/bad:123"])
    assert not result["ok"]
    assert "Invalid" in result["error"]


def test_agents_bind_command_conflict_reported():
    cfg = {
        "agents": {"list": [{"id": "alice", "default": True}, {"id": "bob"}]},
        "bindings": [{"agentId": "alice", "match": {"channel": "discord"}}],
    }
    result = agents_bind_command(cfg, agent="bob", bind_specs=["discord"])
    assert result["conflicts"]


# ============================================================
# agents_unbind_command
# ============================================================


def test_agents_unbind_command_removes_specific():
    cfg = {
        "agents": {"list": [{"id": "alice", "default": True}]},
        "bindings": [{"agentId": "alice", "match": {"channel": "discord"}}],
    }
    result = agents_unbind_command(cfg, agent="alice", bind_specs=["discord"])
    assert result["ok"]
    assert result["removed"]
    assert result["config"]["bindings"] == []


def test_agents_unbind_command_removes_all():
    cfg = {
        "agents": {"list": [{"id": "alice", "default": True}]},
        "bindings": [
            {"agentId": "alice", "match": {"channel": "discord"}},
            {"agentId": "alice", "match": {"channel": "slack"}},
        ],
    }
    result = agents_unbind_command(cfg, agent="alice", all_bindings=True)
    assert result["ok"]
    assert len(result["removed"]) == 2
    assert result["config"]["bindings"] == []


def test_agents_unbind_command_no_specs_no_all():
    cfg = {"agents": {"list": [{"id": "alice", "default": True}]}}
    result = agents_unbind_command(cfg, agent="alice")
    assert not result["ok"]
    assert "all" in result["error"].lower() or "specs" in result["error"].lower() or "--bind" in result["error"]
