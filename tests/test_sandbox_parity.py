"""tests/test_sandbox_parity.py — Behavioral parity tests for OpenClaw sandbox architecture in JARVIS.

Tests all 14 categories:
1. Sandbox configuration parsing and resolution (agents.defaults.sandbox)
2. Sandbox context resolution (mode: off, non-main, all)
3. Creator role immutable requirement (sandbox="required")
4. Container naming and scoping (agent, session, shared)
5. Tool policy evaluation, group:* expansion, and deny-precedence
6. Elevated mode gate and provider allowlists
7. Deepest existing ancestor symlink and path containment
8. Workspace access enforcement (none, ro, rw)
9. Environment variable sanitization and credential scrubbing
10. Process tree containment and kill semantics
11. Docker backend path translation and launch parameter construction
12. Exec tool end-to-end integration and routing
"""

import os
import tempfile
from pathlib import Path
import pytest

from src.config.sandbox_config import (
    SandboxConfig,
    resolve_sandbox_config,
)
from src.agents.sandbox.context import (
    is_main_session_key,
    resolve_sandbox_context,
)
from src.agents.sandbox.tool_policy import (
    evaluate_sandbox_tool_policy,
    expand_tool_policy_items,
)
from src.agents.sandbox.elevated import evaluate_elevated_execution
from src.agents.sandbox.filesystem_guard import (
    validate_sandbox_path,
)
from src.agents.sandbox.environment import (
    is_sensitive_env_key,
    sanitize_execution_environment,
)
from src.agents.sandbox.process_job import ProcessTreeContainment
from src.agents.sandbox.docker_backend import translate_path_to_sandbox
from src.agents.sessions.tools.exec_tool import create_exec_tool
from src.agents.sessions.tools.read import create_read_tool
from src.agents.sessions.tools.write import create_write_tool
from src.agents.sessions.tools.edit import create_edit_tool
from src.agents.sessions.tools.apply_patch import create_apply_patch_tool
from src.agents.sessions.tools.ls import create_ls_tool


# ============================================================================
# 1. Configuration & Schema Parity
# ============================================================================


def test_sandbox_config_defaults():
    cfg = SandboxConfig()
    assert cfg.mode == "off"
    assert cfg.scope == "agent"
    assert cfg.backend == "docker"
    assert cfg.workspace_access == "rw"
    assert cfg.docker.image == "openclaw-sandbox:bookworm-slim"
    assert cfg.docker.network == "none"
    assert cfg.docker.read_only_root is True
    assert cfg.docker.cap_drop == ["ALL"]
    assert "/tmp" in cfg.docker.tmpfs
    assert cfg.browser.auto_start is True


def test_resolve_sandbox_config_nested_agents():
    raw = {
        "agents": {
            "defaults": {
                "sandbox": {
                    "mode": "non-main",
                    "scope": "session",
                    "backend": "podman",
                    "workspaceAccess": "ro",
                    "docker": {
                        "image": "custom-sandbox:latest",
                        "network": "bridge",
                        "readOnlyRoot": False,
                        "capDrop": ["NET_RAW"],
                    },
                }
            }
        }
    }
    cfg = resolve_sandbox_config(raw)
    assert cfg.mode == "non-main"
    assert cfg.scope == "session"
    assert cfg.backend == "podman"
    assert cfg.workspace_access == "ro"
    assert cfg.docker.image == "custom-sandbox:latest"
    assert cfg.docker.network == "bridge"
    assert cfg.docker.read_only_root is False
    assert cfg.docker.cap_drop == ["NET_RAW"]


def test_resolve_sandbox_config_flat():
    raw = {
        "sandbox": {
            "mode": "all",
            "scope": "shared",
            "workspace_access": "none",
        }
    }
    cfg = resolve_sandbox_config(raw)
    assert cfg.mode == "all"
    assert cfg.scope == "shared"
    assert cfg.workspace_access == "none"


def test_resolve_sandbox_config_invalid_fallback():
    raw = {
        "mode": "invalid_mode",
        "scope": "invalid_scope",
        "backend": "unsupported_backend",
        "workspace_access": "super_access",
    }
    cfg = resolve_sandbox_config(raw)
    assert cfg.mode == "off"
    assert cfg.scope == "agent"
    assert cfg.backend == "docker"
    assert cfg.workspace_access == "rw"


# ============================================================================
# 2. Context Resolution & Main Session Detection
# ============================================================================


def test_is_main_session_key():
    assert is_main_session_key("agent:main:main", "main") is True
    assert is_main_session_key("main", "main") is True
    assert is_main_session_key("global", "main") is True
    assert is_main_session_key("agent:coder:main", "coder") is True
    assert is_main_session_key("agent:main:subagent-1", "main") is False
    assert is_main_session_key("telegram:123456", "main") is False
    assert is_main_session_key("discord:987654", "main") is False


def test_resolve_sandbox_context_mode_off():
    cfg = SandboxConfig(mode="off")
    ctx_main = resolve_sandbox_context(session_key="agent:main:main", config=cfg)
    assert ctx_main.is_sandboxed is False

    ctx_channel = resolve_sandbox_context(session_key="telegram:12345", config=cfg)
    assert ctx_channel.is_sandboxed is False


def test_resolve_sandbox_context_mode_non_main():
    cfg = SandboxConfig(mode="non-main")
    ctx_main = resolve_sandbox_context(session_key="agent:main:main", config=cfg)
    assert ctx_main.is_sandboxed is False

    ctx_channel = resolve_sandbox_context(session_key="telegram:12345", config=cfg)
    assert ctx_channel.is_sandboxed is True

    ctx_subagent = resolve_sandbox_context(session_key="agent:main:sub-task", config=cfg)
    assert ctx_subagent.is_sandboxed is True


def test_resolve_sandbox_context_mode_all():
    cfg = SandboxConfig(mode="all")
    ctx_main = resolve_sandbox_context(session_key="agent:main:main", config=cfg)
    assert ctx_main.is_sandboxed is True

    ctx_channel = resolve_sandbox_context(session_key="telegram:12345", config=cfg)
    assert ctx_channel.is_sandboxed is True


def test_resolve_sandbox_context_creator_role_immutable():
    # Even if mode="off", creator role policy="required" forces is_sandboxed=True
    cfg = SandboxConfig(mode="off")
    ctx = resolve_sandbox_context(
        session_key="agent:main:main",
        config=cfg,
        creator_role="untrusted-user",
        creator_sandbox_policy="required",
    )
    assert ctx.is_sandboxed is True
    assert ctx.creator_required is True


def test_sandbox_container_naming_scopes():
    cfg_agent = SandboxConfig(mode="all", scope="agent")
    ctx1 = resolve_sandbox_context(
        session_key="agent:main:sub1", agent_id="researcher", config=cfg_agent
    )
    assert ctx1.container_name == "jarvis-sandbox-researcher"

    cfg_sess = SandboxConfig(mode="all", scope="session")
    ctx2 = resolve_sandbox_context(session_key="telegram:999", agent_id="bot", config=cfg_sess)
    assert ctx2.container_name == "jarvis-sandbox-bot-telegram-999"

    cfg_shared = SandboxConfig(mode="all", scope="shared")
    ctx3 = resolve_sandbox_context(session_key="discord:888", agent_id="bot", config=cfg_shared)
    assert ctx3.container_name == "jarvis-sandbox-shared"


# ============================================================================
# 3. Tool Policy & Group Expansion
# ============================================================================


def test_tool_group_expansion():
    expanded_runtime = expand_tool_policy_items(["group:runtime", "extra_tool"])
    assert "exec" in expanded_runtime
    assert "process" in expanded_runtime
    assert "extra_tool" in expanded_runtime

    expanded_fs = expand_tool_policy_items(["group:fs"])
    assert {"read", "write", "edit", "apply_patch"}.issubset(expanded_fs)


def test_sandbox_tool_policy_allow_and_deny():
    # 1. Deny always wins
    policy = {
        "allow": ["exec", "read", "write"],
        "deny": ["exec"],
    }
    allowed, reason = evaluate_sandbox_tool_policy("exec", policy, is_sandboxed=True)
    assert allowed is False
    assert "deny list" in reason

    allowed, _ = evaluate_sandbox_tool_policy("read", policy, is_sandboxed=True)
    assert allowed is True

    # 2. Deny group:*
    policy_group_deny = {
        "allow": ["read", "exec"],
        "deny": ["group:runtime"],
    }
    allowed, reason = evaluate_sandbox_tool_policy("exec", policy_group_deny, is_sandboxed=True)
    assert allowed is False
    assert "deny list" in reason

    # 3. Not in allow list
    policy_strict = {
        "allow": ["read"],
    }
    allowed, reason = evaluate_sandbox_tool_policy("write", policy_strict, is_sandboxed=True)
    assert allowed is False
    assert "allow list" in reason

    # 4. Host turn bypasses sandbox tool policy
    allowed, _ = evaluate_sandbox_tool_policy("exec", policy, is_sandboxed=False)
    assert allowed is True


# ============================================================================
# 4. Elevated Execution Gate
# ============================================================================


def test_evaluate_elevated_execution_creator_required_blocks():
    cfg = SandboxConfig(mode="all")
    ctx = resolve_sandbox_context(
        session_key="telegram:123",
        config=cfg,
        creator_sandbox_policy="required",
    )
    # Creator role required must NEVER allow elevated execution to escape sandbox
    granted, reason = evaluate_elevated_execution(elevated_requested=True, context=ctx)
    assert granted is False
    assert "creator role requires sandboxing" in reason


def test_evaluate_elevated_execution_standard_sandbox():
    cfg = SandboxConfig(mode="all")
    ctx = resolve_sandbox_context(session_key="telegram:123", config=cfg)

    # Standard sandbox allows elevation if tools.elevated is enabled
    granted, reason = evaluate_elevated_execution(
        elevated_requested=True,
        context=ctx,
        elevated_config={"enabled": True},
    )
    assert granted is True
    assert reason is None

    # Disabled by configuration
    granted_dis, reason_dis = evaluate_elevated_execution(
        elevated_requested=True,
        context=ctx,
        elevated_config={"enabled": False},
    )
    assert granted_dis is False
    assert "disabled by configuration" in reason_dis


def test_evaluate_elevated_execution_provider_allowlist():
    cfg = SandboxConfig(mode="all")
    ctx = resolve_sandbox_context(session_key="telegram:123", config=cfg)

    elev_cfg = {
        "enabled": True,
        "allowFrom": {
            "telegram": True,
            "discord": False,
        },
    }
    granted, _ = evaluate_elevated_execution(
        elevated_requested=True,
        context=ctx,
        elevated_config=elev_cfg,
        sender_provider="telegram",
    )
    assert granted is True

    granted_denied, reason_denied = evaluate_elevated_execution(
        elevated_requested=True,
        context=ctx,
        elevated_config=elev_cfg,
        sender_provider="discord",
    )
    assert granted_denied is False
    assert "not allowed from provider 'discord'" in reason_denied


# ============================================================================
# 5. Filesystem Security Floor & Path Containment
# ============================================================================


def test_filesystem_guard_workspace_access_modes():
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td).resolve()
        target = ws / "file.txt"
        target.write_text("hello", encoding="utf-8")

        # 1. access_mode="none"
        with pytest.raises(PermissionError, match="workspaceAccess: 'none'"):
            validate_sandbox_path("file.txt", ws, access_mode="none")

        # 2. access_mode="ro" read succeeds, mutation fails
        val = validate_sandbox_path("file.txt", ws, is_mutation=False, access_mode="ro")
        assert val == target

        with pytest.raises(PermissionError, match="workspaceAccess: 'ro'"):
            validate_sandbox_path("file.txt", ws, is_mutation=True, access_mode="ro")

        # 3. access_mode="rw"
        val_rw = validate_sandbox_path("file.txt", ws, is_mutation=True, access_mode="rw")
        assert val_rw == target


def test_filesystem_guard_traversal_prevention():
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td).resolve()

        # Direct escape
        with pytest.raises(PermissionError, match="authorized workspace"):
            validate_sandbox_path("../../etc/passwd", ws)


def test_filesystem_guard_deepest_existing_ancestor_symlink():
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td) / "workspace"
        ws.mkdir()
        outside = Path(td) / "secret"
        outside.mkdir()
        (outside / "secret.txt").write_text("classified", encoding="utf-8")

        # Create symlink inside workspace pointing outside
        symlink_dir = ws / "symlink_dir"
        try:
            os.symlink(outside, symlink_dir, target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("Symlink creation not permitted in this environment")

        # Attempting to access file through the symlink parent must be rejected!
        with pytest.raises(PermissionError):
            validate_sandbox_path(symlink_dir / "secret.txt", ws)

        with pytest.raises(PermissionError):
            validate_sandbox_path(symlink_dir / "uncreated" / "file.txt", ws)


# ============================================================================
# 6. Environment Sanitization & Secret Scrubbing
# ============================================================================


def test_is_sensitive_env_key():
    assert is_sensitive_env_key("OPENAI_API_KEY") is True
    assert is_sensitive_env_key("ANTHROPIC_API_KEY") is True
    assert is_sensitive_env_key("GEMINI_API_KEY") is True
    assert is_sensitive_env_key("GITHUB_TOKEN") is True
    assert is_sensitive_env_key("SLACK_BOT_TOKEN") is True
    assert is_sensitive_env_key("AWS_SECRET_ACCESS_KEY") is True
    assert is_sensitive_env_key("DB_PASSWORD") is True
    assert is_sensitive_env_key("AUTH_HEADER") is True
    assert is_sensitive_env_key("PATH") is False
    assert is_sensitive_env_key("HOME") is False
    assert is_sensitive_env_key("USER") is False


def test_sanitize_execution_environment():
    dirty_env = {
        "PATH": "/usr/bin:/bin",
        "HOME": "/root",
        "SYSTEMROOT": "C:\\Windows",
        "OPENAI_API_KEY": "sk-1234567890",
        "GITHUB_TOKEN": "ghp_abcdef123456",
        "MY_SECRET": "topsecret",
        "CUSTOM_VAR": "normal_val",
    }

    clean_host = sanitize_execution_environment(base_env=dirty_env, is_sandboxed=False)
    assert "PATH" in clean_host
    assert "OPENAI_API_KEY" not in clean_host
    assert "GITHUB_TOKEN" not in clean_host
    assert "MY_SECRET" not in clean_host

    clean_sandbox = sanitize_execution_environment(base_env=dirty_env, is_sandboxed=True)
    assert "OPENAI_API_KEY" not in clean_sandbox
    assert "GITHUB_TOKEN" not in clean_sandbox
    assert "MY_SECRET" not in clean_sandbox
    # In sandboxed mode, non-safe variables like CUSTOM_VAR are also stripped
    assert "CUSTOM_VAR" not in clean_sandbox

    # Explicit caller overrides can set non-sensitive custom vars
    clean_with_overrides = sanitize_execution_environment(
        base_env=dirty_env,
        overrides={"APP_PORT": "8080"},
        is_sandboxed=True,
    )
    assert clean_with_overrides["APP_PORT"] == "8080"


# ============================================================================
# 7. Process Containment
# ============================================================================


def test_process_tree_containment_handles_none():
    # Must not raise exceptions on None or invalid objects
    ProcessTreeContainment.kill_process_tree(None)


# ============================================================================
# 8. Docker Backend Path Translation
# ============================================================================


def test_translate_path_to_sandbox():
    ws = Path("/home/user/project")
    assert translate_path_to_sandbox("/home/user/project", ws) == "/agent"
    assert translate_path_to_sandbox("/home/user/project/src/index.js", ws) == "/agent/src/index.js"


# ============================================================================
# 9. Exec Tool End-to-End Integration
# ============================================================================


@pytest.mark.asyncio
async def test_exec_tool_denied_by_tool_policy():
    with tempfile.TemporaryDirectory() as td:
        tool_def = create_exec_tool(
            cwd=td,
            options={
                "session_key": "telegram:123",
                "sandbox_config": {"mode": "all"},
                "tools_policy": {"deny": ["exec"]},
            },
        )
        execute_fn = tool_def["execute"]
        with pytest.raises(PermissionError, match="blocked by sandbox tool policy"):
            await execute_fn("call-1", {"command": "echo hello"})


@pytest.mark.asyncio
async def test_exec_tool_denied_elevated_when_creator_required():
    with tempfile.TemporaryDirectory() as td:
        tool_def = create_exec_tool(
            cwd=td,
            options={
                "session_key": "telegram:123",
                "creator_sandbox_policy": "required",
                "sandbox_config": {"mode": "all"},
            },
        )
        execute_fn = tool_def["execute"]
        with pytest.raises(PermissionError, match="creator role requires sandboxing"):
            await execute_fn("call-1", {"command": "echo hello", "elevated": True})


@pytest.mark.asyncio
async def test_exec_tool_path_traversal_blocked_in_sandbox():
    with tempfile.TemporaryDirectory() as td:
        tool_def = create_exec_tool(
            cwd=td,
            options={
                "session_key": "telegram:123",
                "sandbox_config": {"mode": "all"},
            },
        )
        execute_fn = tool_def["execute"]
        with pytest.raises(PermissionError):
            await execute_fn("call-1", {"command": "echo hello", "workdir": "../../outside"})


@pytest.mark.asyncio
async def test_exec_tool_host_execution_success():
    with tempfile.TemporaryDirectory() as td:
        # mode="off" runs on host
        tool_def = create_exec_tool(
            cwd=td,
            options={
                "session_key": "agent:main:main",
                "sandbox_config": {"mode": "off"},
            },
        )
        execute_fn = tool_def["execute"]

        # Run a simple echo command with allow-all ctx permissions
        class MockCtx:
            permissions = type("Perm", (), {"mode": "allow-all"})()

        res = await execute_fn("call-1", {"command": "echo parity_test_ok"}, ctx=MockCtx())
        assert res is not None
        assert "details" in res
        assert res["details"]["sandboxed"] is False
        assert "content" in res
        output = res["content"][0]["text"]
        assert "parity_test_ok" in output


@pytest.mark.asyncio
async def test_read_tool_sandbox_workspace_access_none():
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td).resolve()
        (ws / "sample.txt").write_text("content", encoding="utf-8")

        tool_def = create_read_tool(
            cwd=str(ws),
            options={
                "session_key": "telegram:123",
                "sandbox_config": {"mode": "all", "workspaceAccess": "none"},
            },
        )
        execute_fn = tool_def["execute"]
        with pytest.raises(PermissionError, match="workspaceAccess: 'none'"):
            await execute_fn("call-1", {"path": "sample.txt"})


@pytest.mark.asyncio
async def test_write_tool_sandbox_workspace_access_ro():
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td).resolve()
        tool_def = create_write_tool(
            cwd=str(ws),
            options={
                "session_key": "telegram:123",
                "sandbox_config": {"mode": "all", "workspaceAccess": "ro"},
            },
        )
        execute_fn = tool_def["execute"]
        with pytest.raises(PermissionError, match="workspaceAccess: 'ro'"):
            await execute_fn("call-1", {"path": "new.txt", "content": "data"})


@pytest.mark.asyncio
async def test_write_tool_sandbox_escape_blocked():
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td).resolve()
        tool_def = create_write_tool(
            cwd=str(ws),
            options={
                "session_key": "telegram:123",
                "sandbox_config": {"mode": "all", "workspaceAccess": "rw"},
            },
        )
        execute_fn = tool_def["execute"]
        with pytest.raises(PermissionError, match="authorized workspace"):
            await execute_fn("call-1", {"path": "../../escape.txt", "content": "data"})


@pytest.mark.asyncio
async def test_edit_tool_sandbox_workspace_access_ro():
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td).resolve()
        target = ws / "test.txt"
        target.write_text("line1\nline2\n", encoding="utf-8")

        tool_def = create_edit_tool(
            cwd=str(ws),
            options={
                "session_key": "telegram:123",
                "sandbox_config": {"mode": "all", "workspaceAccess": "ro"},
            },
        )
        execute_fn = tool_def["execute"]
        with pytest.raises(PermissionError, match="workspaceAccess: 'ro'"):
            await execute_fn(
                "call-1",
                {"path": "test.txt", "edits": [{"oldText": "line1", "newText": "replaced"}]},
            )


@pytest.mark.asyncio
async def test_apply_patch_sandbox_workspace_access_ro():
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td).resolve()
        tool_def = create_apply_patch_tool(
            cwd=str(ws),
            options={
                "session_key": "telegram:123",
                "sandbox_config": {"mode": "all", "workspaceAccess": "ro"},
            },
        )
        execute_fn = tool_def["execute"]
        patch = "*** Begin Patch\n*** Add File: file.txt\n+hello\n*** End Patch"
        with pytest.raises((PermissionError, RuntimeError), match="workspaceAccess: 'ro'"):
            await execute_fn("call-1", {"input": patch})


@pytest.mark.asyncio
async def test_ls_tool_sandbox_workspace_access_none():
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td).resolve()
        tool_def = create_ls_tool(
            cwd=str(ws),
            options={
                "session_key": "telegram:123",
                "sandbox_config": {"mode": "all", "workspaceAccess": "none"},
            },
        )
        execute_fn = tool_def["execute"]
        with pytest.raises(PermissionError, match="workspaceAccess: 'none'"):
            await execute_fn("call-1", {"path": "."})
