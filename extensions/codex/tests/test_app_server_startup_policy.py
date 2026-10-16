"""Tests for app-server startup policy: NODE_OPTIONS attestation, launch
config normalization, env overrides, and doctor launch-config gates.

OpenClaw parity: ``extensions/codex/src/app-server/runtime-artifact.ts``
(NODE_OPTIONS section), ``transport-stdio.test.ts`` (clearEnv),
``config.test.ts`` (BIN/ARGS), and ``config-options.ts`` (homes-stdio).
"""

from __future__ import annotations

import pytest

from extensions.codex.src.app_server.config import (
    read_codex_plugin_config,
    resolve_codex_app_server_runtime_options,
)
from extensions.codex.src.app_server.launch_policy import (
    assert_no_inline_args,
    detect_inline_args,
    normalize_headers,
    normalize_launch_clear_env,
    normalize_service_tier,
    resolve_app_server_args,
    resolve_approval_policy,
    resolve_approvals_reviewer,
    resolve_policy_mode,
    resolve_sandbox_mode,
    split_command_args,
)
from extensions.codex.src.app_server.node_options import (
    assert_safe_node_options_env,
    attest_node_options,
    parse_node_options,
)
from extensions.codex.src.app_server.spawn_env import resolve_codex_app_server_spawn_env
from extensions.codex.src.doctor import check_codex_app_server_launch_config


def test_parse_node_options_lexer():
    assert parse_node_options("--max-old-space-size=512 --no-warnings") == [
        "--max-old-space-size=512",
        "--no-warnings",
    ]
    assert parse_node_options('--dns-result-order "ipv4first"') == [
        "--dns-result-order",
        "ipv4first",
    ]
    # Single quotes are literal (only double quotes group).
    assert parse_node_options("--flag 'a b'") == ["--flag", "'a", "b'"]
    assert parse_node_options("--flag 'oops") == ["--flag", "'oops"]
    assert parse_node_options('--flag "oops') is None
    assert parse_node_options("") == []


@pytest.mark.parametrize(
    "value",
    [
        "--dns-result-order=ipv4first --no-network-family-autoselection",
        "--max-old-space-size=512",
        "--max-old-space-size 512",
        "--no-warnings",
        "--disable-warning=ExperimentalWarning",
    ],
)
def test_attest_node_options_allows_bounded(value):
    assert attest_node_options(value) == {"ok": True}


@pytest.mark.parametrize(
    ("value", "option"),
    [
        ("--require fs", "--require"),
        ("--import ./x.js", "--import"),
        ("--max-old-space-size abc", "--max-old-space-size"),
        ("--dns-result-order mars", "--dns-result-order"),
        ("--mystery-flag", "--mystery-flag"),
        ("--no-warnings=yes", "--no-warnings"),
    ],
)
def test_attest_node_options_fails_closed(value, option):
    assert attest_node_options(value) == {"ok": False, "option": option}


def test_attest_node_options_unparseable_has_no_option():
    assert attest_node_options('--flag "oops') == {"ok": False}


def test_assert_safe_node_options_env():
    assert_safe_node_options_env({"PATH": "/usr/bin"})
    assert_safe_node_options_env({"node_options": ""})
    assert_safe_node_options_env(None)
    with pytest.raises(ValueError, match="cannot attest NODE_OPTIONS option --require"):
        assert_safe_node_options_env({"NODE_OPTIONS": "--require fs"})
    with pytest.raises(ValueError, match="cannot safely parse NODE_OPTIONS"):
        assert_safe_node_options_env({"Node_Options": '--flag "oops'})


def test_normalize_launch_clear_env():
    assert normalize_launch_clear_env([" OPENAI_API_KEY ", "", "  "]) == ["OPENAI_API_KEY"]
    assert normalize_launch_clear_env(None) == []
    assert normalize_launch_clear_env("nope") == []
    # Reserved vars are launch-owned: dropped case-insensitively.
    assert normalize_launch_clear_env(["CODEX_HOME", "HOME", "FOO"]) == ["FOO"]
    assert normalize_launch_clear_env(["codex_home", "home", "FOO"]) == ["FOO"]


def test_split_command_args():
    assert split_command_args('app-server --listen "stdio://"') == [
        "app-server",
        "--listen",
        "stdio://",
    ]
    assert split_command_args("--flag 'a  b'") == ["--flag", "a  b"]
    assert split_command_args('--flag "oops', allow_unclosed_quotes=True) == [
        "--flag",
        "oops",
    ]
    assert split_command_args('--flag "oops') is None
    # Backslashes stay literal outside quotes (command syntax).
    assert split_command_args("a\\b c") == ["a\\b", "c"]


def test_detect_inline_args():
    found = detect_inline_args("node /opt/codex/bin/codex.js --listen stdio")
    assert found == {
        "executable": "node",
        "arguments": "/opt/codex/bin/codex.js --listen stdio",
    }
    assert detect_inline_args("/usr/local/bin/codex") is None
    assert detect_inline_args("") is None
    # Quoted executable with spaces still detects trailing args.
    found = detect_inline_args('"C:\\Program Files\\nodejs\\node.exe" app.js')
    assert found is not None


def test_assert_no_inline_args_message():
    with pytest.raises(ValueError, match="OPENCLAW_CODEX_APP_SERVER_BIN must be only"):
        assert_no_inline_args("node app.js", source="env")
    with pytest.raises(
        ValueError, match="plugins.entries.codex.config.appServer.command must be only"
    ):
        assert_no_inline_args("node app.js", source="config")
    assert_no_inline_args("/usr/local/bin/codex", source="env") is None


def test_resolve_app_server_args():
    assert resolve_app_server_args(["a", "", "b"], "ignored") == ["a", "b"]
    assert resolve_app_server_args(None, '--listen "stdio://"') == ["--listen", "stdio://"]
    assert resolve_app_server_args(None, None) == []
    assert resolve_policy_mode("guardian") == "guardian"
    assert resolve_policy_mode("yolo") == "yolo"
    assert resolve_policy_mode("turbo") is None
    assert resolve_policy_mode(None) is None


def test_parser_posture_env_fallbacks():
    cfg = read_codex_plugin_config(
        {},
        env={
            "OPENCLAW_CODEX_APP_SERVER_APPROVAL_POLICY": "never",
            "OPENCLAW_CODEX_APP_SERVER_SANDBOX": "read-only",
        },
    )
    assert cfg.app_server.approval_policy == "never"
    assert cfg.app_server.sandbox == "read-only"
    # Explicit config wins over env.
    cfg = read_codex_plugin_config(
        {"appServer": {"approvalPolicy": "on-request", "sandbox": "workspace-write"}},
        env={
            "OPENCLAW_CODEX_APP_SERVER_APPROVAL_POLICY": "never",
            "OPENCLAW_CODEX_APP_SERVER_SANDBOX": "read-only",
        },
    )
    assert cfg.app_server.approval_policy == "on-request"
    assert cfg.app_server.sandbox == "workspace-write"


def test_runtime_options_resolve_openclaw_local_posture_and_environment():
    options = resolve_codex_app_server_runtime_options(
        {
            "appServer": {
                "command": "/opt/codex",
                "clearEnv": ["HOME", "CODEX_HOME", "OPENAI_API_KEY"],
            }
        },
        env={},
    )
    assert options.command == "/opt/codex"
    assert options.command_source == "config"
    assert options.approval_policy == "never"
    assert options.sandbox == "danger-full-access"
    assert options.approvals_reviewer == "user"
    assert options.clear_env == ["OPENAI_API_KEY"]


def test_runtime_options_guardian_and_remote_websocket_auth():
    options = resolve_codex_app_server_runtime_options(
        {
            "appServer": {
                "transport": "websocket",
                "url": "ws://gateway-host:39175",
                "authToken": "secret",
                "mode": "guardian",
            }
        },
        env={},
    )
    assert options.connection_class == "remote"
    assert options.approval_policy == "on-request"
    assert options.sandbox == "workspace-write"
    assert options.approvals_reviewer == "auto_review"

    with pytest.raises(ValueError, match="require appServer.authToken"):
        resolve_codex_app_server_runtime_options(
            {"appServer": {"transport": "websocket", "url": "ws://gateway-host:39175"}},
            env={},
        )


def test_spawn_environment_scopes_codex_home_and_prepared_auth():
    options = resolve_codex_app_server_runtime_options(
        {"appServer": {"clearEnv": ["CUSTOM_SECRET"]}},
        env={},
    )
    child_env = resolve_codex_app_server_spawn_env(
        options,
        agent_dir="C:/agents/main",
        base_env={
            "HOME": "C:/Users/operator",
            "CODEX_HOME": "C:/Users/operator/.codex",
            "CODEX_API_KEY": "secret",
            "OPENAI_API_KEY": "secret",
            "CUSTOM_SECRET": "secret",
            "NODE_PATH": "C:/inject",
            "PATH": "C:/bin",
        },
        prepared_auth=True,
    )
    assert child_env["CODEX_HOME"].endswith("agents\\main\\codex-home") or child_env[
        "CODEX_HOME"
    ].endswith("agents/main/codex-home")
    assert child_env["HOME"] == "C:/Users/operator"
    assert "CODEX_API_KEY" not in child_env
    assert "OPENAI_API_KEY" not in child_env
    assert "CUSTOM_SECRET" not in child_env
    assert "NODE_PATH" not in child_env


def test_runtime_options_resolve_network_proxy_profile_and_runtime_fields():
    options = resolve_codex_app_server_runtime_options(
        {
            "appServer": {
                "requestTimeoutMs": 5_000,
                "codeModeOnly": True,
                "serviceTier": "fast",
                "sandbox": "workspace-write",
                "networkProxy": {
                    "enabled": True,
                    "domains": {"api.openai.com": "allow", "blocked.example": "deny"},
                    "unixSockets": {"/tmp/proxy.sock": "allow"},
                },
            }
        },
        env={},
    )
    assert options.code_mode_only is True
    assert options.request_timeout_ms == 5_000
    assert options.service_tier == "priority"
    assert options.network_proxy is not None
    assert options.network_proxy["profileName"].startswith("openclaw-network-")
    patch = options.network_proxy["configPatch"]
    assert patch["features.network_proxy.enabled"] is True
    assert patch["permissions"][options.network_proxy["profileName"]]["network"]["domains"] == {
        "api.openai.com": "allow",
        "blocked.example": "deny",
    }


def test_experimental_sandbox_exec_server_is_read_from_app_server_contract():
    cfg = read_codex_plugin_config(
        {"appServer": {"experimental": {"sandboxExecServer": True}}},
        env={},
    )
    assert cfg.experimental.sandbox_exec_server is True


def test_parser_env_overrides():
    cfg = read_codex_plugin_config({}, env={})
    assert cfg.app_server.command is None
    assert cfg.app_server.args == ["app-server", "--listen", "stdio://"]
    assert cfg.app_server.mode is None
    assert cfg.app_server.clear_env == []
    assert cfg.session_catalog.homes == []

    cfg = read_codex_plugin_config(
        {},
        env={
            "OPENCLAW_CODEX_APP_SERVER_BIN": "/usr/local/bin/codex",
            "OPENCLAW_CODEX_APP_SERVER_ARGS": '--listen "stdio://"',
            "OPENCLAW_CODEX_APP_SERVER_MODE": "guardian",
        },
    )
    assert cfg.app_server.command == "/usr/local/bin/codex"
    assert cfg.app_server.args == ["--listen", "stdio://"]
    assert cfg.app_server.mode == "guardian"

    # Explicit config wins over env.
    cfg = read_codex_plugin_config(
        {"appServer": {"command": "/opt/codex", "mode": "yolo"}},
        env={"OPENCLAW_CODEX_APP_SERVER_BIN": "/usr/local/bin/codex"},
    )
    assert cfg.app_server.command == "/opt/codex"
    assert cfg.app_server.mode == "yolo"

    cfg = read_codex_plugin_config(
        {
            "appServer": {"clearEnv": [" FOO ", "", "CODEX_HOME"]},
            "sessionCatalog": {"homes": ["/data/a", ""]},
        },
        env={},
    )
    assert cfg.app_server.clear_env == ["FOO", "CODEX_HOME"]
    assert cfg.session_catalog.homes == ["/data/a"]


def test_posture_and_service_tier_normalizers():
    assert resolve_approval_policy("never") == "never"
    assert resolve_approval_policy("on-request") == "on-request"
    assert resolve_approval_policy("on-failure") == "on-request"
    assert resolve_approval_policy("untrusted") is None
    assert resolve_approval_policy(None) is None
    assert resolve_sandbox_mode("workspace-write") == "workspace-write"
    assert resolve_sandbox_mode("permissive") is None
    assert resolve_approvals_reviewer("auto_review") == "auto_review"
    assert resolve_approvals_reviewer("guardian_subagent") == "guardian_subagent"
    assert resolve_approvals_reviewer("user") == "user"
    assert resolve_approvals_reviewer("admin") is None
    assert normalize_service_tier("fast") == "priority"
    assert normalize_service_tier("priority") == "priority"
    assert normalize_service_tier("FLEX") == "flex"
    assert normalize_service_tier("turbo") == "turbo"
    assert normalize_service_tier("  ") is None
    assert normalize_service_tier(None) is None
    assert normalize_headers({" x-a ": " 1 ", "empty": "  ", "nonstr": 5}) == {"x-a": "1"}
    assert normalize_headers([]) == {}
    assert normalize_headers(None) == {}


def test_parser_posture_and_workspace_fields():
    cfg = read_codex_plugin_config(
        {
            "appServer": {
                "approvalPolicy": "on-failure",
                "sandbox": "workspace-write",
                "approvalsReviewer": "auto_review",
                "serviceTier": "fast",
                "codeModeOnly": True,
                "headers": {"x-t": "v"},
                "remoteWorkspaceRoot": "/srv/remote",
                "defaultWorkspaceDir": "/srv/local",
            }
        },
        env={},
    )
    app = cfg.app_server
    assert app.approval_policy == "on-request"
    assert app.sandbox == "workspace-write"
    assert app.approvals_reviewer == "auto_review"
    assert app.service_tier == "priority"
    assert app.code_mode_only is True
    assert app.headers == {"x-t": "v"}
    assert app.remote_workspace_root == "/srv/remote"
    assert app.default_workspace_dir == "/srv/local"
    # Plugin-root remote root still resolves (legacy fallback).
    assert cfg.remote_workspace_root == "/srv/remote"

    cfg = read_codex_plugin_config({"remoteWorkspaceRoot": "/srv/legacy"}, env={})
    assert cfg.app_server.remote_workspace_root is None
    assert cfg.remote_workspace_root == "/srv/legacy"

    cfg = read_codex_plugin_config({"appServer": {"approvalPolicy": "bogus"}}, env={})
    assert cfg.app_server.approval_policy is None
    assert cfg.app_server.code_mode_only is False
    assert cfg.app_server.headers == {}


def test_parser_object_surfaces():
    cfg = read_codex_plugin_config(
        {
            "codexPlugins": {"enabled": True, "plugins": {"a": {"pluginName": "a"}}},
            "supervision": {
                "enabled": True,
                "endpoints": [
                    {"id": "n1", "transport": "websocket", "url": "ws://h:1"},
                    {"command": "codex", "args": ["a", ""]},
                    {"transport": "websocket"},
                ],
                "allowWriteControls": True,
            },
            "appServer": {
                "networkProxy": {
                    "enabled": True,
                    "domains": {"api.openai.com": "allow", "x.test": "maybe"},
                    "unixSockets": {"/tmp/p.sock": "allow", "/tmp/b.sock": "yes"},
                    "proxyUrl": "http://127.0.0.1:3128",
                    "allowUpstreamProxy": True,
                    "bogus": 1,
                }
            },
        },
        env={},
    )
    assert cfg.codex_plugins == {"enabled": True, "plugins": {"a": {"pluginName": "a"}}}
    assert cfg.supervision == {
        "enabled": True,
        "endpoints": [
            {"id": "n1", "transport": "websocket", "url": "ws://h:1"},
            {"transport": "stdio-proxy", "command": "codex", "args": ["a"]},
        ],
        "allowWriteControls": True,
    }
    assert cfg.app_server.network_proxy == {
        "enabled": True,
        "domains": {"api.openai.com": "allow"},
        "unixSockets": {"/tmp/p.sock": "allow"},
        "proxyUrl": "http://127.0.0.1:3128",
        "allowUpstreamProxy": True,
    }
    cfg = read_codex_plugin_config({"supervision": {"enabled": "yes"}}, env={})
    assert cfg.supervision is None
    cfg = read_codex_plugin_config({}, env={})
    assert cfg.codex_plugins is None
    assert cfg.supervision is None
    assert cfg.app_server.network_proxy is None


def test_doctor_launch_config_gates():
    # Inline args in a command override fail with the exact setup message.
    findings = check_codex_app_server_launch_config(
        {"appServer": {"command": "node /opt/codex/app.js"}}, env={}
    )
    assert len(findings) == 1
    assert "must be only the Codex app-server executable path" in findings[0].message

    findings = check_codex_app_server_launch_config(
        {"appServer": {"command": "node /opt/codex/app.js"}},
        env={"OPENCLAW_CODEX_APP_SERVER_BIN": "/x"},
    )
    assert any("appServer.command" in f.message for f in findings)

    # homes requires stdio transport.
    findings = check_codex_app_server_launch_config(
        {
            "appServer": {"transport": "websocket", "url": "ws://h:1"},
            "sessionCatalog": {"homes": ["/data/a"]},
        },
        env={},
    )
    assert len(findings) == 1
    assert "sessionCatalog.homes requires appServer.transport=stdio" in findings[0].message

    # Retired approval policy is reported with its replacement.
    findings = check_codex_app_server_launch_config(
        {"appServer": {"approvalPolicy": "untrusted"}}, env={}
    )
    assert len(findings) == 1
    assert '"untrusted" is retired' in findings[0].message
    assert '"on-request"' in (findings[0].fix_hint or "")

    # Clean config: no findings.
    assert check_codex_app_server_launch_config({"appServer": {"transport": "stdio"}}, env={}) == []
