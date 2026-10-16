"""Unit tests for Voice Call telephony providers (Mock, Twilio, Telnyx, Plivo)."""

from __future__ import annotations

import pytest

from extensions.voice_call.src.config import VoiceCallConfig
from extensions.voice_call.src.providers.mock_provider import MockVoiceProvider
from extensions.voice_call.src.providers.plivo_provider import PlivoVoiceProvider
from extensions.voice_call.src.providers.telnyx_provider import TelnyxVoiceProvider
from extensions.voice_call.src.providers.twilio_provider import (
    TwilioVoiceProvider,
    build_twiml_response,
    twiml_gather,
    twiml_say,
    twiml_stream,
)
from extensions.voice_call.src.types import (
    CallSession,
    DtmfRequest,
    InitiateCallRequest,
    SpeakRequest,
)


@pytest.mark.asyncio
async def test_mock_provider_lifecycle() -> None:
    provider = MockVoiceProvider()
    cfg = VoiceCallConfig(enabled=True, provider="mock")

    session = CallSession(
        id="call_mock_1",
        provider="mock",
        from_number="+15555550100",
        to_number="+15555550123",
        direction="outbound",
    )

    # 1. Initiate call
    req = InitiateCallRequest(to_number="+15555550123", message="Hello from mock test")
    res = await provider.initiate_call(req, cfg, session)
    assert res.ok is True
    assert session.is_active is True
    assert len(session.transcript) == 1
    assert session.transcript[0].text == "Hello from mock test"

    # 2. Speak
    spk_res = await provider.speak(
        SpeakRequest(call_id=session.id, text="Second turn"), session, cfg
    )
    assert spk_res.ok is True
    assert len(session.transcript) == 2

    # 3. DTMF
    dtmf_res = await provider.send_dtmf(
        DtmfRequest(call_id=session.id, digits="1234#"), session, cfg
    )
    assert dtmf_res.ok is True
    assert session.dtmf_log == ["1234#"]

    # 4. End call
    end_res = await provider.end_call(session, cfg)
    assert end_res is True
    assert session.status == "completed"
    assert session.is_active is False


def test_twilio_twiml_generation() -> None:
    say_elem = twiml_say("Hello caller", voice="alice")
    assert '<Say voice="alice" language="en-US">Hello caller</Say>' in say_elem

    gather_elem = twiml_gather(action_url="/webhook/gather", say_text="Press 1")
    assert '<Gather action="/webhook/gather"' in gather_elem
    assert "Press 1" in gather_elem

    stream_elem = twiml_stream(stream_url="wss://stream.jarvis.ai", custom_params={"callId": "123"})
    assert '<Stream url="wss://stream.jarvis.ai">' in stream_elem
    assert '<Parameter name="callId" value="123"/>' in stream_elem

    resp = build_twiml_response([say_elem, gather_elem])
    assert "<Response>" in resp
    assert "</Response>" in resp


@pytest.mark.asyncio
async def test_provider_credential_guards() -> None:
    # Twilio missing credentials
    tw_prov = TwilioVoiceProvider()
    cfg_empty = VoiceCallConfig(enabled=True, provider="twilio")
    session = CallSession(
        id="s1",
        provider="twilio",
        from_number="+15555550100",
        to_number="+15555550123",
        direction="outbound",
    )
    res_tw = await tw_prov.initiate_call(
        InitiateCallRequest(to_number="+15555550123"), cfg_empty, session
    )
    assert res_tw.ok is False
    assert "Twilio credentials missing" in (res_tw.error or "")

    # Telnyx missing credentials
    tel_prov = TelnyxVoiceProvider()
    res_tel = await tel_prov.initiate_call(
        InitiateCallRequest(to_number="+15555550123"), cfg_empty, session
    )
    assert res_tel.ok is False
    assert "Telnyx credentials missing" in (res_tel.error or "")

    # Plivo missing credentials
    pl_prov = PlivoVoiceProvider()
    res_pl = await pl_prov.initiate_call(
        InitiateCallRequest(to_number="+15555550123"), cfg_empty, session
    )
    assert res_pl.ok is False
    assert "Plivo credentials missing" in (res_pl.error or "")
