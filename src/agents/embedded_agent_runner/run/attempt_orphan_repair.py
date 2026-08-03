"""jarvis.agents.embedded_agent_runner.run.attempt_orphan_repair — replay trailing entries to repair an orphan session.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-orphan-repair.ts``.

Public surface:

Functions:

- :func:`replay_trailing_entries_for_orphan_repair`
- :func:`resolve_orphan_repair_plan`

Phase 7.6d-6 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Orphan-repair plan shape.
OrphanRepairPlan = Dict[str, Any]


#: Installable hook for the replay-trailing-entries step.
_REPLAY_TRAILING_ENTRIES: Callable[
    [Dict[str, Any]], Any
] = lambda _p: []


def set_replay_trailing_entries_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom replayTrailingEntriesForOrphanRepair hook."""
    global _REPLAY_TRAILING_ENTRIES
    _REPLAY_TRAILING_ENTRIES = hook


#: Installable hook for the resolve-orphan-repair-plan step.
_RESOLVE_ORPHAN_REPAIR_PLAN: Callable[
    [Dict[str, Any]], OrphanRepairPlan
] = lambda _p: {}


def set_resolve_orphan_repair_plan_hook(
    hook: Callable[[Dict[str, Any]], OrphanRepairPlan],
) -> None:
    """Install a custom resolveOrphanRepairPlan hook."""
    global _RESOLVE_ORPHAN_REPAIR_PLAN
    _RESOLVE_ORPHAN_REPAIR_PLAN = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def replay_trailing_entries_for_orphan_repair(
    params: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Replay the trailing entries for an orphan session.

    Mirrors :func:`replayTrailingEntriesForOrphanRepair`
    (``attempt-orphan-repair.ts``).
    """
    result = _REPLAY_TRAILING_ENTRIES(dict(params or {}))
    return list(result or [])


def resolve_orphan_repair_plan(
    params: Dict[str, Any],
) -> OrphanRepairPlan:
    """Resolve the orphan-repair plan for an attempt.

    Mirrors :func:`resolveOrphanRepairPlan`
    (``attempt-orphan-repair.ts``).
    """
    return _RESOLVE_ORPHAN_REPAIR_PLAN(dict(params or {}))


__all__ = [
    "OrphanRepairPlan",
    "replay_trailing_entries_for_orphan_repair",
    "resolve_orphan_repair_plan",
    "set_replay_trailing_entries_hook",
    "set_resolve_orphan_repair_plan_hook",
]
