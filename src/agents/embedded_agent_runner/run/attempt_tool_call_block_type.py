"""jarvis.agents.embedded_agent_runner.run.attempt_tool_call_block_type — check whether a block type is a runner tool-call block.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt.tool-call-block-type.ts``.

Public surface:

- :func:`is_runner_tool_call_block_type`

Phase 7.6e — focused minimal port.
"""
from __future__ import annotations

from typing import Any


#: Runner tool-call block types.
_RUNNER_TOOL_CALL_BLOCK_TYPES: frozenset = frozenset(
    {"toolCall", "toolUse", "tool_use", "assistant_tool_call"}
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_runner_tool_call_block_type(type_value: Any) -> bool:
    """Return True when ``type_value`` is a runner tool-call block type.

    Mirrors :func:`isRunnerToolCallBlockType`
    (``attempt.tool-call-block-type.ts``).
    """
    if not isinstance(type_value, str):
        return False
    return type_value in _RUNNER_TOOL_CALL_BLOCK_TYPES


__all__ = [
    "is_runner_tool_call_block_type",
]
