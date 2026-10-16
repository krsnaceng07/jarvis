"""Teams Meetings setup status and onboarding checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .config import TeamsMeetingsConfig
from .transports.teams_platform_adapter import is_talk_back_mode


@dataclass(slots=True)
class TeamsSetupCheck:
    id: str
    ok: bool
    message: str


@dataclass(slots=True)
class TeamsMeetingsSetupStatus:
    ok: bool
    checks: list[TeamsSetupCheck] = field(default_factory=list)


def get_teams_meetings_setup_status(
    config: TeamsMeetingsConfig,
    *,
    mode: str | None = None,
    transport: str | None = None,
    full_config: Any = None,
) -> TeamsMeetingsSetupStatus:
    checks: list[TeamsSetupCheck] = []
    resolved_mode = mode or config.default_mode
    resolved_transport = transport or config.default_transport
    needs_audio = is_talk_back_mode(resolved_mode)

    checks.append(
        TeamsSetupCheck(
            id="chrome-profile",
            ok=True,
            message=(
                "Local Chrome uses the JARVIS browser profile; chrome.browserProfile is passed to chrome-node hosts"
                if config.chrome.browser_profile
                else "Local Chrome uses the JARVIS browser profile; configure browser.defaultProfile to choose another profile"
            ),
        )
    )

    if needs_audio:
        has_pair = bool(config.chrome.audio_input_command and config.chrome.audio_output_command)
        has_bridge = bool(config.chrome.audio_bridge_command)
        has_backend = bool(config.chrome.audio_backend)
        is_ok = has_pair or has_bridge or has_backend
        checks.append(
            TeamsSetupCheck(
                id="audio-bridge",
                ok=is_ok,
                message=(
                    f"Teams talk-back audio bridge configured ({config.chrome.audio_backend})"
                    if is_ok
                    else "Teams talk-back audio bridge not configured"
                ),
            )
        )
    else:
        checks.append(
            TeamsSetupCheck(
                id="audio-bridge",
                ok=True,
                message="Teams observe-only mode does not require a realtime audio bridge",
            )
        )

    guest_ok = bool(
        config.chrome.guest_name and config.chrome.auto_join and config.chrome.reuse_existing_tab
    )
    checks.append(
        TeamsSetupCheck(
            id="guest-join-defaults",
            ok=guest_ok,
            message=(
                "Guest auto-join and tab reuse defaults are enabled"
                if guest_ok
                else "Set chrome.guestName, chrome.autoJoin, and chrome.reuseExistingTab for unattended guest joins"
            ),
        )
    )

    node_ok = resolved_transport != "chrome-node" or bool(config.chrome_node.node)
    checks.append(
        TeamsSetupCheck(
            id="chrome-node-target",
            ok=node_ok,
            message=(
                f"Teams Chrome node pinned to {config.chrome_node.node}"
                if config.chrome_node.node
                else "Teams Chrome node not pinned; automatic selection works when exactly one capable node is connected"
            ),
        )
    )

    all_ok = all(c.ok for c in checks)
    return TeamsMeetingsSetupStatus(ok=all_ok, checks=checks)
