"""Gateway RPC dispatcher — routes JSON-RPC requests to JARVIS subsystems.

W4.2 — mirrors OpenClaw's ``src/gateway/server/rpc-handler.ts``.

The dispatcher registers one handler per ``RPCMethod``. The Gateway
routes all POST requests to ``/rpc`` through here. Each handler is a
plain callable ``(params: dict) -> Any`` that returns the JSON-safe
result or raises ``RPCDispatchError`` for method-level errors.

Design:
  - Additive: unknown methods return ``method_not_found`` per JSON-RPC 2.0.
  - No async: handlers are synchronous (agents run in background threads).
  - Handler registry is built once at startup; not hot-reloaded.

Registered method handlers are wired by ``GatewayRPCDispatcher.__init__``
via the ``handlers`` dict argument.

Canonical path: ``/rpc`` (POST only).
Request body: ``GatewayRequest`` JSON.
Response body: ``GatewayResponse`` JSON.
"""

from __future__ import annotations

import json
import logging
from typing import Any, cast

from jarvis_gateway_protocol import RPCError, RPCRequest, RPCResponse, GatewayRequest, GatewayResponse

_log = logging.getLogger("jarvis.gateway.rpc")


class RPCDispatchError(Exception):
    """Raised by an RPC handler to return a structured error to the caller."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


class RPCDispatcher:
    """Routes JSON-RPC calls to registered handler callables.

    Parameters
    ----------
    gateway : Any
        The Gateway instance to bind to. (For legacy HTTP routing support)
    handlers : dict[str, callable]
        Method name → handler function mapping.
    """

    def __init__(self, gateway: Any = None, handlers: dict[str, Any] | None = None) -> None:
        # Backwards-compatible constructor: allow passing handlers as first positional arg.
        if isinstance(gateway, dict) and handlers is None:
            handlers = cast(dict[str, Any], gateway)
            gateway = None
        handlers_value: dict[str, Any] = {} if handlers is None else handlers
        self.gateway = cast(Any, gateway)
        self._handlers: dict[str, Any] = dict(handlers_value)
        _log.info(
            "rpc_dispatcher: registered %d method(s): %s",
            len(self._handlers),
            sorted(self._handlers),
        )

    def register(self, method: str, handler: Any) -> None:
        """Register or replace a method handler at runtime."""
        self._handlers[method] = handler

    def has_method(self, method: str) -> bool:
        return method in self._handlers

    def registered_methods(self) -> list[str]:
        return sorted(self._handlers)

    def dispatch(self, request: RPCRequest | GatewayRequest) -> RPCResponse | GatewayResponse:
        """Dispatch one ``GatewayRequest`` or ``RPCRequest`` and return a protocol response.

        Never raises — errors are wrapped in gateway protocol errors.
        """
        # GatewayRequest (OpenClaw frame) uses `payload` in responses;
        # JSON-RPC (RPCRequest) uses `result`. Detect by presence of
        # `jsonrpc` attribute on the incoming request.
        # Prefer explicit GatewayRequest detection (has `type` == 'req').
        is_gateway = getattr(request, "type", "") == "req"
        is_rpc = hasattr(request, "jsonrpc") and not is_gateway
        handler = self._handlers.get(request.method)
        if handler is None:
            if is_rpc:
                return RPCResponse(id=request.id, error=RPCError.method_not_found(request.method))
            return GatewayResponse(id=request.id, error=RPCError.method_not_found(request.method))

        try:
            result = handler(request.params)
            if is_rpc:
                return RPCResponse(id=request.id, result=result)
            return GatewayResponse(id=request.id, payload=result)
        except RPCDispatchError as e:
            if is_rpc:
                return RPCResponse(id=request.id, error=RPCError(code=e.code, message=e.message, data=e.data))
            return GatewayResponse(id=request.id, error=RPCError(code=e.code, message=e.message, data=e.data))
        except Exception as e:  # noqa: BLE001
            _log.warning("rpc_dispatcher: %s raised: %s", request.method, e)
            if is_rpc:
                return RPCResponse(id=request.id, error=RPCError.internal_error(str(e)))
            return GatewayResponse(id=request.id, error=RPCError.internal_error(str(e)))

    def handle_http(
        self,
        http_method: str,
        path: str,
        body: bytes,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        """HTTP handler callable for ``Gateway.add_route``.

        POST /rpc → parse body as GatewayRequest, dispatch, return GatewayResponse.
        """
        if http_method != "POST":
            return RPCResponse(id="", error=RPCError(-32600, "RPC endpoint only accepts POST")).to_dict()

        # Parse body.
        try:
            raw: dict[str, Any] = json.loads(body.decode("utf-8")) if body else {}
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            return RPCResponse(id="", error=RPCError.parse_error(str(e))).to_dict()

        # Validate minimal JSON-RPC shape.
        method = raw.get("method", "")
        if not method:
            return RPCResponse(id=raw.get("id", ""), error=RPCError.invalid_request("missing 'method' field")).to_dict()

        request = RPCRequest(method=method, id=str(raw.get("id", "")), params=raw.get("params", {}))
        response = self.dispatch(request)
        return response.to_dict()


# ── Standard handler factories ─────────────────────────────────────────


def make_status_handler(gateway_version: str = "W4") -> Any:
    """Return a handler for ``admin.status``."""

    def _handler(params: dict[str, Any]) -> dict[str, Any]:
        return {"status": "ok", "version": gateway_version}

    return _handler


def make_plugins_list_handler(plugin_ids: list[str]) -> Any:
    """Return a handler for ``plugins.list``."""
    _ids = list(plugin_ids)

    def _handler(params: dict[str, Any]) -> dict[str, Any]:
        return {"plugins": _ids, "count": len(_ids)}

    return _handler


def make_channel_send_handler(send_fn: Any) -> Any:
    """Return a handler for ``channels.send``.

    ``send_fn(channel_id, conversation_id, text) -> None``
    """

    def _handler(params: dict[str, Any]) -> dict[str, Any]:
        channel_id = params.get("channel_id", "")
        conversation_id = params.get("conversation_id", "")
        text = params.get("text", "")
        if not channel_id or not text:
            raise RPCDispatchError(
                -32602, "channels.send requires channel_id and text", params
            )
        try:
            send_fn(channel_id, conversation_id, text)
            return {"ok": True}
        except Exception as e:  # noqa: BLE001
            raise RPCDispatchError(-32603, f"send failed: {e}") from e

    return _handler


def make_chat_handlers(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from .chat_handlers import make_chat_handlers as _make

    return _make(*args, **kwargs)


def make_cron_handlers(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from .cron_handlers import make_cron_handlers as _make

    return _make(*args, **kwargs)


def make_worktrees_handlers(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from .worktrees import make_worktrees_handlers as _make

    return _make(*args, **kwargs)


def make_sessions_handlers(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from .sessions_handlers import make_sessions_handlers as _make

    return _make(*args, **kwargs)


def make_tasks_handlers(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from .tasks_handlers import make_tasks_handlers as _make

    return _make(*args, **kwargs)


__all__ = [
    "GatewayRPCDispatcher",
    "RPCDispatcher",
    "RPCDispatchError",
    "make_channel_send_handler",
    "make_chat_handlers",
    "make_cron_handlers",
    "make_plugins_list_handler",
    "make_sessions_handlers",
    "make_status_handler",
    "make_tasks_handlers",
    "make_worktrees_handlers",
]

# Backwards compatibility: older callers expect `GatewayRPCDispatcher` name.
GatewayRPCDispatcher = RPCDispatcher

