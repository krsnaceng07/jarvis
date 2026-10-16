"""Tests for Codex remote node exec-server command, policy, and runtime sanitization.

OpenClaw parity: ``extensions/codex/src/node-exec-server.test.ts``.
"""

from __future__ import annotations

import asyncio
import os
import pytest

from extensions.codex.src.commands import CodexCommandContext, handle_codex_command
from extensions.codex.src.node_exec_server import (
    CODEX_NODE_EXEC_SERVER_CAPABILITY,
    CODEX_NODE_EXEC_SERVER_COMMAND,
    create_codex_node_exec_server_command,
    create_codex_node_exec_server_invoke_policy,
    parse_codex_node_placement_workspace,
)
from extensions.codex.src.node_exec_server_runtime import (
    create_remote_node_exec_session,
    sanitize_remote_exec_environment,
    validate_node_exec_server_message,
)


def test_parse_codex_node_placement_workspace_valid():
    workspace = parse_codex_node_placement_workspace(
        {
            "cwd": "/tmp/ws",
            "environmentId": "env_123",
            "sessionId": "sess_456",
            "ownerEpoch": 1,
            "sessionKey": "skey_789",
        }
    )
    assert workspace.cwd == "/tmp/ws"
    assert workspace.environment_id == "env_123"
    assert workspace.session_id == "sess_456"
    assert workspace.owner_epoch == 1
    assert workspace.session_key == "skey_789"


def test_parse_codex_node_placement_workspace_invalid():
    with pytest.raises(ValueError, match="exact managed placement workspace"):
        parse_codex_node_placement_workspace({"cwd": ""})


def test_parse_codex_node_placement_workspace_exact_shape():
    base = {
        "cwd": "/tmp/ws",
        "environmentId": "env_1",
        "sessionId": "sess_1",
        "ownerEpoch": 1,
        "sessionKey": "key_1",
    }
    # Extra keys fail closed even when the five managed keys are present.
    bloated = dict(base)
    bloated["extra"] = "nope"
    with pytest.raises(ValueError, match="exact managed placement workspace"):
        parse_codex_node_placement_workspace(bloated)
    # Missing keys fail closed.
    short = dict(base)
    del short["sessionKey"]
    with pytest.raises(ValueError, match="exact managed placement workspace"):
        parse_codex_node_placement_workspace(short)
    # snake_case spellings resolve under the exact-five shape.
    snaked = {
        "cwd": "/tmp/ws",
        "environment_id": "env_1",
        "session_id": "sess_1",
        "owner_epoch": 1,
        "session_key": "key_1",
    }
    assert parse_codex_node_placement_workspace(snaked).environment_id == "env_1"


def test_create_codex_node_exec_server_command():
    cmd = create_codex_node_exec_server_command()
    assert cmd.command == CODEX_NODE_EXEC_SERVER_COMMAND
    assert cmd.cap == CODEX_NODE_EXEC_SERVER_CAPABILITY
    assert cmd.dangerous is True
    assert cmd.duplex is True


def test_invoke_policy_classification_and_approval():
    policy = create_codex_node_exec_server_invoke_policy()
    assert policy["commands"] == [CODEX_NODE_EXEC_SERVER_COMMAND]

    classification = policy["classify_risk"]()
    assert classification["level"] == "high"
    assert classification["family"] == CODEX_NODE_EXEC_SERVER_CAPABILITY

    # Test approval request flow with mock approvals
    class MockApprovals:
        async def request(self, **kwargs):
            return {"decision": "allow-always"}

    context = {
        "risk": {"level": "high"},
        "params": {
            "cwd": "/tmp/ws",
            "environmentId": "env_1",
            "sessionId": "sess_1",
            "ownerEpoch": 1,
            "sessionKey": "key_1",
        },
        "approvals": MockApprovals(),
    }

    res = asyncio.run(policy["handle"](context))
    assert res.ok is True
    assert res.decision == "allow-always"


def test_validate_node_exec_server_message_valid():
    msg = b'{"jsonrpc":"2.0","method":"initialize","id":1}'
    res = validate_node_exec_server_message(msg)
    assert res.ok is True
    assert res.payload is not None
    assert res.payload["method"] == "initialize"


def test_validate_node_exec_server_message_invalid():
    # Newline in single frame is rejected
    res_newline = validate_node_exec_server_message(b'{"jsonrpc":"2.0"}\n{"method":"foo"}')
    assert res_newline.ok is False
    assert "exactly one message" in (res_newline.error or "").lower()

    # Oversized payload rejected (> 64 MiB)
    oversized = b"x" * (64 * 1024 * 1024 + 1)
    res_oversized = validate_node_exec_server_message(oversized)
    assert res_oversized.ok is False
    assert "64 MiB limit" in (res_oversized.error or "")


def test_sanitize_remote_exec_environment():
    env = {
        "PATH": "/usr/bin",
        "RUST_LOG": "info",
        "AUTHORIZATION": "Bearer secret_token",
        "CODEX_API_KEY": "sk-12345",
        "OPENAI_API_KEY": "sk-67890",
        "GITHUB_TOKEN": "ghp_abc",
    }
    clean = sanitize_remote_exec_environment(env)
    assert "PATH" in clean
    assert "RUST_LOG" in clean
    assert "AUTHORIZATION" not in clean
    assert "CODEX_API_KEY" not in clean
    assert "OPENAI_API_KEY" not in clean
    assert "GITHUB_TOKEN" not in clean


def test_remote_exec_session_cleanup():
    sess = create_remote_node_exec_session(workspace_dir="/tmp/ws")
    assert os.path.exists(sess.temp_home)
    assert os.path.exists(sess.temp_codex_home)

    sess.cleanup()
    assert not os.path.exists(sess.temp_home)
    assert not os.path.exists(sess.temp_codex_home)


def test_btw_side_question_remote_exec_guard():
    # Local placement allows /btw
    ctx_local = CodexCommandContext(args="btw how to list files", placement_execution_mode="local")
    res_local = asyncio.run(handle_codex_command(ctx_local))
    assert "Processing Codex side question" in res_local.text

    # Unpaired remote-exec (no paired node id) keeps /btw: only the
    # paired-device sandbox is unbound (side-question.ts predicate).
    ctx_remote = CodexCommandContext(
        args="btw how to list files", placement_execution_mode="remote-exec"
    )
    res_remote = asyncio.run(handle_codex_command(ctx_remote))
    assert "Processing Codex side question" in res_remote.text

    # Paired-device remote-exec placement blocks /btw with explanation
    ctx_paired = CodexCommandContext(
        args="btw how to list files",
        placement_execution_mode="remote-exec",
        placement_node_id="node-01",
    )
    res_paired = asyncio.run(handle_codex_command(ctx_paired))
    assert "not yet bound to the active placement" in res_paired.text
