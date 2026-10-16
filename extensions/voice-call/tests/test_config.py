"""Unit tests for Voice Call configuration, validation, and normalization."""

from __future__ import annotations

import pytest

from extensions.voice_call.src.config import resolve_voice_call_config
from extensions.voice_call.src.config_compat import migrate_legacy_voice_call_config
from extensions.voice_call.src.phone_utils import (
    is_valid_e164_phone_number,
    normalize_e164_phone_number,
)
from extensions.voice_call.src.secret_ref import resolve_secret_value
from extensions.voice_call.src.session_keys import (
    resolve_explicit_session_key,
    resolve_voice_session_key,
)
from extensions.voice_call.src.streaming_guard import (
    StreamingConnectionCaps,
    StreamingConnectionTracker,
)
from extensions.voice_call.src.webhook_utils import (
    is_provider_unreachable_webhook_url,
    resolve_public_webhook_url,
)


def test_phone_utils_validation_and_normalization() -> None:
    assert is_valid_e164_phone_number("+15555550123") is True
    assert is_valid_e164_phone_number("+442071838750") is True
    assert is_valid_e164_phone_number("5555550123") is False
    assert is_valid_e164_phone_number("+012345") is False
    assert is_valid_e164_phone_number(None) is False

    assert normalize_e164_phone_number("+1 (555) 555-0123") == "+15555550123"
    assert normalize_e164_phone_number("5555550123", default_country_code="1") == "+15555550123"
    assert normalize_e164_phone_number("15555550123", default_country_code="1") == "+15555550123"

    with pytest.raises(ValueError, match="Invalid E.164"):
        normalize_e164_phone_number("+")

    with pytest.raises(ValueError, match="No digits found"):
        normalize_e164_phone_number("abc")


def test_webhook_utils_reachability() -> None:
    # Public URLs
    assert is_provider_unreachable_webhook_url("https://example.ngrok.app/webhook") is False
    assert is_provider_unreachable_webhook_url("https://voice.jarvis.ai/webhook") is False

    # Loopback / Private unreachable URLs
    assert is_provider_unreachable_webhook_url("http://localhost:7433/webhook") is True
    assert is_provider_unreachable_webhook_url("http://127.0.0.1:7433/webhook") is True
    assert is_provider_unreachable_webhook_url("http://0.0.0.0:8000") is True
    assert is_provider_unreachable_webhook_url("http://192.168.1.50:8080") is True
    assert is_provider_unreachable_webhook_url("http://10.0.0.5:8080") is True
    assert is_provider_unreachable_webhook_url("http://172.16.0.2:8080") is True
    assert is_provider_unreachable_webhook_url(None) is True
    assert is_provider_unreachable_webhook_url("not-a-url") is True

    # Resolution
    res_direct = resolve_public_webhook_url(public_url="https://api.example.com")
    assert res_direct == "https://api.example.com"

    res_tunnel = resolve_public_webhook_url(
        tunnel={"provider": "cloudflare", "url": "https://jarvis.trycloudflare.com"}
    )
    assert res_tunnel == "https://jarvis.trycloudflare.com"

    res_tailscale = resolve_public_webhook_url(
        tailscale={"mode": "funnel", "target": "https://node.tailscale.net"}
    )
    assert res_tailscale == "https://node.tailscale.net"


def test_config_resolution_and_defaults() -> None:
    res = resolve_voice_call_config({})
    assert res.is_ok
    cfg = res.unwrap()
    assert cfg.enabled is False
    assert cfg.provider == "twilio"
    assert cfg.inbound_policy == "disabled"
    assert cfg.session_scope == "per-phone"
    assert cfg.max_duration_seconds == 300
    assert cfg.stale_call_reaper_seconds == 120
    assert cfg.silence_timeout_ms == 800
    assert cfg.transcript_timeout_ms == 180000
    assert cfg.ring_timeout_ms == 30000
    assert cfg.max_concurrent_calls == 1
    assert cfg.agent_id == "main"
    assert cfg.mode == "turn"
    assert cfg.twilio.region == "us1"


def test_secret_ref_resolution() -> None:
    env = {"TWILIO_SECRET": "resolved_token_123"}

    assert resolve_secret_value("plain_val", env) == "plain_val"
    assert resolve_secret_value({"secret": "TWILIO_SECRET"}, env) == "resolved_token_123"
    assert resolve_secret_value({"$secret": "TWILIO_SECRET"}, env) == "resolved_token_123"
    assert resolve_secret_value("secret://TWILIO_SECRET", env) == "resolved_token_123"
    assert resolve_secret_value(None, env) is None

    cfg_dict = {
        "twilio": {
            "authToken": {"secret": "TWILIO_SECRET"},
            "region": "ie1",
        }
    }
    res = resolve_voice_call_config(cfg_dict, env=env)
    assert res.is_ok
    cfg = res.unwrap()
    assert cfg.twilio.auth_token == "resolved_token_123"
    assert cfg.twilio.region == "ie1"


def test_session_scope_key_resolution() -> None:
    # 1. per-phone
    k_phone = resolve_voice_session_key(
        scope="per-phone",
        agent_id="sales-bot",
        phone_number="+15555550123",
    )
    assert k_phone == "agent:sales-bot:voice:phone:+15555550123"

    # 2. per-call
    k_call = resolve_voice_session_key(
        scope="per-call",
        agent_id="support-bot",
        call_id="call_999",
    )
    assert k_call == "agent:support-bot:voice:call:call_999"

    # 3. main scope
    k_main = resolve_voice_session_key(
        scope="main",
        agent_id="main",
        core_session_scope="per-agent",
    )
    assert k_main == "agent:main:main"

    # 4. global core session scope aliasing
    k_global = resolve_voice_session_key(
        scope="main",
        agent_id="main",
        core_session_scope="global",
    )
    assert k_global == "global"

    # 5. explicit session keys
    assert resolve_explicit_session_key("global", "main") == "global"
    assert resolve_explicit_session_key("agent:main:main", "main", "global") == "global"
    assert (
        resolve_explicit_session_key("agent:other:foo", "main")
        == "agent:main:voice:foreign:agent_other_foo"
    )


def test_streaming_connection_caps() -> None:
    caps = StreamingConnectionCaps(
        pre_start_timeout_ms=100,
        max_pending_connections=2,
        max_pending_connections_per_ip=1,
        max_connections=3,
    )
    tracker = StreamingConnectionTracker(caps)

    # 1. Register first connection from IP A
    ok1, err1 = tracker.can_accept("192.168.1.10")
    assert ok1 is True
    tracker.register_pending("conn_1", "192.168.1.10")

    # 2. Second connection from same IP rejected by per-IP cap
    ok2, err2 = tracker.can_accept("192.168.1.10")
    assert ok2 is False
    assert "max-pending-per-ip-exceeded" in (err2 or "")

    # 3. Connection from IP B accepted
    ok3, _ = tracker.can_accept("192.168.1.20")
    assert ok3 is True
    tracker.register_pending("conn_2", "192.168.1.20")

    # 4. Third pending connection rejected by total pending cap
    ok4, err4 = tracker.can_accept("192.168.1.30")
    assert ok4 is False
    assert "max-pending-connections-exceeded" in (err4 or "")

    # 5. Mark conn_1 started -> frees pending slot
    assert tracker.mark_started("conn_1") is True
    ok5, _ = tracker.can_accept("192.168.1.30")
    assert ok5 is True


def test_config_all_eight_legacy_migrations() -> None:
    legacy = {
        "provider": "log",
        "twilio": {"from": "+15555550100"},
        "streaming": {
            "sttProvider": "deepgram",
            "openaiApiKey": "sk-legacy",
            "sttModel": "whisper-1",
            "silenceDurationMs": 750,
            "vadThreshold": 0.5,
        },
        "realtime": {
            "agentContext": {
                "includeSystemPrompt": True,
                "customKey": "keep_me",
            }
        },
    }

    migrated = migrate_legacy_voice_call_config(legacy)
    assert migrated["provider"] == "mock"
    assert migrated["fromNumber"] == "+15555550100"
    assert migrated["streaming"]["provider"] == "deepgram"
    assert migrated["streaming"]["providers"]["openai"]["apiKey"] == "sk-legacy"
    assert migrated["streaming"]["providers"]["openai"]["model"] == "whisper-1"
    assert migrated["streaming"]["providers"]["openai"]["silenceDurationMs"] == 750
    assert migrated["streaming"]["providers"]["openai"]["vadThreshold"] == 0.5
    assert "includeSystemPrompt" not in migrated["realtime"]["agentContext"]
    assert migrated["realtime"]["agentContext"]["customKey"] == "keep_me"
