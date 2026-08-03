"""jarvis.agents.embedded_agent_runner.run.attempt_hook_messages — clone hook messages for an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-hook-messages.ts``.

Public surface:

- :func:`clone_hook_messages`

Phase 7.6e — focused minimal port.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional


#: Agent message shape.
AgentMessage = Dict[str, Any]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def clone_hook_messages(messages: List[Any]) -> List[AgentMessage]:
    """Deep-clone a list of hook messages.

    Mirrors :func:`cloneHookMessages`
    (``attempt-hook-messages.ts``).
    """
    if not isinstance(messages, list):
        return []
    return [copy.deepcopy(message) for message in messages]


__all__ = [
    "AgentMessage",
    "clone_hook_messages",
]
