"""jarvis.agents.embedded_agent_runner.tool_name_allowlist — session tool allowlists.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/tool-name-allowlist.ts``.

Public surface (mirrors the OpenClaw
source):

- :data:`AGENT_RESERVED_TOOL_NAMES` —
  the built-in tool names that
  remain present in the embedded
  runtime.
- :func:`collect_allowed_tool_names` —
  collect allowed tool names from
  registered + client tools.
- :func:`collect_registered_tool_names` —
  collect registered tool names.
- :func:`collect_core_builtin_tool_names` —
  collect core built-in tool
  names (filtering out plugin
  tools).
- :func:`to_session_tool_allowlist` —
  normalize an iterable of tool
  names into a sorted unique list.

Phase 7.0 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional


#: Built-in tool names that remain
#: present in the embedded runtime
#: even when OpenClaw routes
#: execution through custom tool
#: definitions. Mirrors
#: :data:`AGENT_RESERVED_TOOL_NAMES`
#: (``tool-name-allowlist.ts:11``).
AGENT_RESERVED_TOOL_NAMES: tuple = (
    "bash",
    "edit",
    "find",
    "grep",
    "ls",
    "read",
    "write",
)


def _add_name(names: set, value: Any) -> None:
    """Append ``value`` to ``names`` if
    it's a non-empty string. Mirrors
    :func:`addName`
    (``tool-name-allowlist.ts:13-21``)."""
    if not isinstance(value, str):
        return
    trimmed = value.strip()
    if trimmed:
        names.add(trimmed)


def collect_allowed_tool_names(
    tools: Iterable[Any],
    client_tools: Optional[Iterable[Any]] = None,
) -> set:
    """Collect allowed tool names
    from registered + client tools.
    Mirrors
    :func:`collectAllowedToolNames`
    (``tool-name-allowlist.ts:23-35``)."""
    names: set = set()
    for tool in tools or []:
        _add_name(names, getattr(tool, "name", None))
    for tool in client_tools or []:
        function = tool.get("function") if isinstance(tool, dict) else None
        if function is None:
            function = getattr(tool, "function", None)
        _add_name(names, function.get("name") if isinstance(function, dict) else None)
    return names


def collect_registered_tool_names(
    tools: Iterable[Any],
) -> set:
    """Collect the exact tool names
    registered with the embedded
    agent for this session. Mirrors
    :func:`collectRegisteredToolNames`
    (``tool-name-allowlist.ts:40-46``)."""
    names: set = set()
    for tool in tools or []:
        _add_name(names, getattr(tool, "name", None))
    return names


def collect_core_builtin_tool_names(
    tools: Iterable[Any],
    is_plugin_tool: Optional[Any] = None,
) -> set:
    """Collect core built-in tool
    names (filtering out plugin
    tools via ``is_plugin_tool``).
    Mirrors
    :func:`collectCoreBuiltinToolNames`
    (``tool-name-allowlist.ts:48-60``)."""
    names: set = set()
    for tool in tools or []:
        if is_plugin_tool and is_plugin_tool(tool):
            continue
        _add_name(names, getattr(tool, "name", None))
    return names


def to_session_tool_allowlist(
    allowed_tool_names: Iterable[str],
) -> list[str]:
    """Normalize an iterable of tool
    names into a sorted unique list.
    Mirrors
    :func:`toSessionToolAllowlist`
    (``tool-name-allowlist.ts:62-64``)."""
    return sorted(set(allowed_tool_names or []))


__all__ = [
    "AGENT_RESERVED_TOOL_NAMES",
    "collect_allowed_tool_names",
    "collect_core_builtin_tool_names",
    "collect_registered_tool_names",
    "to_session_tool_allowlist",
]
