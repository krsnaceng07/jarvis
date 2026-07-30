"""jarvis.agents.sessions — Layer 2 host funnel.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/``.

The Python port mirrors the OpenClaw ``src/agents/sessions/``
subdir; the module bodies land incrementally per
the V2 plan as the corresponding subsystem is ported.

Phase 6.0 — scaffolding + helpers + small types.

This sub-package is the host funnel into the brain
(``createAgentSession`` + the ``AgentSession``
family). The public surface is re-exported from the
Phase-6.0 leaf modules here so callers can use
``from jarvis.agents.sessions import ...`` exactly
the way they would in OpenClaw.

The re-export shape follows the OpenClaw
``index.ts`` (which re-exports every leaf module),
but is restricted to the Phase-6.0 surface only;
later phases extend it as modules land.
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
from .slash_commands import SlashCommandInfo, SlashCommandSource
from .source_info import (
    PathMetadata,
    SourceInfo,
    SourceOrigin,
    SourceScope,
    create_source_info,
    create_synthetic_source_info,
)
from .telemetry import is_install_telemetry_enabled


__all__ = [
    # auth_guidance
    "UNKNOWN_PROVIDER",
    "format_no_api_key_found_message",
    "format_no_model_selected_message",
    "format_no_models_available_message",
    "get_provider_login_help",
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
    # source_info
    "PathMetadata",
    "SourceInfo",
    "SourceOrigin",
    "SourceScope",
    "create_source_info",
    "create_synthetic_source_info",
    # telemetry
    "is_install_telemetry_enabled",
]
