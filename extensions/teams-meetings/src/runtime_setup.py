"""Runtime environment and device setup validation for Teams Meetings."""

from __future__ import annotations

from typing import Any

from jarvis_sdk import Err, Ok, Result

from .config import resolve_teams_meetings_config
from .setup import get_teams_meetings_setup_status


async def validate_teams_meetings_runtime_setup(
    *,
    config: Any = None,
    node_id: str | None = None,
    transport: str | None = None,
    mode: str | None = None,
) -> Result[dict[str, Any], str]:
    """Validate runtime environment and node setup for Teams Meetings."""
    try:
        cfg_res = resolve_teams_meetings_config(config or {})
        cfg = cfg_res.unwrap() if hasattr(cfg_res, "unwrap") else cfg_res
        setup_status = get_teams_meetings_setup_status(
            config=cfg,
            mode=mode,
            transport=transport,
            full_config=config if isinstance(config, dict) else None,
        )
        checks_list = [
            {
                "id": c.id,
                "ok": c.ok,
                "message": c.message,
            }
            for c in setup_status.checks
        ]
        if node_id:
            checks_list.append(
                {"id": "node", "ok": True, "message": f"Paired node {node_id} specified."}
            )
        return Ok(
            {
                "ok": setup_status.ok,
                "nodeId": node_id,
                "checks": checks_list,
            }
        )
    except Exception as e:
        return Err(str(e))
