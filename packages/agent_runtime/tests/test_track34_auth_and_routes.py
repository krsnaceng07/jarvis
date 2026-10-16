"""Test suite for Track 3.4 Authentication, Route Binding & Session Registry (Phase 3.4-B).

Validates:
1. Credential verification, token hashing, expiration, and revocation.
2. Sliding window rate limiting per identity and method.
3. Multi-session registration and access isolation.
4. Server-authoritative ResponseRoute synthesis (Invariant T34-05) rejecting channel spoofing.
5. Multi-connection fan-out mapping per session.
"""

from __future__ import annotations

import datetime
import pytest

from jarvis_agent.gateway.auth import CredentialStore, SlidingWindowRateLimiter
from jarvis_agent.gateway.errors import GatewayErrorCode, GatewayException
from jarvis_agent.gateway.models import (
    ClientIdentity,
    ConnectionContext,
)
from jarvis_agent.gateway.session_registry import SessionRegistry


def test_credential_store_lifecycle() -> None:
    store = CredentialStore()
    cred = store.register_credential(
        raw_token="secret_token_123",
        user_id="user_alice",
        client_type="desktop",
        auth_tier="admin",
        scopes=frozenset(["read", "write", "admin"]),
    )
    assert cred.user_id == "user_alice"

    # Successful authentication
    ident = store.authenticate("secret_token_123")
    assert ident.user_id == "user_alice"
    assert ident.auth_tier == "admin"
    assert ident.has_scope("admin")

    # Invalid token rejection
    with pytest.raises(GatewayException) as exc:
        store.authenticate("wrong_token")
    assert exc.value.code == GatewayErrorCode.AUTH_FAILED

    # Revocation
    store.revoke_credential(cred.token_hash)
    with pytest.raises(GatewayException) as exc2:
        store.authenticate("secret_token_123")
    assert exc2.value.code == GatewayErrorCode.AUTH_FAILED


def test_credential_expiration() -> None:
    store = CredentialStore()
    past_time = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=10)
    ).isoformat()
    store.register_credential(
        raw_token="expired_token",
        user_id="user_bob",
        client_type="web",
        expires_at_utc=past_time,
    )
    with pytest.raises(GatewayException) as exc:
        store.authenticate("expired_token")
    assert exc.value.code == GatewayErrorCode.AUTH_FAILED


def test_rate_limiter_sliding_window() -> None:
    limiter = SlidingWindowRateLimiter(default_limit=3, window_seconds=1.0)
    # 3 allowed
    limiter.check_and_record("user_alice", "chat.send")
    limiter.check_and_record("user_alice", "chat.send")
    limiter.check_and_record("user_alice", "chat.send")

    # 4th in same window blocked
    with pytest.raises(GatewayException) as exc:
        limiter.check_and_record("user_alice", "chat.send")
    assert exc.value.code == GatewayErrorCode.RATE_LIMITED

    # Other method or other user unaffected
    limiter.check_and_record("user_alice", "sessions.get")
    limiter.check_and_record("user_bob", "chat.send")


def test_server_authoritative_response_route_synthesis() -> None:
    registry = SessionRegistry()
    conn = ConnectionContext(
        connection_id="conn_tg_1",
        transport_type="websocket",
        connected_at_utc="2026-09-20T12:00:00Z",
    )
    registry.register_connection(conn)

    ident = ClientIdentity(
        user_id="tg_user_99",
        client_id="bot_tg",
        client_type="telegram",
        auth_tier="user",
    )
    registry.bind_connection_to_session("conn_tg_1", "sess_tg_10", "conv_tg_10", ident)

    # Valid route synthesis deriving channel and user from server-verified identity
    route = registry.synthesize_response_route(
        connection_id="conn_tg_1",
        thread_id="thread_42",
        reply_to_message_id="msg_101",
    )
    assert route.channel == "telegram"
    assert route.user_id == "tg_user_99"
    assert route.conversation_id == "conv_tg_10"
    assert route.thread_id == "thread_42"
    assert route.reply_to_message_id == "msg_101"

    # Invariant T34-05: Non-admin client cannot spoof channel (e.g. claim desktop)
    with pytest.raises(GatewayException) as exc:
        registry.synthesize_response_route(
            connection_id="conn_tg_1",
            claimed_channel="desktop",
        )
    assert exc.value.code == GatewayErrorCode.SESSION_FORBIDDEN


def test_multi_session_isolation_and_connection_mapping() -> None:
    registry = SessionRegistry()
    conn1 = ConnectionContext("conn_1", "websocket", "2026-09-20T12:00:00Z")
    conn2 = ConnectionContext("conn_2", "websocket", "2026-09-20T12:00:00Z")
    conn3 = ConnectionContext("conn_3", "websocket", "2026-09-20T12:00:00Z")
    registry.register_connection(conn1)
    registry.register_connection(conn2)
    registry.register_connection(conn3)

    user_a = ClientIdentity("alice", "client_a", "web", "user")
    user_b = ClientIdentity("bob", "client_b", "web", "user")

    # Conn 1 and 2 join Alice's session
    registry.bind_connection_to_session("conn_1", "sess_alice", "conv_a", user_a)
    registry.bind_connection_to_session("conn_2", "sess_alice", "conv_a", user_a)
    # Conn 3 joins Bob's session
    registry.bind_connection_to_session("conn_3", "sess_bob", "conv_b", user_b)

    alice_conns = registry.get_session_connections("sess_alice")
    assert len(alice_conns) == 2
    assert {c.connection_id for c in alice_conns} == {"conn_1", "conn_2"}

    # Bob cannot bind to Alice's session
    conn4 = ConnectionContext("conn_4", "websocket", "2026-09-20T12:00:00Z")
    registry.register_connection(conn4)
    with pytest.raises(GatewayException) as exc:
        registry.bind_connection_to_session("conn_4", "sess_alice", "conv_a", user_b)
    assert exc.value.code == GatewayErrorCode.SESSION_FORBIDDEN

    # Unregistering cleanly detaches from session
    registry.unregister_connection("conn_1")
    alice_conns_after = registry.get_session_connections("sess_alice")
    assert len(alice_conns_after) == 1
    assert alice_conns_after[0].connection_id == "conn_2"
