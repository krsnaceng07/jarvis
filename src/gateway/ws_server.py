"""Gateway WebSocket server — JARVIS Gateway client session management."""

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

    Accepts a send callable, optional connection id, and optional gateway instance.
    """

    def __init__(self, send_fn: Any, conn_id: str | None = None, gateway: Any = None) -> None:
        if hasattr(send_fn, "send") and callable(getattr(send_fn, "send")):
            self._send = send_fn.send
        else:
            self._send = send_fn
        self.conn_id = conn_id or str(id(self))
        self.gateway = gateway
        self._subscriptions: set[str] = set()
        self._subscription_callbacks: dict[str, Callable[[dict[str, Any]], Awaitable[None]]] = {}
        self.is_connected = False
        self.is_jsonrpc: bool = True
        self.device_identity: dict[str, Any] | None = None
        self.role: str = "client"

    async def send_rpc_event(self, method: str, params: dict[str, Any]) -> None:
        """Send a standard JSON-RPC 2.0 event (notification) frame."""
        payload = json.dumps({"jsonrpc": "2.0", "method": method, "params": params})
        try:
            await self._send(payload)
        except Exception as e:
            _log.warning("ws %s: send_rpc_event failed: %s", self.conn_id, e)

    async def send_event(self, event: dict[str, Any]) -> None:
        """Send an event frame."""
        if "method" in event and "params" in event:
            await self.send_rpc_event(event["method"], event["params"])
            return
        payload = json.dumps({"type": "event", "jsonrpc": "2.0", **event})
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
            try:
                await self._send(json.dumps({"close": 1008, "reason": "Unauthorized"}))
            except Exception:
                pass
            return False

        self.role = req.params.get("role", "client")
        self.device_identity = req.params.get("identity")

        # Keep network session and channel state in the shared live-state registry
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

        self.is_connected = True
        await self.send_response(
            req.id,
            payload={
                "status": "hello-ok",
                "protocol": "jsonrpc-2.0",
                "version": "2026.10-LTS",
                "role": self.role,
            },
        )
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

        # Built-in subscribe handling
        if req.method == "subscribe":
            topic = req.params.get("topic")
            if not topic:
                await self.send_response(req.id, error=RPCError.invalid_params("missing 'topic'"))
                return

            async def _cb(event: dict[str, Any]) -> None:
                # event: { 'topic': topic, 'data': payload } or { 'method': ..., 'params': ... }
                if topic.startswith("event.") or event.get("method"):
                    evt_method = event.get("method") or topic
                    evt_params = event.get("data") if "data" in event else event.get("params", {})
                    frame: dict[str, Any] = {
                        "jsonrpc": "2.0",
                        "method": evt_method,
                        "params": evt_params,
                    }
                else:
                    frame = {
                        "jsonrpc": "2.0",
                        "method": "gateway.event",
                        "params": {"topic": event.get("topic", topic), "data": event.get("data", {})},
                        "id": "",
                    }
                try:
                    await self._send(json.dumps(frame))
                except Exception as e:
                    _log.debug("send to subscriber failed: %s", e)

            GLOBAL_GATEWAY_LIVE_STATE.subscriptions.subscribe(topic, _cb)
            self._subscriptions.add(topic)
            self._subscription_callbacks[topic] = _cb
            await self.send_response(req.id, payload={"subscribed": topic})
            return

        # Built-in unsubscribe handling
        if req.method == "unsubscribe":
            topic = req.params.get("topic")
            if topic and topic in self._subscriptions:
                cb = self._subscription_callbacks.pop(topic, None)
                if cb:
                    GLOBAL_GATEWAY_LIVE_STATE.subscriptions.unsubscribe(topic, cb)
                self._subscriptions.discard(topic)
            await self.send_response(req.id, payload={"unsubscribed": topic})
            return

        # Route standard RPC request via handler
        try:
            res = rpc_handler(req)
            if hasattr(res, "to_dict"):
                await self._send(json.dumps(res.to_dict()))
            else:
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

