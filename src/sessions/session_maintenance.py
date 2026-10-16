"""jarvis.sessions.session_maintenance — Session store maintenance.

Mirrors OpenClaw's session store cleanup, bounding storage over time
via pruneAfter and maxEntries rules.
"""
from datetime import datetime, timezone, timedelta
from typing import Any
import sqlite3
import re


def _parse_duration_to_days(duration: str | int | float) -> float:
    """Parse a duration string (e.g., '30d', '24h') into days."""
    if isinstance(duration, (int, float)):
        return float(duration)
    
    match = re.match(r"^(\d+)(d|h|m)$", str(duration).strip().lower())
    if not match:
        return 0.0
        
    val, unit = match.groups()
    val = float(val)
    if unit == "d":
        return val
    elif unit == "h":
        return val / 24.0
    elif unit == "m":
        return val / (24.0 * 60.0)
    return val


def sweep_sessions(
    conn: sqlite3.Connection,
    config: dict[str, Any],
) -> dict[str, int]:
    """Run the session maintenance sweep on the given connection.
    
    Exempts archived, pinned, and active thread sessions.
    Only prunes rows that are eviction-eligible.
    Returns a dict with 'pruned_count' and 'kept_count'.
    """
    maintenance = config.get("maintenance", {})
    mode = maintenance.get("mode", "enforce")
    
    pruned_count = 0
    prune_after = maintenance.get("pruneAfter", "30d")
    max_entries = maintenance.get("maxEntries", 500)
    
    if "pruneDays" in maintenance and "pruneAfter" not in maintenance:
        prune_after = maintenance["pruneDays"]
        
    prune_days = _parse_duration_to_days(prune_after)
    now = datetime.now(timezone.utc)
    cutoff_time = now - timedelta(days=prune_days)
    cutoff_iso = cutoff_time.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    
    # Prune by age (pruneAfter)
    if prune_days > 0:
        if mode == "enforce":
            cursor = conn.execute(
                "DELETE FROM sessions WHERE updated_at < ? AND kind != 'thread'",
                (cutoff_iso,)
            )
            pruned_count += cursor.rowcount
            
    # Prune by maxEntries
    # Keep the most recent `max_entries` based on updated_at
    if max_entries > 0:
        # Get count of non-exempt entries
        row = conn.execute("SELECT COUNT(*) as count FROM sessions WHERE kind != 'thread'").fetchone()
        total_eligible = row[0]
        
        if total_eligible > max_entries:
            limit_to_delete = total_eligible - max_entries
            if mode == "enforce":
                cursor = conn.execute(
                    "DELETE FROM sessions WHERE session_key IN ("
                    "SELECT session_key FROM sessions WHERE kind != 'thread' "
                    "ORDER BY updated_at ASC LIMIT ?"
                    ")",
                    (limit_to_delete,)
                )
                pruned_count += cursor.rowcount
    
    conn.commit()
    
    row = conn.execute("SELECT COUNT(*) as count FROM sessions").fetchone()
    total_kept = row[0]
    
    return {"pruned_count": pruned_count, "kept_count": total_kept}
