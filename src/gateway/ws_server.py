"""Gateway WebSocket server — mirrors OpenClaw ``src/gateway/server/ws-connection/``."""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Awaitable

from jarvis_gateway_protocol import GatewayError, RPCResponse, RPCError
from jarvis_gateway_protocol.validators import validate_request
from .live_state import GLOBAL_GATEWAY_LIVE_STATE

_log = logging.getLogger("jarvis.gateway.ws_server")


class GatewayWSConnection:
    """Manages a single WebSocket client connection session.

    Accepts a send callable and optional connection id for testability.
    """

    def __init__(self, send_fn: Any, conn_id: str | None = None) -> None:
        if hasattr(send_fn, "send") and callable(getattr(send_fn, "send")):
            self._send = send_fn.send
        else:
            self._send = send_fn
        self.conn_id = conn_id or str(id(self))
        self._subscriptions: set[str] = set()
        self._subscription_callbacks: dict[str, Callable[[dict[str, Any]], Awaitable[None]]] = {}
        self.is_connected = False
        self.device_identity: dict[str, Any] | None = None
        self.role: str = "client"

    async def send_event(self, event: dict[str, Any]) -> None:
        """Send an event frame."""
        payload = json.dumps({"type": "event", **event})
        try:
            await self._send(payload)
        except Exception as e:
            _log.warning("ws %s: send_event failed: %s", self.conn_id, e)

    async def send_response(self, req_id: str, payload: Any = None, error: GatewayError | None = None) -> None:
        """Send a response frame."""
        if error is not None:
            resp = RPCResponse(id=req_id, error=error).to_dict()
        else:
            resp = RPCResponse(id=req_id, result=payload).to_dict()
        try:
            await self._send(json.dumps(resp))
        except Exception as e:
            _log.warning("ws %s: send_response failed: %s", self.conn_id, e)

    async def handle_handshake(self, raw_message: str, gateway_token: str) -> bool:
        """Process the mandatory first connect frame."""
        try:
            req_data = json.loads(raw_message)
            req, err = validate_request(req_data)
        except Exception:
            try:
                await self._send(json.dumps({"close": 1008, "reason": "Invalid JSON"}))
            except Exception:
                pass
            return False

        if err or req is None:
            try:
                await self._send(json.dumps({"close": 1008, "reason": "Invalid request format"}))
            except Exception:
                pass
            return False

        if req.method != "connect":
            try:
                await self._send(json.dumps({"close": 1008, "reason": "First frame must be connect"}))
            except Exception:
                pass
            return False

        auth = req.params.get("auth", {})
        token = auth.get("token") or auth.get("password")
        if token != gateway_token:
            await self.send_response(req.id, error=RPCError.auth_error("Invalid token"))
            # attempt to close if underlying send supports it
            try:
                await self._send(json.dumps({"close": 1008, "reason": "Unauthorized"}))
            except Exception:
                pass
            return False

        self.role = req.params.get("role", "client")
        self.device_identity = req.params.get("identity")

        # OpenClaw keeps the network session and channel state in the shared
        # live-state registry so policy checks and UI watchers can observe it.
        identity = self.device_identity or {}
        session_id = identity.get("session_id") or getattr(self, "conn_id", None)
        channel_id = identity.get("channel") or self.role
        metadata = {
            "role": self.role,
            "identity": identity,
            "conn_id": self.conn_id,
        }
        if session_id:
            GLOBAL_GATEWAY_LIVE_STATE.set_session_active(str(session_id), metadata)
        if channel_id:
            GLOBAL_GATEWAY_LIVE_STATE.set_channel_status(str(channel_id), True)

        # In OpenClaw, node pairing is validated here.
        # For now, if role is node and token matches, we accept.

        self.is_connected = True
        await self.send_response(req.id, payload={"status": "hello-ok"})
        return True

    async def handle_message(self, raw_message: str, rpc_handler: Callable[..., Any]) -> None:
        try:
            req_data = json.loads(raw_message)
            req, err = validate_request(req_data)
        except Exception:
            await self.send_response("", error=RPCError.parse_error())
            return

        if err or req is None:
            await self.send_response(req_data.get("id", ""), error=err)
            return

        # Built-in subscribe handling (no external handler required)
        if req.method == "subscribe":
            topic = req.params.get("topic")
            if not topic:
                await self.send_response(req.id, error=RPCError.invalid_params("missing 'topic'"))
                return

            async def _cb(event: dict[str, Any]) -> None:
                # event: { 'topic': topic, 'data': payload }
                frame: dict[str, Any] = {
                    "jsonrpc": "2.0",
                    "method": "gateway.event",
                    "params": {"topic": event.get("topic"), "data": event.get("data")},
                    "id": "",
                }
                try:
                    await self._send(json.dumps(frame))
                except Exception as e:
                    _log.debug("send to subscriber failed: %s", e)

            # Register subscription and return subscription acknowledgement
            GLOBAL_GATEWAY_LIVE_STATE.subscriptions.subscribe(topic, _cb)
            self._subscriptions.add(topic)
            self._subscription_callbacks[topic] = _cb
            await self._send(json.dumps(RPCResponse(id=req.id, result={"subscribed": topic}).to_dict()))
            return

        # Route standard RPC request via handler
        try:
            res = rpc_handler(req)  # Sync handler that returns RPCResponse or similar
            if hasattr(res, "to_dict"):
                await self._send(json.dumps(res.to_dict()))
            else:
                # If handler returns raw payload, wrap in RPCResponse
                await self._send(json.dumps(RPCResponse(id=req.id, result=res).to_dict()))
        except Exception as e:
            _log.error("ws %s: RPC handler failed: %s", self.conn_id, e)
            await self.send_response(req.id, error=RPCError.internal_error(str(e)))

    def on_close(self) -> None:
        for topic, callback in list(self._subscription_callbacks.items()):
            GLOBAL_GATEWAY_LIVE_STATE.subscriptions.unsubscribe(topic, callback)
            self._subscriptions.discard(topic)
        self._subscription_callbacks.clear()

        identity = self.device_identity or {}
        session_id = identity.get("session_id") or getattr(self, "conn_id", None)
        channel_id = identity.get("channel") or self.role
        if session_id:
            GLOBAL_GATEWAY_LIVE_STATE.remove_session(str(session_id))
        if channel_id:
            GLOBAL_GATEWAY_LIVE_STATE.set_channel_status(str(channel_id), False)


__all__ = ["GatewayWSConnection"]
