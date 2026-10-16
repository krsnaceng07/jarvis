"""jarvis.channels.message.state — durable send recovery state classification.

OpenClaw parity: mirrors ``src/channels/message/state.ts``.
"""

from __future__ import annotations

from typing import Sequence

from src.channels.message.types import DurableSendRecoveryState, MessageReceipt


def classify_durable_send_recovery_state(
    receipts: Sequence[MessageReceipt],
    *,
    has_error: bool = False,
    was_interrupted: bool = False,
    suppressed: bool = False,
) -> DurableSendRecoveryState:
    """Classify the recovery state of a durable send after execution or process interruption.

    Mirrors ``classifyDurableSendRecoveryState`` (``state.ts``).
    """
    if suppressed:
        return "suppressed"

    has_receipts = any(r.platform_message_ids for r in receipts)

    if was_interrupted:
        if has_receipts:
            return "sent"
        return "unknown_after_send"

    if has_error:
        if has_receipts:
            return "partial_failed"
        return "failed"

    if has_receipts:
        return "sent"

    return "suppressed"


__all__ = [
    "classify_durable_send_recovery_state",
]
