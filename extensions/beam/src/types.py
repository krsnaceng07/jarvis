"""Beam types and parsing validation.

OpenClaw parity: mirrors extensions/beam/src/types.ts.
"""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any, Literal, TypedDict

BEAM_HOST_ID = "gateway"
BEAM_SESSION_SHARE_ROUTE = {
    "kind": "thread-id-prefix",
    "routeSegment": "beam",
    "hostId": BEAM_HOST_ID,
    "identifierAlphabet": "lowercase-hex",
    "fullLength": 32,
    "minPrefixLength": 12,
    "lookup": "catalog-list-search-by-thread-id-prefix",
    "ambiguity": "multiple-results-or-next-cursor",
}
BEAM_MAX_BODY_BYTES = 56 * 1024  # 56 KiB
BEAM_RETENTION_MS = 7 * 24 * 60 * 60 * 1000  # 7 days
BEAM_MAX_SESSIONS = 500
BEAM_MAX_ITEMS = 200
BEAM_MAX_ITEM_CHARS = 6_000

BEAM_ID_RE = re.compile(r"^[0-9a-f]{32}$")
ISO_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})$")


class BeamTranscriptItem(TypedDict):
    type: Literal["userMessage", "agentMessage", "other"]
    text: str


class BeamSourceModel(TypedDict):
    provider: str
    model: str


class BeamUpload(TypedDict, total=False):
    version: int
    beamId: str
    source: str
    title: str
    updatedAt: str
    completed: bool
    truncated: bool | None
    hookEvent: str | None
    sourceModel: BeamSourceModel | None
    items: list[BeamTranscriptItem]


class BeamStoredSession(TypedDict, total=False):
    version: int
    beamId: str
    source: str
    title: str
    updatedAt: str
    completed: bool
    truncated: bool | None
    hookEvent: str | None
    sourceModel: BeamSourceModel | None
    items: list[BeamTranscriptItem]
    uploaderProfileId: str | None
    createdAt: int
    receivedAt: int


def is_iso_timestamp(val: str) -> bool:
    if not isinstance(val, str) or not ISO_TS_RE.match(val):
        return False
    try:
        datetime.fromisoformat(val.replace("Z", "+00:00"))
        return True
    except Exception:
        return False


def slugify_title(title: str) -> str:
    """Convert a title to a URL slug (lowercase, hyphens, alphanumeric only)."""
    if not title or not isinstance(title, str):
        return ""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", title.strip().lower())
    return slug.strip("-")


def build_beam_url(title: str, beam_id: str, base_path: str | None = None) -> str:
    """Build canonical Control UI Beam URL with 12-char prefix."""
    slug = slugify_title(title)
    prefix_id = beam_id[:12].lower()
    segment = f"{slug}-{prefix_id}" if slug else prefix_id
    base = base_path.rstrip("/") if base_path else ""
    return f"{base}/beam/{segment}"


def parse_beam_upload(value: Any) -> tuple[bool, BeamUpload | None, str | None]:
    if not isinstance(value, dict):
        return False, None, "request body must be a closed Beam object"

    allowed_keys = {
        "version",
        "beamId",
        "source",
        "title",
        "updatedAt",
        "completed",
        "truncated",
        "hookEvent",
        "sourceModel",
        "items",
    }
    if not set(value.keys()).issubset(allowed_keys):
        return False, None, "request body contains unsupported keys"

    if value.get("version") != 1:
        return False, None, "version must be 1"

    beam_id = value.get("beamId")
    if not isinstance(beam_id, str) or not BEAM_ID_RE.match(beam_id):
        return False, None, "beamId must be 32 lowercase hex characters"

    source = value.get("source")
    if not isinstance(source, str) or not (1 <= len(source) <= 64):
        return False, None, "source must be between 1 and 64 characters"

    title = value.get("title")
    if not isinstance(title, str) or not (1 <= len(title) <= 200):
        return False, None, "title must be between 1 and 200 characters"

    updated_at = value.get("updatedAt")
    if not isinstance(updated_at, str) or not is_iso_timestamp(updated_at):
        return False, None, "updatedAt must be a valid ISO timestamp"

    if not isinstance(value.get("completed"), bool):
        return False, None, "completed must be a boolean"

    items_raw = value.get("items")
    if not isinstance(items_raw, list) or len(items_raw) > BEAM_MAX_ITEMS:
        return False, None, f"items must be an array of at most {BEAM_MAX_ITEMS} entries"

    parsed_items: list[BeamTranscriptItem] = []
    for item in items_raw:
        if not isinstance(item, dict):
            return False, None, "items must contain objects"
        itype = item.get("type")
        if itype not in ("userMessage", "agentMessage", "other"):
            return False, None, "item type must be userMessage, agentMessage, or other"
        itext = item.get("text")
        if not isinstance(itext, str) or len(itext) == 0:
            return False, None, "item text must be non-empty string"
        if len(itext) > BEAM_MAX_ITEM_CHARS:
            return (
                False,
                None,
                f"item text must be string of at most {BEAM_MAX_ITEM_CHARS} characters",
            )
        parsed_items.append({"type": itype, "text": itext})

    upload: BeamUpload = {
        "version": 1,
        "beamId": beam_id,
        "source": source,
        "title": title,
        "updatedAt": updated_at,
        "completed": bool(value["completed"]),
        "items": parsed_items,
    }

    if "truncated" in value and value["truncated"] is not None:
        upload["truncated"] = bool(value["truncated"])
    if "hookEvent" in value and isinstance(value["hookEvent"], str):
        upload["hookEvent"] = value["hookEvent"]
    if "sourceModel" in value and isinstance(value["sourceModel"], dict):
        upload["sourceModel"] = {
            "provider": str(value["sourceModel"].get("provider", "")),
            "model": str(value["sourceModel"].get("model", "")),
        }

    return True, upload, None


__all__ = [
    "BEAM_HOST_ID",
    "BEAM_ID_RE",
    "BEAM_MAX_BODY_BYTES",
    "BEAM_MAX_ITEMS",
    "BEAM_MAX_ITEM_CHARS",
    "BEAM_MAX_SESSIONS",
    "BEAM_RETENTION_MS",
    "BEAM_SESSION_SHARE_ROUTE",
    "BeamSourceModel",
    "BeamStoredSession",
    "BeamTranscriptItem",
    "BeamUpload",
    "build_beam_url",
    "is_iso_timestamp",
    "parse_beam_upload",
    "slugify_title",
]
