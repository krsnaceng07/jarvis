"""Track 3.5 End-to-End Acceptance Tests (T35-E01 - T35-E07).

Validates:
- E2E Desktop HUD full turn execution flow (T35-E01)
- E2E Interactive action-bound approval resolution (T35-E02)
- E2E Multi-channel deduplication & route isolation (T35-E03)
- E2E Network interruption & catch-up replay resumption (T35-E04)
- E2E Multi-tab browser session multiplexing (T35-E05)
- E2E Headless CLI pipeline integration (T35-E06)
- E2E Advisory cancellation roundtrip (T35-E07)
"""

from __future__ import annotations

import json
from typing import Any

from jarvis_channels.transports.adapters.discord import DiscordTransportAdapter
from jarvis_channels.transports.adapters.telegram import TelegramTransportAdapter
from jarvis_channels.transports.deduplication import ChannelInboundDeduplicator
from jarvis_channels.transports.delivery import ChannelDeliveryTracker
from jarvis_client.adapters.cli.cli_adapter import CliAdapter
from jarvis_client.adapters.desktop.hud_adapter import DesktopHudAdapter
from jarvis_client.adapters.web.web_adapter import WebSessionAdapter
from jarvis_client.auth.token_manager import TokenManager
from jarvis_client.connection.transport import LoopbackTransport
from jarvis_client.protocol.client import JarvisClient
from jarvis_client.session.cursor import ResumeCursor
from jarvis_client.state.client_view import ViewFreshness


def _create_acceptance_client(
    client_id: str = "acc_client",
) -> tuple[JarvisClient, list[dict[str, Any]]]:
    server_calls: list[dict[str, Any]] = []

    def _mock_gateway(raw: str) -> str:
        data = json.loads(raw)
        server_calls.append(data)
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
                        "sessionId": f"sess_{client_id}",
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
                        "turnId": "turn_acc_1",
                        "taskId": "task_acc_100",
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
        elif method == "conversation.turn.cancel":
            return json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "accepted": True,
                        "cancellationRequestId": "c_req_acc_1",
                        "taskId": data.get("params", {}).get("taskId", ""),
                    },
                }
            )
        elif method == "events.catchup":
            return json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "replayed": 2,
                        "events": [
                            {
                                "id": "replayed_evt_1",
                                "event": "node.state_changed",
                                "category": "authoritative",
                                "sequence": {
                                    "globalSeq": 51,
                                    "aggregateVersion": 2,
                                    "connectionSeq": 1,
                                },
                                "payload": {
                                    "taskId": "task_acc_100",
                                    "nodeId": "n1",
                                    "newStatus": "RUNNING",
                                },
                            },
                            {
                                "id": "replayed_evt_2",
                                "event": "node.state_changed",
                                "category": "authoritative",
                                "sequence": {
                                    "globalSeq": 52,
                                    "aggregateVersion": 3,
                                    "connectionSeq": 2,
                                },
                                "payload": {
                                    "taskId": "task_acc_100",
                                    "nodeId": "n1",
                                    "newStatus": "COMPLETED",
                                },
                            },
                        ],
                    },
                }
            )

        return json.dumps({"jsonrpc": "2.0", "id": req_id, "result": {"accepted": True}})

    transport = LoopbackTransport(gateway_receiver=_mock_gateway)
    token_mgr = TokenManager(token="tok_acc_test", user_id="user_acceptance")
    client = JarvisClient(transport=transport, token_manager=token_mgr, client_id=client_id)
    client.connect()
    return client, server_calls


# ── T35-E01: Desktop HUD Turn Flow ────────────────────────────────────────


def test_t35_e01_desktop_hud_turn_flow() -> None:
    client, _ = _create_acceptance_client("desktop_client")
    hud = DesktopHudAdapter(client)

    # 1. User submits chat from HUD
    res = hud.submit_user_chat("Deploy production services")
    assert res["accepted"]
    assert res["taskId"] == "task_acc_100"

    # 2. Server streams Task Accepted & Plan
    e1 = json.dumps(
        {
            "id": "e_acc_1",
            "event": "task.created",
            "category": "authoritative",
            "sequence": {"globalSeq": 1, "aggregateVersion": 1, "connectionSeq": 1},
            "payload": {"taskId": "task_acc_100", "title": "Deploy production services"},
        }
    )
    client.transport.receive_from_server(e1)

    # 3. Server streams node execution progress
    e2 = json.dumps(
        {
            "id": "e_acc_2",
            "event": "node.scheduled",
            "category": "authoritative",
            "sequence": {"globalSeq": 2, "aggregateVersion": 2, "connectionSeq": 2},
            "payload": {
                "taskId": "task_acc_100",
                "nodeId": "node_deploy",
                "title": "Execute Terraform",
            },
        }
    )
    client.transport.receive_from_server(e2)

    # 4. Read view projection non-blockingly
    task_view = hud.get_current_task_view("task_acc_100")
    assert task_view is not None
    assert task_view.title == "Deploy production services"
    assert "node_deploy" in task_view.nodes


# ── T35-E02: Interactive Approval Flow ───────────────────────────────────


def test_t35_e02_interactive_approval_flow() -> None:
    client, _ = _create_acceptance_client("hud_approval")
    hud = DesktopHudAdapter(client)

    # Create active task with node requiring approval
    client.view_state.get_or_create_task("task_app_flow")
    client.view_state.active_task_id = "task_app_flow"

    e_app = json.dumps(
        {
            "id": "e_app_1",
            "event": "node.scheduled",
            "category": "authoritative",
            "sequence": {"globalSeq": 10, "aggregateVersion": 1, "connectionSeq": 1},
            "payload": {
                "taskId": "task_app_flow",
                "nodeId": "node_drop_db",
                "title": "Drop Database Schema",
                "requiresApproval": True,
                "approvalId": "app_db_drop_99",
            },
        }
    )
    client.transport.receive_from_server(e_app)

    # Operator approves with CAS plan revision check
    approved = hud.submit_approval(
        approval_id="app_db_drop_99",
        approved=True,
        expected_plan_revision=1,
        current_plan_revision=1,
        reason="Schema backup verified",
    )
    assert approved


# ── T35-E03: Multi-Channel Deduplication & Route Isolation ───────────────


def test_t35_e03_multi_channel_route_and_deduplication() -> None:
    dedup = ChannelInboundDeduplicator()
    tracker = ChannelDeliveryTracker()

    tg = TelegramTransportAdapter(deduplicator=dedup, tracker=tracker)
    disc = DiscordTransportAdapter(deduplicator=dedup, tracker=tracker)

    # Telegram message
    tg_raw = {
        "message": {
            "message_id": 901,
            "from": {"id": 12345},
            "chat": {"id": 12345},
            "text": "Status from TG",
        }
    }
    inbound_tg = tg.handle_inbound(tg_raw)
    assert inbound_tg is not None
    assert inbound_tg.conversation_id == "telegram:12345"

    # Discord message from same user ID integer has separate route isolation
    disc_raw = {
        "id": "disc_msg_901",
        "author": {"id": "12345", "bot": False},
        "channel_id": "disc_chan_1",
        "content": "Status from Discord",
    }
    inbound_disc = disc.handle_inbound(disc_raw)
    assert inbound_disc is not None
    assert inbound_disc.conversation_id == "discord:12345:disc_chan_1"

    # Re-sending exact same Telegram message is dropped by deduplicator
    inbound_tg_dup = tg.handle_inbound(tg_raw)
    assert inbound_tg_dup is None


# ── T35-E04: Socket Disconnect & Catch-up Replay ──────────────────────────


def test_t35_e04_disconnect_and_catchup_replay() -> None:
    client, server_calls = _create_acceptance_client("replay_client")

    # Set up active cursor at globalSeq 50
    assert client.session is not None
    cur = ResumeCursor(
        journal_id="events",
        global_seq=50,
        subscription_id=client.session.session_id,
    )
    client.cursor_store.save_cursor(cur)

    # Simulate abrupt drop & reconnection
    client._on_transport_disconnected("Wi-Fi drop")
    assert client.view_state.freshness == ViewFreshness.RECONNECTING

    # Client reconnects: automatically requests catchup from globalSeq 50
    client.connect()
    assert any(c.get("method") == "events.catchup" for c in server_calls)
    assert client.view_state.freshness == ViewFreshness.LIVE


# ── T35-E05: Multi-Tab Browser Coordination ───────────────────────────────


def test_t35_e05_multi_tab_browser_coordination() -> None:
    client, _ = _create_acceptance_client("web_multiplex")

    tab_overview = WebSessionAdapter(client, tab_id="tab_overview", origin="http://localhost:3000")
    tab_logs = WebSessionAdapter(client, tab_id="tab_logs", origin="http://localhost:3000")

    # State update on client is reflected across both tabs
    client.view_state.get_or_create_task("task_multi", title="Data Processing")
    client.view_state.active_task_id = "task_multi"

    state_overview = tab_overview.get_full_state()
    state_logs = tab_logs.get_full_state()

    assert state_overview["activeTaskId"] == "task_multi"
    assert state_logs["activeTaskId"] == "task_multi"
    assert state_overview["tabId"] == "tab_overview"
    assert state_logs["tabId"] == "tab_logs"


# ── T35-E06: Headless CLI Pipeline Integration ───────────────────────────


def test_t35_e06_headless_cli_pipeline_integration() -> None:
    client, _ = _create_acceptance_client("cli_pipeline")
    cli = CliAdapter(client)

    # 1. Dispatch chat
    chat_res = cli.send_chat_command("Trigger nightly build")
    assert chat_res["success"]

    # 2. Query status JSON
    status = cli.status_command()
    json_out = cli.format_json(status)
    parsed = json.loads(json_out)
    assert parsed["connected"]
    assert parsed["freshness"] == ViewFreshness.LIVE.value


# ── T35-E07: Advisory Cancellation Roundtrip ──────────────────────────────


def test_t35_e07_advisory_cancellation_roundtrip() -> None:
    client, _ = _create_acceptance_client("hud_cancel")
    hud = DesktopHudAdapter(client)

    res = hud.submit_cancellation(task_id="task_acc_100", reason="User pressed Stop")
    assert res["accepted"]
    assert res["cancellationRequestId"] == "c_req_acc_1"
    assert res["taskId"] == "task_acc_100"
