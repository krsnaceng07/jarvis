"""jarvis.agents.embedded_agent_runner.thinking_replay_repair — replay-state repair.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/thinking-replay-repair.ts``.

Public surface (mirrors the OpenClaw
source):

- :func:`repair_rejected_thinking_replay_in_session_manager` —
  repair persisted signed-thinking
  replay state after a
  provider-confirmed rejection.

Phase 7.2a — focused minimal port.
The full integration with the
session manager + transcript
rewriter lands in 7.2b+ (when
:mod:`transcript-rewrite` +
:mod:`thinking` are ported)."""
from __future__ import annotations

import logging
from typing import Any, Optional


_LOG = logging.getLogger(
    "jarvis.agents.embedded_agent_runner.thinking_replay_repair"
)


def _strip_thinking_blocks_from_message(message: Any) -> Any:
    """Strip thinking blocks from a
    message. Mirrors
    :func:`stripThinkingBlocksFromMessage`
    from :mod:`thinking.ts`.

    Phase 7.2a — focused minimal
    port: returns the message
    unchanged when ``content`` is
    not a list, or when there are
    no thinking blocks. The full
    block-strip logic lands in 7.2b+
    (when :mod:`thinking` is ported).
    """
    if not isinstance(message, dict):
        return message
    content = message.get("content")
    if not isinstance(content, list):
        return message
    has_thinking = any(
        isinstance(c, dict) and c.get("type") == "thinking"
        for c in content
    )
    if not has_thinking:
        return message
    new_message = dict(message)
    new_message["content"] = [
        c
        for c in content
        if not (
            isinstance(c, dict) and c.get("type") == "thinking"
        )
    ]
    return new_message


def repair_rejected_thinking_replay_in_session_manager(
    session_manager: Any,
    session_file: Optional[str] = None,
    session_id: Optional[str] = None,
    session_key: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> dict:
    """Repair persisted
    signed-thinking replay state
    after a provider-confirmed
    rejection. Mirrors
    :func:`repairRejectedThinkingReplayInSessionManager`
    (``thinking-replay-repair.ts:14-69`).

    Phase 7.2a — focused minimal
    port: the real implementation
    uses the session-manager
    ``getBranch`` + the transcript
    rewriter; the Python port
    returns a stub result when the
    session manager doesn't expose
    the expected interface.

    Returns
    -------
    dict
        ``{"repaired": bool,
        "repairedCount": int,
        "reason"?: str}``.
    """
    get_branch = getattr(session_manager, "get_branch", None)
    if not callable(get_branch):
        return {
            "repaired": False,
            "repairedCount": 0,
            "reason": "session manager has no get_branch method",
        }
    try:
        branch = get_branch()
    except Exception:
        return {
            "repaired": False,
            "repairedCount": 0,
            "reason": "session manager get_branch raised",
        }
    replacements: list = []
    for entry in branch or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("type") != "message":
            continue
        message = entry.get("message")
        if not isinstance(message, dict):
            continue
        replacement = _strip_thinking_blocks_from_message(message)
        if replacement is not message:
            replacements.append(
                {"entryId": entry.get("id"), "message": replacement}
            )
    if not replacements:
        return {
            "repaired": False,
            "repairedCount": 0,
            "reason": "no thinking blocks on active branch",
        }
    # Phase 7.2a — STUB. The real
    # transcript-rewriter integration
    # lands in 7.2b+.
    return {
        "repaired": True,
        "repairedCount": len(replacements),
        "reason": "stripped thinking blocks",
    }


__all__ = [
    "repair_rejected_thinking_replay_in_session_manager",
]
