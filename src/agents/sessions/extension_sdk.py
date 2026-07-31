"""jarvis.agents.sessions.extension_sdk — extension-safe session SDK surface.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/extension-sdk.ts``.

Phase 6.9c — the cycle-safe barrel that the
extension loader imports to virtualize
``openclaw/plugin-sdk/agent-sessions``.

The OpenClaw source's barrel re-exports:
- ``getAgentDir``, ``VERSION`` from ``config.js``
  (deferred to Phase 6.11+)
- ``auth-storage`` (Phase 6.6 done)
- ``bash-executor`` (Phase 6.10+)
- ``compaction/index`` (Phase 6.12+)
- ``event-bus`` (Phase 6.0 done)
- ``footer-data-provider`` (Phase 6.12+)
- ``messages`` (``convertToLlm``) (deferred)
- ``model-registry`` (Phase 6.7 done)
- ``model-resolver`` (Phase 6.7 done)
- ``package-manager`` (Phase 6.11+)
- ``prompt-templates`` (Phase 6.12+)
- ``resource-loader/diagnostics``
  (Phase 6.11+)
- ``session-manager`` (Phase 6.5 done)
- ``settings-manager`` (Phase 6.8 done)
- ``source-info`` (Phase 6.9+)
- ``tools/index`` (Phase 6.10+)
- ``extensions/types`` + ``extensions/wrapper``
  (Phase 6.9 done)
- ``Skill`` from ``skills/loading/session``
  (deferred)
- Type guards: ``isBashToolResult`` …
  (Phase 6.9 done)

The Python port re-exports the **already
ported** sub-modules. Surface that has not
landed yet is commented as ``# deferred``.
"""
from __future__ import annotations

# Phase 6.0 — event bus
from .event_bus import (
    EventBus,
    EventBusController,
    create_event_bus,
)

# Phase 6.5 — session manager
from .session_manager import (
    ReadonlySessionManager,
    SessionManager,
)

# Phase 6.6 — auth storage + oauth registry
from .auth_storage import (
    AuthStorage,
    FileAuthStorageBackend,
    InMemoryAuthStorageBackend,
    AuthStoragePersistenceError,
)
from .auth_storage_oauth_registry import (
    OAuthProviderRegistry,
    get_auth_storage_oauth_provider_registry,
)

# Phase 6.7 — model registry + resolver
from .model_registry import ModelRegistry
from .model_resolver import (
    find_exact_model_reference_match,
    parse_model_pattern,
    resolve_model_scope,
    resolve_cli_model,
    find_initial_model,
    VALID_THINKING_LEVELS,
    ScopedModel,
    ParsedModelResult,
    ResolveCliModelResult,
    InitialModelResult,
)

# Phase 6.8 — settings manager
from .settings_manager import (
    FileSettingsStorage,
    InMemorySettingsStorage,
    SettingsManager,
    Settings,
    SettingsError,
    SettingsScope,
    SettingsStorage,
)

# Phase 6.9 — extension system
from .extensions import (
    Extension,
    ExtensionAPI,
    ExtensionContext,
    ExtensionFactory,
    ExtensionRuntime,
    ExtensionUIContext,
    ToolDefinition,
    define_tool,
    is_bash_tool_result,
    is_edit_tool_result,
    is_find_tool_result,
    is_grep_tool_result,
    is_ls_tool_result,
    is_read_tool_result,
    is_tool_call_event_type,
    is_write_tool_result,
)
from .extensions.runner import ExtensionRunner
from .extensions.wrapper import (
    wrap_registered_tool,
    wrap_registered_tools,
)


__all__ = [
    # Phase 6.0 — event bus
    "EventBus",
    "EventBusController",
    "create_event_bus",
    # Phase 6.5 — session manager
    "ReadonlySessionManager",
    "SessionManager",
    # Phase 6.6 — auth storage
    "AuthStorage",
    "FileAuthStorageBackend",
    "InMemoryAuthStorageBackend",
    "AuthStoragePersistenceError",
    "OAuthProviderRegistry",
    "get_auth_storage_oauth_provider_registry",
    # Phase 6.7 — model registry + resolver
    "ModelRegistry",
    "find_exact_model_reference_match",
    "parse_model_pattern",
    "resolve_model_scope",
    "resolve_cli_model",
    "find_initial_model",
    "VALID_THINKING_LEVELS",
    "ScopedModel",
    "ParsedModelResult",
    "ResolveCliModelResult",
    "InitialModelResult",
    # Phase 6.8 — settings manager
    "FileSettingsStorage",
    "InMemorySettingsStorage",
    "SettingsManager",
    "Settings",
    "SettingsError",
    "SettingsScope",
    "SettingsStorage",
    # Phase 6.9 — extension system
    "Extension",
    "ExtensionAPI",
    "ExtensionContext",
    "ExtensionFactory",
    "ExtensionRuntime",
    "ExtensionUIContext",
    "ExtensionRunner",
    "ToolDefinition",
    "define_tool",
    "is_bash_tool_result",
    "is_edit_tool_result",
    "is_find_tool_result",
    "is_grep_tool_result",
    "is_ls_tool_result",
    "is_read_tool_result",
    "is_tool_call_event_type",
    "is_write_tool_result",
    "wrap_registered_tool",
    "wrap_registered_tools",
]
