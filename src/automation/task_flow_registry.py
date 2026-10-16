"""jarvis.automation.task_flow_registry — In-process Task Flow registry.

OpenClaw parity: mirrors
``openclaw-main/src/tasks/task-flow-registry.ts``
``openclaw-main/src/tasks/task-flow-registry.store.ts``
``openclaw-main/src/tasks/task-flow-owner-access.ts``
``openclaw-main/src/tasks/task-flow-runtime-internal.ts``
``openclaw-main/src/tasks/task-flow-registry.maintenance.ts`` (pruning / cancel finalization)

Task Flow is the durable orchestration layer above background tasks.
A flow survives process restart (SQLite-backed), tracks revisions to prevent
concurrent clobber, and mirrors single-task spawns for ACP / subagent runs.

Key contracts ported from OpenClaw:
- Managed flows require a ``controller_id`` and enforce it on every patch.
- Mirrored flows derive status/timing from the backing task; no controller needed.
- Every write bumps ``revision``; stale expected-revision writes are rejected.
- ``sync_flow_from_task_result`` is the only path that updates a mirrored flow.
- ``request_flow_cancel`` sets a sticky intent; ``finalize_cancelled_flow`` (called
  from maintenance) completes it once no child task remains active.
"""

from __future__ import annotations

import copy
import time
import uuid
from typing import Any, Callable, Literal

from .task_flow_types import (
    TaskFlowRecord,
    TaskFlowStatus,
    TaskFlowSyncFailed,
    TaskFlowSyncMode,
    TaskFlowSyncOk,
    TaskFlowSyncResult,
    TaskFlowUpdateApplied,
    TaskFlowUpdateRejected,
    TaskFlowUpdateResult,
    is_terminal_flow_status,
)
from .task_types import JsonValue, TaskNotifyPolicy

# ---------------------------------------------------------------------------
# Process-local state
# ---------------------------------------------------------------------------

_FlowRestoreStatus = Literal["uninitialized", "restoring", "ready", "failed"]


class _TaskFlowRegistryState:
    def __init__(self) -> None:
        self.flows: dict[str, TaskFlowRecord] = {}
        self.restore_status: _FlowRestoreStatus = "uninitialized"
        self.restore_error: str | None = None
        # Observers (best-effort; never raise inside writes)
        self._observer: Callable[[str, TaskFlowRecord | None, TaskFlowRecord | None], None] | None = None


_FLOW_REGISTRY = _TaskFlowRegistryState()


def _get_flow_registry() -> _TaskFlowRegistryState:
    return _FLOW_REGISTRY


def _reset_flow_registry_for_testing() -> None:
    global _FLOW_REGISTRY
    _FLOW_REGISTRY = _TaskFlowRegistryState()
    _FLOW_REGISTRY.restore_status = "ready"  # tests skip disk restore


# ---------------------------------------------------------------------------
# Restore lifecycle (mirrors restoreTaskFlowRegistryOnce + ensureTaskFlowRegistryReady)
# ---------------------------------------------------------------------------

def ensure_task_flow_registry_ready() -> None:
    """Mirror of OpenClaw ``ensureTaskFlowRegistryReady``.

    In Jarvis, flow records are restored lazily from SQLite on first access.
    For now this marks the registry ready in-process; the SQLite persistence
    layer (``task_flow_registry.store.sqlite``) is the production path and will
    call ``_load_flows_from_store`` during bootstrap.
    """
    r = _get_flow_registry()
    if r.restore_status == "ready":
        return
    if r.restore_status == "failed":
        raise RuntimeError(f"Task-flow registry restore failed: {r.restore_error}")
    if r.restore_status == "restoring":
        raise RuntimeError("Task-flow registry restore is already in progress.")
    # uninitialized → ready (in-memory; SQLite layer populates via _load_flows_from_store)
    r.restore_status = "ready"


def get_task_flow_registry_restore_failure() -> str | None:
    """Mirror of OpenClaw ``getTaskFlowRegistryRestoreFailure``."""
    try:
        ensure_task_flow_registry_ready()
        return None
    except Exception as exc:
        return str(exc)


def reload_task_flow_registry_from_store(flows: dict[str, TaskFlowRecord] | None = None) -> None:
    """Reload in-memory flows from persisted state (called by SQLite layer on boot)."""
    r = _get_flow_registry()
    r.flows = flows or {}
    r.restore_status = "ready"
    r.restore_error = None


# ---------------------------------------------------------------------------
# Clone / deep-copy helpers
# ---------------------------------------------------------------------------

def _clone_flow(flow: TaskFlowRecord) -> TaskFlowRecord:
    """Deep clone a flow record (mirrors cloneFlowRecord in OpenClaw)."""
    return TaskFlowRecord(
        flow_id=flow.flow_id,
        sync_mode=flow.sync_mode,
        owner_key=flow.owner_key,
        revision=flow.revision,
        status=flow.status,
        notify_policy=flow.notify_policy,
        goal=flow.goal,
        created_at=flow.created_at,
        updated_at=flow.updated_at,
        requester_origin=copy.deepcopy(flow.requester_origin),
        controller_id=flow.controller_id,
        current_step=flow.current_step,
        blocked_task_id=flow.blocked_task_id,
        blocked_summary=flow.blocked_summary,
        state_json=copy.deepcopy(flow.state_json),
        wait_json=copy.deepcopy(flow.wait_json),
        cancel_requested_at=flow.cancel_requested_at,
        ended_at=flow.ended_at,
    )


# ---------------------------------------------------------------------------
# Validation helpers (mirrors assertFlowOwnerKey / assertControllerId)
# ---------------------------------------------------------------------------

def _assert_owner_key(owner_key: str) -> str:
    normalized = (owner_key or "").strip()
    if not normalized:
        raise ValueError("Flow owner_key is required.")
    return normalized


def _assert_controller_id(controller_id: str | None) -> str:
    normalized = (controller_id or "").strip()
    if not normalized:
        raise ValueError("Managed flow controller_id is required.")
    return normalized


def _normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _normalize_json_blob(value: JsonValue | None) -> JsonValue | None:
    return copy.deepcopy(value) if value is not None else None


# ---------------------------------------------------------------------------
# Status derivation from task (mirrors deriveTaskFlowStatusFromTask)
# ---------------------------------------------------------------------------

def derive_flow_status_from_task(
    task_status: str,
    terminal_outcome: str | None,
) -> TaskFlowStatus:
    """Mirror of OpenClaw ``deriveTaskFlowStatusFromTask``."""
    if task_status == "queued":
        return "queued"
    if task_status == "running":
        return "running"
    if task_status == "succeeded":
        return "blocked" if terminal_outcome == "blocked" else "succeeded"
    if task_status == "cancelled":
        return "cancelled"
    if task_status == "lost":
        return "lost"
    return "failed"


# ---------------------------------------------------------------------------
# Timing helper (mirrors resolveTaskMirroredFlowTiming)
# ---------------------------------------------------------------------------

def _resolve_mirrored_flow_timing(
    flow_created_at: float,
    task_last_event_at: float | None,
    task_ended_at: float | None,
    is_terminal: bool,
) -> tuple[float, float | None]:
    """Returns (updated_at, ended_at). Mirrors ``resolveTaskMirroredFlowTiming``."""
    if not is_terminal:
        updated_at = task_last_event_at if task_last_event_at is not None else flow_created_at
        return updated_at, None
    ended_at = task_ended_at or task_last_event_at or flow_created_at
    return ended_at, ended_at


# ---------------------------------------------------------------------------
# Blocked summary resolver (mirrors resolveFlowBlockedSummary)
# ---------------------------------------------------------------------------

def _resolve_flow_blocked_summary(
    task_status: str,
    terminal_outcome: str | None,
    terminal_summary: str | None,
    progress_summary: str | None,
) -> str | None:
    if task_status != "succeeded" or terminal_outcome != "blocked":
        return None
    return _normalize_optional(terminal_summary) or _normalize_optional(progress_summary)


# ---------------------------------------------------------------------------
# Internal write path (mirrors writeFlowRecord)
# ---------------------------------------------------------------------------

def _write_flow_record(
    r: _TaskFlowRegistryState,
    next_flow: TaskFlowRecord,
    previous: TaskFlowRecord | None = None,
) -> TaskFlowRecord | None:
    """Persist and update in-memory state. Returns a clone, or None on persist failure."""
    # In-memory write always succeeds; persistence is best-effort here.
    # Production SQLite persistence hook can be injected via _set_persist_hook.
    _persist_hook = _get_persist_hook()
    if _persist_hook is not None:
        try:
            _persist_hook(next_flow)
        except Exception:
            return None
    r.flows[next_flow.flow_id] = next_flow
    # Notify observer (best-effort)
    if r._observer is not None:
        try:
            r._observer("upserted", next_flow, previous)
        except Exception:
            pass
    return _clone_flow(next_flow)


# ---------------------------------------------------------------------------
# Persistence hook (optional; injected by SQLite layer in production)
# ---------------------------------------------------------------------------

_PERSIST_HOOK: Callable[[TaskFlowRecord], None] | None = None
_DELETE_HOOK: Callable[[str], None] | None = None


def _get_persist_hook() -> Callable[[TaskFlowRecord], None] | None:
    return _PERSIST_HOOK


def _get_delete_hook() -> Callable[[str], None] | None:
    return _DELETE_HOOK


def configure_flow_persistence(
    persist: Callable[[TaskFlowRecord], None] | None = None,
    delete: Callable[[str], None] | None = None,
) -> None:
    """Inject SQLite persistence callbacks (called during gateway boot)."""
    global _PERSIST_HOOK, _DELETE_HOOK
    _PERSIST_HOOK = persist
    _DELETE_HOOK = delete


# ---------------------------------------------------------------------------
# Build helpers (mirrors buildFlowRecord)
# ---------------------------------------------------------------------------

def _now_ms() -> float:
    return time.time() * 1000


def _build_flow_record(
    *,
    sync_mode: TaskFlowSyncMode = "managed",
    owner_key: str,
    controller_id: str | None = None,
    requester_origin: dict[str, Any] | None = None,
    status: TaskFlowStatus = "queued",
    notify_policy: TaskNotifyPolicy = "done_only",
    goal: str,
    current_step: str | None = None,
    blocked_task_id: str | None = None,
    blocked_summary: str | None = None,
    state_json: JsonValue | None = None,
    wait_json: JsonValue | None = None,
    cancel_requested_at: float | None = None,
    created_at: float | None = None,
    updated_at: float | None = None,
    ended_at: float | None = None,
    revision: int = 0,
) -> TaskFlowRecord:
    now = created_at if created_at is not None else _now_ms()
    ctrl = _assert_controller_id(controller_id) if sync_mode == "managed" else None
    return TaskFlowRecord(
        flow_id=str(uuid.uuid4()),
        sync_mode=sync_mode,
        owner_key=_assert_owner_key(owner_key),
        revision=max(0, revision),
        status=status,
        notify_policy=notify_policy,
        goal=goal,
        created_at=now,
        updated_at=updated_at if updated_at is not None else now,
        requester_origin=copy.deepcopy(requester_origin),
        controller_id=ctrl,
        current_step=_normalize_optional(current_step),
        blocked_task_id=_normalize_optional(blocked_task_id),
        blocked_summary=_normalize_optional(blocked_summary),
        state_json=_normalize_json_blob(state_json),
        wait_json=_normalize_json_blob(wait_json),
        cancel_requested_at=cancel_requested_at if cancel_requested_at is not None else None,
        ended_at=ended_at,
    )


# ---------------------------------------------------------------------------
# Public creation API
# ---------------------------------------------------------------------------

def create_managed_task_flow(
    *,
    owner_key: str,
    controller_id: str,
    goal: str,
    notify_policy: TaskNotifyPolicy = "done_only",
    requester_origin: dict[str, Any] | None = None,
    current_step: str | None = None,
    state_json: JsonValue | None = None,
    created_at: float | None = None,
) -> TaskFlowRecord | None:
    """Mirror of OpenClaw ``createManagedTaskFlow``.

    Creates a managed flow. controller_id is required and enforced.
    Returns None if persistence fails.
    """
    ensure_task_flow_registry_ready()
    r = _get_flow_registry()
    flow = _build_flow_record(
        sync_mode="managed",
        owner_key=owner_key,
        controller_id=_assert_controller_id(controller_id),
        goal=goal,
        notify_policy=notify_policy,
        requester_origin=requester_origin,
        current_step=current_step,
        state_json=state_json,
        created_at=created_at,
    )
    return _write_flow_record(r, flow)


def create_task_flow_for_task(
    *,
    task_owner_key: str,
    task_id: str,
    task_label: str | None,
    task_title: str,
    task_status: str,
    task_terminal_outcome: str | None,
    task_notify_policy: TaskNotifyPolicy,
    task_created_at: float,
    task_last_event_at: float | None = None,
    task_ended_at: float | None = None,
    task_terminal_summary: str | None = None,
    task_progress_summary: str | None = None,
    requester_origin: dict[str, Any] | None = None,
) -> TaskFlowRecord | None:
    """Mirror of OpenClaw ``createTaskFlowForTask``.

    Creates a mirrored (task_mirrored) flow for a single detached ACP / subagent task.
    Status, timing, and goal are derived from the backing task.
    """
    ensure_task_flow_registry_ready()
    r = _get_flow_registry()
    flow_status = derive_flow_status_from_task(task_status, task_terminal_outcome)
    is_terminal = is_terminal_flow_status(flow_status)
    updated_at, ended_at = _resolve_mirrored_flow_timing(
        flow_created_at=task_created_at,
        task_last_event_at=task_last_event_at,
        task_ended_at=task_ended_at,
        is_terminal=is_terminal,
    )
    flow = _build_flow_record(
        sync_mode="task_mirrored",
        owner_key=task_owner_key,
        requester_origin=requester_origin,
        status=flow_status,
        notify_policy=task_notify_policy,
        goal=_normalize_optional(task_label) or (task_title.strip() or "Background task"),
        blocked_task_id=task_id if flow_status == "blocked" else None,
        blocked_summary=_resolve_flow_blocked_summary(
            task_status, task_terminal_outcome, task_terminal_summary, task_progress_summary
        ),
        created_at=task_created_at,
        updated_at=updated_at,
        ended_at=ended_at,
    )
    return _write_flow_record(r, flow)


# ---------------------------------------------------------------------------
# Patch helper (mirrors applyFlowPatch)
# ---------------------------------------------------------------------------

def _apply_flow_patch(
    current: TaskFlowRecord,
    *,
    status: TaskFlowStatus | None = None,
    notify_policy: TaskNotifyPolicy | None = None,
    goal: str | None = None,
    controller_id: Any = ...,  # sentinel = no change
    current_step: Any = ...,
    blocked_task_id: Any = ...,
    blocked_summary: Any = ...,
    state_json: Any = ...,
    wait_json: Any = ...,
    cancel_requested_at: Any = ...,
    ended_at: Any = ...,
    updated_at: float | None = None,
) -> TaskFlowRecord:
    _SENTINEL = ...

    def _resolve(new: Any, old: Any) -> Any:
        return old if new is _SENTINEL else new

    new_ctrl = _resolve(controller_id, current.controller_id)
    if new_ctrl is not _SENTINEL:
        new_ctrl = _normalize_optional(str(new_ctrl)) if new_ctrl is not None else None
    else:
        new_ctrl = current.controller_id
    if current.sync_mode == "managed":
        _assert_controller_id(new_ctrl)

    return TaskFlowRecord(
        flow_id=current.flow_id,
        sync_mode=current.sync_mode,
        owner_key=current.owner_key,
        revision=current.revision + 1,
        status=status if status is not None else current.status,
        notify_policy=notify_policy if notify_policy is not None else current.notify_policy,
        goal=goal if goal is not None else current.goal,
        created_at=current.created_at,
        updated_at=updated_at if updated_at is not None else _now_ms(),
        requester_origin=copy.deepcopy(current.requester_origin),
        controller_id=new_ctrl,
        current_step=_normalize_optional(
            current.current_step if current_step is _SENTINEL else current_step  # type: ignore[arg-type]
        ),
        blocked_task_id=_normalize_optional(
            current.blocked_task_id if blocked_task_id is _SENTINEL else blocked_task_id  # type: ignore[arg-type]
        ),
        blocked_summary=_normalize_optional(
            current.blocked_summary if blocked_summary is _SENTINEL else blocked_summary  # type: ignore[arg-type]
        ),
        state_json=_normalize_json_blob(
            current.state_json if state_json is _SENTINEL else state_json  # type: ignore[arg-type]
        ),
        wait_json=_normalize_json_blob(
            current.wait_json if wait_json is _SENTINEL else wait_json  # type: ignore[arg-type]
        ),
        cancel_requested_at=(
            current.cancel_requested_at if cancel_requested_at is _SENTINEL else cancel_requested_at  # type: ignore[assignment]
        ),
        ended_at=(current.ended_at if ended_at is _SENTINEL else ended_at),  # type: ignore[assignment]
    )


# ---------------------------------------------------------------------------
# Optimistic-concurrency update (mirrors updateFlowRecordByIdExpectedRevision)
# ---------------------------------------------------------------------------

def update_flow_record_expected_revision(
    *,
    flow_id: str,
    expected_revision: int,
    status: TaskFlowStatus | None = None,
    notify_policy: TaskNotifyPolicy | None = None,
    goal: str | None = None,
    current_step: Any = ...,
    blocked_task_id: Any = ...,
    blocked_summary: Any = ...,
    state_json: Any = ...,
    wait_json: Any = ...,
    cancel_requested_at: Any = ...,
    ended_at: Any = ...,
    updated_at: float | None = None,
) -> TaskFlowUpdateResult:
    """Mirror of OpenClaw ``updateFlowRecordByIdExpectedRevision``.

    Revision conflict → rejected with reason='revision_conflict'.
    Not found → rejected with reason='not_found'.
    Persist failure → rejected with reason='persist_failed'.
    """
    ensure_task_flow_registry_ready()
    r = _get_flow_registry()
    current = r.flows.get(flow_id)
    if current is None:
        return TaskFlowUpdateRejected(applied=False, reason="not_found")
    if current.revision != expected_revision:
        return TaskFlowUpdateRejected(
            applied=False, reason="revision_conflict", current=_clone_flow(current)
        )
    patched = _apply_flow_patch(
        current,
        status=status,
        notify_policy=notify_policy,
        goal=goal,
        current_step=current_step,
        blocked_task_id=blocked_task_id,
        blocked_summary=blocked_summary,
        state_json=state_json,
        wait_json=wait_json,
        cancel_requested_at=cancel_requested_at,
        ended_at=ended_at,
        updated_at=updated_at,
    )
    written = _write_flow_record(r, patched, current)
    if written is None:
        return TaskFlowUpdateRejected(
            applied=False, reason="persist_failed", current=_clone_flow(current)
        )
    return TaskFlowUpdateApplied(applied=True, flow=written)


def _update_flow_unchecked(
    r: _TaskFlowRegistryState,
    flow_id: str,
    **patch_kwargs: Any,
) -> TaskFlowRecord | None:
    """Unchecked update (no revision guard). Used for mirrored flows."""
    current = r.flows.get(flow_id)
    if current is None:
        return None
    patched = _apply_flow_patch(current, **patch_kwargs)
    return _write_flow_record(r, patched, current)


# ---------------------------------------------------------------------------
# High-level managed-flow mutations (mirrors OpenClaw named helpers)
# ---------------------------------------------------------------------------

def set_flow_waiting(
    *,
    flow_id: str,
    expected_revision: int,
    current_step: Any = ...,
    state_json: Any = ...,
    wait_json: Any = ...,
    blocked_task_id: Any = ...,
    blocked_summary: Any = ...,
    updated_at: float | None = None,
) -> TaskFlowUpdateResult:
    """Mirror of OpenClaw ``setFlowWaiting``.

    Determines waiting vs blocked based on whether blocked_task_id/blocked_summary is set.
    """
    _bt = blocked_task_id if blocked_task_id is not ... else None
    _bs = blocked_summary if blocked_summary is not ... else None
    auto_status: TaskFlowStatus = (
        "blocked"
        if _normalize_optional(str(_bt) if _bt else None) or _normalize_optional(str(_bs) if _bs else None)
        else "waiting"
    )
    return update_flow_record_expected_revision(
        flow_id=flow_id,
        expected_revision=expected_revision,
        status=auto_status,
        current_step=current_step,
        state_json=state_json,
        wait_json=wait_json,
        blocked_task_id=blocked_task_id,
        blocked_summary=blocked_summary,
        ended_at=None,
        updated_at=updated_at,
    )


def resume_flow(
    *,
    flow_id: str,
    expected_revision: int,
    status: Literal["queued", "running"] = "queued",
    current_step: Any = ...,
    state_json: Any = ...,
    updated_at: float | None = None,
) -> TaskFlowUpdateResult:
    """Mirror of OpenClaw ``resumeFlow``."""
    return update_flow_record_expected_revision(
        flow_id=flow_id,
        expected_revision=expected_revision,
        status=status,
        current_step=current_step,
        state_json=state_json,
        wait_json=None,
        blocked_task_id=None,
        blocked_summary=None,
        ended_at=None,
        updated_at=updated_at,
    )


def finish_flow(
    *,
    flow_id: str,
    expected_revision: int,
    current_step: Any = ...,
    state_json: Any = ...,
    updated_at: float | None = None,
    ended_at: float | None = None,
) -> TaskFlowUpdateResult:
    """Mirror of OpenClaw ``finishFlow``."""
    now = _now_ms()
    _ended = ended_at if ended_at is not None else (updated_at if updated_at is not None else now)
    return update_flow_record_expected_revision(
        flow_id=flow_id,
        expected_revision=expected_revision,
        status="succeeded",
        current_step=current_step,
        state_json=state_json,
        wait_json=None,
        blocked_task_id=None,
        blocked_summary=None,
        ended_at=_ended,
        updated_at=updated_at if updated_at is not None else _ended,
    )


def fail_flow(
    *,
    flow_id: str,
    expected_revision: int,
    current_step: Any = ...,
    state_json: Any = ...,
    blocked_task_id: Any = ...,
    blocked_summary: Any = ...,
    updated_at: float | None = None,
    ended_at: float | None = None,
) -> TaskFlowUpdateResult:
    """Mirror of OpenClaw ``failFlow``."""
    now = _now_ms()
    _ended = ended_at if ended_at is not None else (updated_at if updated_at is not None else now)
    return update_flow_record_expected_revision(
        flow_id=flow_id,
        expected_revision=expected_revision,
        status="failed",
        current_step=current_step,
        state_json=state_json,
        wait_json=None,
        blocked_task_id=blocked_task_id,
        blocked_summary=blocked_summary,
        ended_at=_ended,
        updated_at=updated_at if updated_at is not None else _ended,
    )


def request_flow_cancel(
    *,
    flow_id: str,
    expected_revision: int,
    cancel_requested_at: float | None = None,
    updated_at: float | None = None,
) -> TaskFlowUpdateResult:
    """Mirror of OpenClaw ``requestFlowCancel``.

    Sets a sticky cancel intent. The flow finalizes as cancelled once no child
    task remains active (via ``finalize_cancelled_flow`` in maintenance).
    """
    ts = cancel_requested_at if cancel_requested_at is not None else (
        updated_at if updated_at is not None else _now_ms()
    )
    return update_flow_record_expected_revision(
        flow_id=flow_id,
        expected_revision=expected_revision,
        cancel_requested_at=ts,
        updated_at=updated_at,
    )


# ---------------------------------------------------------------------------
# Mirrored-flow sync from task result (mirrors syncFlowFromTaskResult)
# ---------------------------------------------------------------------------

def sync_flow_from_task_result(
    *,
    parent_flow_id: str | None,
    task_id: str,
    task_status: str,
    task_terminal_outcome: str | None,
    task_notify_policy: TaskNotifyPolicy,
    task_label: str | None,
    task_title: str,
    task_last_event_at: float | None,
    task_ended_at: float | None,
    task_terminal_summary: str | None,
    task_progress_summary: str | None,
) -> TaskFlowSyncResult:
    """Mirror of OpenClaw ``syncFlowFromTaskResult``.

    Updates a task_mirrored flow to reflect the backing task's current state.
    Managed flows are left untouched (they drive themselves).
    """
    flow_id = (parent_flow_id or "").strip()
    if not flow_id:
        return TaskFlowSyncOk(ok=True, flow=None)

    ensure_task_flow_registry_ready()
    r = _get_flow_registry()
    flow = r.flows.get(flow_id)
    if flow is None:
        return TaskFlowSyncOk(ok=True, flow=None)
    if flow.sync_mode != "task_mirrored":
        return TaskFlowSyncOk(ok=True, flow=_clone_flow(flow))

    flow_status = derive_flow_status_from_task(task_status, task_terminal_outcome)
    is_terminal = is_terminal_flow_status(flow_status)
    updated_at, ended_at = _resolve_mirrored_flow_timing(
        flow_created_at=flow.created_at,
        task_last_event_at=task_last_event_at,
        task_ended_at=task_ended_at,
        is_terminal=is_terminal,
    )
    updated = _update_flow_unchecked(
        r,
        flow_id,
        status=flow_status,
        notify_policy=task_notify_policy,
        goal=_normalize_optional(task_label) or (task_title.strip() or "Background task"),
        blocked_task_id=task_id.strip() if flow_status == "blocked" else None,
        blocked_summary=_resolve_flow_blocked_summary(
            task_status, task_terminal_outcome, task_terminal_summary, task_progress_summary
        ),
        wait_json=None,
        updated_at=updated_at,
        ended_at=ended_at if is_terminal else None,
    )
    if updated is None:
        return TaskFlowSyncFailed(ok=False, reason="persist_failed", current=_clone_flow(flow))
    return TaskFlowSyncOk(ok=True, flow=updated)


# ---------------------------------------------------------------------------
# Maintenance: cancel finalization + pruning (mirrors task-flow-registry.maintenance.ts)
# ---------------------------------------------------------------------------

def _has_active_linked_tasks(flow_id: str, active_task_ids: frozenset[str]) -> bool:
    """Returns True if any task linked to this flow is still active."""
    return any(tid for tid in active_task_ids if tid == flow_id)


def finalize_cancelled_flow(
    flow: TaskFlowRecord,
    now_ms: float,
    active_flow_task_ids: frozenset[str],
) -> bool:
    """Mirror of OpenClaw ``finalizeCancelledFlow`` (called from maintenance sweep).

    Transitions a cancel-requested managed flow to 'cancelled' once no child
    tasks remain active. Retries once on revision conflict.
    """
    r = _get_flow_registry()
    current = flow
    for _ in range(2):
        if current.sync_mode != "managed":
            return False
        if current.cancel_requested_at is None or is_terminal_flow_status(current.status):
            return False
        # Check no active child tasks remain
        if any(tid for tid in active_flow_task_ids):
            return False
        ended_at = max(now_ms, current.updated_at, current.cancel_requested_at)
        result = update_flow_record_expected_revision(
            flow_id=current.flow_id,
            expected_revision=current.revision,
            status="cancelled",
            blocked_task_id=None,
            blocked_summary=None,
            wait_json=None,
            ended_at=ended_at,
            updated_at=ended_at,
        )
        if isinstance(result, TaskFlowUpdateApplied):
            return True
        if result.reason == "not_found" or result.current is None:
            return False
        current = result.current  # retry with fresher revision
    return False


def should_prune_flow(flow: TaskFlowRecord, now_ms: float) -> bool:
    """Mirror of OpenClaw ``shouldPruneFlow``."""
    if not is_terminal_flow_status(flow.status):
        return False
    terminal_at = flow.ended_at or flow.updated_at or flow.created_at
    from .task_flow_types import TASK_FLOW_RETENTION_MS
    return (now_ms - terminal_at) >= TASK_FLOW_RETENTION_MS


# ---------------------------------------------------------------------------
# Read API
# ---------------------------------------------------------------------------

def get_task_flow_by_id(flow_id: str) -> TaskFlowRecord | None:
    """Mirror of OpenClaw ``getTaskFlowById``."""
    ensure_task_flow_registry_ready()
    flow = _get_flow_registry().flows.get(flow_id)
    return _clone_flow(flow) if flow is not None else None


def list_task_flows_for_owner_key(owner_key: str) -> list[TaskFlowRecord]:
    """Mirror of OpenClaw ``listTaskFlowsForOwnerKey``."""
    ensure_task_flow_registry_ready()
    normalized = (owner_key or "").strip()
    if not normalized:
        return []
    r = _get_flow_registry()
    return sorted(
        (_clone_flow(f) for f in r.flows.values() if f.owner_key.strip() == normalized),
        key=lambda f: -f.created_at,
    )


def find_latest_task_flow_for_owner_key(owner_key: str) -> TaskFlowRecord | None:
    """Mirror of OpenClaw ``findLatestTaskFlowForOwnerKey``."""
    flows = list_task_flows_for_owner_key(owner_key)
    return flows[0] if flows else None


def resolve_task_flow_for_lookup_token(token: str) -> TaskFlowRecord | None:
    """Mirror of OpenClaw ``resolveTaskFlowForLookupToken``.

    Accepts a flow_id or an owner_key (resolves to latest flow for that owner).
    """
    lookup = (token or "").strip()
    if not lookup:
        return None
    return get_task_flow_by_id(lookup) or find_latest_task_flow_for_owner_key(lookup)


def list_task_flow_records() -> list[TaskFlowRecord]:
    """Return all flows sorted newest-first."""
    ensure_task_flow_registry_ready()
    r = _get_flow_registry()
    return sorted(
        (_clone_flow(f) for f in r.flows.values()),
        key=lambda f: -f.created_at,
    )


def delete_task_flow_record_by_id(flow_id: str) -> bool:
    """Mirror of OpenClaw ``deleteTaskFlowRecordById``."""
    ensure_task_flow_registry_ready()
    r = _get_flow_registry()
    flow = r.flows.pop(flow_id, None)
    if flow is None:
        return False
    hook = _get_delete_hook()
    if hook is not None:
        try:
            hook(flow_id)
        except Exception:
            # Restore in-memory on persist failure
            r.flows[flow_id] = flow
            return False
    if r._observer is not None:
        try:
            r._observer("deleted", None, flow)
        except Exception:
            pass
    return True


# ---------------------------------------------------------------------------
# Owner-access helpers (mirrors task-flow-owner-access.ts)
# ---------------------------------------------------------------------------

def get_task_flow_by_id_for_owner(
    flow_id: str,
    caller_owner_key: str,
) -> TaskFlowRecord | None:
    """Mirror of OpenClaw ``getTaskFlowByIdForOwner``."""
    flow = get_task_flow_by_id(flow_id)
    if flow is None:
        return None
    return flow if flow.owner_key.strip() == caller_owner_key.strip() else None


def resolve_task_flow_for_lookup_token_for_owner(
    token: str,
    caller_owner_key: str,
) -> TaskFlowRecord | None:
    """Mirror of OpenClaw ``resolveTaskFlowForLookupTokenForOwner``."""
    direct = get_task_flow_by_id_for_owner(token, caller_owner_key)
    if direct is not None:
        return direct
    normalized_token = (token or "").strip()
    normalized_caller = (caller_owner_key or "").strip()
    if not normalized_token or normalized_token != normalized_caller:
        return None
    return find_latest_task_flow_for_owner_key(normalized_caller)


__all__ = [
    "_reset_flow_registry_for_testing",
    "configure_flow_persistence",
    "create_managed_task_flow",
    "create_task_flow_for_task",
    "delete_task_flow_record_by_id",
    "derive_flow_status_from_task",
    "ensure_task_flow_registry_ready",
    "fail_flow",
    "finalize_cancelled_flow",
    "find_latest_task_flow_for_owner_key",
    "finish_flow",
    "get_task_flow_by_id",
    "get_task_flow_by_id_for_owner",
    "get_task_flow_registry_restore_failure",
    "list_task_flow_records",
    "list_task_flows_for_owner_key",
    "reload_task_flow_registry_from_store",
    "request_flow_cancel",
    "resolve_task_flow_for_lookup_token",
    "resolve_task_flow_for_lookup_token_for_owner",
    "resume_flow",
    "set_flow_waiting",
    "should_prune_flow",
    "sync_flow_from_task_result",
    "update_flow_record_expected_revision",
]
