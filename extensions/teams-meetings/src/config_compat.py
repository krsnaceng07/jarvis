"""Legacy configuration migration helper for Teams Meetings."""

from __future__ import annotations

from typing import Any


def migrate_legacy_teams_meetings_config(
    raw: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    migrated = dict(raw)
    changed = False

    # Migrate legacy flat keys to nested structures
    if "guest_name" in migrated:
        migrated.setdefault("chrome", {})["guestName"] = migrated.pop("guest_name")
        changed = True

    if "auto_join" in migrated:
        migrated.setdefault("chrome", {})["autoJoin"] = migrated.pop("auto_join")
        changed = True

    if "node" in migrated:
        migrated.setdefault("chromeNode", {})["node"] = migrated.pop("node")
        changed = True

    return migrated, changed
