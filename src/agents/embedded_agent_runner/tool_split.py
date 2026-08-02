"""jarvis.agents.embedded_agent_runner.tool_split — split SDK tools from OpenClaw tool definitions.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/tool-split.ts``.

Public surface (mirrors the OpenClaw source):

- :func:`split_sdk_tools` — return the ``customTools`` for the
  provider call. The OpenClaw source always passes tools via
  ``customTools`` so policy filtering, sandbox integration, and
  the extended toolset remain consistent across providers.

Phase 7.4a — focused minimal port.

The OpenClaw source uses :func:`toToolDefinitions` from
``agent-tool-definition-adapter.js``. The Python port delegates
to an installable hook so the host can plug in the real
tool-definition adapter when the runtime layer lands.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


#: Tool-definition adapter. The host installs the real
#: :func:`toToolDefinitions`` when the agent-tool-definition
#: adapter layer lands. The default returns an empty list.
_TO_TOOL_DEFINITIONS: Callable[..., List[Any]] = lambda *args, **kwargs: []


def set_to_tool_definitions_hook(
    hook: Callable[..., List[Any]],
) -> None:
    """Install a custom tool-definition adapter hook."""
    global _TO_TOOL_DEFINITIONS
    _TO_TOOL_DEFINITIONS = hook


def split_sdk_tools(
    options: Dict[str, Any],
) -> Dict[str, List[Any]]:
    """Return the ``customTools`` for the provider call.

    Mirrors :func:`splitSdkTools``
    (``tool-split.ts:12-23``).
    """
    tools = options.get("tools") or []
    tool_hook_context = options.get("toolHookContext")
    return {
        "customTools": _TO_TOOL_DEFINITIONS(tools, tool_hook_context),
    }


__all__ = [
    "set_to_tool_definitions_hook",
    "split_sdk_tools",
]
