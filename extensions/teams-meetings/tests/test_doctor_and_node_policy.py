"""Tests for Teams Meetings node invoke policy and doctor inspection."""

from __future__ import annotations

from typing import Any

import pytest

from extensions.teams_meetings.src import runtime_probes
from extensions.teams_meetings.src.doctor import run_teams_meetings_doctor
from extensions.teams_meetings.src.node_invoke_policy import (
    TeamsMeetingsChromeNodeInvokePolicy,
)
from extensions.teams_meetings.src.transports.types import (
    TeamsMeetingsChromeHealth,
    TeamsMeetingsChromeSession,
    TeamsMeetingsJoinRequest,
    TeamsMeetingsJoinResult,
    TeamsMeetingsJoinResultSession,
    TeamsMeetingsSession,
)


def test_node_invoke_policy() -> None:
    policy = TeamsMeetingsChromeNodeInvokePolicy()

    # setup
    assert policy.evaluate({"params": {"action": "setup"}}).get("ok") is True

    # query_tabs
    assert policy.evaluate({"params": {"action": "query_tabs"}}).get("ok") is True

    # start with valid work Teams URL
    assert (
        policy.evaluate(
            {
                "params": {
                    "action": "start",
                    "url": "https://teams.microsoft.com/l/meetup-join/19%3ameeting_xyz%40thread.v2/0",
                }
            }
        ).get("ok")
        is True
    )

    # start with valid consumer Teams URL
    assert (
        policy.evaluate(
            {
                "params": {
                    "action": "start",
                    "url": "https://teams.live.com/meet/948329482934",
                }
            }
        ).get("ok")
        is True
    )

    # start with invalid URL
    assert (
        policy.evaluate(
            {"params": {"action": "start", "url": "https://meet.google.com/abc-defg-hij"}}
        ).get("ok")
        is False
    )


@pytest.mark.asyncio
async def test_doctor_inspection_and_repair() -> None:
    legacy_config = {
        "guest_name": "OldGuest",
        "auto_join": True,
        "node": "node-1",
    }
    # Inspect without fix
    res_warn = await run_teams_meetings_doctor(config=legacy_config, fix=False)
    assert res_warn.is_ok is True
    report_warn = res_warn.unwrap()
    assert report_warn["ok"] is False
    assert any(c["status"] == "warn" for c in report_warn["checks"])

    # Fix
    res_fix = await run_teams_meetings_doctor(config=legacy_config, fix=True)
    assert res_fix.is_ok is True
    report_fix = res_fix.unwrap()
    assert report_fix["ok"] is True
    assert "Migrated legacy" in report_fix["fixesApplied"][0]


class MockTeamsProbeContext:
    def __init__(self) -> None:
        from extensions.teams_meetings.src.config import resolve_teams_meetings_config

        self.config = resolve_teams_meetings_config({}).unwrap()

    async def join(self, request: TeamsMeetingsJoinRequest) -> TeamsMeetingsJoinResult:
        session = TeamsMeetingsSession(
            id="teams_session_123",
            url=request.url,
            transport=request.transport or "chrome",
            mode=request.mode or "agent",
            chrome=TeamsMeetingsChromeSession(
                health=TeamsMeetingsChromeHealth(
                    in_call=True,
                    transcript_lines=5,
                    last_caption_text="Teams speech verified",
                )
            ),
        )
        return TeamsMeetingsJoinResult(
            session=TeamsMeetingsJoinResultSession(
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
async def test_teams_runtime_probes() -> None:
    ctx = MockTeamsProbeContext()

    # speech probe rejects transcribe mode
    with pytest.raises(ValueError, match="test_speech requires mode: agent or bidi"):
        await runtime_probes.test_teams_meetings_speech(
            ctx,
            TeamsMeetingsJoinRequest(
                url="https://teams.microsoft.com/l/meetup-join/19%3ameeting_xyz%40thread.v2/0",
                mode="transcribe",
            ),
        )

    # listening probe rejects agent mode
    with pytest.raises(ValueError, match="test_listen requires mode: transcribe"):
        await runtime_probes.test_teams_meetings_listening(
            ctx,
            TeamsMeetingsJoinRequest(
                url="https://teams.microsoft.com/l/meetup-join/19%3ameeting_xyz%40thread.v2/0",
                mode="agent",
            ),
        )

    # speech probe succeeds
    speech_res = await runtime_probes.test_teams_meetings_speech(
        ctx,
        TeamsMeetingsJoinRequest(
            url="https://teams.microsoft.com/l/meetup-join/19%3ameeting_xyz%40thread.v2/0",
            mode="agent",
            message="Say exactly: Microsoft Teams speech test complete.",
        ),
    )
    assert speech_res["ok"] is True
    assert speech_res["speechOutputVerified"] is True
    assert speech_res["inCall"] is True
