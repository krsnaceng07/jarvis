"""Gateway HTTP server — mirrors OpenClaw's ``src/gateway/server/``.

Phase 3. The gateway is a small stdlib HTTP server that:
  - Listens on a configurable host:port (default ``127.0.0.1:7433`` —
    matches the JARVIS lock-in from the migration plan).
  - Retries on EADDRINUSE (20 x 500ms — same as OpenClaw's
    ``EADDRINUSE_MAX_RETRIES`` x ``EADDRINUSE_RETRY_INTERVAL_MS``).
  - Raises ``GatewayLockError`` when the port is held by another
    process (the OpenClaw diagnostic that powers
    ``jarvis doctor``).
  - Routes requests to plugin HTTP handlers (registered via
    ``api.register_http_handler({ path, handler, auth, match })``).
  - Validates a shared bearer token from
    ``~/.jarvis/gateway.token`` (auto-generated on first start).

The gateway is a Phase 3 port, not a full OpenClaw rewrite. We
keep the surface small (no websockets, no admin UI, no plugin
reload) and let plugins register their own HTTP routes for
LLM-facing endpoints.
"""

from __future__ import annotations

import errno
import json
import logging
import secrets
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlparse

if TYPE_CHECKING:
    from collections.abc import Callable

_log = logging.getLogger("src.gateway")

# Mirror OpenClaw's retry constants.
EADDRINUSE_MAX_RETRIES = 20
EADDRINUSE_RETRY_INTERVAL_MS = 500

# JARVIS gateway lock-in (Phase 0 user decision).
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7433


class GatewayLockError(RuntimeError):
    """Raised when the gateway port is held by another process.

    Mirrors OpenClaw's ``GatewayLockError`` from
    ``src/infra/gateway-lock.ts``. The doctor runner consumes
    this error and emits a user-friendly finding.
    """


# ── Route registration (mirrors OpenClaw's registerHttpRoute) ───


@dataclass(frozen=True, slots=True)
class HttpRoute:
    """A single HTTP route registered by a plugin.

    Mirrors OpenClaw's ``OpenClawPluginHttpRouteParams``:
      - ``path``        URL path (e.g. ``"/v1/extensions/memory/search"``)
      - ``handler``     callable ``(method, url, body) -> dict``
      - ``auth``        ``"gateway"`` (default) or ``"plugin"``
      - ``match``       ``"exact"`` (default) or ``"prefix"``
    """

    path: str
    handler: Callable[..., Any]
    auth: str = "gateway"  # "gateway" or "plugin"
    match: str = "exact"  # "exact" or "prefix"
    owner_id: str = ""  # set by SDK when registered


# ── Gateway implementation ──────────────────────────────────────


class Gateway:
    """In-process HTTP server for plugin HTTP routes.

    Phase 3 host. Created once at startup; plugins register routes
    via ``api.register_http_handler(route)``. The host's CLI
    (``jarvis gateway start``) starts the server in a background
    thread; ``jarvis gateway stop`` stops it.
    """

    def __init__(
        self,
        *,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        token_path: Path | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self._token_path = token_path or (Path.home() / ".jarvis" / "gateway.token")
        self._routes: list[HttpRoute] = []
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

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
        """Register a route. Last-registered wins for prefix matches."""
        with self._lock:
            self._routes.append(route)

    def add_raw(self, raw: dict[str, Any]) -> None:
        """Add a route from a raw plugin dict (mirrors OpenClaw)."""
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

    def routes(self) -> list[HttpRoute]:
        with self._lock:
            return list(self._routes)

    def is_running(self) -> bool:
        return self._server is not None

    def start(self, *, retry_eaddrinuse: bool = True) -> None:
        """Start the gateway in a background thread.

        Mirrors OpenClaw's ``listenGatewayHttpServer`` retry logic.
        Raises ``GatewayLockError`` if the port is held by another
        process and the retry window expires.
        """
        if self._thread is not None:
            return
        max_retries = EADDRINUSE_MAX_RETRIES if retry_eaddrinuse else 0
        last_err: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                self._server = _ThreadedGatewayServer(
                    (self.host, self.port),
                    _GatewayRequestHandler,
                    gateway=self,
                )
                break
            except OSError as e:
                last_err = e
                if e.errno == errno.EADDRINUSE and attempt < max_retries:
                    _log.info(
                        "gateway: port %d in use, retry %d/%d",
                        self.port,
                        attempt + 1,
                        max_retries,
                    )
                    time.sleep(EADDRINUSE_RETRY_INTERVAL_MS / 1000.0)
                    continue
                if e.errno == errno.EADDRINUSE:
                    raise GatewayLockError(
                        f"another gateway instance is already listening on "
                        f"http://{self.host}:{self.port}",
                        e,
                    ) from e
                raise GatewayLockError(
                    f"failed to bind gateway socket on " f"http://{self.host}:{self.port}: {e}",
                    e,
                ) from e
        if self._server is None:
            # Exhausted retries without raising — should not happen.
            raise GatewayLockError(f"could not bind gateway on {self.host}:{self.port}: {last_err}")
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="jarvis-gateway",
            daemon=True,
        )
        self._thread.start()
        _log.info("gateway: listening on http://%s:%d", self.host, self.port)

    def stop(self) -> None:
        """Stop the gateway cleanly."""
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        _log.info("gateway: stopped")

    def handle_request(
        self, method: str, path: str, body: bytes, headers: dict[str, str]
    ) -> tuple[int, dict[str, Any] | str]:
        """Route a single request through the registered plugins.

        Returns ``(status, payload)``. Used by tests and by the
        gateway's request handler. Plugin routes are tried in
        registration order (last-registered wins for prefix matches).
        """
        # HTTP headers are case-insensitive (RFC 7230 §3.2). We
        # normalize the lookup table once per request so plugins
        # can also do case-insensitive header lookups by convention.
        norm_headers = {k.lower(): v for k, v in headers.items()}

        # Built-in: /health
        if path == "/health":
            return 200, {"status": "ok"}

        # Auth check
        auth_header = norm_headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return 401, {"error": "missing bearer token"}
        if not secrets.compare_digest(auth_header[len("Bearer ") :].strip(), self.token):
            return 403, {"error": "invalid token"}

        # Plugin routes
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
        """Find the best-matching route for ``(method, path)``.

        Mirrors OpenClaw's match="exact" / match="prefix" resolution.
        Exact matches win; prefix matches are tried in registration
        order (last-registered wins, as in OpenClaw).
        """
        parsed = urlparse(path)
        path_only = parsed.path  # strip query string
        for r in reversed(self.routes()):
            if r.match == "exact" and r.path == path_only:
                return r
        for r in reversed(self.routes()):
            if r.match == "prefix" and path_only.startswith(r.path):
                return r
        return None


# ── Internal: stdlib HTTP handler ───────────────────────────────


class _ThreadedGatewayServer(ThreadingHTTPServer):
    """A ThreadingHTTPServer that holds a reference to the Gateway.

    We can't subclass cleanly without overriding the constructor,
    so we attach the gateway as an attribute after construction.
    """

    gateway: Gateway  # type: ignore[assignment]

    def __init__(self, addr: tuple[str, int], handler: type, *, gateway: Gateway) -> None:
        super().__init__(addr, handler, bind_and_activate=False)
        self.gateway = gateway
        # Bind manually so we can retry on EADDRINUSE at the right layer.
        # (The retry happens in Gateway.start; here we just bind.)
        self.server_bind()
        self.server_activate()


class _GatewayRequestHandler(BaseHTTPRequestHandler):
    """One HTTP request → one call to ``Gateway.handle_request``."""

    # Quieter BaseHTTPRequestHandler — no per-request log line.
    def log_message(self, format: str, *args: Any) -> None:
        return

    def _read_body(self) -> bytes:
        length = int(self.headers.get("content-length", "0") or "0")
        if length <= 0:
            return b""
        return self.rfile.read(length)

    def _respond(self, status: int, payload: dict[str, Any] | str) -> None:
        body: bytes
        if isinstance(payload, str):
            body = payload.encode("utf-8")
            ctype = "text/plain; charset=utf-8"
        else:
            body = json.dumps(payload).encode("utf-8")
            ctype = "application/json"
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle(self, method: str) -> None:
        # server is bound on the gateway attr by _ThreadedGatewayServer.
        gw: Gateway = cast("Gateway", self.server.gateway)  # type: ignore[attr-defined]
        body = self._read_body()
        try:
            status_int: int
            response_payload: dict[str, Any] | str
            status_int, response_payload = gw.handle_request(
                method, self.path, body, dict(self.headers.items())
            )
        except Exception as e:
            _log.warning("gateway: handler crashed: %s", e)
            self._respond(500, {"error": str(e)})
            return
        self._respond(status_int, response_payload)

    def do_GET(self) -> None:  # noqa: N802
        self._handle("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._handle("POST")

    def do_PUT(self) -> None:  # noqa: N802
        self._handle("PUT")

    def do_DELETE(self) -> None:  # noqa: N802
        self._handle("DELETE")


__all__ = [
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "Gateway",
    "GatewayLockError",
    "HttpRoute",
]
