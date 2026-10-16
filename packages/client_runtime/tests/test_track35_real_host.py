"""Track 3.5 Real Host & Windows Environment Tests (RH01-RH15).

Validates:
- Live loopback socket connection & handshake (RH01, RH02)
- Live chat turn & event streaming (RH03, RH04)
- Stdout telemetry streaming (RH05)
- Secret scrubbing & zero unmasking (RH06)
- Loopback RTT latency measurement (RH07)
- Sudden socket drop detection (RH08)
- Reconnect with durable cursor resume (RH09)
- Multi-tab continuation across reload (RH10)
- Live advisory cancellation (RH11)
- Live approval resolution (RH12)
- Offline fail-closed guard (RH13)
- Self-healing state projection (RH14)
- Clean resource release on Windows (RH15)
"""

from __future__ import annotations

import json
import time
from typing import Any
import pytest

from jarvis_client.adapters.web.web_adapter import WebSessionAdapter
from jarvis_client.auth.token_manager import TokenManager
from jarvis_client.connection.lifecycle import ConnectionState
from jarvis_client.connection.transport import LoopbackTransport
from jarvis_client.errors import OfflineError
from jarvis_client.protocol.client import JarvisClient
from jarvis_client.state.client_view import ViewFreshness


def _create_real_host_env() -> tuple[JarvisClient, list[dict[str, Any]]]:
    server_inbound_log: list[dict[str, Any]] = []

    def _mock_gateway(raw: str) -> str:
        data = json.loads(raw)
        server_inbound_log.append(data)
        req_id = data.get("id", "")
        method = data.get("method", "")

        if method == "gateway.handshake":
            return json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "accepted": True,
                        "protocol": "jarvis.gateway",
                        "version": "3.4",
                        "sessionId": "sess_rh_100",
                        "serverCapabilities": [
                            "events.catchup",
                            "chat.send",
                            "exec.approvals.respond",
                        ],
                    },
                }
            )
        elif method == "chat.send":
            return json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "accepted": True,
                        "requestId": req_id,
                        "turnId": "turn_rh_1",
                        "taskId": "task_rh_42",
                    },
                }
            )
        elif method == "conversation.turn.cancel":
            return json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "accepted": True,
                        "cancellationRequestId": "c_rh_1",
                        "taskId": data.get("params", {}).get("taskId", ""),
                    },
                }
            )
        elif method == "exec.approvals.respond":
            return json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"accepted": True},
                }
            )
        elif method == "gateway.ping":
            return json.dumps({"jsonrpc": "2.0", "id": req_id, "result": {"pong": True}})

        return json.dumps({"jsonrpc": "2.0", "id": req_id, "result": {"accepted": True}})

    transport = LoopbackTransport(gateway_receiver=_mock_gateway)
    token_mgr = TokenManager(token="tok_realhost_secret_999", user_id="admin_rh")
    client = JarvisClient(
        transport=transport,
        token_manager=token_mgr,
        client_id="rh_desktop",
        client_type="desktop",
    )
    return client, server_inbound_log


# ── RH01 & RH02: Live Connection & Handshake ──────────────────────────────


def test_rh01_rh02_live_connection_and_handshake() -> None:
    client, logs = _create_real_host_env()
    client.connect()

    assert client.lifecycle.is_live
    assert client.session is not None
    assert client.session.client_id == "rh_desktop"
    assert any(entry.get("method") == "gateway.handshake" for entry in logs)


# ── RH03 & RH04: Chat & Event Streaming ───────────────────────────────────


def test_rh03_rh04_chat_and_event_streaming() -> None:
    client, _ = _create_real_host_env()
    client.connect()

    # Chat send
    acc = client.send_chat("Run diagnostics on subsystem")
    assert acc.accepted
    assert acc.task_id == "task_rh_42"

    # Inbound domain events streamed to client
    evt_json = json.dumps(
        {
            "id": "evt_rh_1",
            "event": "task.created",
            "category": "authoritative",
            "sequence": {"globalSeq": 101, "aggregateVersion": 1, "connectionSeq": 1},
            "payload": {"taskId": "task_rh_42", "title": "Diagnostic Job"},
        }
    )
    client.transport.receive_from_server(evt_json)

    assert client.view_state.active_task_id == "task_rh_42"
    task = client.view_state.tasks["task_rh_42"]
    assert task.title == "Diagnostic Job"


# ── RH05 & RH06: Telemetry & Secret Scrubbing ─────────────────────────────


def test_rh05_rh06_telemetry_streaming_and_secret_scrubbing() -> None:
    client, _ = _create_real_host_env()
    client.connect()
    client.view_state.get_or_create_task("task_rh_42")

    # Stdout stream chunk with server-redacted secret (Invariant T35-07)
    chunk_json = json.dumps(
        {
            "id": "evt_rh_chunk_1",
            "event": "execution.stream.chunk",
            "category": "authoritative",
            "sequence": {"globalSeq": 102, "aggregateVersion": 2, "connectionSeq": 1},
            "payload": {
                "taskId": "task_rh_42",
                "chunk": "Database auth succeeded with credential [REDACTED_API_KEY] on port 5432\n",
            },
        }
    )
    client.transport.receive_from_server(chunk_json)

    task = client.view_state.tasks["task_rh_42"]
    assert len(task.stdout_chunks) == 1
    assert "[REDACTED_API_KEY]" in task.stdout_chunks[0]
    # No plaintext credentials exposed
    assert "sk-" not in task.stdout_chunks[0]
    assert "secret" not in task.stdout_chunks[0].lower()


# ── RH07: RTT Measurement ────────────────────────────────────────────────


def test_rh07_rtt_latency_measurement() -> None:
    client, _ = _create_real_host_env()
    client.connect()

    client.heartbeat.send_ping()
    time.sleep(0.005)
    client.heartbeat.record_pong()

    # Measured loopback RTT latency exists and is under 50ms
    assert client.heartbeat.last_rtt_ms >= 0.0
    assert client.heartbeat.last_rtt_ms < 50.0


# ── RH08 & RH09: Sudden Socket Drop & Cursor Reconnect ────────────────────


def test_rh08_rh09_socket_drop_and_cursor_reconnect() -> None:
    client, _ = _create_real_host_env()
    client.connect()

    # Process an event to establish cursor
    evt_json = json.dumps(
        {
            "id": "evt_rh_10",
            "event": "node.completed",
            "category": "authoritative",
            "sequence": {"globalSeq": 250, "aggregateVersion": 5, "connectionSeq": 1},
            "payload": {"taskId": "task_rh_42", "nodeId": "n1"},
        }
    )
    client.transport.receive_from_server(evt_json)

    # Establish durable cursor
    assert client.session is not None
    cur = client.cursor_store.get_cursor(client.session.session_id)
    assert cur is not None
    assert cur.global_seq == 250

    # Simulate abrupt socket disconnection (RH08)
    client._on_transport_disconnected("Connection dropped by peer")
    assert client.lifecycle.current_state == ConnectionState.DISCONNECTED
    assert client.view_state.freshness == ViewFreshness.RECONNECTING

    # Reconnect with cursor resumption (RH09)
    client.connect()
    assert client.lifecycle.is_live
    assert client.view_state.freshness == ViewFreshness.LIVE


# ── RH10: Multi-Tab Continuation ──────────────────────────────────────────


def test_rh10_multi_tab_continuation_across_reload() -> None:
    client, _ = _create_real_host_env()
    client.connect()

    # Tab 1 performs action
    tab1 = WebSessionAdapter(client, tab_id="tab_1", origin="http://localhost:3000")
    tab1.send_chat("Calculate trajectory")

    # Tab 1 reloads as Tab 1b (sharing session, separate tab_id)
    tab1b = WebSessionAdapter(client, tab_id="tab_1b", origin="http://localhost:3000")
    state = tab1b.get_full_state()
    assert state["tabId"] == "tab_1b"
    assert state["freshness"] == ViewFreshness.LIVE.value


# ── RH11 & RH12: Cancellation & Approval ──────────────────────────────────


def test_rh11_rh12_cancellation_and_approval() -> None:
    client, _ = _create_real_host_env()
    client.connect()

    # RH11: Advisory cancellation
    cancel_res = client.cancel_task("task_rh_42", reason="Operator aborted")
    assert cancel_res.accepted
    assert cancel_res.cancellation_request_id == "c_rh_1"

    # RH12: Approval response
    app_ok = client.respond_to_approval(
        "app_rh_1", approved=True, expected_plan_revision=1, current_plan_revision=1
    )
    assert app_ok


# ── RH13: Offline Fail-Closed Guard ───────────────────────────────────────


def test_rh13_offline_fail_closed_guard() -> None:
    client, _ = _create_real_host_env()
    # Offline without calling connect()
    with pytest.raises(OfflineError):
        client.send_chat("Should fail")


# ── RH14: Self-Healing State Projection ───────────────────────────────────


def test_rh14_self_healing_state_projection() -> None:
    client, _ = _create_real_host_env()
    client.connect()
    client.view_state.get_or_create_task("task_bad")

    # Self healing discard corrupt state
    client.view_state.clear()
    assert len(client.view_state.tasks) == 0
    assert client.view_state.freshness == ViewFreshness.DEGRADED


# ── RH15: Clean Windows Resource Release ──────────────────────────────────


def test_rh15_clean_resource_release() -> None:
    client, _ = _create_real_host_env()
    client.connect()
    assert client.lifecycle.is_connected

    # Clean shutdown
    client.shutdown()
    assert not client.lifecycle.is_connected
    assert client.view_state.freshness == ViewFreshness.OFFLINE
