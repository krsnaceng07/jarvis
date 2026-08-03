"""jarvis.agents.embedded_agent_runner.run.attempt_trajectory_status — resolve trajectory terminal state for an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-trajectory-status.ts``.

Public surface:

Functions:

- :func:`resolve_terminal_assistant_texts`
- :func:`resolve_attempt_trajectory_terminal`

Phase 7.6d-6 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Terminal assistant texts shape.
TerminalAssistantTexts = List[str]


#: Trajectory terminal state.
AttemptTrajectoryTerminal = Dict[str, Any]


#: Installable hook for the resolve-terminal-assistant-texts step.
_RESOLVE_TERMINAL_ASSISTANT_TEXTS: Callable[
    [Dict[str, Any]], TerminalAssistantTexts
] = lambda _p: []


def set_resolve_terminal_assistant_texts_hook(
    hook: Callable[[Dict[str, Any]], TerminalAssistantTexts],
) -> None:
    """Install a custom resolveTerminalAssistantTexts hook."""
    global _RESOLVE_TERMINAL_ASSISTANT_TEXTS
    _RESOLVE_TERMINAL_ASSISTANT_TEXTS = hook


#: Installable hook for the resolve-trajectory-terminal step.
_RESOLVE_TRAJECTORY_TERMINAL: Callable[
    [Dict[str, Any]], AttemptTrajectoryTerminal
] = lambda _p: {}


def set_resolve_trajectory_terminal_hook(
    hook: Callable[[Dict[str, Any]], AttemptTrajectoryTerminal],
) -> None:
    """Install a custom resolveAttemptTrajectoryTerminal hook."""
    global _RESOLVE_TRAJECTORY_TERMINAL
    _RESOLVE_TRAJECTORY_TERMINAL = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_terminal_assistant_texts(
    params: Dict[str, Any],
) -> TerminalAssistantTexts:
    """Resolve the terminal assistant texts for an attempt.

    Mirrors :func:`resolveTerminalAssistantTexts`
    (``attempt-trajectory-status.ts``).
    """
    return _RESOLVE_TERMINAL_ASSISTANT_TEXTS(dict(params or {}))


def resolve_attempt_trajectory_terminal(
    params: Dict[str, Any],
) -> AttemptTrajectoryTerminal:
    """Resolve the attempt trajectory terminal state.

    Mirrors :func:`resolveAttemptTrajectoryTerminal`
    (``attempt-trajectory-status.ts``).
    """
    return _RESOLVE_TRAJECTORY_TERMINAL(dict(params or {}))


__all__ = [
    "AttemptTrajectoryTerminal",
    "TerminalAssistantTexts",
    "resolve_attempt_trajectory_terminal",
    "resolve_terminal_assistant_texts",
    "set_resolve_terminal_assistant_texts_hook",
    "set_resolve_trajectory_terminal_hook",
]
