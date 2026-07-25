"""jarvis_sdk — the JARVIS plugin contract.

Mirrors OpenClaw's ``src/plugin-sdk/`` boundary. Every plugin in
``extensions/`` imports only from this package. The host (``apps/desktop``)
imports from here too, to wire the registered capabilities.

Public API (organized like OpenClaw):

- **Result** — ``Ok`` / ``Err`` / ``Result`` discriminated union.
- **Manifest** — ``ToolDecl``, ``ToolParam``, ``PluginManifestSummary``,
  ``PluginKind``, ``PluginActivation``.
- **Contract** — ``Plugin``, ``ToolPlugin``, ``ChannelPlugin``,
  ``ProviderPlugin``, ``MemoryHostPlugin``, ``ToolCallable``.
- **Context** — ``PluginContext`` (passed to ``init()``).
- **Command** — ``PluginCommandContext``, ``PluginCommandResult``,
  ``CommandDecl``.
- **CLI** — ``CliContext``, ``CliDescriptor``, ``CliRegistrar``.
- **API** — ``PluginApi``, ``PluginSessionApi``, ``PluginAgentApi``,
  ``PluginRunContextApi``, ``PluginLifecycleApi``.
- **Entry** — ``define_plugin_entry``, ``PluginEntry``.

All public types are re-exported here so plugins and hosts can do
``from jarvis_sdk import ToolPlugin, PluginApi, Ok, Err``.

stdlib-only deps; pydantic and httpx are deferred to Phase 2+.
"""

from __future__ import annotations

# Phase 4.0 SDK submodules (OpenClaw plugin-sdk parity)
from .agent_runtime import (
    DEFAULT_AGENT_ID,
    DEFAULT_PROVIDER,
    parse_model_ref,
    resolve_agent_config,
    resolve_agent_dir,
    resolve_agent_effective_model_primary,
    resolve_agent_workspace_dir,
    resolve_default_agent_id,
    resolve_default_model_for_agent,
    resolve_remember_across_conversations,
    resolve_session_agent_id,
    resolve_store_path,
)

# API (the registration surface)
from .api import (
    CliDescriptor as ApiCliDescriptor,  # re-export for compatibility
    CommandDecl,
    PluginAgentApi,
    PluginApi,
    PluginLifecycleApi,
    PluginRunContextApi,
    PluginSessionApi,
)
from .chat_channel_ids import BUNDLED_CHAT_CHANNEL_ENVELOPE_PREFIXES

# CLI types
from .cli import CliContext, CliDescriptor, CliRegistrar

# Command types
from .command import (
    PluginCommandContext,
    PluginCommandHandler,
    PluginCommandResult,
)

# Context (runtime handle)
from .context import PluginContext

# Contract (base classes)
from .contract import (
    ChannelPlugin,
    MemoryHostPlugin,
    Plugin,
    ProviderPlugin,
    ToolCallable,
    ToolPlugin,
)

# Cron types
from .cron import CronDecl

# Entry (define_plugin_entry helper)
from .entry import PluginEntry, define_plugin_entry
from .expect_runtime import expect_defined, expect_truthy

# Hook types
from .hook import HookHandler, HookName, HookRegistration
from .json_store import (
    load_json_file,
    read_json_file_with_fallback,
    save_json_file,
    write_json_file_atomically,
)
from .lazy_runtime import create_lazy_runtime_module

# Manifest types
from .manifest import (
    PluginActivation,
    PluginKind,
    PluginManifestSummary,
    ToolDecl,
    ToolParam,
)
from .memory_embeddings import (
    MemoryEmbeddingProvider,
    MemoryEmbeddingProviderAdapter,
    get_memory_embedding_provider,
    list_registered_memory_embedding_providers,
    register_memory_embedding_provider,
)
from .memory_host_search import close_active_memory_search_manager
from .memory_runtime import (
    MemoryFlushPlan,
    MemoryFlushPlanResolver,
    MemoryPluginCapability,
    MemoryPluginPublicArtifact,
    MemoryPluginPublicArtifactsProvider,
    MemoryPluginRuntime,
    MemoryPromptSectionBuilder,
)
from .memory_storage import (
    SOURCE_ALL,
    SOURCE_MEMORY,
    SOURCE_SESSIONS,
    SOURCE_WIKI,
    VALID_SOURCES,
    MemorySearchManager,
    MemorySearchResult,
)
from .message_tool_delivery_hints import MESSAGE_TOOL_DELIVERY_HINTS
from .number_runtime import (
    as_date_timestamp_ms,
    parse_strict_positive_integer,
    resolve_expires_at_ms_from_duration_ms,
    resolve_timer_timeout_ms,
    timestamp_ms_to_iso_string,
)
from .plugin_config import (
    PluginsConfig,
    normalize_plugins_config,
    resolve_live_plugin_config_object,
    resolve_plugin_config_object,
)
from .plugin_state import (
    KeyedStore,
    LeaseHeld,
    OpenKeyedStoreOptions,
    open_keyed_store,
    with_lease,
)
from .plugin_state_keyed_store import (
    OpenKeyedStoreOptions as OpenKeyedStoreOptionsAsync,
    PluginStateEntry,
    PluginStateKeyedStore,
    PluginStateStoreError,
    get_plugin_state_namespace_root,
    open_plugin_state_keyed_store,
    reset_plugin_state_for_tests,
    set_plugin_state_namespace_root,
)

# Result type (Ok / Err / Result)
from .result import Err, Ok, Result, ResultNone
from jarvis_retry.retry_runtime import retry_async
from routing.routing import (
    normalize_agent_id,
    parse_agent_session_key,
    parse_thread_session_suffix,
)
from .runtime_env import ensure_global_undici_env_proxy_dispatcher
from security.security_runtime import (
    FsSafeError,
    append_regular_file,
    fs_root,
    is_path_inside,
    is_regular_file_stat,
    path_exists,
    root,
)
from sessions.session_transcript_runtime import (
    SessionTranscriptTargetParams,
    SqliteSessionFileMarker,
    TranscriptRawDeltaPage,
    build_session_transcript_target,
    cleanup_session_lifecycle_artifacts,
    parse_sqlite_session_file_marker,
    read_session_transcript_events,
    read_session_transcript_raw_delta,
)

# Skill types
from .skill import SkillDecl
from .string_coerce import (
    as_optional_record,
    lowercase_preserving_whitespace,
    normalize_lowercase_string_or_empty,
    normalize_optional_string,
    normalize_single_or_trimmed_string_list,
    normalize_string_entries,
    normalize_trimmed_string_list,
    unique_strings,
)
from .text_utility import truncate_utf16_safe, utf16_length

__all__ = [
    # Chat channel ids
    "BUNDLED_CHAT_CHANNEL_ENVELOPE_PREFIXES",
    # Phase 4.0: OpenClaw plugin-sdk parity
    # Agent runtime
    "DEFAULT_AGENT_ID",
    "DEFAULT_PROVIDER",
    # Message tool delivery hints
    "MESSAGE_TOOL_DELIVERY_HINTS",
    "SOURCE_ALL",
    "SOURCE_MEMORY",
    "SOURCE_SESSIONS",
    "SOURCE_WIKI",
    "VALID_SOURCES",
    # CLI
    "ApiCliDescriptor",
    # Contract
    "ChannelPlugin",
    "CliContext",
    "CliDescriptor",
    "CliRegistrar",
    # Command
    "CommandDecl",
    # Cron
    "CronDecl",
    # Result
    "Err",
    # Hooks
    "FsSafeError",
    "HookHandler",
    "HookName",
    "HookRegistration",
    # Plugin state
    "KeyedStore",
    "LeaseHeld",
    # Memory embeddings
    "MemoryEmbeddingProvider",
    "MemoryEmbeddingProviderAdapter",
    # Memory runtime
    "MemoryFlushPlan",
    "MemoryFlushPlanResolver",
    "MemoryHostPlugin",
    "MemoryPluginCapability",
    "MemoryPluginPublicArtifact",
    "MemoryPluginPublicArtifactsProvider",
    "MemoryPluginRuntime",
    "MemoryPromptSectionBuilder",
    # Memory storage
    "MemorySearchManager",
    "MemorySearchResult",
    "Ok",
    "OpenKeyedStoreOptions",
    "Plugin",
    # Manifest
    "PluginActivation",
    # API
    "PluginAgentApi",
    "PluginApi",
    "PluginCommandContext",
    "PluginCommandHandler",
    "PluginCommandResult",
    # Context
    "PluginContext",
    # Entry
    "PluginEntry",
    "PluginKind",
    "PluginLifecycleApi",
    "PluginManifestSummary",
    "PluginRunContextApi",
    "PluginSessionApi",
    # Plugin config
    "PluginsConfig",
    "ProviderPlugin",
    "Result",
    "ResultNone",
    # Retry runtime
    "retry_async",
    # Session transcript runtime
    "SessionTranscriptTargetParams",
    # Skills
    "SkillDecl",
    "ToolCallable",
    "ToolDecl",
    "ToolParam",
    "ToolPlugin",
    # Number runtime
    "as_date_timestamp_ms",
    # String coerce
    "as_optional_record",
    "append_regular_file",
    "build_session_transcript_target",
    "cleanup_session_lifecycle_artifacts",
    # Memory host search
    "close_active_memory_search_manager",
    # Lazy runtime
    "create_lazy_runtime_module",
    "define_plugin_entry",
    # Runtime env
    "ensure_global_undici_env_proxy_dispatcher",
    # Expect runtime
    "expect_defined",
    "expect_truthy",
    "fs_root",
    "get_memory_embedding_provider",
    # Security runtime
    "is_path_inside",
    "is_regular_file_stat",
    "list_registered_memory_embedding_providers",
    # Routing
    "lowercase_preserving_whitespace",
    "normalize_agent_id",
    "normalize_lowercase_string_or_empty",
    "normalize_optional_string",
    "normalize_single_or_trimmed_string_list",
    "normalize_trimmed_string_list",
    "normalize_plugins_config",
    "normalize_string_entries",
    "open_keyed_store",
    "parse_agent_session_key",
    "parse_model_ref",
    "parse_sqlite_session_file_marker",
    "path_exists",
    "read_session_transcript_events",
    "parse_strict_positive_integer",
    "parse_thread_session_suffix",
    "read_session_transcript_raw_delta",
    "register_memory_embedding_provider",
    "resolve_agent_dir",
    "resolve_agent_effective_model_primary",
    "resolve_agent_workspace_dir",
    "resolve_default_agent_id",
    "resolve_default_model_for_agent",
    "resolve_expires_at_ms_from_duration_ms",
    "resolve_live_plugin_config_object",
    "resolve_plugin_config_object",
    "resolve_remember_across_conversations",
    "resolve_session_agent_id",
    "resolve_store_path",
    "resolve_timer_timeout_ms",
    "root",
    "SessionTranscriptTargetParams",
    "SqliteSessionFileMarker",
    "timestamp_ms_to_iso_string",
    "TranscriptRawDeltaPage",
    # Text utility
    "truncate_utf16_safe",
    "unique_strings",
    "utf16_length",
    "with_lease",
]
