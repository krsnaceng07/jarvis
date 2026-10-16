"""Unit tests for Voice Call setup pre-flight verification, smoke tests, and doctor diagnostics."""

from __future__ import annotations

import pytest

from extensions.voice_call.src.config import (
    VoiceCallConfig,
    VoiceCallRealtimeConfig,
    VoiceCallStreamingConfig,
    VoiceCallTwilioConfig,
)
from extensions.voice_call.src.doctor import run_voice_call_doctor
from extensions.voice_call.src.runtime import VoiceCallRuntime
from extensions.voice_call.src.setup import get_voice_call_setup_status


def test_setup_checks_readiness() -> None:
    # 1. Incomplete Twilio config without credentials or webhook
    cfg_incomplete = VoiceCallConfig(
        enabled=True,
        provider="twilio",
    )
    status_incomplete = get_voice_call_setup_status(cfg_incomplete, env={})
    assert status_incomplete.ok is False
    check_ids = {c.id: c.ok for c in status_incomplete.checks}
    assert check_ids["voice-call-enabled"] is True
    assert check_ids["twilio-credentials"] is False
    assert check_ids["webhook-exposure"] is False

    # 2. Complete Twilio config
    cfg_complete = VoiceCallConfig(
        enabled=True,
        provider="twilio",
        from_number="+15555550100",
        public_url="https://voice.example.com",
        twilio=VoiceCallTwilioConfig(
            account_sid="AC12345",
            auth_token="secret_token",
        ),
    )
    status_complete = get_voice_call_setup_status(cfg_complete, env={})
    assert status_complete.ok is True

    # 3. Audio mode mutual exclusion check
    cfg_dual = VoiceCallConfig(
        enabled=True,
        provider="mock",
        mode="turn",
        realtime=VoiceCallRealtimeConfig(enabled=True),
        streaming=VoiceCallStreamingConfig(enabled=True),
    )
    status_dual = get_voice_call_setup_status(cfg_dual, env={})
    assert status_dual.ok is False
    check_ids_dual = {c.id: c.ok for c in status_dual.checks}
    assert check_ids_dual["only-one-audio-mode-active"] is False


@pytest.mark.asyncio
async def test_smoke_test_flow() -> None:
    cfg = VoiceCallConfig(enabled=True, provider="mock")
    runtime = VoiceCallRuntime(cfg)

    # Dry run
    res_dry = await runtime.smoke_test(to_number="+15555550123", live=False)
    assert res_dry.is_ok
    data_dry = res_dry.unwrap()
    assert data_dry["dryRun"] is True
    assert data_dry["status"] == "ready"

    # Live call
    res_live = await runtime.smoke_test(to_number="+15555550123", live=True)
    assert res_live.is_ok
    data_live = res_live.unwrap()
    assert data_live["dryRun"] is False
    assert data_live["status"] in ("ringing", "in-progress")


@pytest.mark.asyncio
async def test_doctor_diagnostics_and_fix() -> None:
    legacy_config = {
        "callerId": "(555) 555-0100",
        "twilioAccountSid": "AC_doc_123",
        "twilioAuthToken": "doc_token",
        "publicUrl": "https://voice.example.com",
        "enabled": True,
    }

    # Diagnosis only
    res_diag = await run_voice_call_doctor(legacy_config, fix=False)
    assert res_diag.is_ok
    data_diag = res_diag.unwrap()
    assert len(data_diag["repairs"]) > 0

    # Auto-fix
    res_fix = await run_voice_call_doctor(legacy_config, fix=True)
    assert res_fix.is_ok
    data_fix = res_fix.unwrap()
    assert data_fix["fixed"] is True
    assert data_fix["config"]["fromNumber"] == "+15555550100"
    assert data_fix["config"]["twilio"]["accountSid"] == "AC_doc_123"
