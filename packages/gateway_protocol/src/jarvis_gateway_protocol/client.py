"""JARVIS Gateway WebSocket Client — JSON-RPC 2.0 client for Port 7433.

Provides full duplex JSON-RPC 2.0 communication over WebSocket between
clients (Desktop HUD, CLI, TUI, Web Control UI) and the Gateway micro-kernel.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Any, Callable

import websockets

from .schema import RPCError

logger = logging.getLogger("jarvis.gateway.client")


class GatewayWSClient:
    """JSON-RPC 2.0 WebSocket client for the JARVIS Gateway."""

    def __init__(
        self,
        url: str = "ws://127.0.0.1:7433",
        token: str | None = None,
        role: str = "client",
        session_id: str = "desktop:hud:main",
        token_path: Path | None = None,
    ) -> None:
        self.url = url
        self.role = role
        self.session_id = session_id
        self._token_path = token_path or (Path.home() / ".jarvis" / "gateway.token")
        self._token = token
        self._ws: Any = None
        self._pending_requests: dict[str, asyncio.Future[Any]] = {}
        self._event_listeners: dict[str, list[Callable[[dict[str, Any]], Any]]] = {}
        self._listen_task: asyncio.Task[None] | None = None
        self._connected = False

    @property
    def token(self) -> str:
        if self._token:
            return self._token
        if self._token_path.exists():
            return self._token_path.read_text(encoding="utf-8").strip()
        return ""

    @property
    def is_connected(self) -> bool:
        return self._connected and self._ws is not None

    async def connect(self, timeout: float = 5.0) -> dict[str, Any]:
        """Connect to the gateway WebSocket and perform mandatory handshake."""
        if self.is_connected:
            return {"status": "already_connected"}

        self._ws = await asyncio.wait_for(websockets.connect(self.url), timeout=timeout)
        self._connected = True

        # Start background listener task before waiting for handshake reply
        self._listen_task = asyncio.create_task(self._listen_loop())

        # Perform JSON-RPC 2.0 handshake
        connect_id = f"connect-{uuid.uuid4().hex[:8]}"
        handshake_payload = {
            "jsonrpc": "2.0",
            "id": connect_id,
            "method": "connect",
            "params": {
                "auth": {"token": self.token},
                "role": self.role,
                "identity": {
                    "session_id": self.session_id,
                    "client": self.role,
                    "channel": "desktop",
                },
            },
        }

        fut: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._pending_requests[connect_id] = fut

        await self._ws.send(json.dumps(handshake_payload))
        result = await asyncio.wait_for(fut, timeout=timeout)
        logger.info("Connected and authenticated with JARVIS Gateway at %s", self.url)
        return result

    async def call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> Any:
        """Call an RPC method over the WebSocket connection and await the result."""
        if not self.is_connected or self._ws is None:
            raise ConnectionError("Not connected to JARVIS Gateway WebSocket")

        req_id = f"req-{uuid.uuid4().hex[:8]}"
        frame = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params or {},
        }

        fut: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._pending_requests[req_id] = fut

        await self._ws.send(json.dumps(frame))
        return await asyncio.wait_for(fut, timeout=timeout)

    async def dispatch(
        self,
        message: str,
        session_key: str | None = None,
        context: dict[str, Any] | None = None,
        wait: bool = False,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """Convenience method for agent.dispatch."""
        target_session = session_key or self.session_id
        params = {
            "sessionKey": target_session,
            "message": message,
            "context": context or {"agentId": "default"},
            "wait": wait,
        }
        res = await self.call("agent.dispatch", params, timeout=timeout)
        return res if isinstance(res, dict) else {"result": res}

    async def subscribe(
        self,
        topic: str,
        callback: Callable[[dict[str, Any]], Any] | None = None,
    ) -> dict[str, Any]:
        """Subscribe to a topic or event stream."""
        if callback:
            self.on_event(topic, callback)
        return await self.call("subscribe", {"topic": topic})

    async def unsubscribe(self, topic: str) -> dict[str, Any]:
        """Unsubscribe from a topic."""
        return await self.call("unsubscribe", {"topic": topic})

    def on_event(self, event_name: str, callback: Callable[[dict[str, Any]], Any]) -> None:
        """Register an event callback for push notifications and draft streaming."""
        listeners = self._event_listeners.setdefault(event_name, [])
        if callback not in listeners:
            listeners.append(callback)

    async def _listen_loop(self) -> None:
        """Receive incoming frames and dispatch responses and events."""
        try:
            async for raw in self._ws:
                try:
                    data = json.loads(raw)
                except Exception as exc:
                    logger.debug("Malformed JSON from gateway: %s", exc)
                    continue

                # 1. Response Frame (has 'id' and 'result' or 'error' or 'payload')
                req_id = str(data.get("id") or "")
                if req_id and req_id in self._pending_requests:
                    fut = self._pending_requests.pop(req_id)
                    if not fut.done():
                        if "error" in data and data["error"] is not None:
                            err = data["error"]
                            msg = (
                                err.get("message", "RPC Error")
                                if isinstance(err, dict)
                                else str(err)
                            )
                            code = err.get("code", -32603) if isinstance(err, dict) else -32603
                            fut.set_exception(RPCError(code=code, message=msg))
                        else:
                            # result or payload
                            res = data.get("result") if "result" in data else data.get("payload")
                            fut.set_result(res)
                    continue

                # 2. Event Frame (e.g. event.agent.draft, gateway.event)
                method = data.get("method") or data.get("event")
                params = data.get("params") if "params" in data else data.get("payload", {})

                if method:
                    # Notify specific listeners
                    listeners = list(self._event_listeners.get(method, []))
                    # Also notify wildcard or topic listeners
                    if method == "gateway.event" and isinstance(params, dict) and "topic" in params:
                        topic = params["topic"]
                        listeners.extend(self._event_listeners.get(topic, []))
                    listeners.extend(self._event_listeners.get("*", []))

                    for cb in listeners:
                        try:
                            if asyncio.iscoroutinefunction(cb):
                                asyncio.create_task(cb(params))
                            else:
                                cb(params)
                        except Exception as e:
                            logger.warning("Event listener %s failed: %s", method, e)
        except websockets.exceptions.ConnectionClosed:
            logger.debug("WebSocket connection to gateway closed")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug("Gateway listen loop exited: %s", e)
        finally:
            self._connected = False
            # Cancel any pending requests
            for fut in self._pending_requests.values():
                if not fut.done():
                    fut.set_exception(ConnectionError("Gateway connection terminated"))
            self._pending_requests.clear()

    async def close(self) -> None:
        """Close the WebSocket connection."""
        self._connected = False
        if self._listen_task is not None:
            self._listen_task.cancel()
            self._listen_task = None
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None


__all__ = ["GatewayWSClient"]
