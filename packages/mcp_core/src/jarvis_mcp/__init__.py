"""JARVIS MCP Core.

Provides integration with Model Context Protocol (MCP) servers,
exposing tools and managing connection lifecycle.
"""

from .registry import McpRegistry
from .tool_adapter import adapt_mcp_tool

__all__ = [
    "McpRegistry",
    "adapt_mcp_tool",
]
