"""Doctor diagnostics and configuration repair for Teams Meetings."""

from __future__ import annotations

from typing import Any

from jarvis_sdk import Ok, Result

from .config import resolve_teams_meetings_config
from .config_compat import migrate_legacy_teams_meetings_config


async def run_teams_meetings_doctor(
    *,
    config: dict[str, Any],
    fix: bool = False,
) -> Result[dict[str, Any], str]:
    checks: list[dict[str, Any]] = []
    fixes_applied: list[str] = []
    current_config = dict(config)

    migrated_cfg, changed = migrate_legacy_teams_meetings_config(current_config)
    if changed:
        if fix:
            current_config = migrated_cfg
            fixes_applied.append("Migrated legacy Teams Meetings configuration keys.")
            checks.append(
                {
                    "id": "config.legacy_keys",
                    "status": "fixed",
                    "message": "Migrated legacy configuration keys to modern structure.",
                }
            )
        else:
            checks.append(
                {
                    "id": "config.legacy_keys",
                    "status": "warn",
                    "message": "Configuration contains deprecated legacy keys. Run with --fix to migrate.",
                }
            )
    else:
        checks.append(
            {
                "id": "config.legacy_keys",
                "status": "ok",
                "message": "Configuration format is canonical.",
            }
        )

    cfg_res = resolve_teams_meetings_config(current_config)
    if not cfg_res.is_ok:
        checks.append(
            {
                "id": "config.resolution",
                "status": "error",
                "message": f"Failed to resolve configuration: {cfg_res.error}",
            }
        )
        return Ok(
            {
                "ok": False,
                "checks": checks,
                "fixesApplied": fixes_applied,
                "config": current_config,
            }
        )

    cfg = cfg_res.unwrap()
    checks.append(
        {
            "id": "config.resolution",
            "status": "ok",
            "message": f"Configuration resolved (default transport: {cfg.default_transport}, mode: {cfg.default_mode}).",
        }
    )

    all_ok = all(c["status"] in ("ok", "fixed", "info") for c in checks)
    return Ok(
        {
            "ok": all_ok,
            "checks": checks,
            "fixesApplied": fixes_applied,
            "config": current_config,
        }
    )
