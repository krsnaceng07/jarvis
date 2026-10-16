"""Test suite for Track 3.4 Request Idempotency Ledger (Phase 3.4-D).

Validates:
1. New mutating request admission.
2. Completed request caching and idempotent replay.
3. In-flight duplicate rejection (REQUEST_DUPLICATE).
4. Conflicting payload rejection on same request_id (REQUEST_CONFLICT).
5. WAL database persistence across restarts.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from jarvis_agent.gateway.errors import GatewayErrorCode, GatewayException
from jarvis_agent.gateway.idempotency import GatewayRequestLedger


def test_idempotency_new_and_completed_replay() -> None:
    ledger = GatewayRequestLedger()
    try:
        req_id = "req_test_1"
        payload = {"text": "hello jarvis", "channel": "desktop"}

        # 1. First submission -> is_new is True
        is_new, cached = ledger.check_or_record(
            request_id=req_id,
            client_identity_id="alice",
            session_id="sess_1",
            method="chat.send",
            payload=payload,
        )
        assert is_new is True
        assert cached is None

        # 2. Mark completed
        ledger.complete_request(req_id, {"turnId": "turn_101", "accepted": True})

        # 3. Duplicate submission with same payload -> returns cached response
        is_new2, cached2 = ledger.check_or_record(
            request_id=req_id,
            client_identity_id="alice",
            session_id="sess_1",
            method="chat.send",
            payload=payload,
        )
        assert is_new2 is False
        assert cached2 == {"turnId": "turn_101", "accepted": True}
    finally:
        ledger.close()


def test_idempotency_in_flight_duplicate_rejection() -> None:
    ledger = GatewayRequestLedger()
    try:
        req_id = "req_inflight"
        payload = {"cmd": "run"}

        ledger.check_or_record(
            request_id=req_id,
            client_identity_id="bob",
            session_id="sess_2",
            method="conversation.turn",
            payload=payload,
        )

        # Immediate duplicate while PENDING -> REQUEST_DUPLICATE
        with pytest.raises(GatewayException) as exc:
            ledger.check_or_record(
                request_id=req_id,
                client_identity_id="bob",
                session_id="sess_2",
                method="conversation.turn",
                payload=payload,
            )
        assert exc.value.code == GatewayErrorCode.REQUEST_DUPLICATE
    finally:
        ledger.close()


def test_idempotency_conflicting_payload_rejection() -> None:
    ledger = GatewayRequestLedger()
    try:
        req_id = "req_conflict"
        payload1 = {"action": "delete", "target": "file_a"}
        payload2 = {"action": "delete", "target": "file_b"}

        ledger.check_or_record(
            request_id=req_id,
            client_identity_id="charlie",
            session_id="sess_3",
            method="chat.send",
            payload=payload1,
        )

        # Same request_id with different payload -> REQUEST_CONFLICT
        with pytest.raises(GatewayException) as exc:
            ledger.check_or_record(
                request_id=req_id,
                client_identity_id="charlie",
                session_id="sess_3",
                method="chat.send",
                payload=payload2,
            )
        assert exc.value.code == GatewayErrorCode.REQUEST_CONFLICT
    finally:
        ledger.close()


def test_idempotency_wal_persistence() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "idempotency.sqlite"
        l1 = GatewayRequestLedger(db_path)
        try:
            l1.check_or_record(
                request_id="req_persist",
                client_identity_id="dave",
                session_id="sess_4",
                method="chat.send",
                payload={"msg": "ping"},
            )
            l1.complete_request("req_persist", {"pong": True})
        finally:
            l1.close()

        # Reopen on same database
        l2 = GatewayRequestLedger(db_path)
        try:
            is_new, cached = l2.check_or_record(
                request_id="req_persist",
                client_identity_id="dave",
                session_id="sess_4",
                method="chat.send",
                payload={"msg": "ping"},
            )
            assert is_new is False
            assert cached == {"pong": True}
        finally:
            l2.close()
