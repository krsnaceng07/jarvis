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

# Hook types
from .hook import HookHandler, HookName, HookRegistration

# Manifest types
from .manifest import (
    PluginActivation,
    PluginKind,
    PluginManifestSummary,
    ToolDecl,
    ToolParam,
)

# Result type (Ok / Err / Result)
from .result import Err, Ok, Result, ResultNone

# Skill types
from .skill import SkillDecl

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
]
