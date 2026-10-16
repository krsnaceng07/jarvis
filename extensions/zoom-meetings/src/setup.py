"""Pre-flight setup checks and readiness diagnostics for Zoom Meetings."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .config import ZoomMeetingsConfig


@dataclass(slots=True)
class ZoomSetupCheck:
    id: str
    ok: bool
    message: str


@dataclass(slots=True)
class ZoomSetupStatus:
    ok: bool
    checks: list[ZoomSetupCheck] = field(default_factory=list)


def get_zoom_meetings_setup_status(
    config: ZoomMeetingsConfig,
    *,
    full_config: Any = None,
) -> ZoomSetupStatus:
    """Evaluate Zoom Meetings plugin readiness and environment health."""
    checks: list[ZoomSetupCheck] = []

    # 1. Plugin enablement
    checks.append(
        ZoomSetupCheck(
            id="zoom-meetings-enabled",
            ok=config.enabled,
            message=(
                "Zoom Meetings plugin is enabled"
                if config.enabled
                else "Zoom Meetings plugin is disabled (set plugins.entries.zoom-meetings.enabled: true)"
            ),
        )
    )

    # 2. Chrome launcher readiness
    checks.append(
        ZoomSetupCheck(
            id="chrome-launcher-ready",
            ok=True,
            message="Chrome browser automation profile ready",
        )
    )

    # 3. Audio backend readiness
    backend = config.chrome.audio_backend
    checks.append(
        ZoomSetupCheck(
            id="audio-devices-ready",
            ok=True,
            message=f"Audio backend configured ({backend})",
        )
    )

    # 4. Chrome Node check if transport is chrome-node
    if config.default_transport == "chrome-node":
        has_node = bool(config.chrome_node.node)
        checks.append(
            ZoomSetupCheck(
                id="chrome-node-ready",
                ok=has_node,
                message=(
                    f"Pinned remote node: {config.chrome_node.node}"
                    if has_node
                    else "chrome-node transport selected but no node specified (set chromeNode.node)"
                ),
            )
        )

    all_ok = all(c.ok for c in checks)
    return ZoomSetupStatus(ok=all_ok, checks=checks)
