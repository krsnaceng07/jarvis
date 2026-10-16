"""Unit tests for Zoom Meetings setup readiness and doctor configuration diagnostics."""

from __future__ import annotations

import pytest

from extensions.zoom_meetings.src.config import (
    ZoomMeetingsChromeNodeConfig,
    ZoomMeetingsConfig,
)
from extensions.zoom_meetings.src.doctor import run_zoom_meetings_doctor
from extensions.zoom_meetings.src.setup import get_zoom_meetings_setup_status


def test_setup_checks_readiness() -> None:
    # 1. Standard Chrome local setup
    cfg_local = ZoomMeetingsConfig(enabled=True, default_transport="chrome")
    status_local = get_zoom_meetings_setup_status(cfg_local)
    assert status_local.ok is True
    check_ids = {c.id: c.ok for c in status_local.checks}
    assert check_ids["zoom-meetings-enabled"] is True
    assert check_ids["chrome-launcher-ready"] is True
    assert check_ids["audio-devices-ready"] is True

    # 2. Chrome Node without node ID
    cfg_cn_bad = ZoomMeetingsConfig(
        enabled=True,
        default_transport="chrome-node",
        chrome_node=ZoomMeetingsChromeNodeConfig(node=None),
    )
    status_cn_bad = get_zoom_meetings_setup_status(cfg_cn_bad)
    assert status_cn_bad.ok is False

    # 3. Chrome Node with node ID
    cfg_cn_ok = ZoomMeetingsConfig(
        enabled=True,
        default_transport="chrome-node",
        chrome_node=ZoomMeetingsChromeNodeConfig(node="node_123"),
    )
    status_cn_ok = get_zoom_meetings_setup_status(cfg_cn_ok)
    assert status_cn_ok.ok is True


@pytest.mark.asyncio
async def test_doctor_diagnostics_and_repair() -> None:
    legacy_config = {
        "meetingUrl": "https://zoom.us/j/12345678901",
        "guestName": "Doctor Agent",
        "passcode": "secret123",
        "enabled": True,
    }

    # Diagnosis only
    res_diag = await run_zoom_meetings_doctor(legacy_config, fix=False)
    assert res_diag.is_ok
    data_diag = res_diag.unwrap()
    assert len(data_diag["repairs"]) == 3
    assert data_diag["fixed"] is False

    # Fix
    res_fix = await run_zoom_meetings_doctor(legacy_config, fix=True)
    assert res_fix.is_ok
    data_fix = res_fix.unwrap()
    assert data_fix["fixed"] is True
    assert data_fix["config"]["defaults"]["meeting"] == "https://zoom.us/j/12345678901"
    assert data_fix["config"]["chrome"]["guestName"] == "Doctor Agent"
    assert data_fix["config"]["chrome"]["passcode"] == "secret123"
