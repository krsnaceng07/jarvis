"""Wave 4 tests — GatewayRPCDispatcher + JSON-RPC protocol shapes."""

from __future__ import annotations

import json

import pytest

from jarvis_gateway_protocol import RPCError, RPCMethod, RPCRequest, RPCResponse
from src.gateway.rpc_dispatcher import (
    GatewayRPCDispatcher,
    RPCDispatchError,
    make_channel_send_handler,
    make_plugins_list_handler,
    make_status_handler,
)


# ── RPCRequest / RPCResponse / RPCError protocol shapes ────────────────────


class TestGatewayProtocolShapes:
    def test_rpc_request_to_dict(self) -> None:
        req = RPCRequest(method="admin.status", id="r1", params={"a": 1})
        d = req.to_dict()
        assert d["jsonrpc"] == "2.0"
        assert d["method"] == "admin.status"
        assert d["id"] == "r1"
        assert d["params"] == {"a": 1}

    def test_rpc_request_defaults(self) -> None:
        req = RPCRequest(method="plugins.list")
        assert req.id == ""
        assert req.params == {}

    def test_rpc_response_ok_to_dict(self) -> None:
        resp = RPCResponse(id="r1", result={"status": "ok"})
        d = resp.to_dict()
        assert d["jsonrpc"] == "2.0"
        assert d["id"] == "r1"
        assert d["result"] == {"status": "ok"}
        assert "error" not in d

    def test_rpc_response_error_to_dict(self) -> None:
        err = RPCError.method_not_found("foo.bar")
        resp = RPCResponse(id="r1", error=err)
        d = resp.to_dict()
        assert "result" not in d
        assert d["error"]["code"] == -32601

    def test_rpc_error_constructors(self) -> None:
        assert RPCError.parse_error().code == -32700
        assert RPCError.invalid_request().code == -32600
        assert RPCError.method_not_found("x").code == -32601
        assert RPCError.invalid_params().code == -32602
        assert RPCError.internal_error().code == -32603
        assert RPCError.auth_error().code == -32001

    def test_rpc_response_ok_property(self) -> None:
        assert RPCResponse(id="r", result="x").ok
        assert not RPCResponse(id="r", error=RPCError.internal_error()).ok

    def test_rpc_method_enum_values(self) -> None:
        assert RPCMethod.ADMIN_STATUS == "admin.status"
        assert RPCMethod.PLUGINS_LIST == "plugins.list"
        assert RPCMethod.CHANNELS_SEND == "channels.send"
        assert RPCMethod.SESSIONS_CREATE == "sessions.create"


# ── GatewayRPCDispatcher ────────────────────────────────────────────────────


def _make_dispatcher() -> GatewayRPCDispatcher:
    return GatewayRPCDispatcher(
        handlers={
            "echo": lambda p: {"echoed": p},
            "fail": lambda p: 1 / 0,
            "dispatch_error": lambda p: (_ for _ in ()).throw(
                RPCDispatchError(-32000, "plugin error", "detail")
            ),
        }
    )


class TestGatewayRPCDispatcher:
    def test_dispatch_known_method(self) -> None:
        d = _make_dispatcher()
        resp = d.dispatch(RPCRequest(method="echo", id="1", params={"x": 1}))
        assert resp.ok
        assert resp.result == {"echoed": {"x": 1}}
        assert resp.id == "1"

    def test_dispatch_unknown_method_returns_method_not_found(self) -> None:
        d = _make_dispatcher()
        resp = d.dispatch(RPCRequest(method="no.such"))
        assert not resp.ok
        assert resp.error is not None
        assert resp.error.code == -32601

    def test_dispatch_exception_returns_internal_error(self) -> None:
        d = _make_dispatcher()
        resp = d.dispatch(RPCRequest(method="fail"))
        assert not resp.ok
        assert resp.error is not None
        assert resp.error.code == -32603

    def test_dispatch_rpc_dispatch_error_preserved(self) -> None:
        d = _make_dispatcher()
        resp = d.dispatch(RPCRequest(method="dispatch_error"))
        assert not resp.ok
        assert resp.error is not None
        assert resp.error.code == -32000
        assert resp.error.message == "plugin error"

    def test_has_method(self) -> None:
        d = _make_dispatcher()
        assert d.has_method("echo")
        assert not d.has_method("nope")

    def test_registered_methods(self) -> None:
        d = _make_dispatcher()
        methods = d.registered_methods()
        assert "echo" in methods
        assert "fail" in methods

    def test_register_adds_handler(self) -> None:
        d = _make_dispatcher()
        d.register("new_method", lambda p: "hello")
        assert d.has_method("new_method")
        resp = d.dispatch(RPCRequest(method="new_method"))
        assert resp.ok
        assert resp.result == "hello"

    def test_id_echoed_in_response(self) -> None:
        d = _make_dispatcher()
        resp = d.dispatch(RPCRequest(method="echo", id="my-request-id"))
        assert resp.id == "my-request-id"


# ── handle_http ─────────────────────────────────────────────────────────────


def _post_rpc(dispatcher: GatewayRPCDispatcher, body: dict) -> dict:
    raw = json.dumps(body).encode()
    return dispatcher.handle_http("POST", "/rpc", raw, {})


class TestHandleHttp:
    def test_post_known_method(self) -> None:
        d = GatewayRPCDispatcher({"ping": lambda p: "pong"})
        result = _post_rpc(d, {"method": "ping", "id": "1", "params": {}})
        assert result["result"] == "pong"
        assert result["id"] == "1"

    def test_get_returns_invalid_request(self) -> None:
        d = GatewayRPCDispatcher({})
        resp = d.handle_http("GET", "/rpc", b"", {})
        assert "error" in resp
        assert resp["error"]["code"] == -32600

    def test_parse_error_on_bad_json(self) -> None:
        d = GatewayRPCDispatcher({})
        resp = d.handle_http("POST", "/rpc", b"not-json", {})
        assert resp["error"]["code"] == -32700

    def test_missing_method_field(self) -> None:
        d = GatewayRPCDispatcher({})
        resp = d.handle_http("POST", "/rpc", json.dumps({"id": "1"}).encode(), {})
        assert resp["error"]["code"] == -32600

    def test_empty_body_treated_as_empty_dict(self) -> None:
        d = GatewayRPCDispatcher({})
        resp = d.handle_http("POST", "/rpc", b"", {})
        # Empty body → no method → invalid request
        assert "error" in resp

    def test_result_is_json_rpc_2_envelope(self) -> None:
        d = GatewayRPCDispatcher({"x": lambda p: 42})
        resp = _post_rpc(d, {"method": "x", "id": "q"})
        assert resp["jsonrpc"] == "2.0"


# ── Handler factories ────────────────────────────────────────────────────────


class TestHandlerFactories:
    def test_status_handler(self) -> None:
        h = make_status_handler("TestV")
        result = h({})
        assert result["status"] == "ok"
        assert result["version"] == "TestV"

    def test_plugins_list_handler(self) -> None:
        h = make_plugins_list_handler(["a", "b", "c"])
        result = h({})
        assert result["plugins"] == ["a", "b", "c"]
        assert result["count"] == 3

    def test_channel_send_ok(self) -> None:
        sent: list[tuple] = []
        h = make_channel_send_handler(lambda c, v, t: sent.append((c, v, t)))
        result = h({"channel_id": "tg", "conversation_id": "123", "text": "hello"})
        assert result["ok"] is True
        assert sent == [("tg", "123", "hello")]

    def test_channel_send_missing_params(self) -> None:
        h = make_channel_send_handler(lambda c, v, t: None)
        with pytest.raises(RPCDispatchError) as exc:
            h({"text": "hello"})  # missing channel_id
        assert exc.value.code == -32602

    def test_channel_send_fn_error_becomes_rpc_error(self) -> None:
        def _bad_send(c: str, v: str, t: str) -> None:
            raise RuntimeError("network error")

        h = make_channel_send_handler(_bad_send)
        with pytest.raises(RPCDispatchError) as exc:
            h({"channel_id": "tg", "conversation_id": "1", "text": "x"})
        assert exc.value.code == -32603
