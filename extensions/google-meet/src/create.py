"""Google Meet meeting creation routines via REST API or browser proxy fallback."""

from __future__ import annotations

from typing import Any, Callable

from .config import GoogleMeetConfig
from .meet import create_google_meet_space
from .oauth import resolve_google_meet_access_token
from .transports.chrome_create import create_meet_with_browser_proxy_on_node


def normalize_transport(value: Any) -> str | None:
    if value in ("chrome", "chrome-node", "twilio"):
        return str(value)
    return None


def normalize_mode(value: Any) -> str | None:
    if value == "realtime":
        return "agent"
    if value in ("agent", "bidi", "transcribe"):
        return str(value)
    return None


def normalize_google_meet_access_type(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().upper().replace("-", "_")
    return normalized if normalized in ("OPEN", "TRUSTED", "RESTRICTED") else None


def normalize_google_meet_entry_point_access(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().upper().replace("-", "_")
    return normalized if normalized in ("ALL", "CREATOR_APP_ONLY") else None


def resolve_create_space_config(raw: dict[str, Any]) -> dict[str, Any] | None:
    raw_access_type = raw.get("accessType")
    raw_entry_point_access = raw.get("entryPointAccess")
    access_type = normalize_google_meet_access_type(raw_access_type) if raw_access_type else None
    entry_point_access = (
        normalize_google_meet_entry_point_access(raw_entry_point_access)
        if raw_entry_point_access
        else None
    )

    if raw_access_type is not None and not access_type:
        raise ValueError("Invalid Google Meet accessType. Expected OPEN, TRUSTED, or RESTRICTED.")
    if raw_entry_point_access is not None and not entry_point_access:
        raise ValueError("Invalid Google Meet entryPointAccess. Expected ALL or CREATOR_APP_ONLY.")

    config: dict[str, Any] = {}
    if access_type:
        config["accessType"] = access_type
    if entry_point_access:
        config["entryPointAccess"] = entry_point_access
    return config if config else None


def has_create_space_config_input(raw: dict[str, Any]) -> bool:
    return raw.get("accessType") is not None or raw.get("entryPointAccess") is not None


def has_google_meet_oauth(config: GoogleMeetConfig, raw: dict[str, Any]) -> bool:
    return bool(
        raw.get("accessToken")
        or raw.get("refreshToken")
        or config.oauth.access_token
        or config.oauth.refresh_token
    )


async def create_space_from_params(config: GoogleMeetConfig, raw: dict[str, Any]) -> dict[str, Any]:
    token = await resolve_google_meet_access_token(
        client_id=raw.get("clientId") or config.oauth.client_id,
        client_secret=raw.get("clientSecret") or config.oauth.client_secret,
        refresh_token=raw.get("refreshToken") or config.oauth.refresh_token,
        access_token=raw.get("accessToken") or config.oauth.access_token,
        expires_at=raw.get("expiresAt")
        if isinstance(raw.get("expiresAt"), int)
        else config.oauth.expires_at,
    )
    result = await create_google_meet_space(
        access_token=token.access_token,
        config=resolve_create_space_config(raw),
    )
    return {
        "source": "api",
        "token": token,
        "space": result.space,
        "meeting_uri": result.meeting_uri,
    }


async def create_meet_from_params(
    *,
    config: GoogleMeetConfig,
    runtime: Any,
    raw: dict[str, Any],
) -> dict[str, Any]:
    if has_google_meet_oauth(config, raw):
        res = await create_space_from_params(config, raw)
        return {
            **res,
            "joined": False,
            "next_action": (
                "URL-only creation was requested. Call google_meet with action=join and url=meetingUri to enter the meeting."
            ),
        }

    if has_create_space_config_input(raw):
        raise ValueError(
            "Google Meet access policy options require OAuth/API room creation. Configure Google Meet OAuth or remove accessType/entryPointAccess."
        )

    browser = await create_meet_with_browser_proxy_on_node(
        runtime=runtime,
        config=config,
    )
    space_name = f"browser/{browser.meeting_uri.split('/')[-1]}"
    return {
        "source": browser.source,
        "meeting_uri": browser.meeting_uri,
        "joined": False,
        "next_action": (
            "URL-only creation was requested. Call google_meet with action=join and url=meetingUri to enter the meeting."
        ),
        "space": {
            "name": space_name,
            "meeting_uri": browser.meeting_uri,
        },
        "browser": {
            "node_id": browser.node_id,
            "target_id": browser.target_id,
            "browser_url": browser.browser_url,
            "browser_title": browser.browser_title,
            "notes": browser.notes,
        },
    }


async def create_and_join_meet_from_params(
    *,
    config: GoogleMeetConfig,
    runtime: Any,
    raw: dict[str, Any],
    ensure_runtime: Callable[[], Any],
) -> dict[str, Any]:
    created = await create_meet_from_params(
        config=config,
        runtime=runtime,
        raw=raw,
    )
    rt = await ensure_runtime()
    meeting_uri = created.get("meeting_uri") or (created.get("space") or {}).get("meeting_uri")
    join_res = await rt.join(
        url=meeting_uri,
        transport=normalize_transport(raw.get("transport")),
        mode=normalize_mode(raw.get("mode")),
        dial_in_number=raw.get("dialInNumber"),
        pin=raw.get("pin"),
        dtmf_sequence=raw.get("dtmfSequence"),
        message=raw.get("message"),
        requester_session_key=raw.get("requesterSessionKey"),
        agent_id=raw.get("agentId"),
    )
    return {
        **created,
        "joined": True,
        "next_action": "Share meetingUri with participants; the JARVIS agent has started the join flow.",
        "join": join_res,
    }
