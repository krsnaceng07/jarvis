"""jarvis.agents.embedded_agent_runner.message_action_discovery_input — discovery input.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/message-action-discovery-input.ts``.

Public surface (mirrors the OpenClaw
source):

- :func:`build_embedded_message_action_discovery_input` —
  build a normalized
  message-action discovery input
  for embedded-agent tool setup.

Phase 7.0 — focused minimal port.
"""
from __future__ import annotations

from typing import Optional, Union


def _normalize_optional(
    value: Optional[Union[str, int, float, bool]],
) -> Optional[Union[str, int, float, bool]]:
    """Convert ``None`` to ``None``,
    otherwise return ``value`` as-is.
    The OpenClaw source's
    ``?? undefined`` normalizes nulls
    + missing values to ``undefined``;
    in Python we leave the value
    alone (callers can compare with
    ``is None``).
    """
    return value


def build_embedded_message_action_discovery_input(
    params: dict,
) -> dict:
    """Build a normalized
    message-action discovery input.
    Mirrors
    :func:`buildEmbeddedMessageActionDiscoveryInput`
    (``message-action-discovery-input.ts:13-38``)."""
    return {
        "cfg": params.get("cfg"),
        "channel": params.get("channel"),
        "currentChannelId": _normalize_optional(
            params.get("currentChannelId")
        ),
        "currentThreadTs": _normalize_optional(
            params.get("currentThreadTs")
        ),
        "currentMessageId": _normalize_optional(
            params.get("currentMessageId")
        ),
        "accountId": _normalize_optional(params.get("accountId")),
        "sessionKey": _normalize_optional(params.get("sessionKey")),
        "sessionId": _normalize_optional(params.get("sessionId")),
        "agentId": _normalize_optional(params.get("agentId")),
        "requesterSenderId": _normalize_optional(
            params.get("senderId")
        ),
        "senderIsOwner": _normalize_optional(
            params.get("senderIsOwner")
        ),
    }


__all__ = [
    "build_embedded_message_action_discovery_input",
]
