"""Unit tests for visitor-access extension."""

import asyncio
import pytest

from extensions.visitor_access.src.cloudflare import VisitorPolicyClient
from extensions.visitor_access.src.config import (
    resolve_visitor_access_config,
)
from extensions.visitor_access.src.errors import (
    VisitorAccessError,
    visitor_error_text,
)
from extensions.visitor_access.src.visitors import (
    VisitorAccessService,
)


def test_resolve_visitor_access_config(sample_visitor_config):
    cfg = resolve_visitor_access_config(sample_visitor_config)
    assert cfg["accountId"] == "acc_12345"
    assert cfg["appId"] == "app_67890"
    assert cfg["apiToken"] == "secret_token_abc"
    assert cfg["defaultTtlDays"] == 14
    assert cfg["maxVisitors"] == 50


def test_resolve_config_missing_required():
    with pytest.raises(VisitorAccessError, match="accountId is required"):
        resolve_visitor_access_config({"appId": "1", "apiToken": "t"})


def test_visitor_error_text_redaction():
    token = "super-secret-token"
    err = VisitorAccessError(f"Failed auth using {token}")
    redacted = visitor_error_text(err, token)
    assert token not in redacted
    assert "[REDACTED]" in redacted


def test_service_invite_and_revoke(sample_visitor_config):
    mock_cf_emails = []

    def fake_http(url, method, data=None):
        nonlocal mock_cf_emails
        if method == "GET":
            return {
                "success": True,
                "result": [
                    {
                        "id": "pol_1",
                        "name": "Visitors (openclaw-managed)",
                        "include": [{"email": {"email": e}} for e in mock_cf_emails],
                    }
                ],
            }
        if method in ("PUT", "POST"):
            mock_cf_emails = [x["email"]["email"] for x in data["include"]]
            return {"success": True, "result": {"id": "pol_1"}}
        if method == "DELETE":
            mock_cf_emails = []
            return {"success": True, "result": {}}
        return {"success": True}

    cfg = resolve_visitor_access_config(sample_visitor_config)
    client = VisitorPolicyClient(cfg, http_requester=fake_http)
    service = VisitorAccessService(
        config=cfg,
        policy_client=client,
        github_fetcher=lambda gh: (
            {"email": f"{gh}@users.noreply.github.com"} if gh == "testuser" else {}
        ),
    )

    # 1. Invite by explicit email
    msg = asyncio.run(service.invite({"email": "alice@example.com", "days": 7}))
    assert "Granted visitor access to alice@example.com" in msg
    assert "alice@example.com" in mock_cf_emails

    # 2. Invite by GitHub
    msg_gh = asyncio.run(service.invite({"github": "testuser", "forever": True}))
    assert "Granted visitor access to testuser@users.noreply.github.com until never" in msg_gh
    assert "testuser@users.noreply.github.com" in mock_cf_emails

    # 3. List
    listing = asyncio.run(service.list())
    assert "alice@example.com" in listing
    assert "testuser@users.noreply.github.com" in listing

    # 4. Revoke by GitHub
    rev_gh = asyncio.run(service.revoke({"github": "testuser"}))
    assert "Revoked visitor access" in rev_gh
    assert "testuser@users.noreply.github.com" not in mock_cf_emails

    # 5. Revoke by email
    rev_em = asyncio.run(service.revoke({"email": "alice@example.com"}))
    assert "alice@example.com" in rev_em
    assert len(mock_cf_emails) == 0
