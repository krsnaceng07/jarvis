"""Tests for node command allow/deny evaluation + Codex invocability.

OpenClaw parity: ``openclaw-main/src/gateway/node-command-policy.ts``
(``isNodeCommandAllowed``, ``resolveRequiredNodeCommandAuthority``,
``normalizeDeclaredNodeCommands``, ``retainFulfilledNodeCapabilities``,
``DEFAULT_DANGEROUS_NODE_COMMANDS``) and the effectively-invocable
requirement for ``codex.exec-server.stdio.v1``.
"""

from __future__ import annotations

import pytest

from extensions.codex.src.node_exec_server import (
    CODEX_NODE_EXEC_SERVER_COMMAND,
    is_codex_exec_server_effectively_invocable,
)
from src.gateway.node_command_policy import (
    DEFAULT_DANGEROUS_NODE_COMMANDS,
    is_node_command_allowed,
    normalize_declared_node_commands,
    resolve_required_node_command_authority,
    retain_fulfilled_node_capabilities,
)


def test_dangerous_builtins_match_openclaw():
    assert set(DEFAULT_DANGEROUS_NODE_COMMANDS) == {
        "camera.snap",
        "camera.clip",
        "camera.ptz.control",
        "screen.record",
        "desktop.stream",
        "contacts.add",
        "calendar.add",
        "reminders.add",
        "sms.send",
        "sms.search",
        "health.summary",
    }
    # The Codex exec-server is plugin-dangerous, not a built-in.
    assert CODEX_NODE_EXEC_SERVER_COMMAND not in DEFAULT_DANGEROUS_NODE_COMMANDS


def test_is_node_command_allowed():
    allow = {"system.notify", "screen.snapshot"}
    assert is_node_command_allowed(
        {"command": "system.notify", "declared_commands": ["system.notify"], "allowlist": allow}
    ) == {"ok": True}
    assert is_node_command_allowed(
        {"command": "  ", "declared_commands": [], "allowlist": allow}
    ) == {"ok": False, "reason": "command required"}
    assert is_node_command_allowed(
        {
            "command": "worker.launch.v1",
            "declared_commands": ["worker.launch.v1"],
            "allowlist": allow,
        }
    ) == {"ok": False, "reason": "command not allowlisted"}
    assert is_node_command_allowed(
        {"command": "camera.snap", "declared_commands": ["camera.snap"], "allowlist": allow}
    ) == {"ok": False, "reason": "command not allowlisted"}
    assert is_node_command_allowed(
        {"command": "system.notify", "declared_commands": ["screen.snapshot"], "allowlist": allow}
    ) == {"ok": False, "reason": "command not declared by node"}
    assert is_node_command_allowed(
        {"command": "system.notify", "declared_commands": [], "allowlist": allow}
    ) == {"ok": False, "reason": "node did not declare commands"}


def test_normalize_declared_node_commands():
    assert normalize_declared_node_commands(
        {
            "declared_commands": [
                "system.notify",
                " system.notify ",
                "worker.launch.v1",
                "camera.snap",
                "",
                42,
            ],
            "allowlist": {"system.notify"},
        }
    ) == ["system.notify"]


def test_required_authority_states():
    base = {
        "required_commands": ["screen.snapshot"],
        "declared_commands": ["screen.snapshot"],
        "effective_commands": ["screen.snapshot"],
        "withheld_commands": [],
        "allowlist": {"screen.snapshot"},
    }
    assert resolve_required_node_command_authority(base) == {
        "command": "screen.snapshot",
        "state": "invocable",
    }
    pending = {**base, "effective_commands": []}
    assert resolve_required_node_command_authority(pending)["state"] == "pending-approval"
    undeclared = {**base, "declared_commands": [], "effective_commands": []}
    assert resolve_required_node_command_authority(undeclared)["state"] == "undeclared"
    denied = {**base, "withheld_commands": ["screen.snapshot"]}
    assert resolve_required_node_command_authority(denied) == {
        "command": "screen.snapshot",
        "state": "unauthorized",
    }
    assert resolve_required_node_command_authority({**base, "required_commands": []}) is None


def test_retain_fulfilled_node_capabilities():
    assert (
        retain_fulfilled_node_capabilities(
            {"caps": ["camera"], "admitted_commands": [], "withheld_commands": ["camera.snap"]}
        )
        == []
    )
    assert retain_fulfilled_node_capabilities(
        {
            "caps": ["camera"],
            "admitted_commands": ["camera.list"],
            "withheld_commands": ["camera.snap"],
        }
    ) == ["camera"]
    # Families core does not own stay untouched.
    assert retain_fulfilled_node_capabilities(
        {"caps": ["talk"], "admitted_commands": [], "withheld_commands": ["talk.ptt.start"]}
    ) == ["talk"]


def _gateway_cfg(*, allow=(), deny=()):
    return {"gateway": {"nodes": {"commands": {"allow": list(allow), "deny": list(deny)}}}}


def test_codex_invocable_needs_allow_and_declaration():
    declared = [CODEX_NODE_EXEC_SERVER_COMMAND, "system.notify"]
    # Declared but not allowlisted: insufficient.
    assert (
        is_codex_exec_server_effectively_invocable(_gateway_cfg(), declared)["state"]
        == "pending-approval"
    )
    # Explicitly allowed + declared: invocable.
    assert is_codex_exec_server_effectively_invocable(
        _gateway_cfg(allow=[CODEX_NODE_EXEC_SERVER_COMMAND]), declared
    ) == {"command": CODEX_NODE_EXEC_SERVER_COMMAND, "state": "invocable"}
    # Deny wins over allow.
    assert (
        is_codex_exec_server_effectively_invocable(
            _gateway_cfg(
                allow=[CODEX_NODE_EXEC_SERVER_COMMAND], deny=[CODEX_NODE_EXEC_SERVER_COMMAND]
            ),
            declared,
        )["state"]
        == "unauthorized"
    )
    # Not declared at all.
    assert (
        is_codex_exec_server_effectively_invocable(
            _gateway_cfg(allow=[CODEX_NODE_EXEC_SERVER_COMMAND]), ["system.notify"]
        )["state"]
        == "undeclared"
    )


@pytest.mark.parametrize("cfg", [{}, {"gateway": {}}, None])
def test_codex_invocable_without_config_is_not_invocable(cfg):
    state = is_codex_exec_server_effectively_invocable(cfg, [CODEX_NODE_EXEC_SERVER_COMMAND])[
        "state"
    ]
    assert state in ("pending-approval", "unauthorized", "undeclared")
