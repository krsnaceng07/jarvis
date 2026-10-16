"""jarvis.channels.message — channel message outbound & inbound architecture.

OpenClaw parity: mirrors ``src/channels/message/*``.
"""

from src.channels.message.live import LiveMessageState, create_live_message_state
from src.channels.message.receipt import (
    create_message_receipt_from_outbound_results,
    resolve_receipt_message_id,
)
from src.channels.message.receive import (
    MessageReceiveContext,
    create_message_receive_context,
    should_ack_message_after_stage,
)
from src.channels.message.state import classify_durable_send_recovery_state
from src.channels.message.types import (
    ChannelMessageReceiveAckPolicy,
    DeliveryFailureKind,
    DurableSendRecoveryState,
    LiveMessagePhase,
    MessageAckStage,
    MessageAckState,
    MessageDurabilityPolicy,
    MessageReceipt,
    MessageReceiptPart,
    MessageReceiptSourceResult,
)

__all__ = [
    "ChannelMessageReceiveAckPolicy",
    "DeliveryFailureKind",
    "DurableSendRecoveryState",
    "LiveMessagePhase",
    "LiveMessageState",
    "MessageAckStage",
    "MessageAckState",
    "MessageDurabilityPolicy",
    "MessageReceipt",
    "MessageReceiptPart",
    "MessageReceiptSourceResult",
    "MessageReceiveContext",
    "classify_durable_send_recovery_state",
    "create_live_message_state",
    "create_message_receipt_from_outbound_results",
    "create_message_receive_context",
    "resolve_receipt_message_id",
    "should_ack_message_after_stage",
]
