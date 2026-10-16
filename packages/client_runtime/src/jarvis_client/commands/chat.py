"""Ingress chat command builder for Track 3.5.

Formats `chat.send` / `conversation.turn` frames with deterministic client request IDs.
Handles immediate acceptance response.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import uuid

from jarvis_client.protocol.frames import RPCRequestFrame


@dataclass(frozen=True, slots=True)
class ChatAcceptance:
    """Immediate gateway acknowledgement of turn admission."""

    accepted: bool
    request_id: str
    turn_id: str
    task_id: str | None = None
    created_at_utc: str = ""
    error_message: str | None = None


def build_chat_send_frame(
    message: str,
    session_id: str,
    conversation_id: str | None = None,
    client_turn_id: str | None = None,
    client_request_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> tuple[RPCRequestFrame, str]:
    """Construct standard JSON-RPC 2.0 chat.send request frame.

    Returns (RPCRequestFrame, request_id).
    """
    req_id = client_request_id or f"req_{uuid.uuid4().hex[:12]}"
    turn_id = client_turn_id or f"turn_{uuid.uuid4().hex[:8]}"

    params = {
        "sessionId": session_id,
        "conversationId": conversation_id or session_id,
        "turnId": turn_id,
        "message": message,
        "metadata": metadata or {},
    }

    frame = RPCRequestFrame(
        id=req_id,
        method="chat.send",
        params=params,
    )
    return frame, req_id


def parse_chat_acceptance(response_result: Any, request_id: str) -> ChatAcceptance:
    """Extract ChatAcceptance from RPC response result payload."""
    if not isinstance(response_result, dict):
        return ChatAcceptance(
            accepted=False,
            request_id=request_id,
            turn_id="",
            error_message="Invalid gateway response format",
        )

    return ChatAcceptance(
        accepted=bool(response_result.get("accepted", False)),
        request_id=str(response_result.get("requestId", request_id)),
        turn_id=str(response_result.get("turnId", "")),
        task_id=response_result.get("taskId"),
        created_at_utc=str(response_result.get("createdAtUtc", "")),
        error_message=response_result.get("error"),
    )


__all__ = ["ChatAcceptance", "build_chat_send_frame", "parse_chat_acceptance"]
