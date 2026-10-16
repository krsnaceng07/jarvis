"""Codex app-server agent harness registration and runtime contracts.

OpenClaw parity: ``extensions/codex/harness.ts``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from extensions.codex.src.app_server.config import (
    CodexAppServerConfig,
    CodexPluginConfig,
    read_codex_plugin_config,
)
from extensions.codex.src.dynamic_tools import project_codex_dynamic_tools
from extensions.codex.src.native_threads import execute_codex_threads
from extensions.codex.src.web_search import resolve_codex_web_search_plan

CODEX_HARNESS_ID: str = "codex"
CODEX_HARNESS_LABEL: str = "Codex agent harness"
DEFAULT_CODEX_HARNESS_PROVIDER_IDS: tuple[str, ...] = ("codex", "openai")

#: Capabilities supported by Codex app-server context engine projection
CODEX_CONTEXT_ENGINE_HOST_CAPABILITIES: tuple[str, ...] = (
    "bootstrap",
    "assemble-before-prompt",
    "after-turn",
    "maintain",
    "compact",
    "runtime-llm-complete",
    "thread-bootstrap-projection",
)

#: Standard safe deny list of OpenClaw tools isolated during Codex native turns
CODEX_TOOL_POLICY_SAFE_DENY_NAMES: tuple[str, ...] = (
    "web_fetch",
    "x_search",
    "memory_search",
    "memory_get",
    "dashboard",
    "canvas",
    "show_widget",
    "message",
    "heartbeat_respond",
    "automations",
    "gateway",
    "skill_workshop",
    "image_generate",
    "music_generate",
    "video_generate",
    "tts",
)


@dataclass(frozen=True, slots=True)
class RemoteWorkspaceAttachmentReader:
    """No-shell remote file attachment transfer reader matching OpenClaw's security boundary."""

    remote_root: str
    max_file_size_bytes: int = 50 * 1024 * 1024  # 50MB limit

    def validate_and_resolve_remote_path(self, relative_path: str) -> str:
        """Validate path relative to remote_root, rejecting symlinks & directory traversal."""
        root_path = Path(self.remote_root).resolve()
        target_path = (root_path / relative_path.lstrip("/\\")).resolve()

        if not str(target_path).startswith(str(root_path)):
            raise ValueError(
                f"Path traversal rejected: path '{relative_path}' escapes remote workspace root '{self.remote_root}'"
            )

        if target_path.is_symlink():
            raise ValueError(
                f"Symlink rejected: path '{relative_path}' points to a symlink in remote mode"
            )

        return str(target_path)


@dataclass
class CodexAgentHarness:
    """JARVIS Agent Harness instance for Codex app-server execution."""

    id: str = CODEX_HARNESS_ID
    label: str = CODEX_HARNESS_LABEL
    provider_ids: list[str] = field(
        default_factory=lambda: list(DEFAULT_CODEX_HARNESS_PROVIDER_IDS)
    )
    auth_bootstrap: str = "harness"
    context_engine_capabilities: list[str] = field(
        default_factory=lambda: list(CODEX_CONTEXT_ENGINE_HOST_CAPABILITIES)
    )
    safe_deny_tools: list[str] = field(
        default_factory=lambda: list(CODEX_TOOL_POLICY_SAFE_DENY_NAMES)
    )
    auto_selection: dict[str, Any] = field(
        default_factory=lambda: {"providerIds": list(DEFAULT_CODEX_HARNESS_PROVIDER_IDS)}
    )
    cloud_placement: dict[str, Any] = field(
        default_factory=lambda: {
            "mode": "remote-exec",
            "devicePlacement": {
                "requiredNodeCommands": ["codex.exec-server.stdio.v1"],
                "consumesWorkerSlot": False,
            },
        }
    )
    delegated_execution_plugin_ids: list[str] = field(default_factory=lambda: ["voice-call"])
    conversation_tool_policy_support: str = "exact"
    conversation_tool_policy_safe_deny_tools: list[str] = field(
        default_factory=lambda: list(CODEX_TOOL_POLICY_SAFE_DENY_NAMES)
    )
    app_server_config: CodexAppServerConfig = field(default_factory=CodexAppServerConfig)
    plugin_config: CodexPluginConfig = field(default_factory=CodexPluginConfig)

    @property
    def authBootstrap(self) -> str:  # noqa: N802
        return self.auth_bootstrap

    @property
    def contextEngineHostCapabilities(self) -> list[str]:  # noqa: N802
        return self.context_engine_capabilities

    @property
    def providerIds(self) -> list[str]:  # noqa: N802
        return self.provider_ids

    @property
    def autoSelection(self) -> dict[str, Any]:  # noqa: N802
        return self.auto_selection

    @property
    def cloudPlacement(self) -> dict[str, Any]:  # noqa: N802
        return self.cloud_placement

    @property
    def delegatedExecutionPluginIds(self) -> list[str]:  # noqa: N802
        return self.delegated_execution_plugin_ids

    @property
    def conversationToolPolicySupport(self) -> str:  # noqa: N802
        return self.conversation_tool_policy_support

    @property
    def conversationToolPolicySafeDenyTools(self) -> list[str]:  # noqa: N802
        return self.conversation_tool_policy_safe_deny_tools

    @property
    def safeDenyTools(self) -> list[str]:  # noqa: N802
        return self.safe_deny_tools

    def get_remote_attachment_reader(self) -> RemoteWorkspaceAttachmentReader | None:
        """Return configured remote workspace attachment reader if remoteWorkspaceRoot is set."""
        root = self.plugin_config.remote_workspace_root
        return RemoteWorkspaceAttachmentReader(remote_root=root) if root else None

    def project_dynamic_tools(self, tools: list[dict[str, Any]]) -> dict[str, Any]:
        """Project OpenClaw-owned tools using this harness's configured policy."""
        return project_codex_dynamic_tools(
            tools,
            loading=self.plugin_config.codex_dynamic_tools_loading,
            exclude=self.plugin_config.codex_dynamic_tools_exclude,
        )

    def resolve_web_search_plan(self, config: dict[str, Any] | None = None) -> dict[str, Any]:
        """Resolve native-versus-managed web search ownership for one turn."""
        return resolve_codex_web_search_plan(config)

    async def execute_native_threads(
        self,
        params: dict[str, Any],
        request: Any,
        *,
        is_owner: bool,
        session_id: str | None = None,
        attach_fork: Any | None = None,
    ) -> dict[str, Any]:
        """Run the guarded ``codex_threads`` capability for an opted-in run."""
        return await execute_codex_threads(
            self.plugin_config,
            params,
            request,
            is_owner=is_owner,
            session_id=session_id,
            attach_fork=attach_fork,
        )

    def supports(self, ctx: dict[str, Any]) -> dict[str, Any]:
        """Mirror the OpenClaw harness ``supports()`` decision contract."""
        provider = str(ctx.get("provider") or "").strip().lower()
        provider_ids = {str(item).strip().lower() for item in self.provider_ids}
        if not provider:
            return {"supported": False, "reason": "provider is missing"}
        if provider not in provider_ids:
            reason = f"provider is not one of: {', '.join(sorted(provider_ids))}"
            return {"supported": False, "reason": reason}

        model_provider = (
            ctx.get("modelProvider") if isinstance(ctx.get("modelProvider"), dict) else None
        )
        if model_provider and model_provider.get("requestTransportOverrides") == "present":
            return {
                "supported": False,
                "reason": "Codex cannot reproduce authored request transport overrides",
                "fallbackRuntime": "openclaw",
            }

        prepared_auth = model_provider.get("preparedAuth") if model_provider else None
        runtime_policy = model_provider.get("runtimePolicy") if model_provider else None
        normalized_harness_runtime_id = str(self.id).strip().lower()
        if runtime_policy:
            compatible_ids = runtime_policy.get("compatibleIds") or []
            compatible = [str(item).strip().lower() for item in compatible_ids]
            if normalized_harness_runtime_id not in compatible:
                return {
                    "supported": False,
                    "reason": "Codex cannot reproduce the prepared provider route",
                }
        elif model_provider and provider != "codex":
            native_account_owns_unobserved_model = (
                provider == "openai"
                and ctx.get("requestedRuntime") == "codex"
                and bool(str(ctx.get("modelId") or "").strip())
                and (prepared_auth is None or prepared_auth.get("source") == "harness")
                and prepared_auth.get("mode") is None
                and prepared_auth.get("requirement") is None
                and model_provider.get("api") is None
                and model_provider.get("baseUrl") is None
                and model_provider.get("azureApiVersion") is None
                and model_provider.get("request") is None
            )
            if not native_account_owns_unobserved_model:
                return {
                    "supported": False,
                    "reason": "provider route compatibility with Codex is not declared",
                }

        if prepared_auth and prepared_auth.get("requirement") == "subscription":
            reproducible_subscription = prepared_auth.get(
                "source"
            ) == "profile" and prepared_auth.get("mode") in {"oauth", "token"}
            if not reproducible_subscription:
                return {
                    "supported": False,
                    "reason": "Codex subscription auth requires a prepared OAuth or token profile",
                }
        elif prepared_auth and prepared_auth.get("requirement") == "api-key":
            reproducible_api_key = prepared_auth.get("source") not in {
                "none",
                "harness",
            } and prepared_auth.get("mode") in {"api-key", "api_key"}
            if not reproducible_api_key:
                return {
                    "supported": False,
                    "reason": "Codex Platform auth requires a prepared API key",
                }

        return {"supported": True, "priority": 100}


def create_codex_app_server_agent_harness(
    harness_id: str = CODEX_HARNESS_ID,
    config: dict[str, Any] | None = None,
    **kwargs: Any,
) -> CodexAgentHarness:
    """Creates the Codex app-server agent harness matching OpenClaw specifications."""
    if config is None and "resolve_plugin_config" in kwargs and callable(kwargs["resolve_plugin_config"]):
        try:
            config = kwargs["resolve_plugin_config"]()
        except Exception:
            config = None
    parsed_plugin_cfg = read_codex_plugin_config(config)
    return CodexAgentHarness(
        id=harness_id,
        app_server_config=parsed_plugin_cfg.app_server,
        plugin_config=parsed_plugin_cfg,
    )


__all__ = [
    "CODEX_CONTEXT_ENGINE_HOST_CAPABILITIES",
    "CODEX_HARNESS_ID",
    "CODEX_HARNESS_LABEL",
    "CODEX_TOOL_POLICY_SAFE_DENY_NAMES",
    "DEFAULT_CODEX_HARNESS_PROVIDER_IDS",
    "CodexAgentHarness",
    "RemoteWorkspaceAttachmentReader",
    "create_codex_app_server_agent_harness",
]
