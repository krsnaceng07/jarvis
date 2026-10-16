from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

import pytest

from extensions.codex.src.app_server.config import CodexAppServerRuntimeOptions
from extensions.codex.src.app_server.transport import CodexAppServerClient


def _options(**overrides: Any) -> CodexAppServerRuntimeOptions:
    values: dict[str, Any] = {
        "transport": "stdio",
        "home_scope": "agent",
        "command": sys.executable,
        "command_source": "config",
        "args": [],
        "connection_class": "local-loopback",
        "approval_policy": "never",
        "sandbox": "danger-full-access",
        "approvals_reviewer": "user",
        "policy_mode": "yolo",
    }
    values.update(overrides)
    return CodexAppServerRuntimeOptions(**values)


async def test_stdio_transport_round_trip(tmp_path):
    script = (
        "import sys,json\n"
        "for line in sys.stdin:\n"
        " request=json.loads(line)\n"
        " result={'thread': {'id': 'thread-1'}} if request['method']=='thread/start' else {'text': 'hello'}\n"
        " print(json.dumps({'jsonrpc':'2.0','id':request['id'],'result':result}), flush=True)\n"
    )
    client = CodexAppServerClient(
        _options(args=["-u", "-c", script]),
        agent_dir=str(tmp_path / "agent"),
        base_env={"HOME": "C:/operator", "OPENAI_API_KEY": "secret"},
        prepared_auth=True,
    )
    try:
        started = await client.request("thread/start", {})
        response = await client.request("turn/start", {"threadId": started["thread"]["id"]})
    finally:
        await client.close()

    assert started == {"thread": {"id": "thread-1"}}
    assert response == {"text": "hello"}


async def test_websocket_transport_uses_auth_and_handshake_cap():
    calls: list[tuple[str, dict[str, Any]]] = []

    class FakeWebSocket:
        async def send(self, message: str) -> None:
            calls.append(("send", json.loads(message)))

        async def recv(self) -> str:
            return json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}})

        async def close(self) -> None:
            calls.append(("close", {}))

    async def connector(url: str, **kwargs: Any) -> FakeWebSocket:
        calls.append((url, kwargs))
        return FakeWebSocket()

    client = CodexAppServerClient(
        _options(
            transport="websocket",
            connection_class="remote",
            url="ws://gateway-host:39175",
            auth_token="${TOKEN}",
            headers={"X-Trace": "${TRACE}"},
            request_timeout_ms=60_000,
        ),
        agent_dir=".",
        base_env={"TOKEN": "secret", "TRACE": "test"},
        websocket_connector=connector,
    )
    try:
        result = await client.request("status", {})
    finally:
        await client.close()

    assert result == {"ok": True}
    assert calls[0] == (
        "ws://gateway-host:39175",
        {
            "additional_headers": {
                "X-Trace": "test",
                "Authorization": "Bearer secret",
            },
            "open_timeout": 10,
        },
    )
    assert calls[1][1]["method"] == "status"


async def test_websocket_secret_input_fails_closed_when_missing():
    async def connector(url: str, **kwargs: Any) -> Any:
        del url, kwargs
        raise AssertionError("connector must not run with a missing secret")

    client = CodexAppServerClient(
        _options(
            transport="websocket",
            url="ws://gateway-host:39175",
            auth_token="${MISSING_TOKEN}",
        ),
        agent_dir=".",
        base_env={},
        websocket_connector=connector,
    )
    with pytest.raises(RuntimeError, match="SecretInput .* is not available"):
        await client.start()


async def test_websocket_heartbeat_reconnects_after_missed_pong():
    connections: list[Any] = []

    class FakeWebSocket:
        def __init__(self, fail_ping: bool) -> None:
            self.fail_ping = fail_ping
            self.closed = False

        async def send(self, message: str) -> None:
            del message

        async def recv(self) -> str:
            return json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}})

        async def close(self) -> None:
            self.closed = True

        def ping(self) -> Any:
            if self.fail_ping:
                raise RuntimeError("missed pong")
            return None

    async def connector(url: str, **kwargs: Any) -> FakeWebSocket:
        del url, kwargs
        websocket = FakeWebSocket(fail_ping=not bool(connections))
        connections.append(websocket)
        return websocket

    async def no_wait(delay: float) -> None:
        del delay

    client = CodexAppServerClient(
        _options(transport="websocket", url="ws://gateway-host:39175"),
        agent_dir=".",
        websocket_connector=connector,
        heartbeat_interval_seconds=0.001,
        pong_timeout_seconds=0.001,
        max_missed_pongs=1,
        reconnect_sleep=no_wait,
    )
    await client.start()
    try:
        await asyncio.sleep(0.1)
    finally:
        await client.close()

    assert len(connections) >= 2
    assert connections[0].closed is True
