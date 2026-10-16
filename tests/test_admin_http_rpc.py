"""Tests for src/plugins/admin_http_rpc.py.

Mirrors tests of extensions/admin-http-rpc/src/methods.ts in OpenClaw.
"""

from __future__ import annotations


from src.plugins.admin_http_rpc import (
    ADMIN_HTTP_RPC_ROUTE_PATH,
    is_admin_http_rpc_allowed_method,
    list_admin_http_rpc_allowed_methods,
)


def test_admin_http_rpc_route_path():
    assert ADMIN_HTTP_RPC_ROUTE_PATH == "/api/v1/admin/rpc"


def test_is_admin_http_rpc_allowed_method():
    assert is_admin_http_rpc_allowed_method("health") is True
    assert is_admin_http_rpc_allowed_method("commands.list") is True
    assert is_admin_http_rpc_allowed_method("config.patch") is True
    assert is_admin_http_rpc_allowed_method("unregistered.dangerous.method") is False


def test_list_admin_http_rpc_allowed_methods():
    methods = list_admin_http_rpc_allowed_methods()
    assert "health" in methods
    assert "status" in methods
    assert len(methods) > 40
