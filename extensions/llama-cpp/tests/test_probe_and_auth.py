"""Unit tests for server probing, endpoint validation, and auth header resolution."""

from __future__ import annotations

import pytest

from extensions.llama_cpp.src.probe import (
    probe_llama_server,
    resolve_auth_headers,
    validate_endpoint_url,
)


def test_validate_endpoint_url() -> None:
    # 1. Valid URLs
    res1 = validate_endpoint_url("http://127.0.0.1:8080/v1")
    assert res1.is_ok
    assert res1.unwrap() == "http://127.0.0.1:8080/v1"

    # 2. Missing scheme auto-prepends http
    res2 = validate_endpoint_url("localhost:8080")
    assert res2.is_ok
    assert res2.unwrap() == "http://localhost:8080"

    # 3. Reject credentials in authority
    res_cred = validate_endpoint_url("http://admin:secretPass@127.0.0.1:8080/v1")
    assert res_cred.is_ok is False
    assert "username or password" in str(res_cred.error)

    # 4. Empty URL
    res_empty = validate_endpoint_url("")
    assert res_empty.is_ok is False


def test_resolve_auth_headers() -> None:
    # 1. API key provided
    h1 = resolve_auth_headers(api_key="my_secret_token")
    assert h1["Authorization"] == "Bearer my_secret_token"

    # 2. Explicit Authorization header takes precedence over API key
    h2 = resolve_auth_headers(
        api_key="ignored_key",
        explicit_auth_header="Basic custom_token",
    )
    assert h2["Authorization"] == "Basic custom_token"

    # 3. No auth
    h3 = resolve_auth_headers()
    assert "Authorization" not in h3


@pytest.mark.asyncio
async def test_probe_llama_server_states() -> None:
    # 1. Healthy server probe with models
    mock_ready = {
        "/health": {"status": 200},
        "/models": {"data": [{"id": "qwen3.8-27b", "object": "model"}]},
        "/props": {"default_generation_settings": {"n_ctx": 65536}},
    }
    res_ready = await probe_llama_server("http://127.0.0.1:8080", mock_responses=mock_ready)
    assert res_ready.is_ok
    val_ready = res_ready.unwrap()
    assert val_ready.is_healthy is True
    assert val_ready.is_loading is False
    assert len(val_ready.models) == 1
    assert val_ready.models[0]["id"] == "qwen3.8-27b"

    # 2. Loading model probe (HTTP 503)
    mock_loading = {
        "/health": {"status": 503},
    }
    res_loading = await probe_llama_server("http://127.0.0.1:8080", mock_responses=mock_loading)
    assert res_loading.is_ok
    val_loading = res_loading.unwrap()
    assert val_loading.is_healthy is False
    assert val_loading.is_loading is True
    assert "still loading" in (val_loading.error_message or "")
