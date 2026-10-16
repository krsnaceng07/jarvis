"""Test suite for Track 3.4 Canonical Protocol Contracts (Phase 3.4-A).

Validates:
1. Error taxonomy & conversion to GatewayError frames.
2. ProtocolHandshake & version negotiation rules.
3. SequenceTriad decoupling (connectionSeq != globalSeq != aggregateVersion).
4. EnrichedGatewayEvent conversion to canonical OpenClaw GatewayEvent envelope.
5. ClientIdentity scope & session access boundaries.
6. ResumeCursor round-trip serialization.
"""

from __future__ import annotations

import pytest

from jarvis_agent.gateway.errors import (
    GatewayErrorCode,
    GatewayException,
)
from jarvis_agent.gateway.models import (
    ClientIdentity,
    ConnectionContext,
    ConnectionState,
    EnrichedGatewayEvent,
    EventCategory,
    ResumeCursor,
    SequenceTriad,
)
from jarvis_agent.gateway.version import (
    PROTOCOL_NAME,
    PROTOCOL_VERSION,
    ProtocolCapabilities,
    ProtocolHandshake,
)


def test_error_taxonomy_and_exception_mapping() -> None:
    exc = GatewayException(
        code=GatewayErrorCode.APPROVAL_BINDING_MISMATCH,
        message="Action hash mismatch",
        data={"expected": "abc", "got": "def"},
    )
    err = exc.to_gateway_error()
    assert err.code == -32007
    assert err.message == "Action hash mismatch"
    assert err.data == {"expected": "abc", "got": "def"}
    d = err.to_dict()
    assert d["code"] == -32007
    assert "data" in d


def test_protocol_version_negotiation_pass() -> None:
    handshake = ProtocolHandshake(
        protocol=PROTOCOL_NAME,
        version=PROTOCOL_VERSION,
        capabilities=ProtocolCapabilities(streaming=True, replay=True),
    )
    # Compatible version should not raise
    handshake.validate_compatibility()
    d = handshake.to_dict()
    restored = ProtocolHandshake.from_dict(d)
    assert restored.protocol == PROTOCOL_NAME
    assert restored.version == PROTOCOL_VERSION
    assert restored.capabilities.streaming is True


def test_protocol_version_negotiation_reject() -> None:
    bad_proto = ProtocolHandshake(protocol="other.gateway", version="3.4")
    with pytest.raises(GatewayException) as exc_info:
        bad_proto.validate_compatibility()
    assert exc_info.value.code == GatewayErrorCode.PROTOCOL_VERSION_UNSUPPORTED

    bad_ver = ProtocolHandshake(protocol=PROTOCOL_NAME, version="4.0")
    with pytest.raises(GatewayException) as exc_info2:
        bad_ver.validate_compatibility()
    assert exc_info2.value.code == GatewayErrorCode.PROTOCOL_VERSION_UNSUPPORTED


def test_sequence_triad_decoupling() -> None:
    """Validate that connection_seq, global_seq, and aggregate_version are strictly distinct."""
    triad = SequenceTriad(
        global_seq=104,
        aggregate_version=3,
        connection_seq=51,
    )
    assert triad.global_seq == 104
    assert triad.aggregate_version == 3
    assert triad.connection_seq == 51
    assert triad.global_seq != triad.aggregate_version
    assert triad.connection_seq != triad.global_seq


def test_enriched_gateway_event_projection() -> None:
    triad = SequenceTriad(global_seq=250, aggregate_version=12, connection_seq=8)
    enriched = EnrichedGatewayEvent.create(
        event_id="evt_uuid_123",
        event_type="plan.node_state_changed",
        payload={"node_id": "node_1", "status": "running"},
        category=EventCategory.AUTHORITATIVE,
        sequence=triad,
        timestamp_utc="2026-09-20T12:00:00Z",
        correlation_id="turn_corr_99",
    )
    assert enriched.payload_hash != ""
    gw_event = enriched.to_gateway_event()
    assert gw_event.event == "plan.node_state_changed"
    assert gw_event.seq == 8
    assert gw_event.stateVersion == 12
    assert gw_event.type == "event"


def test_client_identity_scopes_and_grants() -> None:
    admin = ClientIdentity(
        user_id="user_admin",
        client_id="cli_1",
        client_type="desktop",
        auth_tier="admin",
        scopes=frozenset(["admin"]),
    )
    assert admin.has_scope("write")
    assert admin.has_scope("approve")
    assert admin.can_access_session("sess_any")

    user = ClientIdentity(
        user_id="user_alice",
        client_id="web_1",
        client_type="web",
        auth_tier="user",
        scopes=frozenset(["read", "write"]),
        session_grants=frozenset(["sess_alice_1"]),
    )
    assert user.has_scope("read")
    assert not user.has_scope("admin")
    assert user.can_access_session("sess_alice_1")
    assert not user.can_access_session("sess_bob_2")


def test_connection_context_monotonic_seq() -> None:
    conn = ConnectionContext(
        connection_id="conn_ws_1",
        transport_type="websocket",
        connected_at_utc="2026-09-20T12:00:00Z",
        state=ConnectionState.CONNECTED,
    )
    assert conn.seq_counter == 0
    assert conn.next_seq() == 1
    assert conn.next_seq() == 2
    assert conn.seq_counter == 2


def test_resume_cursor_serialization() -> None:
    cursor = ResumeCursor(
        journal_id="events_main",
        global_seq=18291,
        aggregate_id="task_441",
        aggregate_version=5,
    )
    d = cursor.to_dict()
    restored = ResumeCursor.from_dict(d)
    assert restored.journal_id == "events_main"
    assert restored.global_seq == 18291
    assert restored.aggregate_id == "task_441"
    assert restored.aggregate_version == 5
