"""Host-owned Codex app-server JSON-RPC transports."""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import random
import re
from collections.abc import Awaitable, Callable, Mapping
from contextlib import suppress
from typing import Any, Protocol

from extensions.codex.src.app_server.config import CodexAppServerRuntimeOptions
from extensions.codex.src.app_server.spawn_env import resolve_codex_app_server_spawn_env


class JsonRpcConnection(Protocol):
    async def send(self, message: str) -> Any: ...

    async def recv(self) -> Any: ...

    async def close(self) -> Any: ...

    def ping(self) -> Any: ...


WebSocketConnector = Callable[..., Awaitable[JsonRpcConnection]]
WebSocketSleep = Callable[[float], Awaitable[None]]

WEBSOCKET_HEARTBEAT_INTERVAL_SECONDS = 20.0
WEBSOCKET_PONG_TIMEOUT_SECONDS = 20.0
WEBSOCKET_MAX_MISSED_PONGS = 5
WEBSOCKET_RECONNECT_BASE_SECONDS = 0.5
WEBSOCKET_RECONNECT_MAX_SECONDS = 30.0
SECRET_INPUT_PATTERN = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")


class CodexAppServerPermanentError(RuntimeError):
    """An authentication or protocol error that must not trigger reconnect."""


class CodexAppServerClient:
    """One serialized request client for a Codex app-server connection."""

    def __init__(
        self,
        options: CodexAppServerRuntimeOptions,
        *,
        agent_dir: str,
        base_env: Mapping[str, str] | None = None,
        cwd: str | None = None,
        prepared_auth: bool = False,
        websocket_connector: WebSocketConnector | None = None,
        heartbeat_interval_seconds: float = WEBSOCKET_HEARTBEAT_INTERVAL_SECONDS,
        pong_timeout_seconds: float = WEBSOCKET_PONG_TIMEOUT_SECONDS,
        max_missed_pongs: int = WEBSOCKET_MAX_MISSED_PONGS,
        reconnect_sleep: WebSocketSleep | None = None,
    ) -> None:
        self.options = options
        self.agent_dir = agent_dir
        self.base_env = base_env
        self.cwd = cwd
        self.prepared_auth = prepared_auth
        self.websocket_connector = websocket_connector
        self.heartbeat_interval_seconds = heartbeat_interval_seconds
        self.pong_timeout_seconds = pong_timeout_seconds
        self.max_missed_pongs = max_missed_pongs
        self.reconnect_sleep = reconnect_sleep or asyncio.sleep
        self._process: asyncio.subprocess.Process | None = None
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._websocket: JsonRpcConnection | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._connection_lock = asyncio.Lock()
        self._closing = False
        self._request_lock = asyncio.Lock()
        self._next_request_id = 0

    async def start(self) -> None:
        """Open the configured local or remote transport."""
        if self._reader or self._websocket:
            return
        if self.options.transport == "websocket":
            await self._start_websocket()
            return
        if self.options.transport == "unix":
            await self._start_unix()
            return
        await self._start_stdio()

    async def close(self) -> None:
        """Close the connection and terminate only a process owned by this client."""
        self._closing = True
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._heartbeat_task
            self._heartbeat_task = None
        if self._websocket is not None:
            with suppress(Exception):
                await self._websocket.close()
            self._websocket = None
        if self._writer is not None:
            self._writer.close()
            with suppress(Exception):
                await self._writer.wait_closed()
            self._writer = None
        if self._process is not None:
            if self._process.returncode is None:
                self._process.terminate()
                with suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(self._process.wait(), timeout=2)
            if self._process.returncode is None:
                self._process.kill()
                await self._process.wait()
            self._process = None
        if self._stderr_task is not None:
            self._stderr_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._stderr_task
            self._stderr_task = None
        self._reader = None

    async def __aenter__(self) -> "CodexAppServerClient":
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        await self.close()

    async def request(self, method: str, params: dict[str, Any]) -> Any:
        """Send one JSON-RPC request and return its result."""
        await self.start()
        async with self._request_lock:
            self._next_request_id += 1
            request_id = self._next_request_id
            payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
            response = await asyncio.wait_for(
                self._exchange(json.dumps(payload, separators=(",", ":"))),
                timeout=max(0.001, self.options.request_timeout_ms / 1000),
            )
        if not isinstance(response, dict):
            raise RuntimeError("Codex app-server returned a non-object JSON-RPC response")
        if response.get("error") is not None:
            raise RuntimeError(f"Codex app-server {method} failed: {response['error']}")
        return response.get("result", response)

    async def _exchange(self, message: str) -> Any:
        if self._websocket is not None:
            await self._websocket.send(message)
            return json.loads(await self._websocket.recv())
        if self._writer is None or self._reader is None:
            raise RuntimeError("Codex app-server transport is not connected")
        self._writer.write((message + "\n").encode("utf-8"))
        await self._writer.drain()
        while True:
            line = await self._reader.readline()
            if not line:
                raise RuntimeError("Codex app-server closed its transport")
            if not line.strip():
                continue
            candidate = json.loads(line)
            if isinstance(candidate, dict) and "id" not in candidate:
                continue
            return candidate

    async def _start_stdio(self) -> None:
        env = resolve_codex_app_server_spawn_env(
            self.options,
            agent_dir=self.agent_dir,
            base_env=self.base_env,
            prepared_auth=self.prepared_auth,
        )
        process = await asyncio.create_subprocess_exec(
            self.options.command,
            *self.options.args,
            cwd=self.cwd or self.options.default_workspace_dir,
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        if process.stdout is None or process.stdin is None:
            process.kill()
            await process.wait()
            raise RuntimeError("Codex app-server stdio pipes were not created")
        self._process = process
        self._reader = process.stdout
        self._writer = process.stdin
        if process.stderr is not None:
            self._stderr_task = asyncio.create_task(self._drain_stderr(process.stderr))

    async def _start_unix(self) -> None:
        path = (self.options.url or "").removeprefix("unix://")
        self._reader, self._writer = await asyncio.open_unix_connection(path)

    async def _start_websocket(self) -> None:
        self._closing = False
        await self._connect_websocket()
        self._heartbeat_task = asyncio.create_task(self._supervise_websocket())

    async def _connect_websocket(self) -> None:
        connector = self.websocket_connector or _load_websocket_connector()
        headers = {
            name: _resolve_secret_input(value, self.base_env)
            for name, value in self.options.headers.items()
        }
        auth_token = _resolve_secret_input(self.options.auth_token, self.base_env)
        if auth_token:
            headers.setdefault("Authorization", f"Bearer {auth_token}")
        try:
            websocket = await connector(
                self.options.url,
                additional_headers=headers,
                open_timeout=min(10, max(0.001, self.options.request_timeout_ms / 1000)),
            )
        except Exception as exc:
            if _is_permanent_websocket_error(exc):
                raise CodexAppServerPermanentError(str(exc)) from exc
            raise
        self._websocket = websocket

    async def _supervise_websocket(self) -> None:
        missed_pongs = 0
        while not self._closing:
            await asyncio.sleep(self.heartbeat_interval_seconds)
            websocket = self._websocket
            if websocket is None:
                continue
            try:
                pong_waiter = websocket.ping()
                if inspect.isawaitable(pong_waiter):
                    pong_waiter = await pong_waiter
                if inspect.isawaitable(pong_waiter):
                    await asyncio.wait_for(pong_waiter, self.pong_timeout_seconds)
                missed_pongs = 0
            except asyncio.CancelledError:
                raise
            except Exception:
                missed_pongs += 1
                if missed_pongs >= self.max_missed_pongs:
                    await self._reconnect_websocket()
                    missed_pongs = 0

    async def _reconnect_websocket(self) -> None:
        old_websocket = self._websocket
        self._websocket = None
        if old_websocket is not None:
            with suppress(Exception):
                await old_websocket.close()
        attempt = 0
        while not self._closing:
            try:
                await self._connect_websocket()
                return
            except CodexAppServerPermanentError:
                return
            except Exception:
                delay = min(
                    WEBSOCKET_RECONNECT_MAX_SECONDS,
                    WEBSOCKET_RECONNECT_BASE_SECONDS * (2**attempt),
                )
                attempt += 1
                await self.reconnect_sleep(delay + random.uniform(0, delay / 2))

    @staticmethod
    async def _drain_stderr(reader: asyncio.StreamReader) -> None:
        while await reader.readline():
            pass


def _is_permanent_websocket_error(error: Exception) -> bool:
    status_code = getattr(error, "status_code", None)
    if status_code in {401, 403, 426}:
        return True
    message = str(error).lower()
    return any(
        value in message for value in ("unauthorized", "forbidden", "authentication", "unsupported")
    )


def _resolve_secret_input(value: str | None, base_env: Mapping[str, str] | None) -> str | None:
    if value is None:
        return None
    match = SECRET_INPUT_PATTERN.fullmatch(value.strip())
    if match is None:
        return value
    env = base_env if base_env is not None else os.environ
    resolved = env.get(match.group(1))
    if not isinstance(resolved, str) or not resolved:
        raise RuntimeError(f"SecretInput {value!r} is not available")
    return resolved


def _load_websocket_connector() -> WebSocketConnector:
    try:
        import websockets
    except ImportError as exc:
        raise RuntimeError(
            "WebSocket Codex transport requires the optional 'websockets' package"
        ) from exc
    connector = getattr(websockets, "connect", None)
    if not callable(connector):
        raise RuntimeError("Installed websockets package does not provide connect()")
    return connector


def create_codex_app_server_client(
    options: CodexAppServerRuntimeOptions,
    *,
    agent_dir: str,
    base_env: Mapping[str, str] | None = None,
    cwd: str | None = None,
    prepared_auth: bool = False,
    websocket_connector: WebSocketConnector | None = None,
) -> CodexAppServerClient:
    """Build a client without starting a process or connecting remotely."""
    return CodexAppServerClient(
        options,
        agent_dir=agent_dir,
        base_env=base_env,
        cwd=cwd,
        prepared_auth=prepared_auth,
        websocket_connector=websocket_connector,
    )


__all__ = ["CodexAppServerClient", "create_codex_app_server_client"]
