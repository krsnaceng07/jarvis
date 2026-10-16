"""Tests for OAuth PKCE flow, token handling, and doctor health inspection."""

import time
import pytest

from extensions.google_meet.src.oauth import (
    GOOGLE_MEET_SCOPES,
    build_google_meet_auth_url,
    generate_pkce_challenge,
    generate_pkce_state,
    parse_oauth_callback_input,
    resolve_google_meet_token_expires_at,
    should_use_cached_google_meet_access_token,
)
from extensions.google_meet.src.cli_doctor import (
    sanitize_oauth_error_message,
)
from extensions.google_meet.src.doctor import run_google_meet_doctor


def test_pkce_generation():
    pkce = generate_pkce_challenge()
    assert "verifier" in pkce
    assert "challenge" in pkce
    assert len(pkce["verifier"]) >= 43
    assert len(pkce["challenge"]) > 0

    state = generate_pkce_state()
    assert len(state) >= 32


def test_build_auth_url():
    url = build_google_meet_auth_url(
        client_id="test-client-id",
        challenge="test-challenge",
        state="test-state",
    )
    assert "https://accounts.google.com/o/oauth2/v2/auth" in url
    assert "client_id=test-client-id" in url
    assert "code_challenge=test-challenge" in url
    assert "code_challenge_method=S256" in url
    assert "state=test-state" in url
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A8085%2Foauth2callback" in url
    for scope in GOOGLE_MEET_SCOPES:
        assert scope.replace("/", "%2F").replace(":", "%3A") in url or scope in url


def test_resolve_token_expires_at():
    now_ms = 1000000
    exp = resolve_google_meet_token_expires_at(3600, now_ms=now_ms)
    assert exp == now_ms + 3600 * 1000

    exp_default = resolve_google_meet_token_expires_at(None, now_ms=now_ms)
    assert exp_default == now_ms + 3600 * 1000


def test_should_use_cached_access_token():
    now_ms = int(time.time() * 1000)
    # Valid token expiring in 10 minutes
    assert should_use_cached_google_meet_access_token(
        access_token="valid-token",
        expires_at=now_ms + 600000,
    )
    # Expired token
    assert not should_use_cached_google_meet_access_token(
        access_token="expired-token",
        expires_at=now_ms - 1000,
    )
    # Missing access token
    assert not should_use_cached_google_meet_access_token(
        access_token=None,
        expires_at=now_ms + 600000,
    )


def test_parse_oauth_callback_input():
    # Valid URL input
    res = parse_oauth_callback_input(
        "http://localhost:8085/oauth2callback?code=abc123xyz&state=state456"
    )
    assert res.get("code") == "abc123xyz"
    assert res.get("state") == "state456"

    # Missing state
    err_state = parse_oauth_callback_input("http://localhost:8085/oauth2callback?code=abc123xyz")
    assert "error" in err_state

    # Missing code
    err_code = parse_oauth_callback_input("http://localhost:8085/oauth2callback?state=state456")
    assert "error" in err_code


def test_sanitize_oauth_error_message():
    raw_error = "Error: invalid access_token='ya29.secret123' and refresh_token='1//secret456' client_secret=secret789"
    sanitized = sanitize_oauth_error_message(raw_error)
    assert "ya29.secret123" not in sanitized
    assert "1//secret456" not in sanitized
    assert "secret789" not in sanitized
    assert "[redacted]" in sanitized


@pytest.mark.asyncio
async def test_google_meet_doctor_inspection():
    config = {
        "oauth": {
            "clientId": "my-client-id",
            "refreshToken": "my-refresh-token",
            "accessToken": "cached-token",
            "expiresAt": int(time.time() * 1000) + 3600000,
        },
        "defaultTransport": "chrome",
        "defaultMode": "agent",
    }
    res = await run_google_meet_doctor(config=config, fix=False)
    assert res.is_ok
    report = res.unwrap()
    assert report["ok"] is True
    check_ids = [c["id"] for c in report["checks"]]
    assert "config.legacy_keys" in check_ids
    assert "config.resolution" in check_ids
    assert "oauth.tokens" in check_ids
