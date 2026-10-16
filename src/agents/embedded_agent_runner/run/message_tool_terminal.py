"""jarvis.agents.embedded_agent_runner.run.message_tool_terminal — install the message-tool-only terminal hook.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/message-tool-terminal.ts``.

Public surface:

- :func:`install_message_tool_only_terminal_hook`

Phase 7.6g — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Callable, Dict


#: Installable hook for the install-message-tool-only-terminal-hook step.
_INSTALL_MESSAGE_TOOL_ONLY_TERMINAL_HOOK: Callable[
    [Dict[str, Any]], Any
] = lambda _p: None


def set_install_message_tool_only_terminal_hook_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom installMessageToolOnlyTerminalHook hook."""
    global _INSTALL_MESSAGE_TOOL_ONLY_TERMINAL_HOOK
    _INSTALL_MESSAGE_TOOL_ONLY_TERMINAL_HOOK = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def install_message_tool_only_terminal_hook(
    params: Dict[str, Any],
) -> Any:
    """Install the message-tool-only terminal hook.

    Mirrors :func:`installMessageToolOnlyTerminalHook`
    (``message-tool-terminal.ts``).
    """
    return _INSTALL_MESSAGE_TOOL_ONLY_TERMINAL_HOOK(dict(params or {}))


__all__ = [
    "install_message_tool_only_terminal_hook",
    "set_install_message_tool_only_terminal_hook_hook",
]
