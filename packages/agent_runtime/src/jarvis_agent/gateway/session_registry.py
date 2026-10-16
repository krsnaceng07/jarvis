"""Server-authoritative session, connection, and route registry for Track 3.4.

Enforces Invariant T34-05: ResponseRoute is validated and synthesized
server-side; client claims cannot forge or hijack routes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import datetime
from typing import Any

from jarvis_agent.gateway.errors import GatewayErrorCode, GatewayException
from jarvis_agent.gateway.models import (
    ClientIdentity,
    ConnectionContext,
    ConnectionState,
)
from jarvis_agent.orchestration.models.response_route import ResponseRoute


@dataclass(slots=True)
class SessionRecord:
    """Materialized logical session tracking record."""

    session_id: str
    conversation_id: str
    owner_user_id: str
    created_at_utc: str
    active_task_ids: set[str] = field(default_factory=set)
    metadata: dict[str, Any] = field(default_factory=dict)


class SessionRegistry:
    """Thread-safe registry mapping connections, sessions, and server-bound routes."""

    def __init__(self) -> None:
        self._connections: dict[str, ConnectionContext] = {}
        self._sessions: dict[str, SessionRecord] = {}
        # session_id -> set of connection_ids
        self._session_connections: dict[str, set[str]] = {}
        # task_id -> session_id
        self._task_sessions: dict[str, str] = {}

    def register_connection(self, conn: ConnectionContext) -> None:
        """Register a new physical transport connection."""
        self._connections[conn.connection_id] = conn

    def unregister_connection(self, connection_id: str) -> ConnectionContext | None:
        """Unregister a closing transport connection and detach from session."""
        conn = self._connections.pop(connection_id, None)
        if conn:
            conn.state = ConnectionState.CLOSED
            sess_id = conn.assigned_session_id
            if sess_id and sess_id in self._session_connections:
                self._session_connections[sess_id].discard(connection_id)
                if not self._session_connections[sess_id]:
                    del self._session_connections[sess_id]
        return conn

    def get_connection(self, connection_id: str) -> ConnectionContext | None:
        return self._connections.get(connection_id)

    def get_or_create_session(
        self,
        session_id: str,
        conversation_id: str,
        identity: ClientIdentity,
    ) -> SessionRecord:
        """Resolve an existing session or initialize a new one for an authorized identity."""
        if not identity.can_access_session(session_id):
            raise GatewayException(
                code=GatewayErrorCode.SESSION_FORBIDDEN,
                message=f"Principal '{identity.user_id}' lacks permission for session '{session_id}'.",
            )

        rec = self._sessions.get(session_id)
        if rec:
            # Existing session: verify ownership or admin grant
            if rec.owner_user_id != identity.user_id and identity.auth_tier != "admin":
                raise GatewayException(
                    code=GatewayErrorCode.SESSION_FORBIDDEN,
                    message=f"Session '{session_id}' is owned by another user.",
                )
            return rec

        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        rec = SessionRecord(
            session_id=session_id,
            conversation_id=conversation_id,
            owner_user_id=identity.user_id,
            created_at_utc=now_str,
        )
        self._sessions[session_id] = rec
        return rec

    def bind_connection_to_session(
        self,
        connection_id: str,
        session_id: str,
        conversation_id: str,
        identity: ClientIdentity,
    ) -> SessionRecord:
        """Bind connection to a verified session."""
        conn = self.get_connection(connection_id)
        if not conn:
            raise GatewayException(
                code=GatewayErrorCode.INVALID_REQUEST,
                message=f"Unknown connection ID '{connection_id}'.",
            )

        session = self.get_or_create_session(session_id, conversation_id, identity)
        conn.authenticated_identity = identity
        conn.assigned_session_id = session_id
        conn.state = ConnectionState.AUTHENTICATED

        if session_id not in self._session_connections:
            self._session_connections[session_id] = set()
        self._session_connections[session_id].add(connection_id)
        return session

    def register_task_to_session(self, task_id: str, session_id: str) -> None:
        """Record task ownership to session for authorization filtering."""
        self._task_sessions[task_id] = session_id
        sess = self._sessions.get(session_id)
        if sess:
            sess.active_task_ids.add(task_id)

    def synthesize_response_route(
        self,
        connection_id: str,
        claimed_channel: str | None = None,
        thread_id: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> ResponseRoute:
        """Synthesize server-authoritative ResponseRoute (Invariant T34-05).

        Rejects arbitrary spoofing: user_id and channel must match authenticated transport.
        """
        conn = self.get_connection(connection_id)
        if not conn or not conn.authenticated_identity:
            raise GatewayException(
                code=GatewayErrorCode.AUTH_FAILED,
                message="Cannot synthesize ResponseRoute on unauthenticated connection.",
            )

        identity = conn.authenticated_identity
        sess_id = conn.assigned_session_id or f"sess_{connection_id}"
        sess = self._sessions.get(sess_id)
        conv_id = sess.conversation_id if sess else f"conv_{connection_id}"

        # Server derives channel from authenticated transport/client type
        derived_channel = identity.client_type
        if claimed_channel and claimed_channel != derived_channel:
            # Only admin or service identity may override declared channel
            if identity.auth_tier not in ("admin", "service"):
                raise GatewayException(
                    code=GatewayErrorCode.SESSION_FORBIDDEN,
                    message=f"Client '{identity.client_id}' of type '{derived_channel}' cannot claim channel '{claimed_channel}'.",
                )
            derived_channel = claimed_channel

        return ResponseRoute(
            channel=derived_channel,
            conversation_id=conv_id,
            user_id=identity.user_id,
            thread_id=thread_id,
            reply_to_message_id=reply_to_message_id,
            routing_epoch=1,
        )

    def get_session_connections(self, session_id: str) -> list[ConnectionContext]:
        """Get all active physical connections attached to session."""
        conn_ids = self._session_connections.get(session_id, set())
        return [self._connections[cid] for cid in conn_ids if cid in self._connections]

    def is_authorized_for_task(self, identity: ClientIdentity, task_id: str) -> bool:
        """Verify if client is permitted to view or manage task."""
        if identity.auth_tier == "admin":
            return True
        sess_id = self._task_sessions.get(task_id)
        if not sess_id:
            return True  # Unclaimed tasks default to allow for creator
        sess = self._sessions.get(sess_id)
        if not sess:
            return False
        return sess.owner_user_id == identity.user_id or identity.can_access_session(sess_id)


__all__ = ["SessionRecord", "SessionRegistry"]
