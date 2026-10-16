"""jarvis.routing.session_lifecycle — Session expiry resolution.

Mirrors OpenClaw's session reset logic (daily and idle rollovers).
"""
from datetime import datetime, timezone, timedelta
from typing import Any, Optional


def is_session_expired(
    session_record: Any,
    session_config: dict[str, Any],
    channel_id: Optional[str] = None,
) -> bool:
    """Determine if a session has expired based on configuration.

    Evaluates resetByChannel, resetByType, and global reset config
    against the session's started and last-interaction times.
    """
    if not session_record:
        return False

    kind = session_record.kind
    started_at_str = getattr(session_record, "session_started_at", "")
    last_interaction_str = getattr(session_record, "last_interaction_at", "")

    if not started_at_str:
        return False

    # Cascading config resolution
    reset_mode = "none"
    idle_minutes = 0
    at_hour = 4

    # Global config
    global_reset = session_config.get("reset", {})
    if global_reset:
        reset_mode = global_reset.get("mode", reset_mode)
        idle_minutes = global_reset.get("idleMinutes", idle_minutes)
        at_hour = global_reset.get("atHour", at_hour)
    
    # Global fallback for idleMinutes
    if "idleMinutes" in session_config and "idleMinutes" not in global_reset:
        idle_minutes = session_config["idleMinutes"]

    # By Type config (direct, group, thread)
    by_type = session_config.get("resetByType", {})
    if kind in by_type:
        type_cfg = by_type[kind]
        reset_mode = type_cfg.get("mode", reset_mode)
        idle_minutes = type_cfg.get("idleMinutes", idle_minutes)
        at_hour = type_cfg.get("atHour", at_hour)
    
    # By Channel config
    by_channel = session_config.get("resetByChannel", {})
    if channel_id and channel_id in by_channel:
        channel_cfg = by_channel[channel_id]
        reset_mode = channel_cfg.get("mode", reset_mode)
        idle_minutes = channel_cfg.get("idleMinutes", idle_minutes)
        at_hour = channel_cfg.get("atHour", at_hour)

    if reset_mode == "none":
        return False
    
    now = datetime.now(timezone.utc)

    def _parse_iso(iso_str: str) -> datetime:
        # Simple ISO-8601 parser for UTC suffix
        iso_str = iso_str.replace("Z", "+00:00")
        return datetime.fromisoformat(iso_str)

    try:
        started_at = _parse_iso(started_at_str)
    except ValueError:
        return False
        
    last_interaction = started_at
    if last_interaction_str:
        try:
            last_interaction = _parse_iso(last_interaction_str)
        except ValueError:
            pass

    if reset_mode == "idle":
        if idle_minutes <= 0:
            return False
        delta = now - last_interaction
        return delta.total_seconds() > (idle_minutes * 60)
        
    if reset_mode == "daily":
        # Check if the started_at time is strictly before the *most recent* occurrence of at_hour on the host
        # To do this in UTC, we need local timezone or we assume atHour is UTC for now.
        # OpenClaw says "configured local hour (session.reset.atHour, default 4, 0-23) on the gateway host".
        # We will use host local time for the boundary calculation.
        
        now_local = datetime.now().astimezone()
        
        # Most recent atHour occurrence
        recent_boundary = now_local.replace(hour=at_hour, minute=0, second=0, microsecond=0)
        if now_local < recent_boundary:
            recent_boundary -= timedelta(days=1)
            
        started_at_local = started_at.astimezone()
        
        return started_at_local < recent_boundary
        
    return False
