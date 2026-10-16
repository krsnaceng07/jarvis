"""jarvis.plugins.beam — Beam coding session ingest plugin configuration & validation.

OpenClaw parity: implements the Beam session ingest contract.

Features:
- `BEAM_ROUTE_PATH`: `"/api/v1/beam/sessions"`
- `BEAM_MAX_BODY_BYTES`: `57_344` (56 KiB)
- `BEAM_MAX_ITEMS`: `200`
- `BEAM_MAX_ITEM_TEXT_CHARS`: `6000`
- `BEAM_MAX_STORED_SESSIONS`: `500`
- `BEAM_RETENTION_DAYS`: `7`
- `BEAM_ITEM_TYPES`: `"userMessage"`, `"agentMessage"`, `"other"`.
- `BeamMirrorConfig`: Dataclass containing mirror settings (`endpoint`, `token`, `catalogs`, `pollSeconds`, `activeWindowMinutes`).
- `resolve_beam_mirror_config()`: Parses `mirror` configuration block.
- `build_beam_session_url()`: Formats Control UI catalog URL for a Beam session.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

BEAM_ROUTE_PATH: str = "/api/v1/beam/sessions"
BEAM_MAX_BODY_BYTES: int = 56 * 1024  # 56 KiB (57,344 bytes)
BEAM_MAX_ITEMS: int = 200
BEAM_MAX_ITEM_TEXT_CHARS: int = 6000
BEAM_MAX_STORED_SESSIONS: int = 500
BEAM_RETENTION_DAYS: int = 7

BeamItemType = Literal["userMessage", "agentMessage", "other"]
BEAM_ITEM_TYPES: list[BeamItemType] = ["userMessage", "agentMessage", "other"]


@dataclass
class BeamMirrorConfig:
    endpoint: str
    catalogs: list[str]
    token: Any | None = None
    pollSeconds: int = 30
    activeWindowMinutes: int = 180


def resolve_beam_mirror_config(plugin_cfg: dict[str, Any] | None) -> BeamMirrorConfig | None:
    """Resolve Beam mirror options from configuration dictionary."""
    val = plugin_cfg if isinstance(plugin_cfg, dict) else {}
    mirror_raw = val.get("mirror")
    if not isinstance(mirror_raw, dict):
        return None

    endpoint = str(mirror_raw.get("endpoint") or "").strip()
    catalogs = mirror_raw.get("catalogs")
    if not endpoint or not isinstance(catalogs, list) or len(catalogs) == 0:
        return None

    poll_sec = int(mirror_raw.get("pollSeconds", 30))
    poll_sec = max(10, poll_sec)

    active_win = int(mirror_raw.get("activeWindowMinutes", 180))

    return BeamMirrorConfig(
        endpoint=endpoint,
        catalogs=[str(c).strip() for c in catalogs if str(c).strip()],
        token=mirror_raw.get("token"),
        pollSeconds=poll_sec,
        activeWindowMinutes=active_win,
    )


def build_beam_session_url(beam_id: str) -> str:
    """Build relative Control UI chat URL for a beamed session."""
    clean_id = beam_id.strip()
    return f"/chat/main?catalog=beam&host=gateway&thread={clean_id}"


__all__ = [
    "BEAM_ITEM_TYPES",
    "BEAM_MAX_BODY_BYTES",
    "BEAM_MAX_ITEMS",
    "BEAM_MAX_ITEM_TEXT_CHARS",
    "BEAM_MAX_STORED_SESSIONS",
    "BEAM_RETENTION_DAYS",
    "BEAM_ROUTE_PATH",
    "BeamItemType",
    "BeamMirrorConfig",
    "build_beam_session_url",
    "resolve_beam_mirror_config",
]
