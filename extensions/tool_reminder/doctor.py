"""Doctor contract for tool_reminder.

Mirrors OpenClaw's ``doctor-contract-api.ts`` pattern. The host's
``jarvis doctor`` command (Phase 1C) calls each plugin's
``detect(state_dir, config)`` and prints a finding. ``apply()`` is a
no-op stub in 1C; a real migration lands when the legacy
``core/reminders.json`` schema is documented.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True, slots=True)
class DoctorFinding:
    """One legacy-data finding reported by a doctor's ``detect()``.

    Mirrors OpenClaw's ``MigrationDetection`` shape. The host's
    ``jarvis doctor`` prints one line per finding.
    """

    label: str
    """Human-readable description (e.g. 'Legacy MARK XXXIX-OR reminders')."""

    path: Path
    """The file path the legacy data was found at."""

    count: int
    """How many legacy items were found (0 means nothing to migrate)."""


def detect_reminder_legacy(state_dir: Path, config: dict[str, Any]) -> list[DoctorFinding]:
    """Find legacy ``core/reminders.json`` data and report it.

    Phase 1C is detect-only. ``apply()`` will land in Phase 2 once the
    legacy schema is documented in the migration plan.
    """
    legacy = state_dir / "core" / "reminders.json"
    if not legacy.exists():
        return []
    try:
        import json

        data = json.loads(legacy.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [
            DoctorFinding(
                label="Legacy MARK XXXIX-OR reminders (unreadable file)",
                path=legacy,
                count=0,
            )
        ]
    if not isinstance(data, dict):
        return [
            DoctorFinding(
                label="Legacy MARK XXXIX-OR reminders (unexpected shape)",
                path=legacy,
                count=0,
            )
        ]
    return [
        DoctorFinding(
            label="Legacy MARK XXXIX-OR reminders",
            path=legacy,
            count=len(data),
        )
    ]


__all__ = ["DoctorFinding", "detect_reminder_legacy"]
