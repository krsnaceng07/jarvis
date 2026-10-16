"""Unit tests for Voice Call cryptographic signature verification and webhook security."""

from __future__ import annotations

import base64
import hashlib
import hmac

from extensions.voice_call.src.config import VoiceCallWebhookSecurityConfig
from extensions.voice_call.src.security import (
    validate_allowed_host,
    validate_forwarding_headers,
    verify_plivo_signature,
    verify_telnyx_signature,
    verify_twilio_signature,
)


def test_twilio_signature_verification() -> None:
    auth_token = "12345secret"
    url = "https://example.com/webhook/voice/twilio/answer"
    params = {"CallSid": "CA12345", "From": "+15555550100", "To": "+15555550199"}

    # Compute expected signature
    sorted_keys = sorted(params.keys())
    data = url + "".join(f"{k}{params[k]}" for k in sorted_keys)
    sig = base64.b64encode(
        hmac.new(auth_token.encode("utf-8"), data.encode("utf-8"), hashlib.sha1).digest()
    ).decode("utf-8")

    assert verify_twilio_signature(auth_token, url, params, sig) is True
    assert verify_twilio_signature(auth_token, url, params, "invalid_sig") is False
    assert verify_twilio_signature("wrong_token", url, params, sig) is False
    assert verify_twilio_signature(auth_token, url, params, None) is False


def test_plivo_signature_verification() -> None:
    auth_token = "plivo_secret_token"
    url = "https://example.com/webhook/voice/plivo/answer"
    params = {"CallUUID": "uuid_123", "From": "+15555550100"}

    sorted_keys = sorted(params.keys())
    data = url + "".join(f"{k}{params[k]}" for k in sorted_keys)
    sig = base64.b64encode(
        hmac.new(auth_token.encode("utf-8"), data.encode("utf-8"), hashlib.sha256).digest()
    ).decode("utf-8")

    assert verify_plivo_signature(auth_token, url, params, sig) is True
    assert verify_plivo_signature(auth_token, url, params, "wrong_sig") is False


def test_telnyx_signature_verification() -> None:
    public_key = "telnyx_test_key"
    timestamp = "1700000000"
    payload = '{"data":{"event_type":"call.initiated"}}'

    msg = f"{timestamp}|{payload}".encode("utf-8")
    sig = base64.b64encode(
        hmac.new(public_key.encode("utf-8"), msg, hashlib.sha256).digest()
    ).decode("utf-8")

    assert verify_telnyx_signature(public_key, timestamp, payload, sig) is True
    assert verify_telnyx_signature(public_key, timestamp, payload, "bad_sig") is False


def test_webhook_security_hosts_and_forwarding() -> None:
    sec = VoiceCallWebhookSecurityConfig(
        allowed_hosts=["voice.example.com", "api.example.com"],
        trust_forwarding_headers=True,
        trusted_proxy_ips=["10.0.0.1", "192.168.1.0/24"],
    )

    # Allowed host check
    assert validate_allowed_host("voice.example.com", sec) is True
    assert validate_allowed_host("voice.example.com:443", sec) is True
    assert validate_allowed_host("evil.com", sec) is False
    assert validate_allowed_host(None, sec) is False

    # Forwarding headers check from trusted proxy
    ok, client_ip = validate_forwarding_headers(
        remote_ip="10.0.0.1",
        headers={"x-forwarded-for": "203.0.113.195, 10.0.0.1"},
        security_config=sec,
    )
    assert ok is True
    assert client_ip == "203.0.113.195"

    # Forwarding headers check from untrusted proxy
    ok_untrusted, _ = validate_forwarding_headers(
        remote_ip="8.8.8.8",
        headers={"x-forwarded-for": "203.0.113.195"},
        security_config=sec,
    )
    assert ok_untrusted is False


def test_public_url_reconstruction() -> None:
    from extensions.voice_call.src.security import reconstruct_public_url

    sec = VoiceCallWebhookSecurityConfig(
        allowed_hosts=["voice.example.com"],
        trust_forwarding_headers=False,
        trusted_proxy_ips=["10.0.0.1"],
    )

    # 1. Direct host
    url1 = reconstruct_public_url(
        request_path="/voice/webhook",
        headers={"Host": "voice.example.com"},
        remote_ip="10.0.0.1",
        security_config=sec,
    )
    assert url1 == "https://voice.example.com/voice/webhook"

    # 2. Forwarded headers from trusted proxy
    url2 = reconstruct_public_url(
        request_path="/voice/webhook",
        headers={
            "Host": "internal-svc:3334",
            "X-Forwarded-Host": "voice.example.com",
            "X-Forwarded-Proto": "https",
        },
        remote_ip="10.0.0.1",
        security_config=sec,
    )
    assert url2 == "https://voice.example.com/voice/webhook"

    # 3. Disallowed forwarded host is rejected/filtered
    url3 = reconstruct_public_url(
        request_path="/voice/webhook",
        headers={
            "Host": "internal-svc:3334",
            "X-Forwarded-Host": "attacker.com",
            "X-Forwarded-Proto": "https",
        },
        remote_ip="10.0.0.1",
        security_config=sec,
    )
    assert "attacker.com" not in url3


def test_webhook_replay_guard() -> None:
    from extensions.voice_call.src.security import WebhookReplayGuard

    guard = WebhookReplayGuard(ttl_seconds=10.0, max_entries=5)

    assert guard.is_replayed("sig_1", current_time=100.0) is False
    assert guard.is_replayed("sig_1", current_time=105.0) is True
    assert guard.is_replayed("sig_2", current_time=105.0) is False

    # After TTL expiry (100 + 10 = 110)
    assert guard.is_replayed("sig_1", current_time=112.0) is False


def test_turn_token_generation_and_verification() -> None:
    from extensions.voice_call.src.security import generate_turn_token, verify_turn_token

    tok0 = generate_turn_token("call_abc", 0, secret="secret123")
    assert len(tok0) == 16

    assert verify_turn_token(tok0, "call_abc", 0, secret="secret123") is True
    assert verify_turn_token(tok0, "call_abc", 1, secret="secret123") is False
    assert verify_turn_token(tok0, "call_other", 0, secret="secret123") is False
    assert verify_turn_token(None, "call_abc", 0, secret="secret123") is False


def test_in_flight_concurrency_limiter() -> None:
    from extensions.voice_call.src.security import InFlightConcurrencyLimiter

    limiter = InFlightConcurrencyLimiter(max_concurrent=2)

    assert limiter.acquire("key_a") is True
    assert limiter.acquire("key_a") is True
    assert limiter.acquire("key_a") is False  # Exceeded cap 2

    assert limiter.acquire("key_b") is True  # Separate key ok
    limiter.release("key_a")
    assert limiter.acquire("key_a") is True  # Now slot available


def test_required_webhook_headers() -> None:
    from extensions.voice_call.src.security import has_required_webhook_headers

    assert has_required_webhook_headers("mock", {}) is True
    assert has_required_webhook_headers("twilio", {}) is False
    assert has_required_webhook_headers("twilio", {"X-Twilio-Signature": "sig"}) is True
    assert has_required_webhook_headers("telnyx", {"telnyx-signature-ed25519": "sig"}) is False
    assert (
        has_required_webhook_headers(
            "telnyx", {"telnyx-signature-ed25519": "sig", "telnyx-timestamp": "123"}
        )
        is True
    )
    assert has_required_webhook_headers("plivo", {}) is False
    assert has_required_webhook_headers("plivo", {"X-Plivo-Signature-V3": "sig"}) is True
