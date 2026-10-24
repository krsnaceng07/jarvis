"""Autonomous Claws Doctor Contract — JARVIS Autonomous Architecture.

Verifies health, SQLite queue persistence, and registered daemons for the Claws subsystem.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from src.doctor import DoctorFinding, Severity


def check_claws_subsystem(
    state_dir: Path | None = None, config: Any | None = None
) -> list[DoctorFinding]:
    """Execute diagnostic checks on the Autonomous Claws subsystem."""
    findings: list[DoctorFinding] = []
    # Look for DB in state_dir or ~/.jarvis/state
    claws_db = (state_dir / "claws.sqlite") if state_dir and (state_dir / "claws.sqlite").exists() else (Path.home() / ".jarvis" / "state" / "claws.sqlite")

    # 1. Database check
    if not claws_db.exists():
        findings.append(
            DoctorFinding(
                plugin_id="claws",
                label="claws.database",
                path=claws_db,
                severity=Severity.WARNING,
                message="Claws SQLite state database not yet created; will be initialized on first run.",
            )
        )
    else:
        try:
            conn = sqlite3.connect(str(claws_db), timeout=5.0)
            cur = conn.execute("PRAGMA integrity_check;")
            res = cur.fetchone()[0]
            conn.close()
            if res == "ok":
                findings.append(
                    DoctorFinding(
                        plugin_id="claws",
                        label="claws.database",
                        path=claws_db,
                        severity=Severity.OK,
                        message="Claws SQLite database integrity verified.",
                    )
                )
            else:
                findings.append(
                    DoctorFinding(
                        plugin_id="claws",
                        label="claws.database",
                        path=claws_db,
                        severity=Severity.ERROR,
                        message=f"Claws SQLite database integrity check failed: {res}",
                    )
                )
        except Exception as e:
            findings.append(
                DoctorFinding(
                    plugin_id="claws",
                    label="claws.database",
                    path=claws_db,
                    severity=Severity.ERROR,
                    message=f"Could not connect to Claws SQLite database: {e}",
                )
            )

    # 2. Engine and registered Claws check
    try:
        from src.claws import get_claws_engine

        engine = get_claws_engine()
        claws = engine.list_claws()
        required_claws = {
            "claw:database_maintenance",
            "claw:repository_health",
            "claw:system_monitor",
            "claw:digest_telemetry",
            "claw:web_monitor",
        }
        registered_ids = {c["claw_id"] for c in claws}
        missing = required_claws - registered_ids

        if not missing:
            findings.append(
                DoctorFinding(
                    plugin_id="claws",
                    label="claws.builtins",
                    severity=Severity.OK,
                    message=f"All {len(required_claws)} canonical autonomous Claws registered successfully.",
                )
            )
        else:
            findings.append(
                DoctorFinding(
                    plugin_id="claws",
                    label="claws.builtins",
                    severity=Severity.WARNING,
                    message=f"Missing registered Claws: {', '.join(sorted(missing))}",
                )
            )

        status = engine.get_status()
        concurrency = status.get("worker_concurrency", 0)
        if concurrency >= 1:
            findings.append(
                DoctorFinding(
                    plugin_id="claws",
                    label="claws.workers",
                    severity=Severity.OK,
                    message=f"Worker pool configured with concurrency limit {concurrency}.",
                )
            )
        else:
            findings.append(
                DoctorFinding(
                    plugin_id="claws",
                    label="claws.workers",
                    severity=Severity.ERROR,
                    message="Worker pool concurrency is zero or negative.",
                )
            )

    except Exception as e:
        findings.append(
            DoctorFinding(
                plugin_id="claws",
                label="claws.engine",
                severity=Severity.ERROR,
                message=f"Failed to load ClawsEngine: {e}",
            )
        )

    return findings


__all__ = ["check_claws_subsystem"]
