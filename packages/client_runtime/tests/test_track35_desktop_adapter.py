"""Track 3.5 Desktop HUD Adapter Tests (D01-D12).

Validates:
- Thread-safe signal bridge (D01, D02)
- Non-blocking task view queries (D03)
- Chat turn submission (D04)
- Approval modal actions & stale protection (D05, D06, D07)
- Advisory cancellation submission (D08)
- Offline read-only enforcement (D09)
- Lifecycle signals mapping (D10)
- Timeline updates (D11)
- Clean teardown (D12)
"""

from __future__ import annotations

import datetime
from typing import Any
import pytest

from jarvis_client.adapters.desktop.hud_adapter import DesktopHudAdapter
from jarvis_client.auth.token_manager import TokenManager
from jarvis_client.connection.lifecycle import ConnectionState
from jarvis_client.connection.transport import LoopbackTransport
from jarvis_client.errors import OfflineError, StaleActionError
from jarvis_client.protocol.client import JarvisClient
from jarvis_client.state.client_view import NodeViewState


def _create_mock_client(is_connected: bool = True) -> JarvisClient:
    import json

    def _mock_gateway(raw: str) -> str:
        try:
            data = json.loads(raw)
            req_id = data.get("id", "")
            method = data.get("method", "")
            if method == "chat.send":
                return json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "accepted": True,
                            "requestId": req_id,
                            "turnId": "turn_123",
                            "taskId": "task_1",
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
                            "cancellationRequestId": "c_req_1",
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
            return json.dumps({"jsonrpc": "2.0", "id": req_id, "result": {"accepted": True}})
        except Exception:
            return ""

    transport = LoopbackTransport(gateway_receiver=_mock_gateway)
    token_mgr = TokenManager(token="tok_test_123", user_id="u1")
    client = JarvisClient(transport=transport, token_manager=token_mgr, client_id="desktop_hud")
    if is_connected:
        client.connect()
    return client


def test_d01_d02_signal_bridge_and_dispatch() -> None:
    client = _create_mock_client()
    adapter = DesktopHudAdapter(client)

    received_signals: list[dict[str, Any]] = []
    adapter.connect_signal("test_signal", lambda data: received_signals.append(data))

    adapter.emit_signal("test_signal", {"status": "ok", "value": 42})
    assert len(received_signals) == 1
    assert received_signals[0]["value"] == 42


def test_d03_get_current_task_view() -> None:
    client = _create_mock_client()
    adapter = DesktopHudAdapter(client)

    # Initially None
    assert adapter.get_current_task_view() is None

    # Populate view projection
    client.view_state.get_or_create_task("task_42", title="Desktop Work")
    client.view_state.active_task_id = "task_42"

    task_view = adapter.get_current_task_view()
    assert task_view is not None
    assert task_view.task_id == "task_42"
    assert task_view.title == "Desktop Work"


def test_d04_submit_user_chat() -> None:
    client = _create_mock_client()
    adapter = DesktopHudAdapter(client)

    res = adapter.submit_user_chat("Open calendar")
    assert res["accepted"]
    assert res["requestId"].startswith("req_")


def test_d05_submit_approval() -> None:
    client = _create_mock_client()
    adapter = DesktopHudAdapter(client)

    ok = adapter.submit_approval(
        approval_id="app_1",
        approved=True,
        expected_plan_revision=1,
        current_plan_revision=1,
        reason="Looks good",
    )
    assert ok


def test_d06_stale_approval_revision_advance_rejected() -> None:
    client = _create_mock_client()
    adapter = DesktopHudAdapter(client)

    # Current revision 2 > expected revision 1 raises StaleActionError (Invariant T35-10)
    with pytest.raises(StaleActionError):
        adapter.submit_approval(
            approval_id="app_stale",
            approved=True,
            expected_plan_revision=1,
            current_plan_revision=2,
        )


def test_d07_expired_approval_rejected() -> None:
    client = _create_mock_client()
    adapter = DesktopHudAdapter(client)

    past = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=10)
    ).isoformat()
    with pytest.raises(StaleActionError):
        adapter.submit_approval(
            approval_id="app_exp",
            approved=True,
            expected_plan_revision=1,
            current_plan_revision=1,
            expires_at_utc=past,
        )


def test_d08_submit_cancellation() -> None:
    client = _create_mock_client()
    adapter = DesktopHudAdapter(client)

    res = adapter.submit_cancellation(task_id="task_99", reason="User closed window")
    assert res["accepted"]
    assert res["taskId"] == "task_99"


def test_d09_offline_read_only_enforcement() -> None:
    client = _create_mock_client(is_connected=False)
    adapter = DesktopHudAdapter(client)

    # Must raise OfflineError (Invariant T35-18)
    with pytest.raises(OfflineError):
        adapter.submit_user_chat("Run action offline")

    with pytest.raises(OfflineError):
        adapter.submit_approval("app_off", True, 1, 1)

    with pytest.raises(OfflineError):
        adapter.submit_cancellation("task_off")


def test_d10_connection_lifecycle_signals() -> None:
    client = _create_mock_client()
    adapter = DesktopHudAdapter(client)

    events: list[dict[str, Any]] = []
    adapter.connect_signal("connection_changed", lambda data: events.append(data))

    client.lifecycle.transition_to(ConnectionState.RESUMING)
    assert len(events) >= 1
    assert events[-1]["newState"] == ConnectionState.RESUMING.value


def test_d11_timeline_node_state_readiness() -> None:
    client = _create_mock_client()
    adapter = DesktopHudAdapter(client)

    task = client.view_state.get_or_create_task("task_timeline")
    task.nodes["node_1"] = NodeViewState(node_id="node_1", title="Compile Source", status="RUNNING")

    tv = adapter.get_current_task_view("task_timeline")
    assert tv is not None
    assert "node_1" in tv.nodes
    assert tv.nodes["node_1"].status == "RUNNING"


def test_d12_adapter_teardown() -> None:
    client = _create_mock_client()
    adapter = DesktopHudAdapter(client)
    adapter.connect_signal("test", lambda x: None)

    client.disconnect()
    assert not client.lifecycle.is_connected
