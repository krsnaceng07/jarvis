"""Tool allowlist guard — mirrors OpenClaw tool access control enforcement."""

from __future__ import annotations

import logging
from typing import Sequence

_log = logging.getLogger("jarvis.agents.tool_allowlist_guard")


class ToolAllowlistDeniedError(PermissionError):
    """Raised when an unallowed tool call is attempted."""
    pass


class ToolAllowlistGuard:
    """Enforces effective allowlist before tool execution."""

    def __init__(self, allowed_tools: Sequence[str]) -> None:
        self._allowed = set(allowed_tools)

    def is_allowed(self, tool_name: str) -> bool:
        return tool_name in self._allowed

    def check_allowed(self, tool_name: str) -> None:
        if not self.is_allowed(tool_name):
            _log.warning("Tool execution blocked by policy: %s", tool_name)
            raise ToolAllowlistDeniedError(f"Tool '{tool_name}' is not in the active allowlist.")


__all__ = ["ToolAllowlistDeniedError", "ToolAllowlistGuard"]
