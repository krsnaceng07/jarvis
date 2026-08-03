"""jarvis.agents.embedded_agent_runner.run.tool_media_payloads — merge tool-media payloads for an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/tool-media-payloads.ts``.

Public surface:

- :func:`merge_attempt_tool_media_payloads`

Phase 7.6g — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Tool-media payload list shape.
ToolMediaPayloadList = List[Dict[str, Any]]


#: Installable hook for the merge-attempt-tool-media-payloads step.
_MERGE_ATTEMPT_TOOL_MEDIA_PAYLOADS: Callable[
    [Dict[str, Any]], ToolMediaPayloadList
] = lambda _p: []


def set_merge_attempt_tool_media_payloads_tool_media_hook(
    hook: Callable[[Dict[str, Any]], ToolMediaPayloadList],
) -> None:
    """Install a custom mergeAttemptToolMediaPayloads hook."""
    global _MERGE_ATTEMPT_TOOL_MEDIA_PAYLOADS
    _MERGE_ATTEMPT_TOOL_MEDIA_PAYLOADS = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def merge_attempt_tool_media_payloads(
    params: Dict[str, Any],
) -> ToolMediaPayloadList:
    """Merge the tool-media payloads for an attempt.

    Mirrors :func:`mergeAttemptToolMediaPayloads`
    (``tool-media-payloads.ts``).
    """
    return _MERGE_ATTEMPT_TOOL_MEDIA_PAYLOADS(dict(params or {}))


__all__ = [
    "ToolMediaPayloadList",
    "merge_attempt_tool_media_payloads",
    "set_merge_attempt_tool_media_payloads_tool_media_hook",
]
