"""Test suite for Track 3.4 Ingress RPC Dispatcher (Phase 3.4-E).

Validates:
1. Raw JSON-RPC 2.0 and OpenClaw frame dispatching.
2. Asynchronous acceptance model for chat.send.
3. Method-not-found and invalid-params error responses.
4. Unauthenticated connection rejection.
5. Idempotent replay of cached responses via GatewayRequestLedger.
6. Asynchronous cancellation submission.
"""

from __future__ import annotations

import json
from typing import Any

from jarvis_agent.gateway.dispatcher import GatewayDispatcher
from jarvis_agent.gateway.errors import GatewayErrorCode
from jarvis_agent.gateway.idempotency import GatewayRequestLedger
from jarvis_agent.gateway.models import (
    ClientIdentity,
    ConnectionContext,
)
from jarvis_agent.gateway.session_registry import SessionRegistry


def test_dispatcher_jsonrpc_chat_send_acceptance() -> None:
    registry = SessionRegistry()
    ledger = GatewayRequestLedger()
    dispatcher = GatewayDispatcher(session_registry=registry, request_ledger=ledger)

    conn = ConnectionContext("conn_1", "websocket", "2026-09-20T12:00:00Z")
    ident = ClientIdentity("alice", "desktop_app", "desktop")
    registry.register_connection(conn)
    registry.bind_connection_to_session("conn_1", "sess_alice", "conv_alice", ident)

    req = {
        "jsonrpc": "2.0",
        "id": "req_100",
        "method": "chat.send",
        "params": {"message": "Play jazz music"},
    }

    raw_resp = dispatcher.dispatch_raw(json.dumps(req), conn)
    resp = json.loads(raw_resp)

    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == "req_100"
    assert "result" in resp
    assert resp["result"]["accepted"] is True
    assert "turnId" in resp["result"]
    assert "taskId" in resp["result"]

    # Replay with same request_id and payload returns cached response
    raw_resp2 = dispatcher.dispatch_raw(json.dumps(req), conn)
    resp2 = json.loads(raw_resp2)
    assert resp2["result"]["turnId"] == resp["result"]["turnId"]

    ledger.close()


def test_dispatcher_openclaw_gateway_frame() -> None:
    registry = SessionRegistry()
    ledger = GatewayRequestLedger()
    dispatcher = GatewayDispatcher(session_registry=registry, request_ledger=ledger)

    conn = ConnectionContext("conn_2", "websocket", "2026-09-20T12:00:00Z")
    ident = ClientIdentity("bob", "web_client", "web")
    registry.register_connection(conn)
    registry.bind_connection_to_session("conn_2", "sess_bob", "conv_bob", ident)

    req = {
        "type": "req",
        "id": "gw_req_1",
        "method": "sessions.get",
        "params": {"sessionId": "sess_bob"},
    }

    raw_resp = dispatcher.dispatch_raw(json.dumps(req), conn)
    resp = json.loads(raw_resp)

    assert resp["type"] == "res"
    assert resp["id"] == "gw_req_1"
    assert resp["ok"] is True
    assert resp["payload"]["sessionId"] == "sess_bob"
    assert resp["payload"]["ownerUserId"] == "bob"

    ledger.close()


def test_dispatcher_error_handling() -> None:
    registry = SessionRegistry()
    ledger = GatewayRequestLedger()
    dispatcher = GatewayDispatcher(session_registry=registry, request_ledger=ledger)

    conn = ConnectionContext("conn_3", "websocket", "2026-09-20T12:00:00Z")
    registry.register_connection(conn)

    # 1. Unauthenticated request rejected
    req = {"jsonrpc": "2.0", "id": "1", "method": "chat.send", "params": {"message": "hi"}}
    raw_resp = dispatcher.dispatch_raw(json.dumps(req), conn)
    resp = json.loads(raw_resp)
    assert resp["error"]["code"] == GatewayErrorCode.AUTH_FAILED

    # Authenticate connection
    ident = ClientIdentity("charlie", "cli", "cli")
    registry.bind_connection_to_session("conn_3", "sess_c", "conv_c", ident)

    # 2. Method not found
    req_unknown = {"jsonrpc": "2.0", "id": "2", "method": "non_existent_method", "params": {}}
    raw_resp2 = dispatcher.dispatch_raw(json.dumps(req_unknown), conn)
    resp2 = json.loads(raw_resp2)
    assert resp2["error"]["code"] == GatewayErrorCode.METHOD_NOT_FOUND

    # 3. Invalid params
    req_bad_param = {"jsonrpc": "2.0", "id": "3", "method": "chat.send", "params": {}}
    raw_resp3 = dispatcher.dispatch_raw(json.dumps(req_bad_param), conn)
    resp3 = json.loads(raw_resp3)
    assert resp3["error"]["code"] == GatewayErrorCode.INVALID_PARAMS

    # 4. Parse error
    raw_resp4 = dispatcher.dispatch_raw("not valid json{", conn)
    resp4 = json.loads(raw_resp4)
    assert resp4["error"]["code"] == GatewayErrorCode.PARSE_ERROR

    ledger.close()


def test_dispatcher_cancellation_acceptance() -> None:
    registry = SessionRegistry()
    ledger = GatewayRequestLedger()
    cancelled_tasks: list[str] = []

    def cancel_cb(tid: str, nid: str, reason: str, ident: ClientIdentity) -> dict[str, Any]:
        cancelled_tasks.append(tid)
        return {"cancelled": True}

    dispatcher = GatewayDispatcher(
        session_registry=registry,
        request_ledger=ledger,
        cancellation_handler=cancel_cb,
    )

    conn = ConnectionContext("conn_4", "websocket", "2026-09-20T12:00:00Z")
    ident = ClientIdentity("dave", "desktop", "desktop")
    registry.register_connection(conn)
    registry.bind_connection_to_session("conn_4", "sess_dave", "conv_dave", ident)
    registry.register_task_to_session("task_999", "sess_dave")

    req = {
        "jsonrpc": "2.0",
        "id": "cancel_1",
        "method": "conversation.turn.cancel",
        "params": {"taskId": "task_999", "reason": "User clicked stop"},
    }

    raw_resp = dispatcher.dispatch_raw(json.dumps(req), conn)
    resp = json.loads(raw_resp)
    assert resp["result"]["accepted"] is True
    assert resp["result"]["taskId"] == "task_999"
    assert "cancellationRequestId" in resp["result"]
    assert cancelled_tasks == ["task_999"]

    ledger.close()
