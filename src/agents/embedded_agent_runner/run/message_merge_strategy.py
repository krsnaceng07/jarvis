"""jarvis.agents.embedded_agent_runner.run.message_merge_strategy — resolve the message-merge strategy.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/message-merge-strategy.ts``.

Public surface:

Types:

- :data:`MessageMergeStrategy`

Functions:

- :func:`resolve_message_merge_strategy`

Phase 7.6g — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Callable, Dict


#: Message-merge strategy shape.
MessageMergeStrategy = Dict[str, Any]


#: Installable hook for the resolve-message-merge-strategy step.
_RESOLVE_MESSAGE_MERGE_STRATEGY: Callable[
    [], MessageMergeStrategy
] = lambda: {}


def set_resolve_message_merge_strategy_hook(
    hook: Callable[[], MessageMergeStrategy],
) -> None:
    """Install a custom resolveMessageMergeStrategy hook."""
    global _RESOLVE_MESSAGE_MERGE_STRATEGY
    _RESOLVE_MESSAGE_MERGE_STRATEGY = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_message_merge_strategy() -> MessageMergeStrategy:
    """Resolve the message-merge strategy.

    Mirrors :func:`resolveMessageMergeStrategy`
    (``message-merge-strategy.ts``).
    """
    return _RESOLVE_MESSAGE_MERGE_STRATEGY()


__all__ = [
    "MessageMergeStrategy",
    "resolve_message_merge_strategy",
    "set_resolve_message_merge_strategy_hook",
]
