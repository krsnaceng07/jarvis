"""jarvis.agents.lanes — command queue lane resolution for agent work.

OpenClaw parity: mirrors ``src/agents/lanes.ts``.

Resolves queue lane names for nested, cron, and subagent agent work.
Builds on the base :mod:`~src.agents.embedded_agent_runner.lanes`
``CommandLane`` constants.

Public surface
--------------
``AGENT_LANE_SUBAGENT``
    The subagent lane constant.
``resolve_cron_agent_lane``
    Lane for embedded runs started from cron.
``resolve_nested_agent_lane_for_session``
    Per-session nested lane to serialize nested agent work.
``is_nested_agent_lane``
    Predicate — true when a lane belongs to nested agent work.
"""

from __future__ import annotations

from src.agents.embedded_agent_runner.lanes import CommandLane

# ---------------------------------------------------------------------------
# Lane constants (mirrors agents/lanes.ts exports)
# ---------------------------------------------------------------------------

AGENT_LANE_SUBAGENT: str = CommandLane.Subagent

_NESTED_LANE = "nested"
_NESTED_LANE_PREFIX = f"{_NESTED_LANE}:"

# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def resolve_cron_agent_lane(lane: str | None = None) -> str:
    """Resolve the lane for agent work started from cron.

    Mirrors ``resolveCronAgentLane``.

    Cron jobs occupy the outer cron lane, so inner agent work needs
    its own lane to avoid self-deadlock without widening shared nested flows.
    """
    trimmed = (lane or "").strip()
    if not trimmed or trimmed == CommandLane.Cron:
        return CommandLane.CronNested
    return trimmed


def resolve_nested_agent_lane_for_session(session_key: str | None) -> str:
    """Resolve a per-session nested lane to serialize nested agent work.

    Mirrors ``resolveNestedAgentLaneForSession``.

    Each session gets its own ``nested:<key>`` lane so concurrent
    sessions do not share the same nested-work slot.
    """
    trimmed = (session_key or "").strip()
    if not trimmed:
        return CommandLane.Nested
    return f"{_NESTED_LANE_PREFIX}{trimmed}"


def is_nested_agent_lane(lane: str | None) -> bool:
    """Return True when *lane* belongs to nested agent work.

    Mirrors ``isNestedAgentLane``.
    """
    if not lane:
        return False
    return lane == _NESTED_LANE or lane.startswith(_NESTED_LANE_PREFIX)


__all__ = [
    "AGENT_LANE_SUBAGENT",
    "is_nested_agent_lane",
    "resolve_cron_agent_lane",
    "resolve_nested_agent_lane_for_session",
]
