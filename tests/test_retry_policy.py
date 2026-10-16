"""Tests for src/infra/retry_policy.py.

Mirrors tests of OpenClaw's infra/retry-policy.ts and retry-after.ts.
"""

from __future__ import annotations

import pytest

from src.infra.retry_policy import (
    DISCORD_API_RETRY_DEFAULTS,
    TELEGRAM_API_RETRY_DEFAULTS,
    calculate_backoff_delay,
    extract_retry_after_ms,
    get_sdk_retry_max_wait_seconds,
    parse_retry_after_header_seconds,
    retry_async,
    should_inject_x_should_retry_false,
)


def test_parse_retry_after_header_seconds():
    assert parse_retry_after_header_seconds("30") == 30.0
    assert parse_retry_after_header_seconds("0") == 0.0
    assert parse_retry_after_header_seconds(None) is None
    assert parse_retry_after_header_seconds("invalid") is None


def test_extract_retry_after_ms():
    err_tg = {"parameters": {"retry_after": 5}}
    assert extract_retry_after_ms(err_tg) == 5000.0

    err_discord = {"retry_after": 2.5}
    assert extract_retry_after_ms(err_discord) == 2500.0

    assert extract_retry_after_ms(Exception("generic")) is None


def test_calculate_backoff_delay():
    cfg = DISCORD_API_RETRY_DEFAULTS  # min: 500, max: 30000, jitter: 0.1
    d1 = calculate_backoff_delay(1, cfg)
    assert 450 <= d1 <= 550  # 500 +- 10%

    d_ra = calculate_backoff_delay(1, cfg, retry_after_ms=4000)
    assert 3600 <= d_ra <= 4400  # 4000 +- 10%


def test_sdk_retry_max_wait_seconds(monkeypatch):
    monkeypatch.delenv("JARVIS_SDK_RETRY_MAX_WAIT_SECONDS", raising=False)
    monkeypatch.delenv("OPENCLAW_SDK_RETRY_MAX_WAIT_SECONDS", raising=False)

    assert get_sdk_retry_max_wait_seconds() == 60.0
    assert should_inject_x_should_retry_false(70.0) is True
    assert should_inject_x_should_retry_false(30.0) is False

    monkeypatch.setenv("OPENCLAW_SDK_RETRY_MAX_WAIT_SECONDS", "120")
    assert get_sdk_retry_max_wait_seconds() == 120.0

    monkeypatch.setenv("OPENCLAW_SDK_RETRY_MAX_WAIT_SECONDS", "off")
    assert get_sdk_retry_max_wait_seconds() is None
    assert should_inject_x_should_retry_false(100.0) is False


@pytest.mark.asyncio
async def test_retry_async_success():
    calls = 0

    async def fn():
        nonlocal calls
        calls += 1
        if calls < 2:
            raise Exception("HTTP 429 Rate limited")
        return "success"

    res = await retry_async(fn, config=TELEGRAM_API_RETRY_DEFAULTS)
    assert res == "success"
    assert calls == 2


@pytest.mark.asyncio
async def test_retry_async_non_retryable_raises():
    calls = 0

    async def fn():
        nonlocal calls
        calls += 1
        raise Exception("404 Not Found")

    with pytest.raises(Exception, match="404 Not Found"):
        await retry_async(fn)

    assert calls == 1
