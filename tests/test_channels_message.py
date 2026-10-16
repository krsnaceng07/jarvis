"""Tests for channel message outbound/inbound architecture components:

- src/channels/message/types.py
- src/channels/message/receipt.py
- src/channels/message/receive.py
- src/channels/message/live.py
- src/channels/message/state.py
"""

from __future__ import annotations

import pytest

from src.channels.message import (
    MessageReceipt,
    MessageReceiptSourceResult,
    classify_durable_send_recovery_state,
    create_live_message_state,
    create_message_receipt_from_outbound_results,
    create_message_receive_context,
    resolve_receipt_message_id,
)


def test_resolve_receipt_message_id():
    res = MessageReceiptSourceResult(message_id="msg-100")
    assert resolve_receipt_message_id(res) == "msg-100"

    res2 = MessageReceiptSourceResult(chat_id="chat-200")
    assert resolve_receipt_message_id(res2) == "chat-200"


def test_create_message_receipt_from_outbound_results():
    r1 = MessageReceiptSourceResult(message_id="m1")
    r2 = MessageReceiptSourceResult(message_id="m2")
    receipt = create_message_receipt_from_outbound_results([r1, r2], kind="text", thread_id="t1")

    assert receipt.platform_message_ids == ["m1", "m2"]
    assert receipt.primary_platform_message_id == "m1"
    assert len(receipt.parts) == 2
    assert receipt.parts[0].platform_message_id == "m1"
    assert receipt.parts[0].thread_id == "t1"


@pytest.mark.asyncio
async def test_create_message_receive_context_ack_nack():
    acked = False

    def on_ack():
        nonlocal acked
        acked = True

    ctx = create_message_receive_context(
        event_id="evt-1",
        channel="telegram",
        message={"text": "hi"},
        ack_policy="after_agent_dispatch",
        on_ack=on_ack,
    )

    assert ctx.ack_state == "pending"
    assert ctx.should_ack_after("agent_dispatch") is True
    assert ctx.should_ack_after("receive_record") is False

    await ctx.ack()
    assert ctx.ack_state == "acked"
    assert acked is True

    # Idempotent second ack does not raise or re-trigger
    await ctx.ack()


@pytest.mark.asyncio
async def test_message_receive_context_nack():
    nacked_msg = None

    def on_nack(err: str):
        nonlocal nacked_msg
        nacked_msg = err

    ctx = create_message_receive_context(
        event_id="evt-2",
        channel="whatsapp",
        message={"text": "fail"},
        on_nack=on_nack,
    )

    await ctx.nack("network timeout")
    assert ctx.ack_state == "nacked"
    assert ctx.nack_error_message == "network timeout"
    assert nacked_msg == "network timeout"


def test_live_message_state_transitions():
    live = create_live_message_state(initial_payload="draft v1")
    assert live.phase == "idle"

    live.mark_preview_updated(payload="draft v2", receipt=MessageReceipt(platform_message_ids=["p1"]))
    assert live.phase == "previewing"
    assert live.can_finalize_in_place is True

    final_receipt = MessageReceipt(platform_message_ids=["f1"])
    live.mark_finalized(final_receipt)
    assert live.phase == "finalized"
    assert live.can_finalize_in_place is False
    assert live.final_receipt == final_receipt


def test_classify_durable_send_recovery_state():
    r = MessageReceipt(platform_message_ids=["m1"])

    assert classify_durable_send_recovery_state([r], suppressed=True) == "suppressed"
    assert classify_durable_send_recovery_state([r], was_interrupted=True) == "sent"
    assert classify_durable_send_recovery_state([], was_interrupted=True) == "unknown_after_send"
    assert classify_durable_send_recovery_state([], has_error=True) == "failed"
    assert classify_durable_send_recovery_state([r], has_error=True) == "partial_failed"
    assert classify_durable_send_recovery_state([r]) == "sent"
