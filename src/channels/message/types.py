"""jarvis.channels.message.types — channel message, receipt, receive, and live state types.

OpenClaw parity: mirrors ``src/channels/message/types.ts``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

MessageDurabilityPolicy = Literal["required", "best_effort", "disabled"]

DeliveryFailureKind = Literal[
    "transient",
    "rate_limit",
    "auth",
    "permission",
    "not_found",
    "invalid_payload",
    "conflict",
    "cancelled",
    "unknown",
]

ChannelMessageReceiveAckPolicy = Literal[
    "after_receive_record",
    "after_agent_dispatch",
    "after_durable_send",
    "manual",
]

MessageAckStage = Literal["receive_record", "agent_dispatch", "durable_send", "manual"]
MessageAckState = Literal["pending", "acked", "nacked"]

LiveMessagePhase = Literal["idle", "previewing", "finalizing", "finalized", "cancelled"]

DurableSendRecoveryState = Literal[
    "sent",
    "suppressed",
    "partial_failed",
    "failed",
    "unknown_after_send",
]


@dataclass(slots=True)
class MessageReceiptPart:
    platform_message_id: str
    kind: str = "unknown"
    index: int = 0
    thread_id: str | None = None
    reply_to_id: str | None = None


@dataclass(slots=True)
class MessageReceipt:
    platform_message_ids: list[str] = field(default_factory=list)
    primary_platform_message_id: str | None = None
    parts: list[MessageReceiptPart] = field(default_factory=list)
    sent_at: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "platformMessageIds": self.platform_message_ids,
            "primaryPlatformMessageId": self.primary_platform_message_id,
            "parts": [
                {
                    "platformMessageId": p.platform_message_id,
                    "kind": p.kind,
                    "index": p.index,
                    "threadId": p.thread_id,
                    "replyToId": p.reply_to_id,
                }
                for p in self.parts
            ],
            "sentAt": self.sent_at,
        }


@dataclass
class MessageReceiptSourceResult:
    channel: str | None = None
    message_id: str | None = None
    chat_id: str | None = None
    channel_id: str | None = None
    room_id: str | None = None
    conversation_id: str | None = None
    to_jid: str | None = None
    poll_id: str | None = None
    receipt: MessageReceipt | None = None


__all__ = [
    "ChannelMessageReceiveAckPolicy",
    "DeliveryFailureKind",
    "DurableSendRecoveryState",
    "LiveMessagePhase",
    "MessageAckStage",
    "MessageAckState",
    "MessageDurabilityPolicy",
    "MessageReceipt",
    "MessageReceiptPart",
    "MessageReceiptSourceResult",
]
