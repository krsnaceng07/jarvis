"""Tests for the remote HTTP credential gate on execution nodes.

OpenClaw parity: ``extensions/codex/src/app-server/sandbox-exec-server-node-relay.ts``
(``rejectCredentialedCodexNodeHttpRequest`` and helpers). Only
credential-free HTTP is forwarded to the node; credentialed requests get a
``-32602`` rejection frame instead.
"""

from __future__ import annotations

import base64
import json

import pytest

from extensions.codex.src.app_server.placement import (
    is_codex_sandbox_exec_server_enabled,
    is_paired_node_remote_exec_placement_sandbox,
    is_remote_exec_placement_sandbox,
)
from extensions.codex.src.node_exec_server_runtime import (
    CODEX_NODE_HTTP_CREDENTIAL_REJECTION_CODE,
    CODEX_NODE_HTTP_CREDENTIAL_REJECTION_MESSAGE,
    has_sensitive_node_text,
    is_node_credential_field,
    reject_credentialed_node_http_request,
    sanitize_exec_server_request,
)


def _http_request(*, request_id=1, url="https://example.com/api", headers=None, body=None):
    params: dict = {"url": url, "headers": headers if headers is not None else []}
    if body is not None:
        params["bodyBase64"] = body
    return {"jsonrpc": "2.0", "id": request_id, "method": "http/request", "params": params}


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def test_non_http_request_passes():
    assert reject_credentialed_node_http_request({"method": "process/start"}) is None
    assert reject_credentialed_node_http_request(None) is None


def test_clean_request_passes():
    request = _http_request(
        headers=[
            {"name": "content-type", "value": "application/json"},
            {"name": "accept", "value": "application/json"},
        ]
    )
    assert reject_credentialed_node_http_request(request) is None


def test_malformed_shapes_raise():
    with pytest.raises(ValueError, match="params must be an object"):
        reject_credentialed_node_http_request({"method": "http/request", "params": []})
    with pytest.raises(ValueError, match="headers must be an array"):
        reject_credentialed_node_http_request(
            {"method": "http/request", "id": 1, "params": {"headers": {}}}
        )
    with pytest.raises(ValueError, match="string names and values"):
        reject_credentialed_node_http_request(
            {
                "method": "http/request",
                "id": 1,
                "params": {"headers": [{"name": "x-ok", "value": 42}]},
            }
        )
    with pytest.raises(ValueError, match="URL must be valid"):
        reject_credentialed_node_http_request(
            {"method": "http/request", "id": 1, "params": {"headers": [], "url": ":::not a url"}}
        )


def test_too_many_headers_rejects():
    headers = [{"name": f"x-h-{i}", "value": "v"} for i in range(257)]
    rejection = reject_credentialed_node_http_request(_http_request(headers=headers))
    assert rejection is not None
    assert rejection["error"]["code"] == CODEX_NODE_HTTP_CREDENTIAL_REJECTION_CODE


@pytest.mark.parametrize("name", ["Authorization", "cookie", "X-Api-Key", "X-Vault-Token"])
def test_exact_credential_header_names_reject(name):
    rejection = reject_credentialed_node_http_request(
        _http_request(request_id=7, headers=[{"name": name, "value": "abc"}])
    )
    assert rejection is not None
    assert rejection["jsonrpc"] == "2.0"
    assert rejection["id"] == 7
    assert rejection["error"]["code"] == CODEX_NODE_HTTP_CREDENTIAL_REJECTION_CODE
    assert rejection["error"]["message"] == CODEX_NODE_HTTP_CREDENTIAL_REJECTION_MESSAGE


@pytest.mark.parametrize("name", ["X-Auth-Token", "x-secret-rotation", "X-Password-Reset"])
def test_credential_like_header_names_reject(name):
    assert (
        reject_credentialed_node_http_request(_http_request(headers=[{"name": name, "value": "v"}]))
        is not None
    )


def test_sensitive_header_value_rejects():
    rejection = reject_credentialed_node_http_request(
        _http_request(headers=[{"name": "x-trace", "value": "token sk-abcdefgh12345678"}])
    )
    assert rejection is not None


def test_conflicting_content_type_rejects():
    rejection = reject_credentialed_node_http_request(
        _http_request(
            headers=[
                {"name": "content-type", "value": "application/json"},
                {"name": "Content-Type", "value": "text/plain"},
            ]
        )
    )
    assert rejection is not None


def test_url_userinfo_rejects():
    assert (
        reject_credentialed_node_http_request(_http_request(url="https://user:pw@example.com/x"))
        is not None
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/x?api_key=abc",
        "https://example.com/x?next=%252Flogin%253Ftoken%253Dabc",
        "https://example.com/x#access_token=abc",
        "https://example.com/files/a;session_id=abc/b",
        "https://example.com/x?next=https%3A%2F%2Fevil.test%2Fp%3Ftoken%3Dabc",
    ],
)
def test_credentialed_url_parts_reject(url):
    assert reject_credentialed_node_http_request(_http_request(url=url)) is not None


def test_json_body_credential_field_rejects():
    body = _b64(json.dumps({"user": "u", "password": "hunter2"}))
    rejection = reject_credentialed_node_http_request(
        _http_request(
            headers=[{"name": "content-type", "value": "application/json"}],
            body=body,
        )
    )
    assert rejection is not None


def test_nested_json_body_credential_rejects():
    body = _b64(json.dumps({"config": {"auth": {"apiKey": "sk-live-1234567890"}}}))
    assert (
        reject_credentialed_node_http_request(
            _http_request(
                headers=[{"name": "content-type", "value": "application/json"}],
                body=body,
            )
        )
        is not None
    )


def test_form_body_token_rejects():
    body = _b64("user=u&token=abc123")
    assert (
        reject_credentialed_node_http_request(
            _http_request(
                headers=[{"name": "content-type", "value": "application/x-www-form-urlencoded"}],
                body=body,
            )
        )
        is not None
    )


def test_plain_text_body_without_assignment_passes():
    body = _b64("just some log output")
    assert (
        reject_credentialed_node_http_request(
            _http_request(
                headers=[{"name": "content-type", "value": "text/plain"}],
                body=body,
            )
        )
        is None
    )


def test_html_body_rejects():
    body = _b64("<html>challenge</html>")
    assert (
        reject_credentialed_node_http_request(
            _http_request(
                headers=[{"name": "content-type", "value": "text/html"}],
                body=body,
            )
        )
        is not None
    )


def test_non_string_body_raises():
    with pytest.raises(ValueError, match="bodyBase64 must be a string"):
        reject_credentialed_node_http_request(
            {"method": "http/request", "id": 1, "params": {"headers": [], "bodyBase64": 42}}
        )


def test_rejection_requires_request_id():
    with pytest.raises(ValueError, match="JSON-RPC request id"):
        reject_credentialed_node_http_request(
            {"method": "http/request", "params": {"headers": [{"name": "cookie", "value": "a=b"}]}}
        )
    with pytest.raises(ValueError, match="JSON-RPC request id"):
        reject_credentialed_node_http_request(
            {
                "method": "http/request",
                "id": True,
                "params": {"headers": [{"name": "cookie", "value": "a=b"}]},
            }
        )


def test_is_node_credential_field():
    assert is_node_credential_field("apiKey") is True
    assert is_node_credential_field("access_token") is True
    assert is_node_credential_field("sessionId") is True
    assert is_node_credential_field("content-type") is False
    assert is_node_credential_field("username") is False
    assert is_node_credential_field("x-trace-id") is False
    assert is_node_credential_field("api%255Fkey") is True  # double-encoded
    assert is_node_credential_field("x" * 300) is True  # overlong fails closed
    assert is_node_credential_field("100%") is True  # stray % fails closed
    assert is_node_credential_field("%zz") is True  # malformed escape fails closed


def test_has_sensitive_node_text():
    assert has_sensitive_node_text("Bearer sk-abcdefgh12345678") is True
    assert has_sensitive_node_text("hello world") is False
    assert has_sensitive_node_text("token=abc") is True


def test_sanitize_exec_server_request_passthrough():
    request = {"method": "other/method", "params": {"env": {"A": "b"}}}
    assert sanitize_exec_server_request(request) is request


def test_sanitize_exec_server_request_drops_userinfo_urls():
    request = {
        "method": "process/start",
        "params": {
            "env": {
                "SAFE": "value",
                "PROXY": "https://user:pw@proxy.local:8080",
                "GITHUB_TOKEN": "ghp_12345678901234567890",
            },
            "envPolicy": {"set": {"OTHER": "https://a:b@example.com/x"}},
        },
    }
    out = sanitize_exec_server_request(request)
    assert out["params"]["env"]["SAFE"] == "value"
    assert "PROXY" not in out["params"]["env"]
    assert "GITHUB_TOKEN" not in out["params"]["env"]
    assert out["params"]["envPolicy"]["set"] == {}


def test_sanitize_exec_server_request_malformed_raises():
    with pytest.raises(ValueError, match="params must be an object"):
        sanitize_exec_server_request({"method": "process/start", "params": []})
    with pytest.raises(ValueError, match="env must be an object"):
        sanitize_exec_server_request({"method": "process/start", "params": {"env": []}})
    with pytest.raises(ValueError, match="envPolicy must be an object"):
        sanitize_exec_server_request({"method": "process/start", "params": {"envPolicy": []}})
    with pytest.raises(ValueError, match="values must be strings"):
        sanitize_exec_server_request({"method": "process/start", "params": {"env": {"A": 1}}})


def test_placement_sandbox_predicates():
    assert is_remote_exec_placement_sandbox({"placementExecutionMode": "remote-exec"}) is True
    assert is_remote_exec_placement_sandbox({"placementExecutionMode": "local"}) is False
    assert is_remote_exec_placement_sandbox(None) is False
    assert is_remote_exec_placement_sandbox("remote-exec") is False
    assert (
        is_paired_node_remote_exec_placement_sandbox(
            {"placementExecutionMode": "remote-exec", "placementNodeId": "node-01"}
        )
        is True
    )
    assert (
        is_paired_node_remote_exec_placement_sandbox({"placementExecutionMode": "local"}) is False
    )


def test_sandbox_exec_server_enabled_combinator():
    remote = {"placementExecutionMode": "remote-exec"}
    assert is_codex_sandbox_exec_server_enabled(None, remote) is True
    assert is_codex_sandbox_exec_server_enabled({}, remote) is True
    local = {"placementExecutionMode": "local"}
    assert is_codex_sandbox_exec_server_enabled(None, local) is False
    assert is_codex_sandbox_exec_server_enabled(None, None) is False
    flag_on = {"appServer": {"experimental": {"sandbox_exec_server": True}}}
    assert is_codex_sandbox_exec_server_enabled(flag_on, local) is True
    flag_off = {"appServer": {"experimental": {"sandbox_exec_server": False}}}
    assert is_codex_sandbox_exec_server_enabled(flag_off, local) is False
    assert (
        is_paired_node_remote_exec_placement_sandbox(
            {"placementExecutionMode": "remote-exec", "placementNodeId": ""}
        )
        is False
    )
    assert (
        is_paired_node_remote_exec_placement_sandbox({"placementExecutionMode": "local"}) is False
    )
