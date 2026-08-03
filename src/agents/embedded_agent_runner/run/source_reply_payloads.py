"""jarvis.agents.embedded_agent_runner.run.source_reply_payloads — build the source-reply payload state.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/source-reply-payloads.ts``.

Public surface:

- :func:`build_source_reply_payload_state`

Phase 7.6g — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Source-reply payload state shape.
SourceReplyPayloadState = Dict[str, Any]


#: Installable hook for the build-source-reply-payload-state step.
_BUILD_SOURCE_REPLY_PAYLOAD_STATE: Callable[
    [Dict[str, Any]], Any
] = lambda _p: {}


def set_build_source_reply_payload_state_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom buildSourceReplyPayloadState hook."""
    global _BUILD_SOURCE_REPLY_PAYLOAD_STATE
    _BUILD_SOURCE_REPLY_PAYLOAD_STATE = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_source_reply_payload_state(
    params: Dict[str, Any],
) -> SourceReplyPayloadState:
    """Build the source-reply payload state.

    Mirrors :func:`buildSourceReplyPayloadState`
    (``source-reply-payloads.ts``).
    """
    state = _BUILD_SOURCE_REPLY_PAYLOAD_STATE(dict(params or {}))
    if not isinstance(state, dict):
        state = {}
    return {
        "replyItems": state.get("replyItems") or [],
        "hasSourceReplyPayload": bool(state.get("hasSourceReplyPayload", False)),
        "deliveredSourceReplyViaMessageTool": bool(
            state.get("deliveredSourceReplyViaMessageTool", False)
        ),
        "explicitFinalSourceReply": state.get("explicitFinalSourceReply"),
        "completedSourceReplyViaMessageTool": bool(
            state.get("completedSourceReplyViaMessageTool", False)
        ),
    }


__all__ = [
    "SourceReplyPayloadState",
    "build_source_reply_payload_state",
    "set_build_source_reply_payload_state_hook",
]
