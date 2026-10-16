"""Unit tests for Webhooks HTTP authentication and rate limiting."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from extensions.webhooks.src.http import (
    TaskFlowWebhookHandler,
    WebhookRateLimiter,
    extract_request_secret,
    resolve_secret_value,
)
from extensions.webhooks.src.types import TaskFlowWebhookTarget


def test_extract_request_secret() -> None:
    """Test secret extraction across Bearer headers, custom headers, and query params."""
    # 1. Bearer header
    headers1 = {"Authorization": "Bearer secret-bearer-123"}
    assert extract_request_secret(headers1) == "secret-bearer-123"

    # 2. X-Jarvis-Secret
    headers2 = {"x-jarvis-secret": "secret-jarvis-456"}
    assert extract_request_secret(headers2) == "secret-jarvis-456"

    # 3. X-OpenClaw-Secret
    headers3 = {"X-OpenClaw-Secret": "secret-openclaw-789"}
    assert extract_request_secret(headers3) == "secret-openclaw-789"

    # 4. Query param
    assert extract_request_secret({}, query_params={"secret": "query-secret"}) == "query-secret"

    # 5. Missing secret
    assert extract_request_secret({}) is None


def test_resolve_secret_value(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test resolving raw string or SecretRef objects."""
    # 1. Plaintext
    assert resolve_secret_value("plain-secret") == "plain-secret"

    # 2. Env SecretRef
    monkeypatch.setenv("TEST_WEBHOOK_KEY", "env-secret-val")
    assert (
        resolve_secret_value({"source": "env", "provider": "default", "id": "TEST_WEBHOOK_KEY"})
        == "env-secret-val"
    )

    # 3. File SecretRef
    secret_file = tmp_path / "secret.txt"
    secret_file.write_text("file-secret-val\n", encoding="utf-8")
    assert (
        resolve_secret_value({"source": "file", "provider": "default", "id": str(secret_file)})
        == "file-secret-val"
    )


@pytest.mark.asyncio
async def test_webhook_handler_auth_and_routing(mock_task_flow: MagicMock) -> None:
    """Test HTTP handler request validation, method checks, and authentication."""
    target = TaskFlowWebhookTarget(
        route_id="r1",
        path="/plugins/webhooks/r1",
        secret_input="valid-secret-123",
        default_controller_id="webhooks/r1",
        task_flow=mock_task_flow,
    )
    handler = TaskFlowWebhookHandler(targets_by_path={"/plugins/webhooks/r1": [target]})

    # 1. Method not allowed (GET)
    status, body = await handler.handle_request(
        path="/plugins/webhooks/r1",
        method="GET",
        headers={},
        body_bytes=b"",
    )
    assert status == 405
    assert body["ok"] is False

    # 2. Path not found
    status, body = await handler.handle_request(
        path="/plugins/webhooks/unknown",
        method="POST",
        headers={"Authorization": "Bearer valid-secret-123"},
        body_bytes=b'{"action":"list_flows"}',
    )
    assert status == 404
    assert body["ok"] is False

    # 3. Unauthorized (wrong secret)
    status, body = await handler.handle_request(
        path="/plugins/webhooks/r1",
        method="POST",
        headers={"Authorization": "Bearer wrong-secret"},
        body_bytes=b'{"action":"list_flows"}',
    )
    assert status == 401
    assert body["ok"] is False

    # 4. Successful authenticated request
    status, body = await handler.handle_request(
        path="/plugins/webhooks/r1",
        method="POST",
        headers={"Authorization": "Bearer valid-secret-123"},
        body_bytes=b'{"action":"list_flows"}',
    )
    assert status == 200
    assert body["ok"] is True
    assert "flows" in body


def test_rate_limiter() -> None:
    """Test rate limiter threshold and window expiry."""
    limiter = WebhookRateLimiter(max_requests=2, window_seconds=10)
    now = 1000.0

    assert limiter.is_allowed("192.168.1.1", now=now) is True
    assert limiter.is_allowed("192.168.1.1", now=now) is True
    assert limiter.is_allowed("192.168.1.1", now=now) is False  # Limit reached

    # Different IP allowed
    assert limiter.is_allowed("192.168.1.2", now=now) is True

    # After window
    assert limiter.is_allowed("192.168.1.1", now=now + 11) is True
