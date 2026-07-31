"""jarvis.agents.sessions — Layer 2 host funnel.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/``.

The Python port mirrors the OpenClaw ``src/agents/sessions/``
subdir; the module bodies land incrementally per
the V2 plan as the corresponding subsystem is ported.

Phase 6.0 — scaffolding + helpers + small types.
Phase 6.1 — storage primitives (storage-lock,
http-dispatcher, exec, bash-executor, keybindings).

This sub-package is the host funnel into the brain
(``createAgentSession`` + the ``AgentSession``
family). The public surface is re-exported from the
Phase-6.0/6.1 leaf modules here so callers can use
``from jarvis.agents.sessions import ...`` exactly
the way they would in OpenClaw.

The re-export shape follows the OpenClaw
``index.ts`` (which re-exports every leaf module),
but is restricted to the Phase-6.0/6.1 surface
only; later phases extend it as modules land.
"""
from __future__ import annotations

# Phase 6.0 leaf modules. The re-exports here match
# the OpenClaw ``src/agents/sessions/index.ts`` list
# in the order they appear in OpenClaw. Modules that
# land in later phases (auth-storage, model-registry,
# session-manager, etc.) are added to this file as
# they are ported.
from .auth_guidance import (
    UNKNOWN_PROVIDER,
    format_no_api_key_found_message,
    format_no_model_selected_message,
    format_no_models_available_message,
    get_provider_login_help,
)
from .bash_executor import (
    BashExecutorOptions,
    BashOperations,
    BashOperationsExecResult,
    BashResult,
    OutputAccumulator,
    create_streaming_binary_output_sanitizer,
    execute_bash_with_operations,
)
from .defaults import DEFAULT_THINKING_LEVEL, ThinkingLevel
from .diagnostics import (
    DiagnosticType,
    ResourceCollision,
    ResourceDiagnostic,
    ResourceType,
)
from .event_bus import (
    EventBus,
    EventBusController,
    Subscriber,
    create_event_bus,
)
from .exec import (
    DEFAULT_OUTPUT_LIMIT_CHARS,
    ExecOptions,
    ExecResult,
    FORCE_KILL_GRACE_MS,
    exec_command,
)
from .http_dispatcher import (
    DEFAULT_HTTP_IDLE_TIMEOUT_MS,
    parse_http_idle_timeout_ms,
)
from .keybindings import (
    KEYBINDINGS,
    KEYBINDING_NAME_MIGRATIONS,
    KeyBindingValue,
    KeybindingDef,
    KeybindingsConfig,
    KeybindingsManager,
    is_legacy_keybinding_name,
    load_raw_config,
    migrate_keybindings_config,
    to_keybindings_config,
)
from .messages import (
    BashExecutionMessage,
    CustomMessage,
    convert_to_llm,
)
from .provider_display_names import BUILT_IN_PROVIDER_DISPLAY_NAMES
from .resolve_config_value import (
    clear_config_value_cache,
    resolve_config_value,
    resolve_config_value_or_throw,
    resolve_config_value_uncached,
    resolve_headers_or_throw,
)
from .session_manager_codec import (
    CURRENT_SESSION_VERSION,
    build_session_context,
    get_latest_compaction_entry,
    has_readable_session_header,
    is_indexed_session_entry,
    is_json_record,
    is_session_entry_type,
    migrate_session_entries,
    migrate_to_current_version,
    normalize_loaded_file_entry,
    parse_jsonl_entries,
    parse_opaque_leaf_entry,
    parse_parent_linked_opaque_entry,
    parse_session_entries,
    partition_session_file_entries,
)
from .session_manager_core import SessionManagerCore, SqliteSessionManagerPersistence
from .session_manager_persistence import SessionManagerPersistence
from .session_manager_entries import SessionManagerEntries
from .session_manager_branching import SessionManagerBranching
from .session_manager import ReadonlySessionManager, SessionManager
from .auth_storage import (
    ApiKeyCredential,
    AuthCredential,
    AuthStatus,
    AuthStorage,
    AuthStorageBackend,
    AuthStorageData,
    AuthStoragePersistenceError,
    FileAuthStorageBackend,
    InMemoryAuthStorageBackend,
    OAuthCredential,
    OAuthCredentials,
    OAuthProviderId,
    find_env_keys,
    get_env_api_key,
)
from .auth_storage_oauth_registry import (
    OAuthProviderRegistry,
    get_auth_storage_oauth_provider_registry,
)
from .model_registry_runtime import (
    ApiRegistry,
    LlmRuntime,
    ModelRegistryRuntime,
    get_model_registry_runtime,
    initialize_model_registry_runtime,
    reset_model_registry_runtime,
)
from .model_registry import ConfiguredModel, ModelDefinition, ModelRegistry
from .model_registry_loader import (
    LoadAgentModelRegistryOptions,
    load_agent_model_registry,
)
from .session_manager_file import (
    LoadedSessionFile,
    MAX_CACHED_SESSION_BYTES,
    MAX_CACHED_SESSION_FILES,
    SessionFileSnapshot,
    can_publish_owned_session_append,
    get_default_session_dir,
    json_serialization_can_run_user_code,
    load_entries_from_file,
    load_entries_from_file_with_snapshot,
    load_sqlite_marked_session_file,
    message_serializes_owned_values,
    publish_remembered_session_file_snapshot,
    read_session_file_snapshot,
    read_session_file_snapshot_if_exists,
    recover_corrupt_session_entries,
    remember_appended_session_entry,
    remember_written_session_entries,
    revalidate_loaded_session_file,
    session_file_needs_append_separator,
)
from .session_manager_id import create_session_id, generate_session_entry_id
from .session_manager_list import (
    find_most_recent_session,
    list_all_sessions,
    list_sessions,
)
from .session_manager_types import (
    AppendPersistenceOptions,
    BranchSummaryEntry,
    CompactionEntry,
    CustomEntry,
    CustomMessageEntry,
    FileEntry,
    LabelEntry,
    ModelChangeEntry,
    NewSessionOptions,
    PreservedOpaqueFileEntry,
    PromptReleasedSessionEntry,
    PromptReleasedSessionMergeResult,
    SessionContext,
    SessionEntry,
    SessionEntryBase,
    SessionEntryType,
    SessionHeader,
    SessionInfo,
    SessionInfoEntry,
    SessionLeafControl,
    SessionListProgress,
    SessionMessageEntry,
    SessionTreeNode,
    ThinkingLevelChangeEntry,
)
from .slash_commands import SlashCommandInfo, SlashCommandSource
from .source_info import (
    PathMetadata,
    SourceInfo,
    SourceOrigin,
    SourceScope,
    create_source_info,
    create_synthetic_source_info,
)
from .storage_lock import (
    LOCK_RETRY_DELAY_MS,
    MAX_LOCK_ATTEMPTS,
    UnlockFn,
    acquire_lock_sync_with_retry,
)
from .telemetry import is_install_telemetry_enabled


__all__ = [
    # auth_guidance
    "UNKNOWN_PROVIDER",
    "format_no_api_key_found_message",
    "format_no_model_selected_message",
    "format_no_models_available_message",
    "get_provider_login_help",
    # bash_executor
    "BashExecutorOptions",
    "BashOperations",
    "BashOperationsExecResult",
    "BashResult",
    "OutputAccumulator",
    "create_streaming_binary_output_sanitizer",
    "execute_bash_with_operations",
    # defaults
    "DEFAULT_THINKING_LEVEL",
    "ThinkingLevel",
    # diagnostics
    "DiagnosticType",
    "ResourceCollision",
    "ResourceDiagnostic",
    "ResourceType",
    # event_bus
    "EventBus",
    "EventBusController",
    "Subscriber",
    "create_event_bus",
    # exec
    "DEFAULT_OUTPUT_LIMIT_CHARS",
    "ExecOptions",
    "ExecResult",
    "FORCE_KILL_GRACE_MS",
    "exec_command",
    # http_dispatcher
    "DEFAULT_HTTP_IDLE_TIMEOUT_MS",
    "parse_http_idle_timeout_ms",
    # keybindings
    "KEYBINDINGS",
    "KEYBINDING_NAME_MIGRATIONS",
    "KeyBindingValue",
    "KeybindingDef",
    "KeybindingsConfig",
    "KeybindingsManager",
    "is_legacy_keybinding_name",
    "load_raw_config",
    "migrate_keybindings_config",
    "to_keybindings_config",
    # messages
    "BashExecutionMessage",
    "CustomMessage",
    "convert_to_llm",
    # provider_display_names
    "BUILT_IN_PROVIDER_DISPLAY_NAMES",
    # resolve_config_value
    "clear_config_value_cache",
    "resolve_config_value",
    "resolve_config_value_or_throw",
    "resolve_config_value_uncached",
    "resolve_headers_or_throw",
    # slash_commands
    "SlashCommandInfo",
    "SlashCommandSource",
    # session_manager_codec
    "CURRENT_SESSION_VERSION",
    "build_session_context",
    "get_latest_compaction_entry",
    "has_readable_session_header",
    "is_indexed_session_entry",
    "is_json_record",
    "is_session_entry_type",
    "migrate_session_entries",
    "migrate_to_current_version",
    "normalize_loaded_file_entry",
    "parse_jsonl_entries",
    "parse_opaque_leaf_entry",
    "parse_parent_linked_opaque_entry",
    "parse_session_entries",
    "partition_session_file_entries",
    # session_manager_id
    "create_session_id",
    "generate_session_entry_id",
    # session_manager_core
    "SessionManagerCore",
    "SqliteSessionManagerPersistence",
    # session_manager_persistence
    "SessionManagerPersistence",
    # session_manager_entries
    "SessionManagerEntries",
    # session_manager_branching
    "SessionManagerBranching",
    # session_manager (facade)
    "SessionManager",
    "ReadonlySessionManager",
    # auth_storage
    "ApiKeyCredential",
    "AuthCredential",
    "AuthStatus",
    "AuthStorage",
    "AuthStorageBackend",
    "AuthStorageData",
    "AuthStoragePersistenceError",
    "FileAuthStorageBackend",
    "InMemoryAuthStorageBackend",
    "OAuthCredential",
    "OAuthCredentials",
    "OAuthProviderId",
    "find_env_keys",
    "get_env_api_key",
    # auth_storage_oauth_registry
    "OAuthProviderRegistry",
    "get_auth_storage_oauth_provider_registry",
    # model_registry_runtime
    "ApiRegistry",
    "LlmRuntime",
    "ModelRegistryRuntime",
    "get_model_registry_runtime",
    "initialize_model_registry_runtime",
    "reset_model_registry_runtime",
    # model_registry (facade — Phase 6.7a minimal)
    "ConfiguredModel",
    "ModelDefinition",
    "ModelRegistry",
    # model_registry_loader
    "LoadAgentModelRegistryOptions",
    "load_agent_model_registry",
    # session_manager_file
    "LoadedSessionFile",
    "MAX_CACHED_SESSION_BYTES",
    "MAX_CACHED_SESSION_FILES",
    "SessionFileSnapshot",
    "can_publish_owned_session_append",
    "get_default_session_dir",
    "json_serialization_can_run_user_code",
    "load_entries_from_file",
    "load_entries_from_file_with_snapshot",
    "load_sqlite_marked_session_file",
    "message_serializes_owned_values",
    "publish_remembered_session_file_snapshot",
    "read_session_file_snapshot",
    "read_session_file_snapshot_if_exists",
    "recover_corrupt_session_entries",
    "remember_appended_session_entry",
    "remember_written_session_entries",
    "revalidate_loaded_session_file",
    "session_file_needs_append_separator",
    # session_manager_list
    "find_most_recent_session",
    "list_all_sessions",
    "list_sessions",
    # session_manager_types
    "AppendPersistenceOptions",
    "BranchSummaryEntry",
    "CompactionEntry",
    "CustomEntry",
    "CustomMessageEntry",
    "FileEntry",
    "LabelEntry",
    "ModelChangeEntry",
    "NewSessionOptions",
    "PreservedOpaqueFileEntry",
    "PromptReleasedSessionEntry",
    "PromptReleasedSessionMergeResult",
    "SessionContext",
    "SessionEntry",
    "SessionEntryBase",
    "SessionEntryType",
    "SessionHeader",
    "SessionInfo",
    "SessionInfoEntry",
    "SessionLeafControl",
    "SessionListProgress",
    "SessionMessageEntry",
    "SessionTreeNode",
    "ThinkingLevelChangeEntry",
    # source_info
    "PathMetadata",
    "SourceInfo",
    "SourceOrigin",
    "SourceScope",
    "create_source_info",
    "create_synthetic_source_info",
    # storage_lock
    "LOCK_RETRY_DELAY_MS",
    "MAX_LOCK_ATTEMPTS",
    "UnlockFn",
    "acquire_lock_sync_with_retry",
    # telemetry
    "is_install_telemetry_enabled",
]
