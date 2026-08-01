"""jarvis.agents.sessions.agent_session_utils — AgentSession small utilities.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/agent-session-utils.ts``.

Ships the small helpers the AgentSession
family uses:

- :func:`unwrap_core_result` — extract the
  ``value`` from a ``Result`` (or raise
  the error).
- :func:`normalize_branch_summary_result`
  — collapse the core's
  ``BranchSummaryResult`` into a flat
  dict for the session.
- :func:`has_persisted_assistant_content`
  — whether an assistant message has
  content worth persisting.
- :func:`extract_text_content` — pull the
  text out of a string-or-content-block
  message.
- :func:`estimate_messages_from_content`
  — total token estimate for a message
  list.

Phase 6.12a — focused port.

Adaptations
-----------
- The OpenClaw source imports from
  ``@openclaw/ai/internal/runtime``. The
  Python port imports
  :func:`estimate_tokens` from
  ``packages.jarvis_agent_runtime`` (the
  Layer 1 token-estimator). When the
  package is not installed, the function
  falls back to a character-based
  estimate (4 chars per token).
"""
from __future__ import annotations

from typing import Any, Union


#: Try to import the real ``estimate_tokens``
#: from the agent-runtime package. If it
#: isn't installed (e.g. during isolated
#: unit tests), fall back to a
#: character-based estimate.
try:
    from packages.jarvis_agent_runtime.src.jarvis_agent.tokens import (  # type: ignore[import-not-found]
        estimate_tokens as _real_estimate_tokens,
    )

    def _estimate_tokens(message: Any) -> int:
        return int(_real_estimate_tokens(message))

except ImportError:  # pragma: no cover — fallback.
    def _estimate_tokens(message: Any) -> int:
        """Character-based fallback when
        :mod:`jarvis_agent.tokens` is not
        installed. Counts ``len(message) // 4``
        — OpenClaw's default heuristic
        (``4 chars ≈ 1 token``)."""
        if message is None:
            return 0
        if isinstance(message, str):
            return max(1, len(message) // 4)
        if isinstance(message, dict):
            content = message.get("content", "")
            if isinstance(content, str):
                return max(1, len(content) // 4)
            if isinstance(content, list):
                total = 0
                for block in content:
                    if isinstance(block, dict):
                        text = block.get("text", "")
                        if isinstance(text, str):
                            total += len(text)
                return max(1, total // 4)
        return 1


def unwrap_core_result(
    result: Union[
        dict,  # {"ok": True, "value": T}
        dict,  # {"ok": False, "error": Error}
    ],
) -> Any:
    """Extract ``value`` from a Result
    (``{ok, value, error}``) — or raise
    the error. Mirrors ``unwrapCoreResult``
    (``agent-session-utils.ts:7-14``).

    The Python port uses plain dicts for
    the Result shape (the OpenClaw source
    uses a tagged union).
    """
    if result.get("ok"):
        return result["value"]
    err = result.get("error")
    if isinstance(err, Exception):
        raise err
    raise RuntimeError(str(err) if err is not None else "core result error")


def normalize_branch_summary_result(
    result: dict,
) -> dict:
    """Collapse the core's
    ``BranchSummaryResult`` into a flat
    dict for the session. Mirrors
    ``normalizeBranchSummaryResult``
    (``agent-session-utils.ts:16-34``).

    Returns
    -------
    dict
        ``{summary?, readFiles?, modifiedFiles?,
        aborted?, error?}`` — the field
        names use the Python convention
        (camelCase preserved to match the
        core's shape).
    """
    if result.get("ok"):
        return dict(result["value"])
    err = result.get("error") or {}
    code = err.get("code", "")
    if code == "aborted":
        return {
            "aborted": True,
            "error": err.get("message", "aborted"),
        }
    return {"error": err.get("message", "branch summary failed")}


def has_persisted_assistant_content(content: Any) -> bool:
    """Whether an assistant message has
    content worth persisting to disk.
    Mirrors ``hasPersistedAssistantContent``
    (``agent-session-utils.ts:36-38``)."""
    return (
        isinstance(content, str) or isinstance(content, list)
    ) and len(content) > 0


def extract_text_content(content: Any) -> str:
    """Pull the text out of a string-or-
    content-block message. Mirrors
    ``extractTextContent``
    (``agent-session-utils.ts:40-58``)."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return "".join(parts)


def estimate_messages_from_content(messages: list) -> int:
    """Total token estimate for a message
    list. Mirrors
    ``estimateMessagesFromContent``
    (``agent-session-utils.ts:60-62``)."""
    return sum(_estimate_tokens(m) for m in messages)


__all__ = [
    "estimate_messages_from_content",
    "extract_text_content",
    "has_persisted_assistant_content",
    "normalize_branch_summary_result",
    "unwrap_core_result",
]
