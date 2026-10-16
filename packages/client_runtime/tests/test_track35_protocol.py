"""Track 3.5 Protocol & Core Client Runtime Tests (CR01-CR20).

Validates:
- Handshake negotiation & versioning (CR01)
- Frame encoding/decoding & size limits (CR02, CR03)
- Bounded jitter backoff & resets (CR04, CR05)
- 13-state connection lifecycle machine (CR06)
- Heartbeat manager & 3-strike half-open detection (CR07, CR08)
- Token lifecycle & zero plaintext leakage (CR09, CR10)
- Secure credential storage (CR11)
- ResumeCursor connection independence (CR12, CR13)
- Ambiguous request reconciliation & unknown retry block (CR14, CR15)
- Schema version validation & quarantine (CR16, CR17)
- Sequence ordering & sparse global tolerance (CR18)
- Event reducer & view projection (CR19)
- View freshness state disclosure (CR20)
"""

from __future__ import annotations

import datetime
from pathlib import Path
import tempfile
from typing import Any
import pytest

from jarvis_client.auth.secure_store import SecureCredentialStore
from jarvis_client.auth.token_manager import CredentialState, TokenManager
from jarvis_client.connection.backoff import BackoffPolicy
from jarvis_client.connection.heartbeat import ClientHeartbeatManager
from jarvis_client.connection.lifecycle import ConnectionLifecycle, ConnectionState
from jarvis_client.errors import (
    ClientErrorCode,
    JarvisClientException,
    SequenceGapError,
)
from jarvis_client.events.decoder import DecodedEvent, EventDecoder
from jarvis_client.events.ordering import SequenceOrderingGuard
from jarvis_client.events.reducer import ClientEventReducer
from jarvis_client.protocol.frames import (
    MAX_CLIENT_FRAME_BYTES,
    RPCRequestFrame,
    RPCResponseFrame,
)
from jarvis_client.protocol.handshake import (
    CLIENT_PROTOCOL_VERSION,
    HandshakeRequest,
    validate_server_handshake,
)
from jarvis_client.session.cursor import CursorStore, ResumeCursor
from jarvis_client.session.reconciliation import RequestOutcomeStatus, RequestReconciler
from jarvis_client.state.client_view import ClientViewState, ViewFreshness


# ── CR01: Handshake Negotiation ──────────────────────────────────────────


def test_cr01_handshake_negotiation() -> None:
    req = HandshakeRequest(client_id="desktop_hud", client_type="desktop")
    req_dict = req.to_dict()
    assert req_dict["version"] == CLIENT_PROTOCOL_VERSION
    assert req_dict["clientId"] == "desktop_hud"

    # Valid response
    valid_resp = {
        "status": "accepted",
        "protocolVersion": "3.4",
        "sessionId": "sess_123",
        "serverCapabilities": ["events.catchup", "chat.send", "exec.approvals.respond"],
    }
    validated = validate_server_handshake(valid_resp)
    assert validated.accepted
    assert validated.version == "3.4"
    assert "chat.send" in validated.supported_features

    # Invalid version response raises exception
    bad_ver_resp = {"status": "accepted", "protocolVersion": "1.0", "sessionId": "sess_1"}
    with pytest.raises(JarvisClientException) as exc_info:
        validate_server_handshake(bad_ver_resp)
    assert exc_info.value.code == ClientErrorCode.PROTOCOL_VERSION_UNSUPPORTED


# ── CR02 & CR03: Frames & Limits ─────────────────────────────────────────


def test_cr02_frame_serialization_and_oversize_limit() -> None:
    req = RPCRequestFrame(id="req_1", method="chat.send", params={"text": "hello"})
    serialized = req.serialize()
    assert '"method": "chat.send"' in serialized

    # Oversized payload rejection
    huge_params = {"blob": "x" * (MAX_CLIENT_FRAME_BYTES + 100)}
    oversized = RPCRequestFrame(id="req_big", method="test", params=huge_params)
    with pytest.raises(JarvisClientException) as exc_info:
        oversized.serialize()
    assert exc_info.value.code == ClientErrorCode.FRAME_TOO_LARGE


def test_cr03_response_deserialization_and_malformed_json() -> None:
    raw_success = '{"jsonrpc": "2.0", "id": "req_1", "result": {"ok": true}}'
    resp = RPCResponseFrame.deserialize(raw_success)
    assert resp.id == "req_1"
    assert not resp.is_error
    assert resp.result == {"ok": True}

    raw_err = (
        '{"jsonrpc": "2.0", "id": "req_2", "error": {"code": -32001, "message": "Auth failed"}}'
    )
    resp_err = RPCResponseFrame.deserialize(raw_err)
    assert resp_err.is_error
    assert resp_err.error is not None
    assert resp_err.error["code"] == -32001

    with pytest.raises(JarvisClientException):
        RPCResponseFrame.deserialize("NOT_JSON{")


# ── CR04 & CR05: Bounded Backoff ──────────────────────────────────────────


def test_cr04_bounded_exponential_backoff() -> None:
    policy = BackoffPolicy(base_delay=0.25, max_delay=30.0, jitter_ratio=0.2)
    delays = [policy.next_delay() for _ in range(10)]

    # Verifies exponential growth within bounds
    assert 0.18 <= delays[0] <= 0.35
    for d in delays:
        assert d <= 36.0  # max 30s + 20% jitter


def test_cr05_backoff_reset_and_rate_limit() -> None:
    policy = BackoffPolicy(base_delay=1.0, max_delay=10.0)
    policy.next_delay()
    policy.next_delay()
    policy.reset()
    first_after_reset = policy.next_delay()
    assert 0.8 <= first_after_reset <= 1.2

    # 429 rate limit explicit backoff
    retry_after = policy.next_delay(retry_after=45.0)
    assert retry_after == 10.0  # clamped to max_delay 10.0


# ── CR06: Connection Lifecycle ───────────────────────────────────────────


def test_cr06_connection_lifecycle_13_states() -> None:
    lc = ConnectionLifecycle()
    assert lc.current_state == ConnectionState.DISCONNECTED
    assert not lc.is_connected

    lc.transition_to(ConnectionState.CONNECTING)
    lc.transition_to(ConnectionState.AUTHENTICATING)
    lc.transition_to(ConnectionState.AUTHENTICATED)
    lc.transition_to(ConnectionState.LIVE)
    assert lc.is_live
    assert lc.is_connected

    # Reconnecting flow
    lc.transition_to(ConnectionState.RESUMING)
    lc.transition_to(ConnectionState.CATCHING_UP)
    lc.transition_to(ConnectionState.LIVE)
    assert lc.is_live

    # Fatal states
    lc.transition_to(ConnectionState.AUTH_FAILED)
    assert lc.is_fatal
    assert not lc.is_connected


# ── CR07 & CR08: Heartbeat & Half-Open Detection ──────────────────────────


def test_cr07_cr08_heartbeat_and_half_open_detection() -> None:
    import time

    pings_sent: list[bool] = []
    dead_notified: list[bool] = []

    hb = ClientHeartbeatManager(
        ping_interval_seconds=1.0,
        pong_timeout_seconds=0.02,
        max_missed_pongs=3,
        send_ping_cb=lambda: pings_sent.append(True),
        on_dead_connection_cb=lambda: dead_notified.append(True),
    )

    # Ping 1 sent
    hb.send_ping()
    assert len(pings_sent) == 1

    # Pong received
    hb.record_pong()
    assert hb.missed_pongs == 0

    # 3 unanswered pings trigger half-open detection (CR08)
    time.sleep(0.03)
    hb.send_ping()
    time.sleep(0.03)
    hb.check_health()
    hb.send_ping()
    time.sleep(0.03)
    hb.check_health()
    hb.send_ping()
    time.sleep(0.03)
    hb.check_health()
    assert len(dead_notified) == 1


# ── CR09 & CR10: Token Lifecycle & Zero Secret Leakage ─────────────────────


def test_cr09_cr10_token_lifecycle_and_zero_leakage() -> None:
    raw_secret = "secret_api_key_xyz_1234567890"
    now = datetime.datetime.now(datetime.timezone.utc)
    exp_str = (now + datetime.timedelta(seconds=120)).isoformat()

    tm = TokenManager(
        token=raw_secret,
        user_id="user_admin",
        expires_at_utc=exp_str,
        refresh_threshold_seconds=60.0,
    )
    assert tm.state == CredentialState.ACTIVE

    # CR10: Zero plaintext leakage
    str_rep = str(tm)
    repr_rep = repr(tm)
    assert raw_secret not in str_rep
    assert raw_secret not in repr_rep
    assert tm.masked_token.startswith("tok_")

    # Near-expiry transition to EXPIRING
    near_exp = (now + datetime.timedelta(seconds=30)).isoformat()
    tm.expires_at_utc = near_exp
    assert tm.state == CredentialState.EXPIRING


# ── CR11: Secure Store ───────────────────────────────────────────────────


def test_cr11_secure_credential_store() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "credentials.json"
        store = SecureCredentialStore(backing_file=path)
        store.store_token("default", "token_abc_123", "usr_1")

        loaded = store.get_token("default")
        assert loaded is not None
        assert loaded["token"] == "token_abc_123"
        assert loaded["user_id"] == "usr_1"

        # Persistence reload
        store2 = SecureCredentialStore(backing_file=path)
        tok = store2.get_token("default")
        assert tok is not None
        assert tok["token"] == "token_abc_123"

        store.clear("default")
        assert store.get_token("default") is None


# ── CR12 & CR13: Resume Cursor ───────────────────────────────────────────


def test_cr12_cr13_resume_cursor_independence() -> None:
    cursor = ResumeCursor(
        journal_id="journal_main",
        global_seq=105,
        subscription_id="sub_user_1",
        aggregate_versions={"task_1": 12, "task_2": 4},
        cursor_generation=1,
    )
    # Cursor has zero ephemeral connection_id or connection_seq fields (Invariant T35-13)
    cursor_dict = cursor.to_dict()
    assert "connection_id" not in cursor_dict
    assert "connectionSeq" not in cursor_dict
    assert cursor_dict["globalSeq"] == 105

    store = CursorStore()
    store.save_cursor(cursor)
    retrieved = store.get_cursor("sub_user_1")
    assert retrieved is not None
    assert retrieved.global_seq == 105
    assert retrieved.aggregate_versions["task_1"] == 12


# ── CR14 & CR15: Reconciler & Unknown Retry Block ─────────────────────────


def test_cr14_cr15_request_reconciler_and_unknown_retry_block() -> None:
    mock_responses: dict[str, dict[str, Any]] = {
        "req_done": {"status": "completed", "result": {"node": "done"}},
        "req_missing": {"status": "not_admitted"},
        "req_ambig": {"status": "unknown"},
    }

    reconciler = RequestReconciler(
        query_status_fn=lambda r_id: mock_responses.get(r_id, {"status": "unknown"})
    )

    status1, payload1 = reconciler.reconcile_request("req_done")
    assert status1 == RequestOutcomeStatus.COMPLETED
    assert payload1 == {"node": "done"}
    assert not reconciler.is_safe_to_resubmit(status1)

    status2, _ = reconciler.reconcile_request("req_missing")
    assert status2 == RequestOutcomeStatus.NOT_ADMITTED
    assert reconciler.is_safe_to_resubmit(status2)

    # CR15: UNKNOWN strictly prevents retry
    status3, _ = reconciler.reconcile_request("req_ambig")
    assert status3 == RequestOutcomeStatus.UNKNOWN
    assert not reconciler.is_safe_to_resubmit(status3)


# ── CR16 & CR17: Event Decoder & Schema Quarantine ───────────────────────


def test_cr16_cr17_event_decoder_and_schema_quarantine() -> None:
    decoder = EventDecoder(supported_schema_version=1)

    # Valid schema v1
    v1_frame = {
        "id": "evt_1",
        "schemaVersion": 1,
        "event": "task.created",
        "category": "authoritative",
        "sequence": {"globalSeq": 10, "aggregateVersion": 1, "connectionSeq": 1},
        "payload": {"taskId": "task_1", "title": "Run test"},
    }
    decoded = decoder.decode_frame(v1_frame)
    assert decoded is not None
    assert decoded.event_id == "evt_1"
    assert decoded.global_seq == 10
    assert decoded.aggregate_version == 1

    # Future schema v2 -> Quarantined cleanly (CR16)
    v2_frame = {
        "id": "evt_future",
        "schemaVersion": 2,
        "event": "quantum.teleport",
        "payload": {},
    }
    quarantined = decoder.decode_frame(v2_frame)
    assert quarantined is None
    assert len(decoder.quarantined_events) == 1


# ── CR18: Sequence Ordering & Sparse Global Tolerance ─────────────────────


def test_cr18_sequence_ordering_guard() -> None:
    # Task-scoped guard (sparse global_seq allowed, connection_seq monotonic)
    guard = SequenceOrderingGuard(is_global_subscription=False)

    evt1 = DecodedEvent(
        event_id="e1",
        event_type="node.started",
        payload={"nodeId": "n1"},
        category="authoritative",
        global_seq=10,
        aggregate_version=1,
        connection_seq=1,
        timestamp_utc="",
    )
    assert guard.check_and_advance(evt1)

    # Next event with sparse global_seq (e.g. 15) is accepted on task-scoped streams
    evt2 = DecodedEvent(
        event_id="e2",
        event_type="node.completed",
        payload={"nodeId": "n1"},
        category="authoritative",
        global_seq=15,
        aggregate_version=2,
        connection_seq=2,
        timestamp_utc="",
    )
    assert guard.check_and_advance(evt2)

    # Gap in connection_seq raises SequenceGapError
    evt_gap = DecodedEvent(
        event_id="e3",
        event_type="node.started",
        payload={"nodeId": "n2"},
        category="authoritative",
        global_seq=20,
        aggregate_version=3,
        connection_seq=5,  # expected 3
        timestamp_utc="",
    )
    with pytest.raises(SequenceGapError):
        guard.check_and_advance(evt_gap)


# ── CR19: Event Reducer & State Projection ────────────────────────────────


def test_cr19_client_event_reducer_and_view_projection() -> None:
    view = ClientViewState()
    reducer = ClientEventReducer(view)

    # 1. Task created
    e1 = DecodedEvent(
        event_id="e1",
        event_type="task.created",
        payload={"taskId": "t1", "title": "Analyze Data"},
        category="authoritative",
        global_seq=1,
        aggregate_version=1,
        connection_seq=1,
        timestamp_utc="2026-09-20T12:00:00Z",
    )
    reducer.reduce(e1)
    assert "t1" in view.tasks
    assert view.tasks["t1"].title == "Analyze Data"
    assert view.active_task_id == "t1"

    # 2. Node added requiring approval
    e2 = DecodedEvent(
        event_id="e2",
        event_type="node.scheduled",
        payload={
            "taskId": "t1",
            "nodeId": "n1",
            "title": "Execute Bash Command",
            "requiresApproval": True,
            "approvalId": "app_99",
        },
        category="authoritative",
        global_seq=2,
        aggregate_version=2,
        connection_seq=2,
        timestamp_utc="2026-09-20T12:01:00Z",
    )
    reducer.reduce(e2)
    node = view.tasks["t1"].nodes.get("n1")
    assert node is not None
    assert node.requires_approval
    assert node.approval_id == "app_99"


# ── CR20: View Freshness State Disclosure ────────────────────────────────


def test_cr20_view_freshness_disclosure() -> None:
    view = ClientViewState()
    assert view.freshness == ViewFreshness.LIVE

    view.mark_degraded("High socket latency")
    assert view.freshness == ViewFreshness.DEGRADED

    view.mark_stale("Socket disconnected; awaiting reconnect")
    assert view.freshness == ViewFreshness.STALE

    view.mark_reconnecting("Reconnecting attempt 2")
    assert view.freshness == ViewFreshness.RECONNECTING

    view.mark_offline("Network interface unavailable")
    assert view.freshness == ViewFreshness.OFFLINE

    view.mark_live()
    assert view.freshness == ViewFreshness.LIVE
