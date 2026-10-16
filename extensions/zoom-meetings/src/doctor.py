"""Configuration diagnostics and automated repair for Zoom Meetings."""

from __future__ import annotations

from typing import Any

from jarvis_sdk import Ok, Result


async def run_zoom_meetings_doctor(
    config: dict[str, Any] | None,
    *,
    fix: bool = False,
) -> Result[dict[str, Any], str]:
    """Inspect and optionally repair Zoom Meetings configuration."""
    raw = dict(config or {})
    repairs: list[dict[str, str]] = []
    fixed_config = dict(raw)

    # 1. Check legacy top-level meetingUrl
    if "meetingUrl" in raw:
        old_val = raw["meetingUrl"]
        repairs.append(
            {
                "id": "migrate-top-level-meeting-url",
                "message": f"Moved legacy 'meetingUrl' ({old_val}) to 'defaults.meeting'",
            }
        )
        if fix:
            if "defaults" not in fixed_config:
                fixed_config["defaults"] = {}
            fixed_config["defaults"]["meeting"] = old_val
            fixed_config.pop("meetingUrl", None)

    # 2. Check legacy top-level guestName
    if "guestName" in raw:
        old_name = raw["guestName"]
        repairs.append(
            {
                "id": "migrate-top-level-guest-name",
                "message": f"Moved legacy 'guestName' ({old_name}) to 'chrome.guestName'",
            }
        )
        if fix:
            if "chrome" not in fixed_config:
                fixed_config["chrome"] = {}
            fixed_config["chrome"]["guestName"] = old_name
            fixed_config.pop("guestName", None)

    # 3. Check legacy top-level passcode
    if "passcode" in raw or "meetingPasscode" in raw:
        old_pwd = raw.get("passcode") or raw.get("meetingPasscode")
        repairs.append(
            {
                "id": "migrate-top-level-passcode",
                "message": "Moved legacy top-level passcode to 'chrome.passcode'",
            }
        )
        if fix:
            if "chrome" not in fixed_config:
                fixed_config["chrome"] = {}
            fixed_config["chrome"]["passcode"] = old_pwd
            fixed_config.pop("passcode", None)
            fixed_config.pop("meetingPasscode", None)

    return Ok(
        {
            "ok": True,
            "repairs": repairs,
            "fixed": fix and len(repairs) > 0,
            "config": fixed_config if fix else raw,
        }
    )
