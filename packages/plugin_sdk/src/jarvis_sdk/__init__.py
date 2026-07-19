"""JARVIS Plugin SDK — the contract all extensions import from.

Mirrors OpenClaw's `src/plugin-sdk/` re-export facade. Real implementations
of each capability (agent loop, LLM, memory host) live in their own
`packages/<feature>/` directory; this SDK is the stable seam.

Usage (matches OpenClaw's `definePluginEntry`):

    from jarvis_sdk import define_plugin_entry, Ok, Err, Result, ToolDecl

    def register(api):
        api.register_tool(
            MyTool(),
            names=["my_tool"],
        )

    entry = define_plugin_entry(
        id="my_tool",
        kind="tool",
        name="My Tool",
        description="...",
        register=register,
    )
"""

from __future__ import annotations

from .api import CliDescriptor, CommandDecl, PluginApi
from .context import PluginContext
from .contract import (
    ChannelPlugin,
    MemoryHostPlugin,
    Plugin,
    ProviderPlugin,
    ToolPlugin,
)
from .entry import PluginEntry, define_plugin_entry
from .manifest import (
    PluginActivation,
    PluginKind,
    ToolDecl,
    ToolParam,
)
from .result import Err, Ok, Result

__all__ = [
    # Result type
    "Err",
    "Ok",
    "Result",
    # Manifest types
    "PluginActivation",
    "PluginKind",
    "ToolDecl",
    "ToolParam",
    # Context
    "PluginContext",
    # Base classes
    "ChannelPlugin",
    "MemoryHostPlugin",
    "Plugin",
    "ProviderPlugin",
    "ToolPlugin",
    # API
    "CliDescriptor",
    "CommandDecl",
    "PluginApi",
    # Entry
    "PluginEntry",
    "define_plugin_entry",
]
