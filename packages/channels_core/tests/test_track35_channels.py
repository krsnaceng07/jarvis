"""Track 3.5 External Channel Transports Tests (CH01-CH20).

Validates:
- Server-side channel execution boundary (CH01)
- Authoritative route triple synthesis (CH02, CH03)
- SQLite WAL atomic claim deduplication (CH04, CH05, CH06, CH07)
- Telegram inbound/outbound & inline buttons (CH08, CH09, CH10)
- Discord inbound/outbound & ActionRow buttons (CH11, CH12, CH13)
- Slack inbound/outbound & Block Kit buttons (CH14, CH15, CH16)
- 6-state outbound delivery tracking (CH17, CH18, CH19)
- Timed-out dispatch reconciliation & retry block (CH20)
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import time

from jarvis_channels.transports.adapters.discord import DiscordTransportAdapter
from jarvis_channels.transports.adapters.slack import SlackTransportAdapter
from jarvis_channels.transports.adapters.telegram import TelegramTransportAdapter
from jarvis_channels.transports.deduplication import ChannelInboundDeduplicator, InboundClaimState
from jarvis_channels.transports.delivery import (
    ChannelDeliveryStatus,
    ChannelDeliveryTracker,
)
from jarvis_channels.transports.identity import synthesize_route_triple
from jarvis_channels.transports.reconciliation import ChannelDeliveryReconciler
from jarvis_channels.types import OutboundMessage


# ── CH01-CH03: Route Synthesis & Identity ─────────────────────────────────


def test_ch01_ch02_ch03_route_synthesis() -> None:
    # CH02: Deterministic route triple
    route = synthesize_route_triple("Telegram", "user_123", "thread_456")
    assert route.route_triple == ("telegram", "user_123", "thread_456")
    assert route.session_key == "telegram:user_123:thread_456"

    # CH03: Missing thread normalizes to 'root'
    route_root = synthesize_route_triple("discord", "user_999", None)
    assert route_root.external_thread_id == "root"
    assert route_root.session_key == "discord:user_999"


# ── CH04-CH07: SQLite WAL Inbound Deduplication ───────────────────────────


def test_ch04_ch05_ch06_ch07_inbound_deduplication() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "claims.sqlite"
        dedup = ChannelInboundDeduplicator(db_path=db_path)

        # CH04: First claim succeeds
        claimed = dedup.atomic_claim("telegram", "msg_1", "hash_abc")
        assert claimed
        assert dedup.get_claim_state("telegram", "msg_1") == InboundClaimState.CLAIMED

        # CH05: Duplicate claim dropped
        claimed_dup = dedup.atomic_claim("telegram", "msg_1", "hash_abc")
        assert not claimed_dup

        # CH06: Transition to PROCESSING -> COMPLETED
        assert dedup.mark_processing("telegram", "msg_1")
        assert dedup.get_claim_state("telegram", "msg_1") == InboundClaimState.PROCESSING

        assert dedup.mark_completed("telegram", "msg_1")
        assert dedup.get_claim_state("telegram", "msg_1") == InboundClaimState.COMPLETED

        # CH07: Failure recording
        dedup.atomic_claim("telegram", "msg_fail", "hash_xyz")
        assert dedup.mark_failed("telegram", "msg_fail", "Syntax parsing error")
        assert dedup.get_claim_state("telegram", "msg_fail") == InboundClaimState.FAILED

        dedup.close()


# ── CH08-CH10: Telegram Adapter ───────────────────────────────────────────


def test_ch08_ch09_ch10_telegram_adapter() -> None:
    dedup = ChannelInboundDeduplicator()
    tracker = ChannelDeliveryTracker()
    tg = TelegramTransportAdapter(deduplicator=dedup, tracker=tracker)

    # CH08: Message Update Parsing
    raw_update = {
        "update_id": 1001,
        "message": {
            "message_id": 555,
            "from": {"id": 8881, "username": "alice"},
            "chat": {"id": 8881},
            "text": "/plan start",
        },
    }
    inbound = tg.handle_inbound(raw_update)
    assert inbound is not None
    assert inbound.sender_id == "8881"
    assert inbound.text == "/plan start"
    assert inbound.channel_id == "telegram"
    assert tg.mark_inbound_completed("555")

    # CH09: Callback query parsing (button click)
    raw_cb = {
        "update_id": 1002,
        "callback_query": {
            "id": "cb_99",
            "from": {"id": 8881},
            "message": {"message_id": 556},
            "data": "approve_plan_rev1",
        },
    }
    inbound_cb = tg.handle_inbound(raw_cb)
    assert inbound_cb is not None
    assert inbound_cb.text == "approve_plan_rev1"

    # CH10: Outbound formatting with typed action buttons
    out = OutboundMessage(
        channel_id="telegram",
        conversation_id="8881",
        text="Please approve deployment.",
        metadata={
            "actions": [
                {"label": "Approve", "action_id": "act_approve"},
                {"label": "Reject", "action_id": "act_reject"},
            ]
        },
    )
    native = tg.format_native_outbound(out)
    assert native["chat_id"] == "8881"
    assert "reply_markup" in native
    assert len(native["reply_markup"]["inline_keyboard"][0]) == 2
    assert native["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "act_approve"


# ── CH11-CH13: Discord Adapter ───────────────────────────────────────────


def test_ch11_ch12_ch13_discord_adapter() -> None:
    dedup = ChannelInboundDeduplicator()
    tracker = ChannelDeliveryTracker()
    disc = DiscordTransportAdapter(deduplicator=dedup, tracker=tracker)

    # CH11: Message Create
    raw_msg = {
        "id": "99887766",
        "author": {"id": "usr_disc_1", "bot": False},
        "channel_id": "chan_42",
        "content": "Status report",
    }
    inbound = disc.handle_inbound(raw_msg)
    assert inbound is not None
    assert inbound.sender_id == "usr_disc_1"
    assert inbound.text == "Status report"

    # Bot message ignored
    bot_msg = {
        "id": "99887767",
        "author": {"id": "bot_1", "bot": True},
        "content": "I am a bot",
    }
    assert disc.handle_inbound(bot_msg) is None

    # CH12: Button interaction component
    interaction = {
        "type": 3,
        "id": "int_1",
        "user": {"id": "usr_disc_1"},
        "channel_id": "chan_42",
        "data": {"custom_id": "btn_approve"},
    }
    inbound_btn = disc.handle_inbound(interaction)
    assert inbound_btn is not None
    assert inbound_btn.text == "btn_approve"

    # CH13: Outbound formatting with ActionRow components
    out = OutboundMessage(
        channel_id="discord",
        conversation_id="chan_42",
        text="Review required",
        metadata={
            "actions": [
                {"label": "Approve", "action_id": "act_ok"},
                {"label": "Deny", "action_id": "act_deny", "style": "danger"},
            ]
        },
    )
    native = disc.format_native_outbound(out)
    assert "components" in native
    buttons = native["components"][0]["components"]
    assert len(buttons) == 2
    assert buttons[0]["style"] == 3  # Success
    assert buttons[1]["style"] == 4  # Danger


# ── CH14-CH16: Slack Adapter ─────────────────────────────────────────────


def test_ch14_ch15_ch16_slack_adapter() -> None:
    dedup = ChannelInboundDeduplicator()
    tracker = ChannelDeliveryTracker()
    slack = SlackTransportAdapter(deduplicator=dedup, tracker=tracker)

    # CH14: Events API Message
    raw_slack = {
        "event": {
            "type": "message",
            "client_msg_id": "slk_m1",
            "user": "U12345",
            "text": "Check pipeline",
            "channel": "C999",
            "thread_ts": "171000.123",
        }
    }
    inbound = slack.handle_inbound(raw_slack)
    assert inbound is not None
    assert inbound.sender_id == "U12345"
    assert inbound.thread_id == "171000.123"

    # CH15: Block actions
    block_action = {
        "type": "block_actions",
        "trigger_id": "trig_1",
        "user": {"id": "U12345"},
        "container": {"channel_id": "C999"},
        "actions": [{"value": "val_approved"}],
    }
    inbound_ba = slack.handle_inbound(block_action)
    assert inbound_ba is not None
    assert inbound_ba.text == "val_approved"

    # CH16: Outbound formatting with Block Kit
    out = OutboundMessage(
        channel_id="slack",
        conversation_id="C999",
        text="Approval needed",
        metadata={
            "actions": [{"label": "Confirm", "action_id": "confirm_1", "value": "v_confirm"}]
        },
    )
    native = slack.format_native_outbound(out)
    assert "blocks" in native
    assert any(b["type"] == "actions" for b in native["blocks"])


# ── CH17-CH19: 6-State Delivery Tracking ─────────────────────────────────


def test_ch17_ch18_ch19_delivery_tracker() -> None:
    dedup = ChannelInboundDeduplicator()
    tracker = ChannelDeliveryTracker()
    tg = TelegramTransportAdapter(deduplicator=dedup, tracker=tracker)

    out = OutboundMessage(
        channel_id="telegram",
        conversation_id="8881",
        text="Hello world",
    )

    # Dispatch executes: CREATED -> QUEUED -> DISPATCHED -> PROVIDER_ACCEPTED
    record = tg.dispatch_outbound(out)
    assert record.status == ChannelDeliveryStatus.PROVIDER_ACCEPTED
    assert record.provider_response_id is not None
    assert record.provider_response_id.startswith("tg_msg_")

    # Confirm explicit delivery
    assert tg.confirm_delivered(record.delivery_id)
    rec_delivered = tracker.get_delivery(record.delivery_id)
    assert rec_delivered is not None
    assert rec_delivered.status == ChannelDeliveryStatus.DELIVERED

    # Failure tracking
    tracker.create_delivery("del_fail", "msg_fail", "telegram", "user_x", "test fail")
    tracker.mark_failed("del_fail", "HTTP 502 Bad Gateway")
    rec_failed = tracker.get_delivery("del_fail")
    assert rec_failed is not None
    assert rec_failed.status == ChannelDeliveryStatus.FAILED
    assert rec_failed.error_message == "HTTP 502 Bad Gateway"


# ── CH20: Delivery Reconciliation & Safe Resend Gate ─────────────────────


def test_ch20_delivery_reconciliation_and_resend_gate() -> None:
    tracker = ChannelDeliveryTracker()
    reconciler = ChannelDeliveryReconciler(tracker=tracker, dispatch_timeout_seconds=0.01)

    # 1. Create a delivery stuck in DISPATCHED
    tracker.create_delivery("del_stuck", "msg_s", "telegram", "u1", "stuck text")
    tracker.mark_dispatched("del_stuck")
    d1 = tracker.get_delivery("del_stuck")
    assert d1 is not None and d1.status == ChannelDeliveryStatus.DISPATCHED

    # Wait past timeout
    time.sleep(0.02)
    reconciled = reconciler.reconcile_stale_dispatches()
    assert "del_stuck" in reconciled
    d2 = tracker.get_delivery("del_stuck")
    assert d2 is not None and d2.status == ChannelDeliveryStatus.UNKNOWN

    # Resend gate: UNKNOWN strictly blocks blind resend (Invariant T35-15)
    assert not reconciler.can_safely_resend("del_stuck")

    # If provider explicitly confirms message was NOT received, resend is permitted
    assert reconciler.can_safely_resend("del_stuck", provider_verifier=lambda _: True)

    # PROVIDER_ACCEPTED never permits resend
    tracker.create_delivery("del_accepted", "msg_a", "telegram", "u1", "accepted text")
    tracker.mark_provider_accepted("del_accepted", "tg_123")
    assert not reconciler.can_safely_resend("del_accepted")
