"""Track 3.5 Web Browser Adapter Tests (W01-W12).

Validates:
- Origin verification & CSWSH protection (W01, W02, W03)
- Multi-tab session multiplexing (W04, W05)
- Initial state hydration & freshness disclosure (W06)
- Subscriber notification on updates (W07, W12)
- Web chat turn ingress (W08)
- Approval modal actions & stale protection (W09)
- Advisory cancellation submission (W10)
- Offline read-only enforcement (W11)
"""

from __future__ import annotations

import json
from typing import Any
import pytest

from jarvis_client.adapters.web.web_adapter import (
    WebSessionAdapter,
    is_allowed_origin,
)
from jarvis_client.auth.token_manager import TokenManager
from jarvis_client.connection.transport import LoopbackTransport
from jarvis_client.errors import JarvisClientException, OfflineError, StaleActionError
from jarvis_client.protocol.client import JarvisClient
from jarvis_client.state.client_view import ViewFreshness


def _create_web_client(is_connected: bool = True) -> JarvisClient:
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
                            "turnId": "turn_web",
                            "taskId": "task_web_1",
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
                            "cancellationRequestId": "c_web_1",
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
    token_mgr = TokenManager(token="tok_web_secret", user_id="web_user_1")
    client = JarvisClient(transport=transport, token_manager=token_mgr, client_id="web_client")
    if is_connected:
        client.connect()
    return client


# ── W01-W03: Origin Verification & CSWSH Protection ───────────────────────


def test_w01_allowed_origins() -> None:
    assert is_allowed_origin("http://localhost:3000")
    assert is_allowed_origin("http://127.0.0.1:8080")
    assert is_allowed_origin("http://[::1]:5173")


def test_w02_unauthorized_cross_site_origin_rejected() -> None:
    assert not is_allowed_origin("https://evil-hacker.com")
    assert not is_allowed_origin("http://phishing.site:8080")

    client = _create_web_client()
    with pytest.raises(JarvisClientException):
        WebSessionAdapter(client=client, tab_id="tab_1", origin="https://attacker.site")


def test_w03_missing_origin_rejected() -> None:
    assert not is_allowed_origin(None)
    assert not is_allowed_origin("")


# ── W04-W05: Multi-Tab Session Multiplexing ───────────────────────────────


def test_w04_w05_multi_tab_session_multiplexing() -> None:
    client = _create_web_client()

    adapter_tab1 = WebSessionAdapter(
        client=client, tab_id="tab_alpha", origin="http://localhost:3000"
    )
    adapter_tab2 = WebSessionAdapter(
        client=client, tab_id="tab_beta", origin="http://localhost:3000"
    )

    ctx1 = adapter_tab1.tab_context
    ctx2 = adapter_tab2.tab_context

    assert ctx1.tab_id == "tab_alpha"
    assert ctx2.tab_id == "tab_beta"
    # Both tabs share the underlying client session
    assert ctx1.session_id == ctx2.session_id
    assert ctx1.is_active and ctx2.is_active


# ── W06: Hydration & Freshness ───────────────────────────────────────────


def test_w06_full_state_hydration() -> None:
    client = _create_web_client()
    adapter = WebSessionAdapter(client=client, tab_id="tab_hydra", origin="http://localhost:3000")

    client.view_state.get_or_create_task("task_web", title="Web Dashboard")
    client.view_state.active_task_id = "task_web"

    full_state = adapter.get_full_state()
    assert full_state["tabId"] == "tab_hydra"
    assert full_state["freshness"] == ViewFreshness.LIVE.value
    assert full_state["activeTaskId"] == "task_web"
    assert "task_web" in full_state["tasks"]


# ── W07 & W12: Subscription & Unsubscription ─────────────────────────────


def test_w07_w12_subscribe_and_unsubscribe() -> None:
    client = _create_web_client()
    adapter = WebSessionAdapter(client=client, tab_id="tab_sub", origin="http://localhost:3000")

    received_events: list[dict[str, Any]] = []

    def listener(evt: dict[str, Any]) -> None:
        received_events.append(evt)

    adapter.subscribe(listener)
    client.view_state.mark_degraded("Latency spike")
    assert len(received_events) >= 1
    assert received_events[-1]["freshness"] == ViewFreshness.DEGRADED.value

    # Unsubscribe
    adapter.unsubscribe(listener)
    client.view_state.mark_live()
    # Event count does not increase after unsubscribe
    assert len(received_events) == 1


# ── W08-W10: Commands ────────────────────────────────────────────────────


def test_w08_send_chat() -> None:
    client = _create_web_client()
    adapter = WebSessionAdapter(client=client, tab_id="tab_chat", origin="http://localhost:3000")

    res = adapter.send_chat("Show metrics")
    assert res["accepted"]
    assert res["requestId"].startswith("req_")


def test_w09_respond_to_approval() -> None:
    client = _create_web_client()
    adapter = WebSessionAdapter(client=client, tab_id="tab_app", origin="http://localhost:3000")

    ok = adapter.respond_to_approval("app_web", True, 1, 1, reason="Approved by web user")
    assert ok

    with pytest.raises(StaleActionError):
        adapter.respond_to_approval(
            "app_web", True, expected_plan_revision=1, current_plan_revision=2
        )


def test_w10_cancel_task() -> None:
    client = _create_mock = _create_web_client()
    adapter = WebSessionAdapter(client=client, tab_id="tab_cancel", origin="http://localhost:3000")

    res = adapter.cancel_task("task_web_1", reason="User closed tab")
    assert res["accepted"]
    assert res["taskId"] == "task_web_1"


# ── W11: Offline Rejection ───────────────────────────────────────────────


def test_w11_offline_rejection() -> None:
    client = _create_web_client(is_connected=False)
    adapter = WebSessionAdapter(client=client, tab_id="tab_off", origin="http://localhost:3000")

    with pytest.raises(OfflineError):
        adapter.send_chat("Offline web chat")

    with pytest.raises(OfflineError):
        adapter.respond_to_approval("app_1", True, 1, 1)

    with pytest.raises(OfflineError):
        adapter.cancel_task("task_1")
