"""Doctor contract for memory_core.

Mirrors OpenClaw's ``extensions/memory-core/src/public-artifacts.ts``
+ the migration contract shape. Phase 2 ships ``detect`` only;
``apply`` lands in Phase 2.5.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from jarvis.doctor import DoctorFinding

if TYPE_CHECKING:
    from pathlib import Path


def detect_legacy(state_dir: Path, config: dict[str, Any]) -> list[DoctorFinding]:
    """Find legacy ``memory/memory.json`` data and report it.

    The legacy JARVIS format was a JSON dict with no schema version
    and no category column. Phase 2.5 will write a migration that
    reads this file and bulk-inserts into the SQLite store.
    """
    legacy = state_dir / "memory" / "memory.json"
    if not legacy.exists():
        return []
    try:
        data: dict[str, object] = json.loads(legacy.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [
            DoctorFinding(
                label="Legacy memory.json (unreadable file)",
                path=legacy,
                count=0,
            )
        ]
    if not isinstance(data, dict):
        return [
            DoctorFinding(
                label="Legacy memory.json (unexpected shape)",
                path=legacy,
                count=0,
            )
        ]
    return [
        DoctorFinding(
            label="Legacy memory.json (pre-Phase-2 format)",
            path=legacy,
            count=len(data),
            details={"sample_keys": list(data.keys())[:5]},
        )
    ]


__all__ = ["detect_legacy"]
