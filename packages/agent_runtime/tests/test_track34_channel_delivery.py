"""Test suite for Track 3.4 Outbound Channel Router & Delivery Ledger (Phase 3.4-K).

Validates:
1. Formal delivery state progression (QUEUED -> DISPATCHED -> DELIVERED).
2. Outbound delivery idempotency preventing duplicate message transmission (Invariant T34-19).
3. Routing strictly honoring ResponseRoute.channel without channel cross-leakage.
4. Transport adapter failure handling.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any
import pytest

from jarvis_agent.gateway.channel_router import ChannelRouter
from jarvis_agent.gateway.delivery_ledger import DeliveryLedger
from jarvis_agent.gateway.errors import GatewayErrorCode, GatewayException
from jarvis_agent.gateway.models import DeliveryStatus
from jarvis_agent.orchestration.models.response_route import ResponseRoute


class MockChannelAdapter:
    def __init__(self, succeed: bool = True) -> None:
        self.succeed = succeed
        self.delivered_calls: list[tuple[ResponseRoute, dict[str, Any], str]] = []

    def deliver_message(
        self, route: ResponseRoute, payload: dict[str, Any], delivery_id: str
    ) -> bool:
        self.delivered_calls.append((route, payload, delivery_id))
        return self.succeed


def test_channel_router_delivery_and_idempotency() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "deliveries.sqlite"
        ledger = DeliveryLedger(db_path)
        try:
            router = ChannelRouter(delivery_ledger=ledger)

            tg_adapter = MockChannelAdapter(succeed=True)
            desktop_adapter = MockChannelAdapter(succeed=True)
            router.register_adapter("telegram", tg_adapter)
            router.register_adapter("desktop", desktop_adapter)

            route_tg = ResponseRoute(
                channel="telegram",
                conversation_id="conv_tg",
                user_id="tg_user_1",
                reply_to_message_id="123",
            )

            payload = {"text": "Your task is complete!"}

            # 1. First outbound dispatch -> DELIVERED
            rec = router.dispatch_outbound(route_tg, message_id="msg_001", payload=payload)
            assert rec.status == DeliveryStatus.DELIVERED
            assert len(tg_adapter.delivered_calls) == 1
            assert len(desktop_adapter.delivered_calls) == 0  # Zero leakage to desktop!

            # 2. Retrying same (message_id, recipient_id) returns cached DELIVERED without calling adapter again
            rec_retry = router.dispatch_outbound(route_tg, message_id="msg_001", payload=payload)
            assert rec_retry.status == DeliveryStatus.DELIVERED
            assert len(tg_adapter.delivered_calls) == 1  # Unchanged!
        finally:
            ledger.close()


def test_channel_router_adapter_failure() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "deliveries.sqlite"
        ledger = DeliveryLedger(db_path)
        try:
            router = ChannelRouter(delivery_ledger=ledger)

            failing_adapter = MockChannelAdapter(succeed=False)
            router.register_adapter("discord", failing_adapter)

            route = ResponseRoute(channel="discord", conversation_id="c1", user_id="u1")
            rec = router.dispatch_outbound(route, message_id="msg_fail", payload={"text": "hi"})
            assert rec.status == DeliveryStatus.FAILED
        finally:
            ledger.close()


def test_channel_router_unregistered_channel() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "deliveries.sqlite"
        ledger = DeliveryLedger(db_path)
        try:
            router = ChannelRouter(delivery_ledger=ledger)

            route = ResponseRoute(channel="unregistered_chan", conversation_id="c1", user_id="u1")
            with pytest.raises(GatewayException) as exc:
                router.dispatch_outbound(route, message_id="m1", payload={})
            assert exc.value.code == GatewayErrorCode.INVALID_PARAMS
        finally:
            ledger.close()
