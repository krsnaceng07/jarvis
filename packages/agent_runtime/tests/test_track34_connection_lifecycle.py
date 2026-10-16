"""Test suite for Track 3.4 Connection Lifecycle & Heartbeat Management (Phase 3.4-C).

Validates:
1. Ping tracking and missed pong increments.
2. Pong responses restoring HEALTHY connection state.
3. 3-strike half-open detection transitioning connection to CLOSING.
4. HeartbeatManager sweeping connections and unregistering dead sockets.
"""

from __future__ import annotations

from jarvis_agent.gateway.connection import ConnectionLifecycleTracker
from jarvis_agent.gateway.heartbeat import HeartbeatManager
from jarvis_agent.gateway.models import (
    ClientIdentity,
    ConnectionContext,
    ConnectionState,
)
from jarvis_agent.gateway.session_registry import SessionRegistry


def test_heartbeat_ping_pong_lifecycle() -> None:
    tracker = ConnectionLifecycleTracker(max_missed_pongs=3)
    conn = ConnectionContext("conn_1", "websocket", "2026-09-20T12:00:00Z")
    conn.state = ConnectionState.AUTHENTICATED

    # 1 missed ping -> SUSPECTED_DEAD
    tracker.record_ping_sent("conn_1", 100.0)
    assert tracker.evaluate_connection_health(conn, 105.0) == ConnectionState.SUSPECTED_DEAD

    # Pong received -> HEALTHY
    tracker.record_pong_received(conn, 106.0)
    assert conn.state == ConnectionState.HEALTHY
    assert conn.last_heartbeat_at_utc != ""
    assert tracker.evaluate_connection_health(conn, 107.0) == ConnectionState.HEALTHY


def test_heartbeat_half_open_three_strikes() -> None:
    registry = SessionRegistry()
    conn = ConnectionContext("conn_dead", "websocket", "2026-09-20T12:00:00Z")
    registry.register_connection(conn)
    ident = ClientIdentity("alice", "client_1", "web")
    registry.bind_connection_to_session("conn_dead", "sess_1", "conv_1", ident)

    pings_sent: list[str] = []
    closed_conns: list[str] = []

    mgr = HeartbeatManager(
        session_registry=registry,
        ping_sender=lambda c: pings_sent.append(c.connection_id),
        close_handler=lambda c: closed_conns.append(c.connection_id),
    )

    # Sweep 1: 1st ping
    mgr.check_all_connections(now=10.0)
    assert pings_sent == ["conn_dead"]
    assert conn.state == ConnectionState.AUTHENTICATED

    # Sweep 2: missed 1 -> suspected dead, 2nd ping sent
    mgr.check_all_connections(now=30.0)
    assert conn.state == ConnectionState.SUSPECTED_DEAD

    # Sweep 3: missed 2 -> still suspected dead, 3rd ping sent
    mgr.check_all_connections(now=50.0)
    assert conn.state == ConnectionState.SUSPECTED_DEAD

    # Sweep 4: missed 3 -> CLOSING -> unregisters from registry
    reaped = mgr.check_all_connections(now=70.0)
    assert reaped == ["conn_dead"]
    assert closed_conns == ["conn_dead"]
    assert registry.get_connection("conn_dead") is None
    assert len(registry.get_session_connections("sess_1")) == 0
