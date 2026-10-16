"""Tests for Google Meet pre-flight live test checklist and troubleshooting behavior."""

from __future__ import annotations

from typing import Any
import pytest

from extensions.google_meet.src import runtime_probes
from extensions.google_meet.src.config import resolve_google_meet_config
from extensions.google_meet.src.node_invoke_policy import GoogleMeetChromeNodeInvokePolicy
from extensions.google_meet.src.setup import (
    get_google_meet_setup_status,
    get_voice_call_webhook_exposure_check,
    is_provider_unreachable_webhook_url,
)
from extensions.google_meet.src.transports.types import (
    GoogleMeetChromeHealth,
    GoogleMeetChromeSession,
    GoogleMeetJoinRequest,
    GoogleMeetJoinResult,
    GoogleMeetJoinResultSession,
    GoogleMeetSession,
)


def test_is_provider_unreachable_webhook_url() -> None:
    # Loopback and local hostnames
    assert is_provider_unreachable_webhook_url("http://localhost:8080/webhook") is True
    assert is_provider_unreachable_webhook_url("http://127.0.0.1:3000/voice") is True
    assert is_provider_unreachable_webhook_url("http://0.0.0.0:8000") is True
    assert is_provider_unreachable_webhook_url("http://[::1]:8080") is True
    assert is_provider_unreachable_webhook_url("http://app.localhost/webhook") is True

    # Private IPv4 ranges (RFC 1918)
    assert is_provider_unreachable_webhook_url("http://10.0.0.1:8000/webhook") is True
    assert is_provider_unreachable_webhook_url("http://172.16.5.10:8000/webhook") is True
    assert is_provider_unreachable_webhook_url("http://172.31.255.255:8000/webhook") is True
    assert is_provider_unreachable_webhook_url("http://192.168.1.100:8000/webhook") is True

    # Link-local IPv4
    assert is_provider_unreachable_webhook_url("http://169.254.169.254/webhook") is True

    # Unique Local IPv6 (fc00::/7)
    assert is_provider_unreachable_webhook_url("http://[fc00::1]:8000/webhook") is True
    assert is_provider_unreachable_webhook_url("http://[fd12:3456:789a::1]:8000/webhook") is True

    # Public reachable URLs
    assert is_provider_unreachable_webhook_url("https://voice.example.com/voice/webhook") is False
    assert (
        is_provider_unreachable_webhook_url("https://abc123xyz.ngrok-free.app/voice/webhook")
        is False
    )
    assert (
        is_provider_unreachable_webhook_url("https://my-node.tailnet.ts.net/voice/webhook") is False
    )


def test_get_voice_call_webhook_exposure_check() -> None:
    # 1. Public URL
    chk_pub = get_voice_call_webhook_exposure_check(
        {"publicUrl": "https://voice.example.com/voice/webhook"}
    )
    assert chk_pub.ok is True
    assert "public webhook URL configured" in chk_pub.message

    # 2. Private URL
    chk_priv = get_voice_call_webhook_exposure_check({"publicUrl": "http://192.168.1.50:8000"})
    assert chk_priv.ok is False
    assert "local/private" in chk_priv.message

    # 3. Tunnel (ngrok)
    chk_tun = get_voice_call_webhook_exposure_check({"tunnel": {"provider": "ngrok"}})
    assert chk_tun.ok is True
    assert "tunnel" in chk_tun.message

    # 4. Tailscale
    chk_ts = get_voice_call_webhook_exposure_check({"tailscale": {"mode": "funnel"}})
    assert chk_ts.ok is True
    assert "Tailscale" in chk_ts.message

    # 5. Missing
    chk_none = get_voice_call_webhook_exposure_check({})
    assert chk_none.ok is False


def test_google_meet_setup_status_checks() -> None:
    cfg = resolve_google_meet_config(
        {
            "defaultTransport": "chrome-node",
            "chromeNode": {"node": "parallels-macos"},
            "chrome": {
                "guestName": "Jarvis Bot",
                "autoJoin": True,
                "reuseExistingTab": True,
                "audioInputCommand": ["parec", "--raw"],
                "audioOutputCommand": ["pacat", "--raw"],
                "waitForInCallMs": 5000,
            },
        }
    ).unwrap()

    status = get_google_meet_setup_status(cfg)
    check_ids = [c.id for c in status.checks]
    assert "chrome-node-target" in check_ids
    assert "guest-join-defaults" in check_ids
    assert "audio-bridge" in check_ids
    assert "intro-after-in-call" in check_ids

    # Pinned node check should be ok
    node_check = next(c for c in status.checks if c.id == "chrome-node-target")
    assert node_check.ok is True
    assert "parallels-macos" in node_check.message


def test_node_invoke_policy_setup_action() -> None:
    policy = GoogleMeetChromeNodeInvokePolicy()

    # setup action
    res_setup = policy.evaluate({"params": {"action": "setup"}})
    assert res_setup.get("ok") is True

    # query_tabs action
    res_query = policy.evaluate({"params": {"action": "query_tabs"}})
    assert res_query.get("ok") is True

    # create_room action
    res_create = policy.evaluate({"params": {"action": "create_room"}})
    assert res_create.get("ok") is True

    # start action with valid meet url
    res_start = policy.evaluate(
        {"params": {"action": "start", "url": "https://meet.google.com/abc-defg-hij"}}
    )
    assert res_start.get("ok") is True

    # start action with invalid url
    res_bad = policy.evaluate({"params": {"action": "start", "url": "https://zoom.us/j/12345"}})
    assert res_bad.get("ok") is False


class MockProbeContext:
    def __init__(self) -> None:
        self.config = resolve_google_meet_config({}).unwrap()

    async def join(self, request: GoogleMeetJoinRequest) -> GoogleMeetJoinResult:
        session = GoogleMeetSession(
            id="test_session_123",
            url=request.url,
            transport=request.transport or "chrome",
            mode=request.mode or "agent",
            chrome=GoogleMeetChromeSession(
                health=GoogleMeetChromeHealth(
                    in_call=True,
                    transcript_lines=3,
                    last_caption_text="Speech test complete",
                )
            ),
        )
        return GoogleMeetJoinResult(
            session=GoogleMeetJoinResultSession(
                id=session.id,
                url=session.url,
                transport=session.transport,
                mode=session.mode,
            ),
            reused=False,
        )

    async def refresh_caption_health(self, session: Any) -> None:
        pass


@pytest.mark.asyncio
async def test_runtime_probes_modes() -> None:
    ctx = MockProbeContext()

    # test_google_meet_speech rejects mode: "transcribe"
    with pytest.raises(ValueError, match="test_speech requires mode: agent or bidi"):
        await runtime_probes.test_google_meet_speech(
            ctx,
            GoogleMeetJoinRequest(url="https://meet.google.com/abc-defg-hij", mode="transcribe"),
        )

    # test_google_meet_listening rejects mode: "agent"
    with pytest.raises(ValueError, match="test_listen requires mode: transcribe"):
        await runtime_probes.test_google_meet_listening(
            ctx,
            GoogleMeetJoinRequest(url="https://meet.google.com/abc-defg-hij", mode="agent"),
        )

    # Valid speech probe invocation
    speech_res = await runtime_probes.test_google_meet_speech(
        ctx,
        GoogleMeetJoinRequest(
            url="https://meet.google.com/abc-defg-hij",
            mode="agent",
            message="Say exactly: Google Meet speech test complete.",
        ),
    )
    assert speech_res["ok"] is True
    assert speech_res["speechOutputVerified"] is True
    assert speech_res["speechOutputTimedOut"] is False
    assert speech_res["inCall"] is True
