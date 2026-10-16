"""Codex app-server configuration contracts and parser.

OpenClaw parity: ``extensions/codex/src/app-server/config-contracts.ts`` and
``extensions/codex/src/app-server/config-parsing.ts``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Literal

from extensions.codex.src.computer_use.config import (
    CodexComputerUseConfig,
    resolve_codex_computer_use_config,
)

CodexAppServerTransportMode = Literal["stdio", "websocket", "unix"]
CodexAppServerHomeScope = Literal["agent", "user"]
CodexAppServerConnectionScope = Literal["harness", "supervision"]
CodexAppServerCommandSource = Literal["config", "env", "managed"]
CodexAppServerConnectionClass = Literal["local-loopback", "remote"]


def resolve_codex_app_server_home_scope(
    app_server: "CodexAppServerConfig | None",
    *,
    connection_scope: CodexAppServerConnectionScope = "harness",
) -> CodexAppServerHomeScope:
    """Resolve the effective home scope for an app-server connection.

    OpenClaw parity: mirrors ``resolveCodexAppServerHomeScope``
    (``config-options.ts:78``). Rules:

    - An explicit ``homeScope`` config value wins unconditionally.
    - A supervision connection on a non-websocket transport defaults to
      ``"user"`` (the operator's native Codex home), so the session
      catalog can discover native threads without extra configuration.
    - Everything else defaults to ``"agent"`` (isolated per-agent home).
    """
    configured = getattr(app_server, "home_scope", None)
    if configured in ("agent", "user"):
        return configured  # type: ignore[return-value]
    transport = getattr(app_server, "transport", "stdio")
    if connection_scope == "supervision" and transport != "websocket":
        return "user"
    return "agent"


@dataclass(frozen=True, slots=True)
class CodexAppServerRuntimeOptions:
    """Resolved launch contract consumed by the app-server transport."""

    transport: CodexAppServerTransportMode
    home_scope: CodexAppServerHomeScope
    command: str
    command_source: CodexAppServerCommandSource
    args: list[str]
    connection_class: CodexAppServerConnectionClass
    approval_policy: str
    sandbox: str
    approvals_reviewer: str
    policy_mode: str
    code_mode_only: bool = False
    request_timeout_ms: int = 60_000
    service_tier: str | None = None
    network_proxy: dict[str, Any] | None = None
    default_workspace_dir: str | None = None
    url: str | None = None
    auth_token: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    clear_env: list[str] = field(default_factory=list)
    managed_command_order: Literal["package-first", "desktop-first"] = "package-first"
    remote_workspace_root: str | None = None
    codex_plugins: dict[str, Any] | None = None

    @property
    def homeScope(self) -> CodexAppServerHomeScope:  # noqa: N802
        return self.home_scope

    @property
    def commandSource(self) -> CodexAppServerCommandSource:  # noqa: N802
        return self.command_source

    @property
    def approvalPolicy(self) -> str:  # noqa: N802
        return self.approval_policy

    @property
    def approvalsReviewer(self) -> str:  # noqa: N802
        return self.approvals_reviewer


@dataclass(frozen=True, slots=True)
class CodexAppServerConfig:
    """Codex app-server transport and process execution configuration."""

    transport: CodexAppServerTransportMode = "stdio"
    home_scope: CodexAppServerHomeScope = "agent"
    command: str | None = None
    args: list[str] = field(default_factory=lambda: ["app-server", "--listen", "stdio://"])
    url: str | None = None
    auth_token: str | None = None
    request_timeout_ms: int = 60_000
    turn_completion_idle_timeout_ms: int = 60_000
    post_tool_raw_assistant_completion_idle_timeout_ms: int = 300_000
    managed_command_order: Literal["package-first", "desktop-first"] = "package-first"
    clear_env: list[str] = field(default_factory=list)
    mode: str | None = None
    approval_policy: str | None = None
    sandbox: str | None = None
    approvals_reviewer: str | None = None
    service_tier: str | None = None
    code_mode_only: bool = False
    headers: dict[str, str] = field(default_factory=dict)
    remote_workspace_root: str | None = None
    default_workspace_dir: str | None = None
    network_proxy: dict[str, Any] | None = None

    @property
    def homeScope(self) -> CodexAppServerHomeScope:  # noqa: N802
        """Expose the OpenClaw wire name used by harness callers."""
        return self.home_scope

    @property
    def authToken(self) -> str | None:  # noqa: N802
        """Expose the OpenClaw wire name used by harness callers."""
        return self.auth_token


@dataclass(frozen=True, slots=True)
class CodexSessionCatalogConfig:
    """Codex session catalog discovery configuration."""

    enabled: bool = True
    homes: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class CodexAppServerExperimentalConfig:
    """Experimental app-server capabilities."""

    sandbox_exec_server: bool = False


@dataclass(frozen=True, slots=True)
class CodexPluginConfig:
    """Root configuration block for the Codex plugin."""

    enabled: bool = True
    codex_plugins: dict[str, Any] | None = None
    supervision: dict[str, Any] | None = None
    app_server: CodexAppServerConfig = field(default_factory=CodexAppServerConfig)
    computer_use: CodexComputerUseConfig = field(default_factory=CodexComputerUseConfig)
    session_catalog: CodexSessionCatalogConfig = field(default_factory=CodexSessionCatalogConfig)
    remote_workspace_root: str | None = None
    fast_mode: str = "auto"
    codex_dynamic_tools_loading: Literal["searchable", "direct"] = "searchable"
    codex_dynamic_tools_exclude: list[str] = field(default_factory=list)
    experimental: CodexAppServerExperimentalConfig = field(
        default_factory=CodexAppServerExperimentalConfig
    )


def _read_non_empty_str(value: Any) -> str | None:
    """Mirror ``readNonEmptyString`` for env/config override reads."""
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed or None


def read_codex_plugin_config(
    raw_config: dict[str, Any] | None = None, env: dict[str, Any] | None = None
) -> CodexPluginConfig:
    """Parse raw configuration dictionary into structured ``CodexPluginConfig``.

    Local-testing env overrides (mirroring ``config-options.ts``): an
    explicit ``appServer.command`` wins, else
    ``OPENCLAW_CODEX_APP_SERVER_BIN``; args resolve from config
    (list or string) else ``OPENCLAW_CODEX_APP_SERVER_ARGS``; mode from
    config else ``OPENCLAW_CODEX_APP_SERVER_MODE``. Pass ``env={}`` for
    hermetic parsing without process-env reads.
    """
    from extensions.codex.src.app_server.launch_policy import (  # noqa: PLC0415
        APP_SERVER_APPROVAL_POLICY_ENV_VAR,
        APP_SERVER_ARGS_ENV_VAR,
        APP_SERVER_BIN_ENV_VAR,
        APP_SERVER_MODE_ENV_VAR,
        APP_SERVER_SANDBOX_ENV_VAR,
        normalize_headers,
        normalize_network_proxy,
        normalize_service_tier,
        normalize_supervision,
        normalize_trimmed_string_list,
        read_non_empty_env,
        resolve_app_server_args,
        resolve_approval_policy,
        resolve_approvals_reviewer,
        resolve_policy_mode,
        resolve_sandbox_mode,
    )

    if not isinstance(raw_config, dict):
        return CodexPluginConfig()

    live_env: dict[str, Any] = env if isinstance(env, dict) else dict(os.environ)
    enabled = bool(raw_config.get("enabled", True))

    # Parse appServer sub-block
    app_raw = raw_config.get("appServer") or raw_config.get("app_server")
    if app_raw is None and any(
        key in raw_config
        for key in ("transport", "homeScope", "home_scope", "url", "authToken", "auth_token")
    ):
        app_raw = raw_config
    app_raw = app_raw or {}
    if isinstance(app_raw, dict):
        transport = app_raw.get("transport", "stdio")
        if transport not in ("stdio", "websocket", "unix"):
            transport = "stdio"
        home_scope = app_raw.get("homeScope", app_raw.get("home_scope", "agent"))
        if home_scope not in ("agent", "user"):
            home_scope = "agent"

        command = _read_non_empty_str(app_raw.get("command")) or _read_non_empty_str(
            live_env.get(APP_SERVER_BIN_ENV_VAR)
        )
        args_list = resolve_app_server_args(
            app_raw.get("args"), live_env.get(APP_SERVER_ARGS_ENV_VAR)
        ) or ["app-server", "--listen", "stdio://"]

        app_cfg = CodexAppServerConfig(
            transport=transport,
            home_scope=home_scope,
            command=command,
            args=args_list,
            url=app_raw.get("url"),
            auth_token=app_raw.get("authToken") or app_raw.get("auth_token"),
            request_timeout_ms=int(app_raw.get("requestTimeoutMs", 60_000)),
            turn_completion_idle_timeout_ms=int(app_raw.get("turnCompletionIdleTimeoutMs", 60_000)),
            post_tool_raw_assistant_completion_idle_timeout_ms=int(
                app_raw.get("postToolRawAssistantCompletionIdleTimeoutMs", 300_000)
            ),
            managed_command_order="desktop-first"
            if app_raw.get("managedCommandOrder") == "desktop-first"
            else "package-first",
            clear_env=normalize_trimmed_string_list(
                app_raw.get("clearEnv", app_raw.get("clear_env", []))
            ),
            mode=resolve_policy_mode(app_raw.get("mode"))
            or resolve_policy_mode(_read_non_empty_str(live_env.get(APP_SERVER_MODE_ENV_VAR))),
            approval_policy=resolve_approval_policy(
                app_raw.get("approvalPolicy", app_raw.get("approval_policy"))
            )
            or resolve_approval_policy(
                read_non_empty_env(live_env, APP_SERVER_APPROVAL_POLICY_ENV_VAR)
            ),
            sandbox=resolve_sandbox_mode(app_raw.get("sandbox"))
            or resolve_sandbox_mode(read_non_empty_env(live_env, APP_SERVER_SANDBOX_ENV_VAR)),
            approvals_reviewer=resolve_approvals_reviewer(
                app_raw.get("approvalsReviewer", app_raw.get("approvals_reviewer"))
            ),
            service_tier=normalize_service_tier(
                app_raw.get("serviceTier", app_raw.get("service_tier"))
            ),
            code_mode_only=bool(app_raw.get("codeModeOnly", app_raw.get("code_mode_only", False))),
            headers=normalize_headers(app_raw.get("headers")),
            remote_workspace_root=_read_non_empty_str(app_raw.get("remoteWorkspaceRoot"))
            or _read_non_empty_str(app_raw.get("remote_workspace_root")),
            default_workspace_dir=_read_non_empty_str(
                app_raw.get("defaultWorkspaceDir", app_raw.get("default_workspace_dir"))
            ),
            network_proxy=normalize_network_proxy(app_raw.get("networkProxy")),
        )
    else:
        app_cfg = CodexAppServerConfig()

    # Parse computerUse sub-block via resolved helper
    cu_raw = raw_config.get("computerUse") or raw_config.get("computer_use") or {}
    cu_dict = cu_raw if isinstance(cu_raw, dict) else {}
    cu_config_obj = CodexComputerUseConfig(
        enabled=cu_dict.get("enabled"),
        auto_install=cu_dict.get("autoInstall", cu_dict.get("auto_install")),
        marketplace_discovery_timeout_ms=cu_dict.get("marketplaceDiscoveryTimeoutMs"),
        live_test_timeout_ms=cu_dict.get("liveTestTimeoutMs"),
        tool_call_timeout_ms=cu_dict.get("toolCallTimeoutMs"),
        health_check_enabled=cu_dict.get("healthCheckEnabled"),
        health_check_interval_minutes=cu_dict.get("healthCheckIntervalMinutes"),
        plugin_cache_mode=cu_dict.get("pluginCacheMode"),
        strict_readiness=cu_dict.get("strictReadiness"),
        auto_repair=cu_dict.get("autoRepair"),
        marketplace_source=cu_dict.get("marketplaceSource"),
        marketplace_path=cu_dict.get("marketplacePath"),
        marketplace_name=cu_dict.get("marketplaceName"),
        plugin_name=cu_dict.get("pluginName"),
        mcp_server_name=cu_dict.get("mcpServerName"),
    )
    resolved_cu = resolve_codex_computer_use_config(
        cu_config_obj,
        force_enable=raw_config.get("computerUse") is not None
        or raw_config.get("computer_use") is not None,
    )
    cu_cfg = CodexComputerUseConfig(
        enabled=resolved_cu.enabled,
        auto_install=resolved_cu.auto_install,
        marketplace_discovery_timeout_ms=resolved_cu.marketplace_discovery_timeout_ms,
        live_test_timeout_ms=resolved_cu.live_test_timeout_ms,
        tool_call_timeout_ms=resolved_cu.tool_call_timeout_ms,
        health_check_enabled=resolved_cu.health_check_enabled,
        health_check_interval_minutes=resolved_cu.health_check_interval_minutes,
        plugin_cache_mode=resolved_cu.plugin_cache_mode,
        strict_readiness=resolved_cu.strict_readiness,
        auto_repair=resolved_cu.auto_repair,
        marketplace_source=resolved_cu.marketplace_source,
        marketplace_path=resolved_cu.marketplace_path,
        marketplace_name=resolved_cu.marketplace_name,
        plugin_name=resolved_cu.plugin_name,
        mcp_server_name=resolved_cu.mcp_server_name,
    )

    # Parse sessionCatalog
    sc_raw = raw_config.get("sessionCatalog") or raw_config.get("session_catalog") or {}
    sc_enabled = bool(sc_raw.get("enabled", True)) if isinstance(sc_raw, dict) else True
    sc_cfg = CodexSessionCatalogConfig(
        enabled=sc_enabled,
        homes=normalize_trimmed_string_list(
            sc_raw.get("homes", []) if isinstance(sc_raw, dict) else []
        ),
    )

    # Parse experimental
    exp_raw = (
        app_raw.get("experimental", {})
        if isinstance(app_raw, dict)
        else raw_config.get("experimental", {})
    )
    exp_cfg = CodexAppServerExperimentalConfig(
        sandbox_exec_server=bool(exp_raw.get("sandboxExecServer", False))
        if isinstance(exp_raw, dict)
        else False
    )

    # Canonical home is appServer.remoteWorkspaceRoot (OpenClaw placement);
    # the plugin-root spelling stays as a legacy fallback so existing
    # harness attachment readers keep working.
    remote_root = (
        app_cfg.remote_workspace_root
        or raw_config.get("remoteWorkspaceRoot")
        or raw_config.get("remote_workspace_root")
    )
    fast_mode = raw_config.get("fastMode", raw_config.get("fast_mode", "auto"))
    dt_loading = raw_config.get("codexDynamicToolsLoading", "searchable")
    if dt_loading not in ("searchable", "direct"):
        dt_loading = "searchable"
    dt_exclude = raw_config.get("codexDynamicToolsExclude", [])
    if not isinstance(dt_exclude, list):
        dt_exclude = []

    # codexPlugins passes through unvalidated (mirrors the zod unknown
    # passthrough); supervision normalizes to its endpoint shapes.
    codex_plugins_raw = raw_config.get("codexPlugins")
    return CodexPluginConfig(
        enabled=enabled,
        codex_plugins=codex_plugins_raw if isinstance(codex_plugins_raw, dict) else None,
        supervision=normalize_supervision(raw_config.get("supervision")),
        app_server=app_cfg,
        computer_use=cu_cfg,
        session_catalog=sc_cfg,
        remote_workspace_root=str(remote_root) if remote_root else None,
        fast_mode=str(fast_mode),
        codex_dynamic_tools_loading=dt_loading,
        codex_dynamic_tools_exclude=[str(x) for x in dt_exclude],
        experimental=exp_cfg,
    )


def resolve_codex_app_server_runtime_options(
    raw_config: dict[str, Any] | None = None,
    env: dict[str, Any] | None = None,
    *,
    plugin_root: str | None = None,
    platform: str | None = None,
) -> CodexAppServerRuntimeOptions:
    """Resolve the OpenClaw-style app-server launch contract.

    Raw config parsing stays side-effect free; this function owns the final
    transport, command, environment, and execution-posture decisions.
    """
    from extensions.codex.src.app_server.config_security import (
        assert_codex_app_server_connection_security,
        infer_codex_app_server_connection_class,
        resolve_codex_app_server_network_proxy,
    )
    from extensions.codex.src.app_server.launch_policy import (
        assert_no_inline_args,
        normalize_launch_clear_env,
        resolve_policy_mode,
    )
    from extensions.codex.src.app_server.managed_binary import (
        find_managed_codex_app_server_command_path,
    )

    live_env = env if isinstance(env, dict) else dict(os.environ)
    parsed = read_codex_plugin_config(raw_config, env=live_env)
    app = parsed.app_server
    configured_app = (raw_config or {}).get("appServer", (raw_config or {}).get("app_server", {}))
    configured_app = configured_app if isinstance(configured_app, dict) else {}
    config_command = _read_non_empty_str(configured_app.get("command"))
    env_command = _read_non_empty_str(live_env.get("OPENCLAW_CODEX_APP_SERVER_BIN"))
    command_source: CodexAppServerCommandSource = (
        "config" if config_command else "env" if env_command else "managed"
    )
    command = config_command or env_command
    if command is None:
        command = (
            find_managed_codex_app_server_command_path(
                plugin_root=plugin_root,
                platform=platform,
                order=app.managed_command_order,
            )
            or "codex"
        )
    if command_source in {"config", "env"}:
        assert_no_inline_args(command, source=command_source)

    transport = app.transport
    url = _read_non_empty_str(app.url)
    if transport == "websocket" and not url:
        raise ValueError("appServer.url is required when appServer.transport is websocket")
    if transport == "unix" and app.home_scope != "user":
        raise ValueError("appServer.transport=unix requires appServer.homeScope=user")
    if transport == "unix" and not (url or "").startswith("unix://"):
        raise ValueError("appServer.url must use unix:// when appServer.transport is unix")
    connection_class = infer_codex_app_server_connection_class(
        transport=transport,
        url=url,
    )
    assert_codex_app_server_connection_security(
        transport=transport,
        url=url,
        auth_token=app.auth_token,
        headers=app.headers,
    )

    policy_mode = resolve_policy_mode(app.mode) or "yolo"
    if policy_mode == "guardian":
        default_approval_policy = "on-request"
        default_sandbox = "workspace-write"
        default_reviewer = "auto_review"
    else:
        default_approval_policy = "never"
        default_sandbox = "danger-full-access"
        default_reviewer = "user"

    return CodexAppServerRuntimeOptions(
        transport=transport,
        home_scope=app.home_scope,
        command=command,
        command_source=command_source,
        args=app.args,
        connection_class=connection_class,
        approval_policy=app.approval_policy or default_approval_policy,
        sandbox=app.sandbox or default_sandbox,
        approvals_reviewer=app.approvals_reviewer or default_reviewer,
        policy_mode=policy_mode,
        code_mode_only=app.code_mode_only,
        request_timeout_ms=max(1, app.request_timeout_ms),
        service_tier=app.service_tier,
        network_proxy=resolve_codex_app_server_network_proxy(
            app.network_proxy,
            app.sandbox or default_sandbox,
        ),
        default_workspace_dir=app.default_workspace_dir,
        url=url,
        auth_token=app.auth_token,
        headers=dict(app.headers),
        clear_env=normalize_launch_clear_env(app.clear_env),
        managed_command_order=app.managed_command_order,
        remote_workspace_root=app.remote_workspace_root or parsed.remote_workspace_root,
        codex_plugins=parsed.codex_plugins,
    )


__all__ = [
    "CodexAppServerConfig",
    "CodexAppServerConnectionScope",
    "CodexAppServerRuntimeOptions",
    "CodexAppServerExperimentalConfig",
    "CodexAppServerHomeScope",
    "CodexAppServerTransportMode",
    "CodexPluginConfig",
    "CodexSessionCatalogConfig",
    "read_codex_plugin_config",
    "resolve_codex_app_server_home_scope",
    "resolve_codex_app_server_runtime_options",
]
