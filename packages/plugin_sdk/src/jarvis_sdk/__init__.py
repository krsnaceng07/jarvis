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
    resolve_agent_dir,
    resolve_agent_workspace_dir,
    resolve_default_agent_id,
    resolve_session_agent_id,
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
    parse_strict_positive_integer,
    resolve_timer_timeout_ms,
)
from .plugin_config import resolve_live_plugin_config_object
from .plugin_state import (
    KeyedStore,
    LeaseHeld,
    OpenKeyedStoreOptions,
    open_keyed_store,
    with_lease,
)

# Result type (Ok / Err / Result)
from .result import Err, Ok, Result, ResultNone
from .routing import normalize_agent_id
from .runtime_env import ensure_global_undici_env_proxy_dispatcher

# Skill types
from .skill import SkillDecl
from .string_coerce import (
    as_optional_record,
    normalize_lowercase_string_or_empty,
)
from .text_utility import truncate_utf16_safe, utf16_length

__all__ = [
    # Result
    "Err",
    "Ok",
    "Result",
    "ResultNone",
    # Manifest
    "PluginActivation",
    "PluginKind",
    "PluginManifestSummary",
    "ToolDecl",
    "ToolParam",
    # Contract
    "ChannelPlugin",
    "MemoryHostPlugin",
    "Plugin",
    "ProviderPlugin",
    "ToolCallable",
    "ToolPlugin",
    # Context
    "PluginContext",
    # Command
    "CommandDecl",
    "PluginCommandContext",
    "PluginCommandHandler",
    "PluginCommandResult",
    # CLI
    "ApiCliDescriptor",
    "CliContext",
    "CliDescriptor",
    "CliRegistrar",
    # Cron
    "CronDecl",
    # Hooks
    "HookHandler",
    "HookName",
    "HookRegistration",
    # Skills
    "SkillDecl",
    # API
    "PluginAgentApi",
    "PluginApi",
    "PluginLifecycleApi",
    "PluginRunContextApi",
    "PluginSessionApi",
    # Entry
    "PluginEntry",
    "define_plugin_entry",
    # Phase 4.0: OpenClaw plugin-sdk parity
    # Agent runtime
    "DEFAULT_AGENT_ID",
    "resolve_agent_dir",
    "resolve_agent_workspace_dir",
    "resolve_default_agent_id",
    "resolve_session_agent_id",
    # Chat channel ids
    "BUNDLED_CHAT_CHANNEL_ENVELOPE_PREFIXES",
    # Expect runtime
    "expect_defined",
    "expect_truthy",
    # Lazy runtime
    "create_lazy_runtime_module",
    # Memory embeddings
    "MemoryEmbeddingProvider",
    "MemoryEmbeddingProviderAdapter",
    "get_memory_embedding_provider",
    "list_registered_memory_embedding_providers",
    "register_memory_embedding_provider",
    # Memory runtime
    "MemoryFlushPlan",
    "MemoryFlushPlanResolver",
    "MemoryPluginCapability",
    "MemoryPluginPublicArtifact",
    "MemoryPluginPublicArtifactsProvider",
    "MemoryPluginRuntime",
    "MemoryPromptSectionBuilder",
    # Memory storage
    "MemorySearchManager",
    "MemorySearchResult",
    "SOURCE_ALL",
    "SOURCE_MEMORY",
    "SOURCE_SESSIONS",
    "SOURCE_WIKI",
    "VALID_SOURCES",
    # Message tool delivery hints
    "MESSAGE_TOOL_DELIVERY_HINTS",
    # Number runtime
    "parse_strict_positive_integer",
    "resolve_timer_timeout_ms",
    # Plugin config
    "resolve_live_plugin_config_object",
    # Plugin state
    "KeyedStore",
    "LeaseHeld",
    "OpenKeyedStoreOptions",
    "open_keyed_store",
    "with_lease",
    # Routing
    "normalize_agent_id",
    # Runtime env
    "ensure_global_undici_env_proxy_dispatcher",
    # String coerce
    "as_optional_record",
    "normalize_lowercase_string_or_empty",
    # Text utility
    "truncate_utf16_safe",
    "utf16_length",
]
