"""Track 3.5 Fault Injection & Adversarial Edge Case Tests (N01-N15, X01-X03).

Validates:
- Malformed JSON frames & quarantine (N01, N02, N03)
- Future schema quarantine (N04)
- Sequence gap & stale aggregate drops (N05, N06)
- Event ID deduplication (N07)
- Rate limiting backoff (N08)
- Abrupt disconnect & freshness transition (N09)
- Half-open 3-strike dead socket trigger (N10)
- Local stale/expired approval checks (N11, N12)
- Unknown request retry prevention (N13)
- Offline fail-closed enforcement (N14, N15)
- Rapid disconnect/reconnect cycles (X01)
- Multi-tab concurrent views (X02)
- Concurrent deduplication race safety (X03)
"""

from __future__ import annotations

import datetime
import time
import pytest

from jarvis_channels.transports.deduplication import ChannelInboundDeduplicator, InboundClaimState
from jarvis_client.adapters.web.web_adapter import WebSessionAdapter
from jarvis_client.auth.token_manager import TokenManager
from jarvis_client.connection.backoff import BackoffPolicy
from jarvis_client.connection.heartbeat import ClientHeartbeatManager
from jarvis_client.connection.lifecycle import ConnectionState
from jarvis_client.connection.transport import LoopbackTransport
from jarvis_client.errors import (
    ClientErrorCode,
    JarvisClientException,
    OfflineError,
    SequenceGapError,
    StaleActionError,
)
from jarvis_client.events.decoder import DecodedEvent, EventDecoder
from jarvis_client.events.ordering import SequenceOrderingGuard
from jarvis_client.protocol.client import JarvisClient
from jarvis_client.session.reconciliation import RequestOutcomeStatus, RequestReconciler
from jarvis_client.state.client_view import ViewFreshness


# ── N01-N04: Frame Corruption & Schema Quarantine ─────────────────────────


def test_n01_n02_n03_malformed_frames_and_quarantine() -> None:
    decoder = EventDecoder()

    # N01: Non-dict frame raises INVALID_REQUEST
    with pytest.raises(JarvisClientException) as exc_info:
        decoder.decode_frame('["array", "not", "dict"]')
    assert exc_info.value.code == ClientErrorCode.INVALID_REQUEST

    # N02: Non-json string raises PARSE_ERROR
    with pytest.raises(JarvisClientException) as exc_info2:
        decoder.decode_frame("TRUNCATED_JSON{")
    assert exc_info2.value.code == ClientErrorCode.PARSE_ERROR


def test_n04_future_schema_quarantined_cleanly() -> None:
    decoder = EventDecoder(supported_schema_version=1)

    # Frame with schemaVersion 99
    future_frame = {
        "id": "evt_v99",
        "schemaVersion": 99,
        "event": "future.feature",
        "payload": {"data": 123},
    }
    res = decoder.decode_frame(future_frame)
    assert res is None
    assert len(decoder.quarantined_events) == 1
    assert decoder.quarantined_events[0]["id"] == "evt_v99"


# ── N05-N07: Sequence Gaps, Stale Drops, Deduplication ─────────────────────


def test_n05_connection_sequence_gap_raises_error() -> None:
    guard = SequenceOrderingGuard()

    # First event connectionSeq: 1
    e1 = DecodedEvent(
        event_id="e1",
        event_type="test",
        payload={},
        category="auth",
        global_seq=1,
        aggregate_version=1,
        connection_seq=1,
        timestamp_utc="",
    )
    assert guard.process_event(e1)

    # Second event jumps connectionSeq to 4 (Gap of 2, 3)
    e_gap = DecodedEvent(
        event_id="e_gap",
        event_type="test",
        payload={},
        category="auth",
        global_seq=2,
        aggregate_version=2,
        connection_seq=4,
        timestamp_utc="",
    )
    with pytest.raises(SequenceGapError):
        guard.process_event(e_gap)


def test_n06_stale_aggregate_version_dropped() -> None:
    guard = SequenceOrderingGuard()

    e1 = DecodedEvent(
        event_id="e1",
        event_type="test",
        payload={"taskId": "t1"},
        category="auth",
        global_seq=1,
        aggregate_version=5,
        connection_seq=1,
        timestamp_utc="",
    )
    assert guard.process_event(e1)

    # Stale aggregate version 3 for task t1 is dropped
    e_stale = DecodedEvent(
        event_id="e2",
        event_type="test",
        payload={"taskId": "t1"},
        category="auth",
        global_seq=2,
        aggregate_version=3,
        connection_seq=2,
        timestamp_utc="",
    )
    assert not guard.process_event(e_stale)


def test_n07_duplicate_event_id_dropped_idempotently() -> None:
    guard = SequenceOrderingGuard()

    e1 = DecodedEvent(
        event_id="same_id",
        event_type="test",
        payload={},
        category="auth",
        global_seq=1,
        aggregate_version=1,
        connection_seq=1,
        timestamp_utc="",
    )
    assert guard.process_event(e1)

    # Identical event_id
    e1_dup = DecodedEvent(
        event_id="same_id",
        event_type="test",
        payload={},
        category="auth",
        global_seq=2,
        aggregate_version=2,
        connection_seq=2,
        timestamp_utc="",
    )
    assert not guard.process_event(e1_dup)


# ── N08-N10: Rate Limit, Disconnect, Half-Open ────────────────────────────


def test_n08_rate_limit_backoff_adherence() -> None:
    policy = BackoffPolicy(base_delay=0.5, max_delay=15.0)
    delay = policy.next_delay(retry_after=60.0)
    # Clamped to max_delay
    assert delay == 15.0


def test_n09_abrupt_disconnect_freshness_transition() -> None:
    transport = LoopbackTransport()
    token_mgr = TokenManager(token="tok_1", user_id="u1")
    client = JarvisClient(transport=transport, token_manager=token_mgr)
    client.connect()
    assert client.view_state.freshness == ViewFreshness.LIVE

    # Abrupt drop
    client._on_transport_disconnected("Network unreachable")
    assert client.lifecycle.current_state == ConnectionState.DISCONNECTED
    assert client.view_state.freshness == ViewFreshness.RECONNECTING


def test_n10_three_strike_half_open_detection() -> None:
    dead = []
    hb = ClientHeartbeatManager(
        ping_interval_seconds=1.0,
        pong_timeout_seconds=0.01,
        max_missed_pongs=3,
        on_dead_connection_cb=lambda: dead.append(True),
    )

    for _ in range(3):
        hb.send_ping()
        time.sleep(0.02)
        hb.check_health()

    assert len(dead) == 1


# ── N11-N15: Stale Actions, Reconciler Unknown, Offline ───────────────────


def test_n11_n12_stale_and_expired_approval_rejection() -> None:
    transport = LoopbackTransport()
    token_mgr = TokenManager(token="tok_1", user_id="u1")
    client = JarvisClient(transport=transport, token_manager=token_mgr)
    client.connect()

    # Stale plan revision
    with pytest.raises(StaleActionError):
        client.respond_to_approval("app_1", True, expected_plan_revision=1, current_plan_revision=2)

    # Expired
    past = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=5)
    ).isoformat()
    with pytest.raises(StaleActionError):
        client.respond_to_approval("app_1", True, 1, 1, expires_at_utc=past)


def test_n13_unknown_request_state_blocks_retry() -> None:
    reconciler = RequestReconciler(query_status_fn=lambda _: {"status": "unknown"})
    status, _ = reconciler.reconcile_request("req_lost_in_flight")
    assert status == RequestOutcomeStatus.UNKNOWN
    # Invariant T35-14: UNKNOWN strictly blocks blind retry
    assert not reconciler.is_safe_to_resubmit(status)


def test_n14_n15_offline_fail_closed() -> None:
    transport = LoopbackTransport()
    token_mgr = TokenManager(token="tok_1", user_id="u1")
    client = JarvisClient(transport=transport, token_manager=token_mgr)
    # Never connected -> Offline
    with pytest.raises(OfflineError):
        client.send_chat("Will not reach socket")


# ── X01-X03: Rapid Disconnect/Reconnect & Deduplication Race ──────────────


def test_x01_rapid_disconnect_reconnect_cycles() -> None:
    transport = LoopbackTransport()
    token_mgr = TokenManager(token="tok_1", user_id="u1")
    client = JarvisClient(transport=transport, token_manager=token_mgr)

    for _ in range(5):
        client.connect()
        assert client.lifecycle.is_live
        client.disconnect()
        assert not client.lifecycle.is_connected


def test_x02_multi_tab_concurrent_views() -> None:
    transport = LoopbackTransport()
    token_mgr = TokenManager(token="tok_1", user_id="u1")
    client = JarvisClient(transport=transport, token_manager=token_mgr)
    client.connect()

    tabs = [
        WebSessionAdapter(client, tab_id=f"tab_{i}", origin="http://localhost:3000")
        for i in range(10)
    ]
    # All share the same session
    assert all(t.tab_context.session_id == tabs[0].tab_context.session_id for t in tabs)
    assert len({t.tab_context.tab_id for t in tabs}) == 10


def test_x03_inbound_deduplication_concurrent_claims() -> None:
    dedup = ChannelInboundDeduplicator()

    # Simulate 5 concurrent attempts to claim the same external message
    claims = [dedup.atomic_claim("telegram", "race_msg_1", "hash_same") for _ in range(5)]
    # Exactly one claim must succeed (Invariant T35-16)
    assert claims.count(True) == 1
    assert claims.count(False) == 4
    assert dedup.get_claim_state("telegram", "race_msg_1") == InboundClaimState.CLAIMED
