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

# ruff: noqa: E402
from __future__ import annotations

# ── Legacy src/ bridge ────────────────────────────────────────────────
# TODO(migration): ``src/routing/`` and ``src/memory/`` are legacy packages
# that are not yet workspace members.  Until they are migrated into proper
# installable packages under ``packages/``, we prepend ``src/`` to
# ``sys.path`` so the absolute imports below resolve correctly.
# Remove this block once those packages are migrated.
import sys as _sys
import pathlib as _pathlib

_src_dir = str(_pathlib.Path(__file__).parent.parent.parent.parent.parent / "src")
if _src_dir not in _sys.path:
    _sys.path.append(_src_dir)  # append — must not shadow stdlib (e.g. src/config/logging.py)
del _src_dir, _pathlib, _sys
# ──────────────────────────────────────────────────────────────────────


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
    RegistrationMode,
    set_host_effective_agent_runtime_resolver,
    set_host_thinking_policy_resolver,
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
from .channel_actions import (
    CHANNEL_MESSAGE_ACTION_NAMES,
    ApprovalAction,
    ChannelAction,
    ChannelActionKind,
    CommandAction,
    SelectAction,
    TextAction,
    UrlAction,
    action_kind,
    is_known_message_action,
    validate_action,
)
from .channel_capabilities import ChannelCapabilities
from .context import PluginContext

# Contract (base classes)
from .contract import (
    ChannelPlugin,
    MemoryHostPlugin,
    MigrationProviderPlugin,
    Plugin,
    ProviderPlugin,
    ToolCallable,
    ToolPlugin,
)

# Channel adapter protocols
from .channel_adapters import (
    ChannelConversationBindings,
    ChannelOutboundAdapter,
    ChannelPairingAdapter,
    ChannelSecurityAdapter,
    ChannelThreadingAdapter,
)
from .channels import (
    ChannelMessageAdapter,
    StatusReactionAdapter,
    TypingCallbacks,
)
from .channel_supervisor import ChannelAccountState, ChannelSupervisor

# Cron types
from .cron import CronDecl

# Entry (define_plugin_entry helper)
from .entry import PluginEntry, define_plugin_entry
from .plugin_entry import (
    PluginEntryDefinition,
    create_channel_plugin_base,
    create_chat_channel_plugin,
    define_channel_plugin_entry,
    define_setup_plugin_entry,
)
from .expect_runtime import expect_defined, expect_truthy

# Hook types
from .hook import HookHandler, HookName, HookRegistration
from jarvis_normalization_core.json_store import (
    load_json_file,
    read_json_file_with_fallback,
    save_json_file,
    write_json_file_atomically,
)
from .lazy_runtime import create_lazy_runtime_module

# Loader & discovery (OpenClaw discovery parity)
from .loader import (
    LoadResult,
    discover_plugins,
    load_all_plugins,
    load_all_plugins_from_workspace,
    load_plugins,
)

# Manifest types
from .manifest import (
    PluginActivation,
    PluginBundleFormat,
    PluginFormat,
    PluginKind,
    PluginManifestSummary,
    ToolDecl,
    ToolParam,
)

# Bundle system (Agent Plugins / Codex / Claude / Cursor parity with OpenClaw)
from .bundle_manifest import (
    BundleManifest,
    detect_bundle_format,
    is_bundle_capability_supported,
    load_bundle_manifest,
    merge_bundle_path_lists,
    normalize_bundle_path_list,
)
from .bundle_mcp import (
    BundleMcpConfig,
    load_bundle_mcp_config,
    sanitize_mcp_tool_name,
)
from .bundle_commands import load_bundle_command_skills

from .memory_embeddings import (
    MemoryEmbeddingProvider,
    MemoryEmbeddingProviderAdapter,
    get_memory_embedding_provider,
    list_registered_memory_embedding_providers,
    register_memory_embedding_provider,
)

# Media understanding provider surface (Phase 5.15+)
from .media_understanding import (
    AudioTranscriptionRequest,
    AudioTranscriptionResult,
    MediaUnderstandingProvider,
    transcribe_openai_compatible_audio,
)
from .image_generation import (
    ImageGenerationProvider,
    ImageGenerationProviderCapabilities,
    ImageGenerationRequest,
    ImageGenerationResult,
    GeneratedImageAsset,
    ImageGenerationSourceImage,
)
from ._plugin_api_registration_media import (
    register_image_generation_provider,
    get_image_generation_provider,
    list_image_generation_providers,
    register_video_generation_provider,
    get_video_generation_provider,
    list_video_generation_providers,
    register_music_generation_provider,
    get_music_generation_provider,
    list_music_generation_providers,
    register_tts_provider,
    get_tts_provider,
    list_tts_providers,
    register_stt_provider,
    get_stt_provider,
    list_stt_providers,
)
from .video_generation import (
    VideoGenerationProvider,
    VideoGenerationProviderCapabilities,
    VideoGenerationRequest,
    VideoGenerationResult,
    GeneratedVideoAsset,
    VideoGenerationSourceImage,
    VideoGenerationSourceVideo,
)
from .music_generation import (
    MusicGenerationProvider,
    MusicGenerationProviderCapabilities,
    MusicGenerationRequest,
    MusicGenerationResult,
    GeneratedMusicAsset,
    MusicGenerationSourceAudio,
)
from .tts import (
    TtsProvider,
    TtsProviderCapabilities,
    TtsRequest,
    TtsResult,
    GeneratedTtsAsset,
)
from .stt import (
    SttProvider,
    SttProviderCapabilities,
    SttRequest,
    SttResult,
)
from .memory_host_search import close_active_memory_search_manager
from memory.memory_runtime import (
    MemoryFlushPlan,
    MemoryFlushPlanResolver,
    MemoryPluginCapability,
    MemoryPluginPublicArtifact,
    MemoryPluginPublicArtifactsProvider,
    MemoryPluginRuntime,
    MemoryPromptSectionBuilder,
)
from memory.memory_storage import (
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
from .provider_models import (
    IncompatibleResolution,
    IndeterminateResolution,
    ProviderModelRouteAuthRequirement,
    ProviderModelRouteCandidate,
    ProviderModelRouteResolution,
    ProviderModelRouteRuntimePolicy,
    ProviderResolveModelRoutesContext,
    ProviderRouteOverridePresence,
    RoutesResolution,
)
from .provider_stream import StreamWrapperFactory, compose_provider_stream_wrappers
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
from .test_support import (
    StreamingResponseFixture,
    create_provider_dynamic_model_context,
    create_streaming_response,
)

# Result type (Ok / Err / Result)
from jarvis_normalization_core.result import Err, Ok, Result, ResultNone
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
from .capability_bridge import (
    BridgedCapability,
    BridgeSecurityPolicy,
    CapabilityBridge,
    PluginAllowlist,
    PluginAllowlistEntry,
    PluginToolSource,
    RiskLevel,
    SecurityViolation,
    SideEffectLevel,
    translate_plugin_tool,
)
from .capability_ladder import (
    CapabilityLadderContract,
    CapabilityTier,
    CapabilityViolationError,
)
from .execution_adapter import (
    ExecutionAdapterOutput,
    PluginExecutionAdapter,
)

from jarvis_normalization_core.string_coerce import (
    as_optional_record,
    lowercase_preserving_whitespace,
    normalize_lowercase_string_or_empty,
    normalize_optional_string,
    normalize_single_or_trimmed_string_list,
    normalize_string_entries,
    normalize_trimmed_string_list,
    unique_strings,
)
from jarvis_normalization_core.text_utility import truncate_utf16_safe, utf16_length

__all__ = [
    # Chat channel ids
    "BUNDLED_CHAT_CHANNEL_ENVELOPE_PREFIXES",
    # Channel presentation actions (typed, no string inference)
    "ApprovalAction",
    "CHANNEL_MESSAGE_ACTION_NAMES",
    "ChannelAction",
    "ChannelActionKind",
    "ChannelCapabilities",
    "ChannelAccountState",
    "ChannelMessageAdapter",
    "ChannelSupervisor",
    "CommandAction",
    "SelectAction",
    "StatusReactionAdapter",
    "TextAction",
    "TypingCallbacks",
    "UrlAction",
    "action_kind",
    "compose_provider_stream_wrappers",
    "is_known_message_action",
    "validate_action",
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
    # Channel adapter protocols (OpenClaw parity)
    "ChannelConversationBindings",
    "ChannelOutboundAdapter",
    "ChannelPairingAdapter",
    "ChannelSecurityAdapter",
    "ChannelThreadingAdapter",
    # Command
    "CommandDecl",
    # Cron
    "CronDecl",
    # Result
    "AudioTranscriptionRequest",
    "AudioTranscriptionResult",
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
    # Migration provider (OpenClaw parity)
    "MigrationProviderPlugin",
    "Ok",
    "OpenKeyedStoreOptions",
    "Plugin",
    # Loader & discovery (OpenClaw parity)
    "LoadResult",
    "discover_plugins",
    "load_all_plugins",
    "load_all_plugins_from_workspace",
    "load_plugins",
    # Manifest
    "MediaUnderstandingProvider",
    "PluginActivation",
    "PluginBundleFormat",
    "PluginFormat",
    # Bundle system (Agent Plugins / Codex / Claude / Cursor)
    "BundleManifest",
    "BundleMcpConfig",
    "detect_bundle_format",
    "is_bundle_capability_supported",
    "load_bundle_manifest",
    "load_bundle_mcp_config",
    "load_bundle_command_skills",
    "merge_bundle_path_lists",
    "normalize_bundle_path_list",
    "sanitize_mcp_tool_name",
    # API
    "PluginAgentApi",
    "PluginApi",
    "PluginCommandContext",
    "PluginCommandHandler",
    "PluginCommandResult",
    # Plugin entry (OpenClaw parity)
    "PluginEntryDefinition",
    "RegistrationMode",
    "create_channel_plugin_base",
    "create_chat_channel_plugin",
    "define_channel_plugin_entry",
    "define_setup_plugin_entry",
    "set_host_effective_agent_runtime_resolver",
    "set_host_thinking_policy_resolver",
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
    "IncompatibleResolution",
    "IndeterminateResolution",
    "ProviderModelRouteAuthRequirement",
    "ProviderModelRouteCandidate",
    "ProviderModelRouteResolution",
    "ProviderModelRouteRuntimePolicy",
    "ProviderPlugin",
    "ProviderResolveModelRoutesContext",
    "ProviderRouteOverridePresence",
    "RoutesResolution",
    "StreamWrapperFactory",
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
    "register_image_generation_provider",
    "get_image_generation_provider",
    "list_image_generation_providers",
    "ImageGenerationProvider",
    "ImageGenerationProviderCapabilities",
    "ImageGenerationRequest",
    "ImageGenerationResult",
    "GeneratedImageAsset",
    "ImageGenerationSourceImage",
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
    "transcribe_openai_compatible_audio",
    "TranscriptRawDeltaPage",
    # Text utility
    "truncate_utf16_safe",
    "unique_strings",
    "utf16_length",
    "with_lease",
    # Agent runtime (additional)
    "resolve_agent_config",
    # Plugin state keyed store
    "OpenKeyedStoreOptionsAsync",
    "PluginStateEntry",
    "PluginStateKeyedStore",
    "PluginStateStoreError",
    "get_plugin_state_namespace_root",
    "open_plugin_state_keyed_store",
    "reset_plugin_state_for_tests",
    "set_plugin_state_namespace_root",
    # TTS
    "TtsProvider",
    "TtsProviderCapabilities",
    "TtsRequest",
    "TtsResult",
    "GeneratedTtsAsset",
    "get_tts_provider",
    "list_tts_providers",
    "register_tts_provider",
    # STT
    "SttProvider",
    "SttProviderCapabilities",
    "SttRequest",
    "SttResult",
    "get_stt_provider",
    "list_stt_providers",
    "register_stt_provider",
    # Video generation
    "VideoGenerationProvider",
    "VideoGenerationProviderCapabilities",
    "VideoGenerationRequest",
    "VideoGenerationResult",
    "VideoGenerationSourceImage",
    "VideoGenerationSourceVideo",
    "GeneratedVideoAsset",
    "get_video_generation_provider",
    "list_video_generation_providers",
    "register_video_generation_provider",
    # Music generation
    "MusicGenerationProvider",
    "MusicGenerationProviderCapabilities",
    "MusicGenerationRequest",
    "MusicGenerationResult",
    "MusicGenerationSourceAudio",
    "GeneratedMusicAsset",
    "get_music_generation_provider",
    "list_music_generation_providers",
    "register_music_generation_provider",
    # JSON file helpers
    "load_json_file",
    "read_json_file_with_fallback",
    "save_json_file",
    "write_json_file_atomically",
    # Test support
    "StreamingResponseFixture",
    "create_provider_dynamic_model_context",
    "create_streaming_response",
    # Capability Ladder Contract
    "CapabilityLadderContract",
    "CapabilityTier",
    "CapabilityViolationError",
    # Track 3.6 Extensibility Bridge & Execution Adapter
    "BridgedCapability",
    "BridgeSecurityPolicy",
    "CapabilityBridge",
    "ExecutionAdapterOutput",
    "PluginAllowlist",
    "PluginAllowlistEntry",
    "PluginExecutionAdapter",
    "PluginToolSource",
    "RiskLevel",
    "SecurityViolation",
    "SideEffectLevel",
    "translate_plugin_tool",
]
