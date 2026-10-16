"""Gateway server — mirrors OpenClaw's ``src/gateway/server/``.

Phase 3. The gateway is a WebSocket and HTTP server that:
  - Listens on a configurable host:port (default ``127.0.0.1:7433`` —
    matches the JARVIS lock-in from the migration plan).
  - Retries on EADDRINUSE (20 x 500ms — same as OpenClaw's
    ``EADDRINUSE_MAX_RETRIES`` x ``EADDRINUSE_RETRY_INTERVAL_MS``).
  - Routes WebSocket clients (Control plane, Nodes) via OpenClaw wire format.
  - Routes HTTP requests to plugin HTTP handlers (registered via
    ``api.register_http_handler({ path, handler, auth, match })``).
"""

from __future__ import annotations

import asyncio
import errno
import json
import logging
import secrets
import threading
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlparse

import websockets

from .ws_server import GatewayWSConnection
from .rpc_dispatcher import RPCDispatcher, RPCDispatchError
from .agent_runs import AgentRunService, Runner
from .chat_handlers import make_chat_handlers
from .cron_handlers import make_cron_handlers
from .sessions_handlers import make_sessions_handlers
from .tasks_handlers import make_tasks_handlers

if TYPE_CHECKING:
    pass

_log = logging.getLogger("src.gateway")

EADDRINUSE_MAX_RETRIES = 20
EADDRINUSE_RETRY_INTERVAL_MS = 500

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7433


class GatewayLockError(RuntimeError):
    """Raised when the gateway port is held by another process."""


class _ServerAddressProxy:
    """Expose the bound socket address for websockets.Server instances.

    The upstream server object does not reliably support arbitrary attribute
    assignment on all Python/websockets combinations, so we wrap it and keep the
    bound address on the proxy itself while forwarding lifecycle calls.
    """

    __slots__ = ("_server", "server_address")

    def __init__(self, server: Any, server_address: tuple[str, int] | tuple[str, int, int, int]) -> None:
        self._server = server
        self.server_address = server_address

    def __getattr__(self, name: str) -> Any:
        return getattr(self._server, name)

    def close(self) -> None:
        return self._server.close()

    def wait_closed(self) -> Any:
        return self._server.wait_closed()


@dataclass(frozen=True, slots=True)
class HttpRoute:
    path: str
    handler: Callable[..., Any]
    auth: str = "gateway"
    match: str = "exact"
    owner_id: str = ""


class Gateway:
    """In-process WebSocket and HTTP server."""

    def __init__(
        self,
        *,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        token_path: Path | None = None,
        agent_runner: Runner | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self._token_path = token_path or (Path.home() / ".jarvis" / "gateway.token")
        self._routes: list[HttpRoute] = []

        self._loop: asyncio.AbstractEventLoop | None = None
        self._server: Any = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

        # In OpenClaw, the RPC dispatcher handles standard JSON-RPC
        # or the new `GatewayRequest` typed format.
        self._agent_runs = AgentRunService(agent_runner or _unconfigured_agent_runner)
        self._dispatcher = RPCDispatcher(
            self,
            handlers={
                "agent": self._agent_runs.agent,
                "agent.run": self._agent_runs.agent,
                "agents.run": self._agent_runs.agent,
                "agent.wait": self._agent_runs.wait,
                "agents.wait": self._agent_runs.wait,
                "agent.abort": self._agent_runs.abort,
                "agents.abort": self._agent_runs.abort,
            },
        )
        # Register host gateway handlers for managed worktrees
        try:
            from .worktrees import make_worktrees_handlers

            for name, handler in make_worktrees_handlers().items():
                self._dispatcher.register(name, handler)
        except Exception:
            # Defensive: if worktrees wiring fails, gateway still starts.
            _log.exception("gateway: failed to register worktrees handlers")
        # Register sessions handlers (supports sessions.create with worktree option, list, get, resolve, search)
        try:
            from .sessions_handlers import make_sessions_handlers

            for name, handler in make_sessions_handlers().items():
                self._dispatcher.register(name, handler)
        except Exception:
            _log.exception("gateway: failed to register sessions handlers")
        # Register tasks handlers (tasks.list, tasks.get, tasks.cancel)
        try:
            from .tasks_handlers import make_tasks_handlers

            for name, handler in make_tasks_handlers().items():
                self._dispatcher.register(name, handler)
        except Exception:
            _log.exception("gateway: failed to register tasks handlers")
        # Register chat handlers (chat.send, chat.abort, chat.history)
        try:
            from .chat_handlers import make_chat_handlers

            for name, handler in make_chat_handlers(agent_runs=self._agent_runs).items():
                self._dispatcher.register(name, handler)
        except Exception:
            _log.exception("gateway: failed to register chat handlers")
        # Register cron handlers (cron.list, cron.add, cron.remove, cron.run)
        try:
            from .cron_handlers import make_cron_handlers

            for name, handler in make_cron_handlers().items():
                self._dispatcher.register(name, handler)
        except Exception:
            _log.exception("gateway: failed to register cron handlers")
        # Register health and status handlers (status, health, system.info)
        try:
            from .status_handlers import make_system_handlers

            for name, handler in make_system_handlers().items():
                self._dispatcher.register(name, handler)
        except Exception:
            _log.exception("gateway: failed to register status handlers")
        # Register config handlers (config.get, config.set, config.patch, config.schema)
        try:
            from .config_handlers import make_config_handlers

            for name, handler in make_config_handlers().items():
                self._dispatcher.register(name, handler)
        except Exception:
            _log.exception("gateway: failed to register config handlers")
        # Register tools handlers (tools.catalog, tools.effective)
        try:
            from .tools_handlers import make_tools_handlers

            for name, handler in make_tools_handlers().items():
                self._dispatcher.register(name, handler)
        except Exception:
            _log.exception("gateway: failed to register tools handlers")
        # Register models handlers (models.list)
        try:
            from .models_handlers import make_models_handlers

            for name, handler in make_models_handlers().items():
                self._dispatcher.register(name, handler)
        except Exception:
            _log.exception("gateway: failed to register models handlers")
        # Register skills handlers (skills.status, skills.list, skills.library.list)
        try:
            from .skills_handlers import make_skills_handlers

            for name, handler in make_skills_handlers().items():
                self._dispatcher.register(name, handler)
        except Exception:
            _log.exception("gateway: failed to register skills handlers")
        # Register channels handlers (channels.status, channels.list)
        try:
            from .channels_handlers import make_channels_handlers

            for name, handler in make_channels_handlers().items():
                self._dispatcher.register(name, handler)
        except Exception:
            _log.exception("gateway: failed to register channels handlers")
        # Register agents handlers (agents.list)
        try:
            from .agents_handlers import make_agents_handlers

            for name, handler in make_agents_handlers().items():
                self._dispatcher.register(name, handler)
        except Exception:
            _log.exception("gateway: failed to register agents handlers")
        # Register commands handlers (commands.list)
        try:
            from .commands_handlers import make_commands_handlers

            for name, handler in make_commands_handlers().items():
                self._dispatcher.register(name, handler)
        except Exception:
            _log.exception("gateway: failed to register commands handlers")

    @property
    def token(self) -> str:
        """Return the bearer token; generate + persist on first access."""
        if not self._token_path.exists():
            self._token_path.parent.mkdir(parents=True, exist_ok=True)
            token = secrets.token_urlsafe(32)
            self._token_path.write_text(token, encoding="utf-8")
            _log.info("gateway: generated new token at %s", self._token_path)
        return self._token_path.read_text(encoding="utf-8").strip()

    def add_route(self, route: HttpRoute) -> None:
        """Register an HTTP route."""
        with self._lock:
            self._routes.append(route)

    def add_raw(self, raw: dict[str, Any]) -> None:
        """Add a route from a raw plugin dict."""
        if "path" not in raw or "handler" not in raw:
            raise ValueError(f"http route missing path/handler: {raw!r}")
        route = HttpRoute(
            path=str(raw["path"]),
            handler=raw["handler"],
            auth=str(raw.get("auth", "gateway")),
            match=str(raw.get("match", "exact")),
            owner_id=str(raw.get("_owner_id", "")),
        )
        self.add_route(route)

    def add_gateway_method(self, method: str, handler: Any) -> None:
        """Register a gateway RPC method from a plugin or host integration."""
        if not method or not isinstance(method, str):
            raise ValueError("gateway method name must be a non-empty string")
        if not callable(handler):
            raise TypeError(
                f"gateway method handler must be callable; got {type(handler).__name__}"
            )

        def _handler(params: dict[str, Any]) -> Any:
            response: dict[str, Any] = {
                "called": False,
                "ok": False,
                "payload": None,
                "error": None,
            }

            def respond(ok: bool, payload: Any = None, error: Any = None) -> None:
                if response["called"]:
                    raise RuntimeError("respond() may only be called once")
                response["called"] = True
                response["ok"] = ok
                response["payload"] = payload
                response["error"] = error

            result = handler({"params": params, "respond": respond})
            if response["called"]:
                if response["ok"]:
                    return response["payload"]
                raise RuntimeError(response["error"] or response["payload"])
            return result

        with self._lock:
            self._dispatcher.register(method, _handler)

    def routes(self) -> list[HttpRoute]:
        with self._lock:
            return list(self._routes)

    def is_running(self) -> bool:
        return self._server is not None

    def start(self, *, retry_eaddrinuse: bool = True) -> None:
        """Start the gateway in a background thread."""
        if self._thread is not None:
            return

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop,
            args=(retry_eaddrinuse,),
            name="jarvis-gateway",
            daemon=True,
        )
        self._thread.start()

        # Wait until server is bound or thread dies
        while not self.is_running() and self._thread.is_alive():
            import time
            time.sleep(0.01)

        if not self.is_running():
            raise GatewayLockError(f"failed to start gateway on {self.host}:{self.port}")

    def _run_loop(self, retry_eaddrinuse: bool) -> None:
        if self._loop is None:
            return
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._async_start(retry_eaddrinuse))
            self._loop.run_forever()
        except Exception as e:
            _log.error("gateway: loop crashed: %s", e)

    async def _async_start(self, retry_eaddrinuse: bool) -> None:
        max_retries = EADDRINUSE_MAX_RETRIES if retry_eaddrinuse else 0
        last_err: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                self._server = await websockets.serve(
                    self._ws_handler,
                    self.host,
                    self.port,
                    process_request=self._process_http_request
                )
                break
            except OSError as e:
                last_err = e
                if e.errno == errno.EADDRINUSE and attempt < max_retries:
                    _log.info("gateway: port %d in use, retry %d/%d", self.port, attempt + 1, max_retries)
                    await asyncio.sleep(EADDRINUSE_RETRY_INTERVAL_MS / 1000.0)
                    continue
                if e.errno == errno.EADDRINUSE:
                    raise GatewayLockError(f"another gateway instance is already listening on ws://{self.host}:{self.port}", e) from e
                raise GatewayLockError(f"failed to bind gateway socket on ws://{self.host}:{self.port}: {e}", e) from e

        if self._server is None:
            raise GatewayLockError(f"could not bind gateway on {self.host}:{self.port}: {last_err}")

        # The websockets Server does not reliably expose a mutable
        # ``server_address`` attribute across Python/websockets variants.
        # Keep a stable bound-address snapshot on a thin proxy so both the
        # runtime and tests can inspect the actual socket without relying on
        # server-internal mutability.
        bound: tuple[str, int] | tuple[str, int, int, int] = (self.host, self.port)
        try:
            sockets = cast(list[Any], getattr(self._server, "sockets", None) or [])
            if sockets:
                socket = cast(Any, sockets[0])
                getsockname = getattr(socket, "getsockname", None)
                if callable(getsockname):
                    result = getsockname()
                    if isinstance(result, tuple):
                        result_tuple = cast(tuple[Any, ...], result)
                        if len(result_tuple) in (2, 4) and isinstance(result_tuple[0], str) and isinstance(result_tuple[1], int):
                            bound = cast(tuple[str, int] | tuple[str, int, int, int], result_tuple)
        except Exception:
            bound = (self.host, self.port)
        self._server = _ServerAddressProxy(self._server, bound)

        _log.info("gateway: listening on ws://%s:%d", self.host, self.port)

        try:
            import time
            from src.hooks import get_global_dispatcher, InternalHookEvent
            d = get_global_dispatcher()
            if d:
                await d.fire_and_wait(InternalHookEvent(
                    type="gateway",
                    action="startup",
                    session_key="gateway",
                    context={"host": self.host, "port": self.port},
                    timestamp=time.time(),
                ))
        except Exception as e:
            _log.warning("gateway: startup hooks failed: %s", e)

    def stop(self) -> None:
        """Stop the gateway cleanly."""
        try:
            import time
            from src.hooks import get_global_dispatcher, InternalHookEvent
            d = get_global_dispatcher()
            if d and self._loop and self.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    d.fire_and_wait(InternalHookEvent(
                        type="gateway",
                        action="shutdown",
                        session_key="gateway",
                        context={"reason": "stop"},
                        timestamp=time.time(),
                    )), 
                    self._loop
                )
                try:
                    future.result(timeout=5.0)
                except Exception as e:
                    _log.warning("gateway: shutdown hooks failed: %s", e)
        except Exception:
            pass

        if self._server is not None and self._loop is not None:
            self._server.close()
            # Wait for it to close
            future = asyncio.run_coroutine_threadsafe(self._server.wait_closed(), self._loop)
            try:
                future.result(timeout=2.0)
            except Exception:
                pass

            self._loop.call_soon_threadsafe(self._loop.stop)
            self._server = None

        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

        self._loop = None
        _log.info("gateway: stopped")

    async def _ws_handler(self, ws: Any) -> None:
        """Handle an incoming WebSocket connection."""
        conn = GatewayWSConnection(ws)
        _log.debug("gateway: ws %s connected", conn.conn_id)

        try:
            # 1. Mandatory Handshake
            try:
                first_msg = await ws.recv()
            except websockets.exceptions.ConnectionClosed:
                return

            if not await conn.handle_handshake(str(first_msg), self.token):
                return

            # 2. Main Event Loop
            async for raw_message in ws:
                await conn.handle_message(str(raw_message), self._dispatcher.dispatch)
        except Exception as e:
            _log.warning("gateway: ws %s error: %s", conn.conn_id, e)
        finally:
            conn.on_close()
            _log.debug("gateway: ws %s disconnected", conn.conn_id)

    def _process_http_request(self, connection: Any, request: Any) -> Any:
        """Intercept plain HTTP requests before WS upgrade."""
        # For websockets 12+, request is websockets.http11.Request
        # Check for WS upgrade
        headers = request.headers
        if headers.get("Upgrade", "").lower() == "websocket":
            return None # Proceed with WS upgrade

        # Extract basic info
        method = getattr(request, "method", "GET")
        path = getattr(request, "path", "/")

        # Websockets doesn't give us the HTTP body for POSTs easily in process_request,
        # but for simple JARVIS HTTP routes this is an acceptable fallback.
        body = b""

        # Convert headers to dict for our handle_request
        header_dict = dict(headers.items()) if hasattr(headers, "items") else {}

        status, response_payload = self.handle_request(method, path, body, header_dict)

        # Format response
        resp_headers: list[tuple[str, str]] = []

        if isinstance(response_payload, str):
            resp_body = response_payload.encode("utf-8")
            resp_headers.append(("Content-Type", "text/plain; charset=utf-8"))
        else:
            resp_body = json.dumps(response_payload).encode("utf-8")
            resp_headers.append(("Content-Type", "application/json"))

        resp_headers.append(("Content-Length", str(len(resp_body))))

        # We must return an http11.Response object
        try:
            from websockets.datastructures import Headers
            from websockets.http11 import Response
            return Response(status, "OK", Headers(resp_headers), resp_body)
        except ImportError:
            # fallback for older websockets versions
            return (status, resp_headers, resp_body)

    def handle_request(
        self, method: str, path: str, body: bytes, headers: dict[str, str]
    ) -> tuple[int, dict[str, Any] | str]:
        """Route a single HTTP request through the registered plugins."""
        norm_headers = {k.lower(): v for k, v in headers.items()}

        if path == "/health":
            return 200, {"status": "ok"}

        auth_header = norm_headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return 401, {"error": "missing bearer token"}
        if not secrets.compare_digest(auth_header[len("Bearer ") :].strip(), self.token):
            return 403, {"error": "invalid token"}

        route = self._match_route(method, path)
        if route is None:
            return 404, {"error": "no route", "path": path}

        try:
            raw_payload: Any = route.handler(method, path, body, headers)
            if not isinstance(raw_payload, dict | list | str):
                payload: dict[str, Any] | str = {"result": raw_payload}
            else:
                payload = cast("dict[str, Any] | str", raw_payload)
            return 200, payload
        except Exception as e:
            _log.warning("gateway: route %s raised: %s", route.path, e)
            return 500, {"error": str(e)}

    def _match_route(self, method: str, path: str) -> HttpRoute | None:
        parsed = urlparse(path)
        path_only = parsed.path
        for r in reversed(self.routes()):
            if r.match == "exact" and r.path == path_only:
                return r
        for r in reversed(self.routes()):
            if r.match == "prefix" and path_only.startswith(r.path):
                return r
        return None


__all__ = [
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "Gateway",
    "GatewayLockError",
    "HttpRoute",
    "RPCDispatcher",
    "RPCDispatchError",
    "make_chat_handlers",
    "make_cron_handlers",
    "make_sessions_handlers",
    "make_tasks_handlers",
]


def _unconfigured_agent_runner(
    params: dict[str, Any],
    abort: threading.Event,
    emit: Callable[[dict[str, Any]], None],
) -> dict[str, Any]:
    """Fail clearly until a host supplies its embedded runner."""
    raise RuntimeError("embedded agent runner is not configured")
