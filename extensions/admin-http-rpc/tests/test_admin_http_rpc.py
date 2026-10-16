"""Unit tests for Admin HTTP RPC extension.

Covers methods allowlist, request validation, size limits, error code mapping,
and Gateway method dispatching.
"""

from __future__ import annotations

import json
import pytest

from ..src.handler import (
    AdminHttpRpcHandler,
    MAX_REQUEST_BYTES,
)
from ..src.methods import (
    ADMIN_HTTP_RPC_ALLOWED_METHOD_GROUPS,
    ADMIN_HTTP_RPC_ALLOWED_METHODS,
    ADMIN_HTTP_RPC_ROUTE_PATH,
    is_admin_http_rpc_allowed_method,
    list_admin_http_rpc_allowed_methods,
)
from ..plugin import admin_http_rpc_plugin


def test_route_path():
    assert ADMIN_HTTP_RPC_ROUTE_PATH == "/api/v1/admin/rpc"


def test_method_groups():
    expected_groups = {
        "discovery",
        "gateway",
        "config",
        "channels",
        "web",
        "models",
        "agents",
        "approvals",
        "cron",
        "devices",
        "nodes",
        "tasks",
        "diagnostics",
    }
    assert expected_groups.issubset(set(ADMIN_HTTP_RPC_ALLOWED_METHOD_GROUPS.keys()))
    assert "commands.list" in ADMIN_HTTP_RPC_ALLOWED_METHOD_GROUPS["discovery"]
    assert "health" in ADMIN_HTTP_RPC_ALLOWED_METHOD_GROUPS["gateway"]
    assert "config.patch" in ADMIN_HTTP_RPC_ALLOWED_METHOD_GROUPS["config"]
    assert "channels.start" in ADMIN_HTTP_RPC_ALLOWED_METHOD_GROUPS["channels"]
    assert "cron.run" in ADMIN_HTTP_RPC_ALLOWED_METHOD_GROUPS["cron"]
    assert "node.rename" in ADMIN_HTTP_RPC_ALLOWED_METHOD_GROUPS["nodes"]


def test_is_allowed_method():
    assert is_admin_http_rpc_allowed_method("health") is True
    assert is_admin_http_rpc_allowed_method("commands.list") is True
    assert is_admin_http_rpc_allowed_method("gateway.restart.request") is True
    assert is_admin_http_rpc_allowed_method("doctor.memory.status") is True
    assert is_admin_http_rpc_allowed_method("unknown.dangerous.method") is False
    assert is_admin_http_rpc_allowed_method("") is False
    assert is_admin_http_rpc_allowed_method(None) is False  # type: ignore


def test_list_allowed_methods():
    methods = list_admin_http_rpc_allowed_methods()
    assert isinstance(methods, list)
    assert len(methods) == len(ADMIN_HTTP_RPC_ALLOWED_METHODS)
    assert "health" in methods
    assert "status" in methods
    assert "commands.list" in methods


@pytest.mark.asyncio
async def test_handler_method_not_allowed():
    handler = AdminHttpRpcHandler()
    res = await handler.handle_request("GET", b"{}")
    assert res.status == 405
    data = json.loads(res.body)
    assert data["ok"] is False
    assert data["error"]["code"] == "METHOD_NOT_ALLOWED"


@pytest.mark.asyncio
async def test_handler_payload_too_large():
    handler = AdminHttpRpcHandler()
    oversized = b"x" * (MAX_REQUEST_BYTES + 10)
    res = await handler.handle_request("POST", oversized)
    assert res.status == 413
    data = json.loads(res.body)
    assert data["ok"] is False
    assert data["error"]["code"] == "PAYLOAD_TOO_LARGE"


@pytest.mark.asyncio
async def test_handler_invalid_json():
    handler = AdminHttpRpcHandler()
    res = await handler.handle_request("POST", b"invalid json content")
    assert res.status == 400
    data = json.loads(res.body)
    assert data["ok"] is False
    assert data["error"]["code"] == "INVALID_REQUEST"


@pytest.mark.asyncio
async def test_handler_non_dict_json():
    handler = AdminHttpRpcHandler()
    res = await handler.handle_request("POST", b"[1, 2, 3]")
    assert res.status == 400
    data = json.loads(res.body)
    assert data["ok"] is False
    assert data["error"]["code"] == "INVALID_REQUEST"


@pytest.mark.asyncio
async def test_handler_missing_method():
    handler = AdminHttpRpcHandler()
    res = await handler.handle_request("POST", b'{"params": {}}')
    assert res.status == 400
    data = json.loads(res.body)
    assert data["ok"] is False
    assert data["error"]["code"] == "INVALID_REQUEST"


@pytest.mark.asyncio
async def test_handler_disallowed_method():
    handler = AdminHttpRpcHandler()
    res = await handler.handle_request(
        "POST", json.dumps({"method": "arbitrary.system.eval", "params": {}}).encode("utf-8")
    )
    assert res.status == 400
    data = json.loads(res.body)
    assert data["ok"] is False
    assert data["error"]["code"] == "INVALID_REQUEST"
    assert "not allowed" in data["error"]["message"]


@pytest.mark.asyncio
async def test_handler_commands_list():
    handler = AdminHttpRpcHandler()
    res = await handler.handle_request(
        "POST", json.dumps({"id": "req-1", "method": "commands.list"}).encode("utf-8")
    )
    assert res.status == 200
    data = json.loads(res.body)
    assert data["id"] == "req-1"
    assert data["ok"] is True
    assert "methods" in data["payload"]
    assert "health" in data["payload"]["methods"]
    assert "commands.list" in data["payload"]["methods"]


@pytest.mark.asyncio
async def test_handler_health_default():
    handler = AdminHttpRpcHandler()
    res = await handler.handle_request(
        "POST", json.dumps({"id": "req-health", "method": "health"}).encode("utf-8")
    )
    assert res.status == 200
    data = json.loads(res.body)
    assert data["id"] == "req-health"
    assert data["ok"] is True
    assert data["payload"] == {"status": "ok"}


@pytest.mark.asyncio
async def test_handler_dispatch_success():
    async def fake_dispatcher(method: str, params: dict, ctx: dict | None):
        if method == "config.get":
            return {"version": "1.0", "theme": "dark"}
        return {}

    handler = AdminHttpRpcHandler(dispatch_method=fake_dispatcher)
    res = await handler.handle_request(
        "POST", json.dumps({"id": "req-cfg", "method": "config.get", "params": {}}).encode("utf-8")
    )
    assert res.status == 200
    data = json.loads(res.body)
    assert data["id"] == "req-cfg"
    assert data["ok"] is True
    assert data["payload"] == {"version": "1.0", "theme": "dark"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("err_code", "expected_status"),
    [
        ("INVALID_REQUEST", 400),
        ("APPROVAL_NOT_FOUND", 404),
        ("NOT_LINKED", 409),
        ("NOT_PAIRED", 409),
        ("UNAVAILABLE", 503),
        ("AGENT_TIMEOUT", 504),
        ("CUSTOM_UNKNOWN_CODE", 500),
    ],
)
async def test_handler_dispatch_error_mapping(err_code: str, expected_status: int):
    async def failing_dispatcher(method: str, params: dict, ctx: dict | None):
        return {
            "ok": False,
            "error": {"code": err_code, "message": f"Simulated error: {err_code}"},
        }

    handler = AdminHttpRpcHandler(dispatch_method=failing_dispatcher)
    res = await handler.handle_request(
        "POST", json.dumps({"id": "req-err", "method": "status"}).encode("utf-8")
    )
    assert res.status == expected_status
    data = json.loads(res.body)
    assert data["id"] == "req-err"
    assert data["ok"] is False
    assert data["error"]["code"] == err_code


def test_plugin_registration():
    registered_routes = []

    class MockContext:
        def register_http_route(self, path: str, method: str, handler):
            registered_routes.append((path, method, handler))

    ctx = MockContext()
    admin_http_rpc_plugin.init(ctx)
    assert len(registered_routes) == 1
    path, method, _ = registered_routes[0]
    assert path == "/api/v1/admin/rpc"
    assert method == "POST"
