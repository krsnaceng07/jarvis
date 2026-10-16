"""jarvis.automation.automation_hub — Background automation mechanisms hub.

OpenClaw parity: mirrors
``openclaw-main/docs/automation/background-work.md`` and
``openclaw-main/src/tasks/task-flow-registry.types.ts``
``openclaw-main/src/infra/heartbeat-schedule.ts``.

Provides unified access to all background execution mechanisms:
1. **Automations** — Precise cron/one-shot scheduling with task records.
2. **Tasks** — Background task ledger tracking all detached work.
3. **Task Flow** — Durable multi-step flow orchestration with revision tracking.
4. **Heartbeat** — Periodic main-session turn (default every 30 minutes).
5. **Hooks** — Event-driven lifecycle scripts.
6. **Standing Orders** — Persistent per-session operating authority.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Task Flow
# ---------------------------------------------------------------------------

TaskFlowStatus = Literal[
    "queued", "running", "waiting", "blocked", "succeeded", "failed", "cancelled", "lost"
]
TaskFlowSyncMode = Literal["task_mirrored", "managed"]

TASK_FLOW_STATUSES: frozenset[str] = frozenset(
    ["queued", "running", "waiting", "blocked", "succeeded", "failed", "cancelled", "lost"]
)
TASK_FLOW_SYNC_MODES: frozenset[str] = frozenset(["task_mirrored", "managed"])


def parse_task_flow_status(value: Any) -> TaskFlowStatus:
    """Parse and validate a persisted TaskFlowStatus value."""
    if isinstance(value, str) and value in TASK_FLOW_STATUSES:
        return value  # type: ignore[return-value]
    raise ValueError(f"Invalid persisted task flow status: {value!r}")


def parse_optional_task_flow_sync_mode(value: Any) -> TaskFlowSyncMode | None:
    """Parse an optional TaskFlowSyncMode value."""
    if value is None or value == "":
        return None
    if isinstance(value, str) and value in TASK_FLOW_SYNC_MODES:
        return value  # type: ignore[return-value]
    raise ValueError(f"Invalid persisted task flow sync mode: {value!r}")


@dataclass
class TaskFlowRecord:
    flow_id: str
    sync_mode: TaskFlowSyncMode
    owner_key: str
    status: TaskFlowStatus
    goal: str
    revision: int = 0
    current_step: str | None = None
    blocked_task_id: str | None = None
    created_at: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Heartbeat scheduling (from heartbeat-schedule.ts)
# ---------------------------------------------------------------------------

HEARTBEAT_DEFAULT_INTERVAL_MS = 30 * 60 * 1000  # 30 minutes


def resolve_heartbeat_phase_ms(scheduler_seed: str, agent_id: str, interval_ms: int) -> int:
    """Compute a deterministic per-agent heartbeat phase offset using SHA-256."""
    interval_ms = max(1, int(interval_ms))
    digest = hashlib.sha256(f"{scheduler_seed}:{agent_id}".encode()).digest()
    phase = int.from_bytes(digest[:4], "big") % interval_ms
    return phase


def compute_next_heartbeat_phase_due_ms(now_ms: int, interval_ms: int, phase_ms: int) -> int:
    """Compute the next heartbeat due timestamp in milliseconds."""
    interval_ms = max(1, int(interval_ms))
    now_ms = int(now_ms)
    phase_ms = phase_ms % interval_ms
    cycle_position_ms = now_ms % interval_ms
    delta_ms = (phase_ms - cycle_position_ms) % interval_ms
    if delta_ms == 0:
        delta_ms = interval_ms
    return now_ms + delta_ms


# ---------------------------------------------------------------------------
# Standing Orders
# ---------------------------------------------------------------------------

@dataclass
class StandingOrdersConfig:
    """Persistent operating authority injected into every session."""
    instructions: list[str] = field(default_factory=list)
    source_file: str | None = None


# ---------------------------------------------------------------------------
# Automation decision helper
# ---------------------------------------------------------------------------

AutomationMechanism = Literal[
    "automations", "heartbeat", "tasks", "taskflow", "hooks", "standing_orders"
]


def recommend_automation_mechanism(
    needs_exact_timing: bool = False,
    needs_session_context: bool = False,
    needs_event_driven: bool = False,
    needs_persistent_instructions: bool = False,
    needs_multi_step: bool = False,
    needs_audit_trail: bool = False,
) -> AutomationMechanism:
    """Recommend the best automation mechanism given requirements."""
    if needs_persistent_instructions:
        return "standing_orders"
    if needs_event_driven:
        return "hooks"
    if needs_multi_step:
        return "taskflow"
    if needs_audit_trail:
        return "tasks"
    if needs_exact_timing:
        return "automations"
    if needs_session_context:
        return "heartbeat"
    return "automations"


__all__ = [
    "HEARTBEAT_DEFAULT_INTERVAL_MS",
    "TASK_FLOW_STATUSES",
    "TASK_FLOW_SYNC_MODES",
    "AutomationMechanism",
    "StandingOrdersConfig",
    "TaskFlowRecord",
    "TaskFlowStatus",
    "TaskFlowSyncMode",
    "compute_next_heartbeat_phase_due_ms",
    "parse_optional_task_flow_sync_mode",
    "parse_task_flow_status",
    "recommend_automation_mechanism",
    "resolve_heartbeat_phase_ms",
]
