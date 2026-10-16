"""Ingress RPC dispatcher and frame router for Track 3.4.

Enforces Invariant T34-01: Gateway is a protocol seam, not an authority.
Enforces Invariant T34-10: Reconnection and queries are strictly read-only.
Enforces Invariant T34-13: Mutating requests are protected by idempotency ledger.
"""

from __future__ import annotations

import datetime
import json
from typing import Any, Callable
import uuid

from jarvis_agent.gateway.errors import (
    GatewayError,
    GatewayErrorCode,
    GatewayException,
)
from jarvis_agent.gateway.idempotency import GatewayRequestLedger
from jarvis_agent.gateway.models import (
    MAX_REQUEST_BYTES,
    ClientIdentity,
    ConnectionContext,
    GatewayResponse,
    RPCMethod,
    RPCResponse,
)
from jarvis_agent.gateway.session_registry import SessionRegistry
from jarvis_agent.orchestration.models.user_turn import UserTurn
from jarvis_agent.orchestration.orchestration_runtime import OrchestrationRuntime


class GatewayDispatcher:
    """Dispatches incoming JSON-RPC and OpenClaw protocol frames to Track 3 subsystems."""

    def __init__(
        self,
        session_registry: SessionRegistry,
        request_ledger: GatewayRequestLedger,
        orchestration_runtime: OrchestrationRuntime | None = None,
        approval_handler: Callable[[str, dict[str, Any], ClientIdentity], dict[str, Any]]
        | None = None,
        cancellation_handler: Callable[[str, str, str, ClientIdentity], dict[str, Any]]
        | None = None,
        catchup_handler: Callable[[dict[str, Any], ClientIdentity], list[dict[str, Any]]]
        | None = None,
    ) -> None:
        self.session_registry = session_registry
        self.request_ledger = request_ledger
        self.orchestration_runtime = orchestration_runtime
        self.approval_handler = approval_handler
        self.cancellation_handler = cancellation_handler
        self.catchup_handler = catchup_handler

    def dispatch_raw(self, raw_frame: str, conn: ConnectionContext) -> str:
        """Parse raw JSON string frame, dispatch, and return serialized response."""
        if len(raw_frame.encode("utf-8")) > MAX_REQUEST_BYTES:
            err = GatewayError(
                code=GatewayErrorCode.FRAME_TOO_LARGE,
                message=f"Request frame exceeds max limit of {MAX_REQUEST_BYTES} bytes.",
            )
            return json.dumps(GatewayResponse(error=err).to_dict())

        try:
            parsed = json.loads(raw_frame)
        except Exception as e:
            err = GatewayError(
                code=GatewayErrorCode.PARSE_ERROR,
                message=f"Parse error: {e}",
            )
            return json.dumps(GatewayResponse(error=err).to_dict())

        if not isinstance(parsed, dict):
            err = GatewayError(
                code=GatewayErrorCode.INVALID_REQUEST,
                message="Request frame must be a JSON object.",
            )
            return json.dumps(GatewayResponse(error=err).to_dict())

        # Determine frame type: JSON-RPC 2.0 vs OpenClaw req
        is_jsonrpc = parsed.get("jsonrpc") == "2.0"
        req_id = str(parsed.get("id", ""))
        method = str(parsed.get("method", ""))
        params = parsed.get("params", {})
        if not isinstance(params, dict):
            params = {}

        try:
            res_payload = self.handle_request(
                req_id=req_id,
                method=method,
                params=params,
                conn=conn,
            )
            if is_jsonrpc:
                return json.dumps(RPCResponse(id=req_id, result=res_payload).to_dict())
            else:
                return json.dumps(GatewayResponse(id=req_id, payload=res_payload).to_dict())
        except GatewayException as ge:
            err = ge.to_gateway_error()
            if is_jsonrpc:
                return json.dumps(RPCResponse(id=req_id, error=err).to_dict())
            else:
                return json.dumps(GatewayResponse(id=req_id, error=err).to_dict())
        except Exception as ex:
            err = GatewayError(
                code=GatewayErrorCode.INTERNAL_ERROR,
                message=f"Internal gateway error: {ex}",
            )
            if is_jsonrpc:
                return json.dumps(RPCResponse(id=req_id, error=err).to_dict())
            else:
                return json.dumps(GatewayResponse(id=req_id, error=err).to_dict())

    def handle_request(
        self,
        req_id: str,
        method: str,
        params: dict[str, Any],
        conn: ConnectionContext,
    ) -> Any:
        """Route validated request parameters to specific method handler."""
        if not conn.authenticated_identity:
            raise GatewayException(
                code=GatewayErrorCode.AUTH_FAILED,
                message="Connection must be authenticated before issuing RPC requests.",
            )

        identity = conn.authenticated_identity

        # Check idempotency for mutating operations
        is_mutating = method in (
            RPCMethod.CHAT_SEND.value,
            RPCMethod.CONVERSATION_TURN.value,
            RPCMethod.EXEC_APPROVALS_RESPOND.value,
            RPCMethod.CONVERSATION_TURN_CANCEL.value,
            RPCMethod.SESSIONS_ABORT.value,
        )

        if is_mutating and req_id:
            sess_id = conn.assigned_session_id or "default"
            is_new, cached = self.request_ledger.check_or_record(
                request_id=req_id,
                client_identity_id=identity.user_id,
                session_id=sess_id,
                method=method,
                payload=params,
            )
            if not is_new:
                return cached

        try:
            result = self._route_method(method, params, conn, identity)
            if is_mutating and req_id:
                self.request_ledger.complete_request(req_id, result)
            return result
        except Exception as e:
            if is_mutating and req_id:
                self.request_ledger.fail_request(req_id, {"error": str(e)})
            raise

    def _route_method(
        self,
        method: str,
        params: dict[str, Any],
        conn: ConnectionContext,
        identity: ClientIdentity,
    ) -> Any:
        if method in (RPCMethod.CHAT_SEND.value, RPCMethod.CONVERSATION_TURN.value):
            return self._handle_chat_send(params, conn, identity)

        elif method in (RPCMethod.CONVERSATION_TURN_CANCEL.value, RPCMethod.SESSIONS_ABORT.value):
            return self._handle_cancellation(params, conn, identity)

        elif method in (RPCMethod.EXEC_APPROVALS_RESPOND.value, RPCMethod.APPROVAL_RESOLVE.value):
            return self._handle_approval_respond(params, conn, identity)

        elif method in (RPCMethod.SESSIONS_GET.value, "sessions.get"):
            return self._handle_sessions_get(params, conn, identity)

        elif method in ("events.catchup", "gateway.resume"):
            return self._handle_catchup(params, conn, identity)

        else:
            raise GatewayException(
                code=GatewayErrorCode.METHOD_NOT_FOUND,
                message=f"Gateway method '{method}' is not supported.",
            )

    def _handle_chat_send(
        self,
        params: dict[str, Any],
        conn: ConnectionContext,
        identity: ClientIdentity,
    ) -> dict[str, Any]:
        text = params.get("message") or params.get("text")
        if not text or not isinstance(text, str):
            raise GatewayException(
                code=GatewayErrorCode.INVALID_PARAMS,
                message="Parameter 'message' or 'text' is required and must be non-empty string.",
            )

        sess_id = conn.assigned_session_id or f"sess_{conn.connection_id}"
        sess = self.session_registry._sessions.get(sess_id)
        conv_id = sess.conversation_id if sess else f"conv_{conn.connection_id}"

        # Invariant T34-05: Server-Authoritative ResponseRoute
        route = self.session_registry.synthesize_response_route(
            connection_id=conn.connection_id,
            claimed_channel=params.get("channel"),
            thread_id=params.get("thread_id"),
            reply_to_message_id=params.get("reply_to_message_id"),
        )

        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
        turn_id = f"turn_{uuid.uuid4().hex[:8]}"
        req_id = f"req_{uuid.uuid4().hex[:8]}"

        user_turn = UserTurn(
            turn_id=turn_id,
            request_id=req_id,
            session_id=sess_id,
            conversation_id=conv_id,
            user_id=identity.user_id,
            timestamp_utc=now_utc,
            raw_text=text,
            clean_text=text.strip(),
            response_route=route,
        )

        task_id = f"task_{uuid.uuid4().hex[:8]}"
        if self.orchestration_runtime:
            state, decision, cmd = self.orchestration_runtime.process_turn(user_turn)
            if state and state.task:
                task_id = state.task.identity.task_id

        self.session_registry.register_task_to_session(task_id, sess_id)

        # Asynchronous acceptance model
        return {
            "accepted": True,
            "turnId": turn_id,
            "taskId": task_id,
            "conversationId": conv_id,
            "sessionId": sess_id,
        }

    def _handle_cancellation(
        self,
        params: dict[str, Any],
        conn: ConnectionContext,
        identity: ClientIdentity,
    ) -> dict[str, Any]:
        task_id = str(params.get("taskId") or params.get("task_id") or "")
        node_id = str(params.get("nodeId") or params.get("node_id") or "")
        reason = str(params.get("reason", "Client requested cancellation"))

        if not task_id:
            raise GatewayException(
                code=GatewayErrorCode.INVALID_PARAMS,
                message="Parameter 'taskId' is required for cancellation.",
            )

        if not self.session_registry.is_authorized_for_task(identity, task_id):
            raise GatewayException(
                code=GatewayErrorCode.SESSION_FORBIDDEN,
                message=f"Unauthorized to cancel task '{task_id}'.",
            )

        req_id = f"cancel_req_{uuid.uuid4().hex[:8]}"
        if self.cancellation_handler:
            self.cancellation_handler(task_id, node_id, reason, identity)

        return {
            "accepted": True,
            "cancellationRequestId": req_id,
            "taskId": task_id,
            "nodeId": node_id,
        }

    def _handle_approval_respond(
        self,
        params: dict[str, Any],
        conn: ConnectionContext,
        identity: ClientIdentity,
    ) -> dict[str, Any]:
        approval_id = str(params.get("approvalId") or params.get("approval_id") or "")
        if not approval_id:
            raise GatewayException(
                code=GatewayErrorCode.INVALID_PARAMS,
                message="Parameter 'approvalId' is required.",
            )

        if not self.approval_handler:
            return {"accepted": True, "approvalId": approval_id, "status": "APPROVED"}

        return self.approval_handler(approval_id, params, identity)

    def _handle_sessions_get(
        self,
        params: dict[str, Any],
        conn: ConnectionContext,
        identity: ClientIdentity,
    ) -> dict[str, Any]:
        sess_id = params.get("sessionId") or conn.assigned_session_id
        if not sess_id:
            raise GatewayException(
                code=GatewayErrorCode.INVALID_PARAMS,
                message="Parameter 'sessionId' is required.",
            )

        sess = self.session_registry._sessions.get(sess_id)
        if not sess:
            raise GatewayException(
                code=GatewayErrorCode.INVALID_PARAMS,
                message=f"Session '{sess_id}' not found.",
            )

        if not identity.can_access_session(sess_id):
            raise GatewayException(
                code=GatewayErrorCode.SESSION_FORBIDDEN,
                message="Forbidden access to session.",
            )

        return {
            "sessionId": sess.session_id,
            "conversationId": sess.conversation_id,
            "ownerUserId": sess.owner_user_id,
            "createdAtUtc": sess.created_at_utc,
            "activeTaskIds": sorted(list(sess.active_task_ids)),
        }

    def _handle_catchup(
        self,
        params: dict[str, Any],
        conn: ConnectionContext,
        identity: ClientIdentity,
    ) -> list[dict[str, Any]]:
        if not self.catchup_handler:
            return []
        return self.catchup_handler(params, identity)


__all__ = ["GatewayDispatcher"]
