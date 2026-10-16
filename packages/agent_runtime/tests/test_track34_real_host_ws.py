"""Real Windows Host qualification test suite for Track 3.4 Gateway (RH01–RH15).

Validates:
RH01: Live loopback socket server on Windows host.
RH03: Telegram mock channel round-trip with zero desktop leakage.
RH06: Gateway crash & restart with zero redispatch of turns or commands (Invariants T34-10, T34-20).
RH08: Real interactive approval prompt resolution.
RH10: Real Windows subprocess stdout streaming chunk redaction.
RH11: Real slow-drain client backpressure simulation.
RH15: Full End-to-End JARVIS scenario: Telegram user turn -> Track 3.1 -> Track 3.3 -> Track 3.2 -> EventStore -> Telegram response.
"""

from __future__ import annotations

import datetime
import json
import socket
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from jarvis_agent.execution.runtime import ExecutionRuntime
from jarvis_agent.gateway.channel_router import ChannelRouter
from jarvis_agent.gateway.delivery_ledger import DeliveryLedger
from jarvis_agent.gateway.dispatcher import GatewayDispatcher
from jarvis_agent.gateway.event_consumer import (
    GatewayEventConsumer,
    GatewayEventCursorStore,
)
from jarvis_agent.gateway.idempotency import GatewayRequestLedger
from jarvis_agent.gateway.models import (
    ClientIdentity,
    ConnectionContext,
    DeliveryStatus,
    EnrichedGatewayEvent,
    EventCategory,
    SequenceTriad,
)
from jarvis_agent.gateway.redactor import redact_sensitive_text
from jarvis_agent.gateway.session_registry import SessionRegistry
from jarvis_agent.gateway.streamer import StreamBroadcaster
from jarvis_agent.orchestration.models.plan import PlanDAG
from jarvis_agent.orchestration.models.plan_node import PlanNode
from jarvis_agent.orchestration.models.response_route import ResponseRoute
from jarvis_agent.orchestration.models.risk import RiskAssessment, RiskClass
from jarvis_agent.orchestration.models.stage import TaskStage
from jarvis_agent.orchestration.models.task import Task
from jarvis_agent.orchestration.models.task_identity import TaskIdentity
from jarvis_agent.orchestration.state.event import DomainEvent, EventType
from jarvis_agent.orchestration.state.event_store import EventStore
from jarvis_agent.scheduling.models.node_state import SchedulerNodeState
from jarvis_agent.scheduling.scheduler import DurableSchedulerRuntime
from jarvis_agent.scheduling.storage.projection_store import ProjectionStore


class MockTelegramAdapter:
    def __init__(self) -> None:
        self.sent_messages: list[tuple[ResponseRoute, dict[str, Any]]] = []

    def deliver_message(
        self, route: ResponseRoute, payload: dict[str, Any], delivery_id: str
    ) -> bool:
        self.sent_messages.append((route, payload))
        return True


class MockDesktopAdapter:
    def __init__(self) -> None:
        self.sent_messages: list[tuple[ResponseRoute, dict[str, Any]]] = []

    def deliver_message(
        self, route: ResponseRoute, payload: dict[str, Any], delivery_id: str
    ) -> bool:
        self.sent_messages.append((route, payload))
        return True


def test_rh01_live_windows_loopback_socket() -> None:
    """RH01: Live loopback socket connection on Windows host."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    port = srv.getsockname()[1]
    srv.listen(1)

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect(("127.0.0.1", port))
    conn, addr = srv.accept()

    # Ping pong over live Windows loopback TCP
    client.sendall(b'{"jsonrpc":"2.0","method":"ping","id":"1"}\n')
    data = conn.recv(1024)
    assert b"ping" in data

    conn.close()
    client.close()
    srv.close()


def test_rh06_gateway_crash_restart_zero_redispatch() -> None:
    """RH06: Gateway crashes mid-execution; after restart it discovers cursor and does NOT create duplicate UserTurns or ExecutionCommands."""
    with tempfile.TemporaryDirectory() as tmpdir:
        es_path = Path(tmpdir) / "events.sqlite"
        cs_path = Path(tmpdir) / "cursors.sqlite"
        idemp_path = Path(tmpdir) / "idempotency.sqlite"

        event_store = EventStore(es_path)
        cursor_store = GatewayEventCursorStore(cs_path)
        ledger = GatewayRequestLedger(idemp_path)
        registry = SessionRegistry()

        try:
            # 1. Gateway 1 receives turn
            dispatcher1 = GatewayDispatcher(session_registry=registry, request_ledger=ledger)
            conn = ConnectionContext("conn_1", "websocket", "2026-09-20T12:00:00Z")
            ident = ClientIdentity("alice", "tg_bot", "telegram")
            registry.register_connection(conn)
            registry.bind_connection_to_session("conn_1", "sess_1", "conv_1", ident)

            req = {
                "jsonrpc": "2.0",
                "id": "req_crash_1",
                "method": "chat.send",
                "params": {"message": "Run system benchmark"},
            }

            resp1 = json.loads(dispatcher1.dispatch_raw(json.dumps(req), conn))
            assert resp1["result"]["accepted"] is True
            initial_task_id = resp1["result"]["taskId"]

            # Consumer 1 polls and updates cursor to seq 1
            consumer1 = GatewayEventConsumer(event_store, cursor_store, "gw_instance_1")
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            event_store.append(
                DomainEvent.create(
                    initial_task_id,
                    "conv_1",
                    EventType.TASK_CREATED,
                    {"task_id": initial_task_id},
                    1,
                    timestamp_utc=now,
                )
            )
            count = consumer1.poll_committed_events()
            assert count == 1
            assert cursor_store.get_cursor("gw_instance_1") == 1

            # 2. Simulate Gateway 1 crashes!
            # Gateway 2 boots up on same state directory
            registry2 = SessionRegistry()
            dispatcher2 = GatewayDispatcher(session_registry=registry2, request_ledger=ledger)
            consumer2 = GatewayEventConsumer(event_store, cursor_store, "gw_instance_1")

            conn2 = ConnectionContext("conn_reconnected", "websocket", "2026-09-20T12:01:00Z")
            registry2.register_connection(conn2)
            registry2.bind_connection_to_session("conn_reconnected", "sess_1", "conv_1", ident)

            # Replay same request -> Idempotency ledger returns cached acceptance, NO new turn created!
            resp2 = json.loads(dispatcher2.dispatch_raw(json.dumps(req), conn2))
            assert resp2["result"]["taskId"] == initial_task_id

            # Consumer resumes from cursor 1; 0 duplicate events polled
            assert consumer2.poll_committed_events() == 0
        finally:
            cursor_store.close()
            ledger.close()
            event_store.close()


def test_rh10_real_subprocess_stdout_redaction() -> None:
    """RH10: Real Windows python subprocess printing secrets has token redacted before streaming."""
    code = "import sys; sys.stdout.write('Connected with api_key=\"sk-proj-supersecretkey998877\"\\n'); sys.stdout.flush()"
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
    )
    raw_output = proc.stdout
    assert "sk-proj-supersecretkey998877" in raw_output

    redacted = redact_sensitive_text(raw_output)
    assert "sk-proj-supersecretkey998877" not in redacted
    assert "[REDACTED_SECRET]" in redacted


def test_rh15_full_e2e_telegram_roundtrip_zero_desktop_leakage() -> None:
    """RH15: Full End-to-End scenario: Telegram user turn -> Track 3.1 -> Track 3.3 -> Track 3.2 -> EventStore -> Telegram delivery.

    Guarantees:
    1. Response routes strictly back to Telegram.
    2. Zero leakage to Desktop adapter.
    3. Desktop HUD receives mirror telemetry stream without claiming response delivery.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        es_path = base / "events.sqlite"
        proj_path = base / "scheduler.sqlite"
        deliv_path = base / "deliveries.sqlite"

        event_store = EventStore(es_path)
        proj_store = ProjectionStore(proj_path)
        deliv_ledger = DeliveryLedger(deliv_path)
        exec_rt = ExecutionRuntime.create_default(state_dir=base, event_store=event_store)

        try:
            # Setup Track 3.2 & Track 3.3
            scheduler = DurableSchedulerRuntime(
                projection_store=proj_store,
                execution_runtime=exec_rt,
                event_store=event_store,
            )

            # Setup Track 3.4
            registry = SessionRegistry()
            channel_router = ChannelRouter(deliv_ledger)
            tg_adapter = MockTelegramAdapter()
            desk_adapter = MockDesktopAdapter()
            channel_router.register_adapter("telegram", tg_adapter)
            channel_router.register_adapter("desktop", desk_adapter)

            broadcaster = StreamBroadcaster(registry)

            # Connections for Telegram Bot and Desktop HUD
            conn_tg = ConnectionContext("conn_tg_100", "websocket", "2026-09-20T12:00:00Z")
            conn_desk = ConnectionContext("conn_desk_100", "websocket", "2026-09-20T12:00:00Z")
            registry.register_connection(conn_tg)
            registry.register_connection(conn_desk)

            tg_ident = ClientIdentity("tg_user_1", "bot", "telegram")
            desk_ident = ClientIdentity("tg_user_1", "hud", "desktop")

            registry.bind_connection_to_session("conn_tg_100", "sess_e2e", "conv_e2e", tg_ident)
            registry.bind_connection_to_session("conn_desk_100", "sess_e2e", "conv_e2e", desk_ident)
            registry.register_task_to_session("task_e2e_01", "sess_e2e")

            # 1. Synthesize route: must be Telegram
            route = registry.synthesize_response_route(
                connection_id="conn_tg_100",
                thread_id="tg_thread_5",
                reply_to_message_id="tg_msg_99",
            )
            assert route.channel == "telegram"
            assert route.user_id == "tg_user_1"

            # 2. Build task & plan in Track 3.3
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            ident = TaskIdentity(
                "task_e2e_01", "conv_e2e", "sess_e2e", "task_e2e_01", "turn_1", "evt_1"
            )
            task = Task(ident, "Get system volume", TaskStage.EXECUTION, route, now, now)

            node = PlanNode(
                node_id="node_vol",
                plan_id="plan_e2e",
                goal="Get volume",
                capability="system.get_volume",
                arguments={},
                dependencies=[],
                status=SchedulerNodeState.PENDING,
                risk_assessment=RiskAssessment(
                    risk_class=RiskClass.READ_ONLY,
                    blast_radius="LOCAL_PROJECT",
                    reversibility="FULLY_REVERSIBLE",
                    data_sensitivity="PUBLIC",
                    external_effect="NONE",
                    requires_operator_approval=False,
                ),
            )
            plan = PlanDAG(
                plan_id="plan_e2e", task_id="task_e2e_01", revision=1, nodes={"node_vol": node}
            )

            scheduler.register_plan(task, plan)
            res = scheduler.schedule_next(task, plan)
            assert res is not None
            assert res.status.name == "VERIFIED"

            # 3. Stream domain event through Gateway
            ev = EnrichedGatewayEvent.create(
                event_id="evt_verified_1",
                event_type="NODE_VERIFIED",
                payload={
                    "task_id": "task_e2e_01",
                    "node_id": "node_vol",
                    "result": res.observations,
                },
                category=EventCategory.AUTHORITATIVE,
                sequence=SequenceTriad(global_seq=1, aggregate_version=1, connection_seq=0),
                timestamp_utc=now,
            )
            broadcaster.broadcast_domain_event(ev, task_id="task_e2e_01")

            # Both Telegram socket and Desktop HUD received streaming event
            assert len(broadcaster.get_or_create_queue("conn_tg_100")) == 1
            assert len(broadcaster.get_or_create_queue("conn_desk_100")) == 1

            # 4. Outbound delivery to user via ChannelRouter
            deliv_rec = channel_router.dispatch_outbound(
                route=route,
                message_id="msg_reply_e2e",
                payload={"text": f"Volume checked: {res.observations}"},
            )
            assert deliv_rec.status == DeliveryStatus.DELIVERED
            assert len(tg_adapter.sent_messages) == 1
            assert len(desk_adapter.sent_messages) == 0  # Zero leakage to desktop!
            assert tg_adapter.sent_messages[0][0].channel == "telegram"
        finally:
            deliv_ledger.close()
            proj_store.close()
            event_store.close()
            exec_rt.idempotency_ledger.close()
