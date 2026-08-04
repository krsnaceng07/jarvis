"""jarvis.config.mcp_config — top-level MCP config facade.

OpenClaw parity: mirrors ``openclaw-main/src/config/mcp-config.ts``.

Focused minimal port: thin facade. The full config surface is
delegated to caller-provided callables (Zod validator + server
normalizers) until those land.
"""
from __future__ import annotations

from typing import Any, Callable, Optional


#: Top-level MCP config schema (zod facade).
McpConfigSchema: Any = None  # z.object({...}).strict()


def validate_mcp_config(value: Any, *, mcp_server_config_fn: Optional[Callable] = None) -> Optional[list]:
    """Validate a parsed MCP config and return any issues.

    Mirrors the superRefine checks performed by the upstream Zod schema.
    """
    if not isinstance(value, dict):
        return None
    if not callable(mcp_server_config_fn):
        return None
    issues: list = []
    servers = value.get("servers")
    if isinstance(servers, dict):
        for name, server in servers.items():
            if not isinstance(server, dict):
                continue
            entry_issues = mcp_server_config_fn({"name": name, "server": server})
            if isinstance(entry_issues, list):
                issues.extend({"path": ["servers", name, *i.get("path", [])], "message": i.get("message", "")} for i in entry_issues)
    return issues or None


__all__ = [
    "McpConfigSchema",
    "validate_mcp_config",
]
