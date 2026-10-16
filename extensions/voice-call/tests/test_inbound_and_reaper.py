"""Unit tests for inbound policy matrices, per-number routing, and stale call reaper."""

from __future__ import annotations

import time

import pytest

from extensions.voice_call.src.config import (
    VoiceCallConfig,
    VoiceCallNumberRouting,
    VoiceCallTTSConfig,
)
from extensions.voice_call.src.inbound import evaluate_inbound_call
from extensions.voice_call.src.reaper import StaleCallReaper
from extensions.voice_call.src.types import CallSession


def test_inbound_policy_evaluation() -> None:
    # 1. Disabled
    cfg_disabled = VoiceCallConfig(inbound_policy="disabled")
    res_dis = evaluate_inbound_call("+15555550100", "+15555550199", cfg_disabled)
    assert res_dis.allowed is False
    assert res_dis.reason == "inbound-policy-disabled"

    # 2. Open
    cfg_open = VoiceCallConfig(inbound_policy="open")
    res_open = evaluate_inbound_call("+15555550100", "+15555550199", cfg_open)
    assert res_open.allowed is True
    assert res_open.reason is None

    # 3. Allowlist (low-assurance caller-ID screen with E.164 normalization)
    cfg_allow = VoiceCallConfig(
        inbound_policy="allowlist",
        allow_from=["+15555550100", "+15555550101"],
    )
    res_allow_ok = evaluate_inbound_call("+1 (555) 555-0100", "+15555550199", cfg_allow)
    assert res_allow_ok.allowed is True

    res_allow_deny = evaluate_inbound_call("+15555550999", "+15555550199", cfg_allow)
    assert res_allow_deny.allowed is False
    assert res_allow_deny.reason == "caller-not-allowlisted"

    # 4. Pairing
    cfg_pair = VoiceCallConfig(inbound_policy="pairing")
    res_pair_fail = evaluate_inbound_call(
        "+15555550100", "+15555550199", cfg_pair, active_pairings=set()
    )
    assert res_pair_fail.allowed is False
    assert res_pair_fail.reason == "pairing-required"

    res_pair_ok = evaluate_inbound_call(
        "+15555550100", "+15555550199", cfg_pair, active_pairings={"+15555550100"}
    )
    assert res_pair_ok.allowed is True


def test_per_number_routing_override() -> None:
    custom_number = "+15555559000"
    cfg = VoiceCallConfig(
        agent_id="main",
        response_model="gpt-4o",
        response_system_prompt="Default assistant prompt",
        response_timeout_ms=30000,
        inbound_policy="disabled",
        tts=VoiceCallTTSConfig(provider="openai", voice="coral"),
        numbers={
            custom_number: VoiceCallNumberRouting(
                number=custom_number,
                agent_id="support-agent",
                inbound_policy="open",
                inbound_greeting="Welcome to VIP support line.",
                response_model="gemini-2.5-pro",
                response_system_prompt="You are a concise support specialist.",
                response_timeout_ms=15000,
                tts=VoiceCallTTSConfig(providers={"openai": {"speakerVoice": "alloy"}}),
            )
        },
    )

    # Calling general number -> disabled
    res_gen = evaluate_inbound_call("+15555550100", "+15555550199", cfg)
    assert res_gen.allowed is False

    # Calling VIP number -> open, routed to support-agent with custom overrides
    res_vip = evaluate_inbound_call("+15555550100", custom_number, cfg)
    assert res_vip.allowed is True
    assert res_vip.agent_id == "support-agent"
    assert res_vip.greeting == "Welcome to VIP support line."
    assert res_vip.response_model == "gemini-2.5-pro"
    assert res_vip.response_system_prompt == "You are a concise support specialist."
    assert res_vip.response_timeout_ms == 15000
    assert res_vip.tts_override is not None
    assert res_vip.tts_override.providers["openai"]["speakerVoice"] == "alloy"


@pytest.mark.asyncio
async def test_stale_call_reaper_unanswered_and_max_duration() -> None:
    reaper = StaleCallReaper(timeout_seconds=60, max_duration_seconds=300)
    cfg = VoiceCallConfig(stale_call_reaper_seconds=60, max_duration_seconds=300)
    now = time.time()

    # 1. Recent unanswered call -> not stale
    unanswered_recent = CallSession(
        id="c1",
        provider="mock",
        from_number="+155501",
        to_number="+155502",
        direction="outbound",
        status="initiated",
        created_at=now - 10,
        answered_at=None,
    )

    # 2. Stale unanswered call -> should be reaped as stale-unanswered
    unanswered_stale = CallSession(
        id="c2",
        provider="mock",
        from_number="+155501",
        to_number="+155502",
        direction="outbound",
        status="initiated",
        created_at=now - 120,
        answered_at=None,
    )

    # 3. Answered conversation (even if created long ago) -> not reaped by stale timer
    answered_active = CallSession(
        id="c3",
        provider="mock",
        from_number="+155501",
        to_number="+155502",
        direction="outbound",
        status="in-progress",
        created_at=now - 200,
        answered_at=now - 50,
        conversation_state="listening",
    )

    # 4. Answered call exceeding maxDurationSeconds (300s) -> reaped by max duration cap
    answered_over_max = CallSession(
        id="c4",
        provider="mock",
        from_number="+155501",
        to_number="+155502",
        direction="outbound",
        status="in-progress",
        created_at=now - 400,
        answered_at=now - 350,
    )

    sessions = {
        "c1": unanswered_recent,
        "c2": unanswered_stale,
        "c3": answered_active,
        "c4": answered_over_max,
    }

    stale_list = reaper.find_stale_sessions(sessions, current_time=now)
    stale_ids = [s.id for s, _ in stale_list]
    assert "c2" in stale_ids
    assert "c4" in stale_ids
    assert "c1" not in stale_ids
    assert "c3" not in stale_ids

    reaped_count = await reaper.reap_stale_sessions(sessions, cfg, current_time=now)
    assert reaped_count == 2
    assert unanswered_stale.status == "canceled"
    assert unanswered_stale.metadata["reaped_reason"] == "stale-unanswered-timeout"
    assert answered_over_max.status == "completed"
    assert answered_over_max.metadata["reaped_reason"] == "max-duration-exceeded"


@pytest.mark.asyncio
async def test_stale_call_reaper_disabled() -> None:
    # Setting timeout_seconds=0 disables unanswered reaper
    reaper = StaleCallReaper(timeout_seconds=0, max_duration_seconds=0)
    now = time.time()
    unanswered_old = CallSession(
        id="c_old",
        provider="mock",
        from_number="+155501",
        to_number="+155502",
        direction="outbound",
        status="initiated",
        created_at=now - 500,
        answered_at=None,
    )
    sessions = {"c_old": unanswered_old}
    stale_list = reaper.find_stale_sessions(sessions, current_time=now)
    assert len(stale_list) == 0
