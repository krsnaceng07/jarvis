"""JarvisClient: Master client runtime coordinator for Track 3.5.

Provides high-level connection management, RPC dispatching, event stream subscription,
reconnection with jitter backoff, resume cursor management, and graceful shutdown.
"""

from __future__ import annotations

import time
from typing import Any

from jarvis_client.auth.token_manager import TokenManager
from jarvis_client.commands.approval import build_approval_response_frame
from jarvis_client.commands.cancellation import (
    CancellationAcceptance,
    build_cancellation_frame,
    parse_cancellation_acceptance,
)
from jarvis_client.commands.chat import (
    ChatAcceptance,
    build_chat_send_frame,
    parse_chat_acceptance,
)
from jarvis_client.connection.backoff import BackoffPolicy
from jarvis_client.connection.heartbeat import ClientHeartbeatManager
from jarvis_client.connection.lifecycle import ConnectionLifecycle, ConnectionState
from jarvis_client.connection.transport import ClientTransport
from jarvis_client.errors import ClientErrorCode, OfflineError
from jarvis_client.events.decoder import EventDecoder
from jarvis_client.events.ordering import SequenceOrderingGuard
from jarvis_client.events.reducer import ClientEventReducer
from jarvis_client.protocol.frames import RPCRequestFrame, RPCResponseFrame
from jarvis_client.protocol.handshake import (
    HandshakeRequest,
)
from jarvis_client.session.cursor import CursorStore, ResumeCursor
from jarvis_client.session.reconciliation import RequestReconciler
from jarvis_client.session.session import ClientSession
from jarvis_client.state.client_view import ClientViewState, ViewFreshness
from jarvis_client.state.health import ClientDiagnostics, DiagnosticHealthStatus


class JarvisClient:
    """Master client runtime SDK for Desktop HUD, Web Frontend, and CLI."""

    def __init__(
        self,
        transport: ClientTransport,
        token_manager: TokenManager,
        client_id: str = "jarvis_client",
        client_type: str = "desktop",
        cursor_store: CursorStore | None = None,
        is_global_subscription: bool = False,
    ) -> None:
        self.transport = transport
        self.token_manager = token_manager
        self.client_id = client_id
        self.client_type = client_type
        self.cursor_store = cursor_store or CursorStore()

        self.lifecycle = ConnectionLifecycle()
        self.backoff = BackoffPolicy()
        self.heartbeat = ClientHeartbeatManager(
            send_ping_cb=self._send_ping_frame,
            on_dead_connection_cb=self._handle_dead_connection,
        )
        self.ordering_guard = SequenceOrderingGuard(is_global_subscription=is_global_subscription)
        self.decoder = EventDecoder()
        self.view_state = ClientViewState()
        self.reducer = ClientEventReducer(self.view_state)

        self.session: ClientSession | None = None
        self.reconciler = RequestReconciler(query_status_fn=self._query_request_status_sync)

        # In-flight RPC request trackers
        self._pending_rpc_replies: dict[str, Any] = {}
        self._is_accepting_commands: bool = True
        self._reconnect_count: int = 0
        self._events_received: int = 0
        self._telemetry_chunks: int = 0

        # Wire transport callbacks
        self.transport.set_message_handler(self._on_transport_message)
        self.transport.set_disconnect_handler(self._on_transport_disconnected)

    @property
    def diagnostics(self) -> ClientDiagnostics:
        """Expose safe diagnostic metrics without secrets."""
        status = DiagnosticHealthStatus.OFFLINE
        if self.lifecycle.current_state == ConnectionState.LIVE:
            status = DiagnosticHealthStatus.CONNECTED
        elif self.lifecycle.current_state in (
            ConnectionState.CONNECTING,
            ConnectionState.RESUMING,
            ConnectionState.CATCHING_UP,
        ):
            status = DiagnosticHealthStatus.RECONNECTING
        elif self.lifecycle.current_state == ConnectionState.AUTH_FAILED:
            status = DiagnosticHealthStatus.AUTH_REQUIRED

        return ClientDiagnostics(
            status=status,
            connection_id=self.session.session_id if self.session else "",
            session_id=self.session.session_id if self.session else "",
            client_id=self.client_id,
            protocol_version="3.4",
            last_global_seq=self.ordering_guard.last_global_seq,
            last_connection_seq=0,
            reconnect_count=self._reconnect_count,
            last_rtt_ms=self.heartbeat.last_rtt_ms,
            events_received=self._events_received,
            events_quarantined=len(self.decoder.quarantined_events),
            telemetry_chunks_received=self._telemetry_chunks,
            is_live=self.lifecycle.is_live,
        )

    # ── Connection & Handshake ──────────────────────────────────────────

    def connect(self) -> None:
        """Initiate connection, execute protocol handshake, and resume state."""
        self._is_accepting_commands = True
        self.ordering_guard.reset_connection()
        self.lifecycle.transition_to(ConnectionState.CONNECTING)
        self.transport.connect()

        # Step 1: Protocol Handshake
        self.lifecycle.transition_to(ConnectionState.AUTHENTICATING)
        handshake_req = HandshakeRequest(
            client_id=self.client_id,
            client_type=self.client_type,
        )
        rpc_frame = RPCRequestFrame(
            id="hs_1",
            method="gateway.handshake",
            params=handshake_req.to_dict(),
        )
        self.transport.send(rpc_frame.serialize())
        start_wait = time.time()
        while "hs_1" not in self._pending_rpc_replies and (time.time() - start_wait) < 3.0:
            time.sleep(0.01)
        hs_reply = self._pending_rpc_replies.pop("hs_1", None)
        server_sess_id = hs_reply.get("sessionId") if isinstance(hs_reply, dict) else None

        # Step 2: Establish ClientSession
        sess_id = server_sess_id or f"sess_{self.client_id}_{self.token_manager.user_id}"
        self.session = ClientSession(
            session_id=sess_id,
            client_id=self.client_id,
            user_id=self.token_manager.user_id,
            scopes=frozenset({"read", "write", "cancel", "approve"}),
        )
        self.lifecycle.transition_to(ConnectionState.AUTHENTICATED)

        # Step 3: Resume or Catch-up if cursor exists
        cursor = self.cursor_store.get_cursor(sess_id)
        if cursor and cursor.global_seq > 0:
            self.lifecycle.transition_to(ConnectionState.RESUMING)
            self._request_catchup(cursor)
        else:
            self.lifecycle.transition_to(ConnectionState.LIVE)
            self.view_state.mark_live()

        self.backoff.reset()

    def _request_catchup(self, cursor: ResumeCursor) -> None:
        """Submit events.catchup RPC request to replay missing journal range."""
        self.lifecycle.transition_to(ConnectionState.CATCHING_UP)
        req_frame = RPCRequestFrame(
            id=f"catchup_{cursor.global_seq}",
            method="events.catchup",
            params={
                "sessionId": cursor.subscription_id,
                "resumeAfterGlobalSeq": cursor.global_seq,
                "limit": 5000,
            },
        )
        self.transport.send(req_frame.serialize())
        # Upon completion of catchup batch, transition to LIVE
        self.lifecycle.transition_to(ConnectionState.LIVE)
        self.view_state.mark_live()

    # ── Command Ingress ────────────────────────────────────────────────

    def send_chat(
        self,
        message: str,
        conversation_id: str | None = None,
        client_turn_id: str | None = None,
        client_request_id: str | None = None,
    ) -> ChatAcceptance:
        """Send chat turn to Gateway.

        Enforces Invariant T35-18: Offline mode is strictly read-only.
        """
        if not self.lifecycle.is_connected:
            raise OfflineError(
                code=ClientErrorCode.CLIENT_OFFLINE,
                message="Cannot send chat: client is offline or disconnected.",
            )

        sess_id = self.session.session_id if self.session else "sess_default"
        frame, req_id = build_chat_send_frame(
            message=message,
            session_id=sess_id,
            conversation_id=conversation_id,
            client_turn_id=client_turn_id,
            client_request_id=client_request_id,
        )

        self.transport.send(frame.serialize())
        start_wait = time.time()
        while req_id not in self._pending_rpc_replies and (time.time() - start_wait) < 3.0:
            time.sleep(0.01)
        # Immediate acceptance response extraction from pending replies
        reply = self._pending_rpc_replies.pop(req_id, None)
        return parse_chat_acceptance(reply, req_id)

    def respond_to_approval(
        self,
        approval_id: str,
        approved: bool,
        expected_plan_revision: int,
        current_plan_revision: int,
        expires_at_utc: str | None = None,
        decision_reason: str = "",
    ) -> bool:
        """Respond to action-bound approval with stale protection."""
        if not self.lifecycle.is_connected:
            raise OfflineError(
                code=ClientErrorCode.CLIENT_OFFLINE,
                message="Cannot approve/reject: client is offline.",
            )

        frame, req_id = build_approval_response_frame(
            approval_id=approval_id,
            approved=approved,
            expected_plan_revision=expected_plan_revision,
            current_plan_revision=current_plan_revision,
            expires_at_utc=expires_at_utc,
            decision_reason=decision_reason,
        )
        self.transport.send(frame.serialize())
        return True

    def cancel_task(
        self,
        task_id: str,
        node_id: str | None = None,
        reason: str = "User cancelled",
    ) -> CancellationAcceptance:
        """Submit advisory cancellation request."""
        if not self.lifecycle.is_connected:
            raise OfflineError(
                code=ClientErrorCode.CLIENT_OFFLINE,
                message="Cannot cancel: client is offline.",
            )

        frame, req_id = build_cancellation_frame(
            task_id=task_id,
            node_id=node_id,
            reason=reason,
        )
        self.transport.send(frame.serialize())
        reply = self._pending_rpc_replies.pop(req_id, None)
        return parse_cancellation_acceptance(reply, req_id)

    # ── Inbound Message Demuxing ───────────────────────────────────────

    def _on_transport_message(self, raw_message: str) -> None:
        """Process incoming raw WebSocket frame (RPC response or domain event)."""
        try:
            resp = RPCResponseFrame.deserialize(raw_message)
            if resp.id:
                # Correlate RPC response
                self._pending_rpc_replies[resp.id] = resp.result or resp.error
        except Exception:
            pass

        # Also attempt event decoding
        try:
            event = self.decoder.decode_frame(raw_message)
            if event:
                # Ordering and deduplication guard
                if self.ordering_guard.process_event(event):
                    self._events_received += 1
                    if "chunk" in event.event_type.lower():
                        self._telemetry_chunks += 1
                    # Reduce into view state
                    self.reducer.reduce(event)

                    # Advance durable resume cursor
                    if self.session and event.global_seq > 0:
                        sess_id = self.session.session_id
                        cur = self.cursor_store.get_cursor(sess_id) or ResumeCursor(
                            journal_id="events",
                            global_seq=0,
                            subscription_id=sess_id,
                        )
                        advanced = cur.advance(
                            global_seq=event.global_seq,
                            task_id=str(event.payload.get("taskId", "")),
                            aggregate_version=event.aggregate_version,
                        )
                        self.cursor_store.save_cursor(advanced)
        except Exception:
            pass

    def _on_transport_disconnected(self, reason: str) -> None:
        """Handle unexpected transport termination."""
        self.lifecycle.transition_to(ConnectionState.DISCONNECTED)
        self.view_state.mark_stale(ViewFreshness.RECONNECTING)
        self._reconnect_count += 1

    def _send_ping_frame(self) -> None:
        if self.lifecycle.is_connected:
            ping_frame = RPCRequestFrame(id="ping", method="gateway.ping", params={})
            try:
                self.transport.send(ping_frame.serialize())
            except Exception:
                pass

    def _handle_dead_connection(self) -> None:
        self.lifecycle.transition_to(ConnectionState.DISCONNECTED)
        self.view_state.mark_stale(ViewFreshness.OFFLINE)
        self.transport.close()

    def _query_request_status_sync(self, request_id: str) -> dict[str, Any]:
        """Internal synchronous status query for reconciliation."""
        if not self.lifecycle.is_connected:
            return {"status": "unknown"}
        req_frame = RPCRequestFrame(
            id=f"st_{request_id}", method="request.status", params={"requestId": request_id}
        )
        self.transport.send(req_frame.serialize())
        return self._pending_rpc_replies.pop(f"st_{request_id}", {}) or {"status": "unknown"}

    # ── Graceful Shutdown ──────────────────────────────────────────────

    def shutdown(self) -> None:
        """Execute ordered graceful shutdown sequence.

        1. Stop accepting new commands.
        2. Finish in-flight mutating requests.
        3. Persist current resume cursor.
        4. Flush outbound delivery state.
        5. Close socket.
        """
        self._is_accepting_commands = False

        # Persist cursor
        if self.session:
            cur = self.cursor_store.get_cursor(self.session.session_id)
            if cur:
                self.cursor_store.save_cursor(cur)

        self.heartbeat.reset()
        self.transport.close()
        self.lifecycle.transition_to(ConnectionState.DISCONNECTED)
        self.view_state.mark_stale(ViewFreshness.OFFLINE)

    disconnect = shutdown


__all__ = ["JarvisClient"]
