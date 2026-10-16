"""jarvis.channels.message.receive — inbound message receive acknowledgement context.

OpenClaw parity: mirrors ``src/channels/message/receive.ts``.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from src.channels.message.types import (
    ChannelMessageReceiveAckPolicy,
    MessageAckStage,
    MessageAckState,
)


def should_ack_message_after_stage(
    policy: ChannelMessageReceiveAckPolicy,
    stage: MessageAckStage,
) -> bool:
    """Return True if *policy* acknowledges at *stage*.

    Mirrors ``shouldAckMessageAfterStage`` (``receive.ts``).
    """
    if policy == "after_receive_record":
        return stage == "receive_record"
    if policy == "after_agent_dispatch":
        return stage == "agent_dispatch"
    if policy == "after_durable_send":
        return stage == "durable_send"
    if policy == "manual":
        return False
    return False


class MessageReceiveContext:
    """Mutable receive context tracking ack/nack state for one inbound event.

    Mirrors ``MessageReceiveContext`` (``receive.ts``).
    """

    def __init__(
        self,
        event_id: str,
        channel: str,
        message: Any,
        *,
        account_id: str | None = None,
        ack_policy: ChannelMessageReceiveAckPolicy = "manual",
        on_ack: Callable[[], Any] | None = None,
        on_nack: Callable[[str], Any] | None = None,
    ) -> None:
        self.id = event_id
        self.channel = channel
        self.account_id = account_id
        self.message = message
        self.ack_policy = ack_policy
        self.ack_state: MessageAckState = "pending"
        self.acked_at: int | None = None
        self.nack_error_message: str | None = None
        self.received_at: int = int(time.time() * 1000)

        self._on_ack = on_ack
        self._on_nack = on_nack

    def should_ack_after(self, stage: MessageAckStage) -> bool:
        """Return True if this context should acknowledge after *stage*."""
        return should_ack_message_after_stage(self.ack_policy, stage)

    async def ack(self) -> None:
        """Idempotently acknowledge this receive context."""
        if self.ack_state != "pending":
            return
        self.ack_state = "acked"
        self.acked_at = int(time.time() * 1000)
        if self._on_ack:
            res = self._on_ack()
            if hasattr(res, "__await__"):
                await res

    async def nack(self, error: Any) -> None:
        """Explicitly negative-acknowledge this receive context with an error."""
        if self.ack_state != "pending":
            return
        self.ack_state = "nacked"
        msg = str(error.message if isinstance(error, Exception) else error)
        self.nack_error_message = msg
        if self._on_nack:
            res = self._on_nack(msg)
            if hasattr(res, "__await__"):
                await res


def create_message_receive_context(
    event_id: str,
    channel: str,
    message: Any,
    *,
    account_id: str | None = None,
    ack_policy: ChannelMessageReceiveAckPolicy = "manual",
    on_ack: Callable[[], Any] | None = None,
    on_nack: Callable[[str], Any] | None = None,
) -> MessageReceiveContext:
    """Create a receive context with idempotent ack and explicit nack state transitions.

    Mirrors ``createMessageReceiveContext``.
    """
    return MessageReceiveContext(
        event_id=event_id,
        channel=channel,
        message=message,
        account_id=account_id,
        ack_policy=ack_policy,
        on_ack=on_ack,
        on_nack=on_nack,
    )


__all__ = [
    "MessageReceiveContext",
    "create_message_receive_context",
    "should_ack_message_after_stage",
]
