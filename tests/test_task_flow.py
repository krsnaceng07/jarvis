"""Tests for the Task Flow orchestration layer.

OpenClaw parity: mirrors behaviour of
  src/tasks/task-flow-registry.types.ts
  src/tasks/task-flow-registry.ts
  src/tasks/task-flow-owner-access.ts
  src/tasks/task-flow-registry.maintenance.ts
  src/tasks/task-flow-registry.audit.ts
"""

from __future__ import annotations

import time

import pytest

from src.automation.task_flow_audit import (
    DEFAULT_FLOW_CANCEL_STUCK_MS,
    DEFAULT_FLOW_STALE_RUNNING_MS,
    DEFAULT_FLOW_STALE_WAITING_MS,
    TaskFlowAuditFinding,
    build_task_flow_audit_summary,
    list_task_flow_audit_findings,
)
from src.automation.task_flow_registry import (
    _reset_flow_registry_for_testing,
    create_managed_task_flow,
    create_task_flow_for_task,
    delete_task_flow_record_by_id,
    derive_flow_status_from_task,
    fail_flow,
    find_latest_task_flow_for_owner_key,
    finish_flow,
    get_task_flow_by_id,
    get_task_flow_by_id_for_owner,
    list_task_flow_records,
    list_task_flows_for_owner_key,
    request_flow_cancel,
    resolve_task_flow_for_lookup_token,
    resolve_task_flow_for_lookup_token_for_owner,
    resume_flow,
    set_flow_waiting,
    should_prune_flow,
    sync_flow_from_task_result,
)
from src.automation.task_flow_types import (
    TASK_FLOW_RETENTION_MS,
    TASK_FLOW_STATUSES,
    TASK_FLOW_SYNC_MODES,
    TaskFlowRecord,
    TaskFlowSyncFailed,
    TaskFlowSyncOk,
    TaskFlowUpdateApplied,
    TaskFlowUpdateRejected,
    is_active_flow_status,
    is_terminal_flow_status,
    parse_optional_task_flow_sync_mode,
    parse_task_flow_status,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def fresh_flow_registry():
    _reset_flow_registry_for_testing()
    yield
    _reset_flow_registry_for_testing()


def _ms() -> float:
    return time.time() * 1000


def _managed(
    owner_key: str = "owner-1",
    controller_id: str = "ctrl-1",
    goal: str = "Do work",
    **kw,
) -> TaskFlowRecord:
    flow = create_managed_task_flow(
        owner_key=owner_key,
        controller_id=controller_id,
        goal=goal,
        **kw,
    )
    assert flow is not None
    return flow


def _mirrored(
    owner_key: str = "owner-1",
    task_status: str = "queued",
    task_terminal_outcome: str | None = None,
    task_created_at: float | None = None,
    goal: str = "Mirror task",
) -> TaskFlowRecord:
    flow = create_task_flow_for_task(
        task_owner_key=owner_key,
        task_id="task-abc",
        task_label=goal,
        task_title=goal,
        task_status=task_status,
        task_terminal_outcome=task_terminal_outcome,
        task_notify_policy="done_only",
        task_created_at=task_created_at if task_created_at is not None else _ms(),
    )
    assert flow is not None
    return flow


# ---------------------------------------------------------------------------
# task_flow_types: parse helpers and predicates
# ---------------------------------------------------------------------------

class TestFlowTypeHelpers:
    def test_parse_sync_mode_valid(self):
        for mode in TASK_FLOW_SYNC_MODES:
            assert parse_optional_task_flow_sync_mode(mode) == mode

    def test_parse_sync_mode_none(self):
        assert parse_optional_task_flow_sync_mode(None) is None
        assert parse_optional_task_flow_sync_mode("") is None

    def test_parse_sync_mode_invalid(self):
        with pytest.raises(ValueError, match="sync mode"):
            parse_optional_task_flow_sync_mode("auto")

    def test_parse_flow_status_valid(self):
        for s in TASK_FLOW_STATUSES:
            assert parse_task_flow_status(s) == s

    def test_parse_flow_status_invalid(self):
        with pytest.raises(ValueError, match="status"):
            parse_task_flow_status("active")

    @pytest.mark.parametrize("status", ["succeeded", "blocked", "failed", "cancelled", "lost"])
    def test_terminal_statuses(self, status):
        assert is_terminal_flow_status(status)  # type: ignore[arg-type]
        assert not is_active_flow_status(status)  # type: ignore[arg-type]

    @pytest.mark.parametrize("status", ["queued", "running", "waiting"])
    def test_active_statuses(self, status):
        assert is_active_flow_status(status)  # type: ignore[arg-type]

    def test_retention_7_days(self):
        assert TASK_FLOW_RETENTION_MS == 7 * 24 * 60 * 60 * 1000


# ---------------------------------------------------------------------------
# derive_flow_status_from_task
# ---------------------------------------------------------------------------

class TestDeriveFlowStatus:
    @pytest.mark.parametrize("task_status,outcome,expected", [
        ("queued",    None,       "queued"),
        ("running",   None,       "running"),
        ("succeeded", None,       "succeeded"),
        ("succeeded", "blocked",  "blocked"),
        ("cancelled", None,       "cancelled"),
        ("lost",      None,       "lost"),
        ("failed",    None,       "failed"),
        ("timed_out", None,       "failed"),
    ])
    def test_derive(self, task_status, outcome, expected):
        assert derive_flow_status_from_task(task_status, outcome) == expected


# ---------------------------------------------------------------------------
# create_managed_task_flow
# ---------------------------------------------------------------------------

class TestCreateManagedFlow:
    def test_creates_flow(self):
        flow = _managed()
        assert flow.sync_mode == "managed"
        assert flow.controller_id == "ctrl-1"
        assert flow.revision == 0
        assert flow.status == "queued"

    def test_requires_controller_id(self):
        with pytest.raises(ValueError, match="controller_id"):
            create_managed_task_flow(owner_key="o", controller_id="", goal="g")

    def test_requires_owner_key(self):
        with pytest.raises(ValueError, match="owner_key"):
            create_managed_task_flow(owner_key="", controller_id="ctrl", goal="g")

    def test_is_retrievable(self):
        flow = _managed(owner_key="o-abc")
        found = get_task_flow_by_id(flow.flow_id)
        assert found is not None
        assert found.flow_id == flow.flow_id

    def test_immutable_state_json(self):
        state = {"step": 1}
        flow = _managed(state_json=state)
        state["step"] = 99  # mutate caller dict
        found = get_task_flow_by_id(flow.flow_id)
        assert found is not None
        assert found.state_json == {"step": 1}  # deep-copied


# ---------------------------------------------------------------------------
# create_task_flow_for_task (mirrored)
# ---------------------------------------------------------------------------

class TestCreateMirroredFlow:
    def test_creates_mirrored_flow(self):
        flow = _mirrored(task_status="running")
        assert flow.sync_mode == "task_mirrored"
        assert flow.controller_id is None
        assert flow.status == "running"

    def test_blocked_outcome_maps_to_blocked(self):
        flow = _mirrored(task_status="succeeded", task_terminal_outcome="blocked")
        assert flow.status == "blocked"

    def test_succeeded_sets_ended_at(self):
        now = _ms()
        flow = _mirrored(task_status="succeeded", task_created_at=now)
        assert flow.ended_at is not None

    def test_queued_has_no_ended_at(self):
        flow = _mirrored(task_status="queued")
        assert flow.ended_at is None


# ---------------------------------------------------------------------------
# Revision-guarded update
# ---------------------------------------------------------------------------

class TestRevisionGuard:
    def test_apply_succeeds_correct_revision(self):
        flow = _managed()
        result = finish_flow(flow_id=flow.flow_id, expected_revision=0)
        assert isinstance(result, TaskFlowUpdateApplied)
        assert result.flow.status == "succeeded"
        assert result.flow.revision == 1

    def test_revision_conflict_rejected(self):
        flow = _managed()
        result = finish_flow(flow_id=flow.flow_id, expected_revision=99)
        assert isinstance(result, TaskFlowUpdateRejected)
        assert result.reason == "revision_conflict"
        assert result.current is not None
        assert result.current.revision == 0

    def test_not_found_rejected(self):
        result = finish_flow(flow_id="nonexistent", expected_revision=0)
        assert isinstance(result, TaskFlowUpdateRejected)
        assert result.reason == "not_found"

    def test_revision_bumps_on_each_update(self):
        flow = _managed()
        r1 = resume_flow(flow_id=flow.flow_id, expected_revision=0, status="running")
        assert isinstance(r1, TaskFlowUpdateApplied)
        r2 = finish_flow(flow_id=flow.flow_id, expected_revision=1)
        assert isinstance(r2, TaskFlowUpdateApplied)
        assert r2.flow.revision == 2


# ---------------------------------------------------------------------------
# Named mutation helpers
# ---------------------------------------------------------------------------

class TestFlowMutations:
    def test_resume_flow_clears_wait_state(self):
        flow = _managed()
        # First set waiting
        set_flow_waiting(flow_id=flow.flow_id, expected_revision=0, wait_json={"t": 1})
        flow2 = get_task_flow_by_id(flow.flow_id)
        assert flow2 is not None and flow2.wait_json is not None
        # Then resume
        result = resume_flow(flow_id=flow.flow_id, expected_revision=1, status="running")
        assert isinstance(result, TaskFlowUpdateApplied)
        assert result.flow.wait_json is None
        assert result.flow.status == "running"

    def test_set_flow_waiting_sets_waiting(self):
        flow = _managed()
        result = set_flow_waiting(flow_id=flow.flow_id, expected_revision=0, wait_json={"tok": "x"})
        assert isinstance(result, TaskFlowUpdateApplied)
        assert result.flow.status == "waiting"

    def test_set_flow_waiting_with_blocked_task_id_sets_blocked(self):
        flow = _managed()
        result = set_flow_waiting(
            flow_id=flow.flow_id, expected_revision=0,
            blocked_task_id="task-123", blocked_summary="step failed"
        )
        assert isinstance(result, TaskFlowUpdateApplied)
        assert result.flow.status == "blocked"
        assert result.flow.blocked_task_id == "task-123"

    def test_finish_flow_sets_succeeded_and_ended_at(self):
        flow = _managed()
        result = finish_flow(flow_id=flow.flow_id, expected_revision=0)
        assert isinstance(result, TaskFlowUpdateApplied)
        assert result.flow.status == "succeeded"
        assert result.flow.ended_at is not None

    def test_fail_flow_sets_failed_and_ended_at(self):
        flow = _managed()
        result = fail_flow(flow_id=flow.flow_id, expected_revision=0,
                           blocked_summary="step error")
        assert isinstance(result, TaskFlowUpdateApplied)
        assert result.flow.status == "failed"
        assert result.flow.blocked_summary == "step error"
        assert result.flow.ended_at is not None

    def test_request_flow_cancel_sets_cancel_intent(self):
        flow = _managed()
        result = request_flow_cancel(flow_id=flow.flow_id, expected_revision=0)
        assert isinstance(result, TaskFlowUpdateApplied)
        assert result.flow.cancel_requested_at is not None
        assert result.flow.status == "queued"  # not yet cancelled

    def test_cancel_intent_persists_on_re_read(self):
        flow = _managed()
        request_flow_cancel(flow_id=flow.flow_id, expected_revision=0)
        found = get_task_flow_by_id(flow.flow_id)
        assert found is not None
        assert found.cancel_requested_at is not None


# ---------------------------------------------------------------------------
# sync_flow_from_task_result (mirrored sync)
# ---------------------------------------------------------------------------

class TestSyncFlowFromTaskResult:
    def _sync(self, flow: TaskFlowRecord, task_status: str, outcome: str | None = None) -> TaskFlowSyncOk | TaskFlowSyncFailed:
        return sync_flow_from_task_result(
            parent_flow_id=flow.flow_id,
            task_id="task-abc",
            task_status=task_status,
            task_terminal_outcome=outcome,
            task_notify_policy="done_only",
            task_label="Work",
            task_title="Work",
            task_last_event_at=_ms(),
            task_ended_at=None,
            task_terminal_summary=None,
            task_progress_summary=None,
        )

    def test_mirrored_flow_syncs_status(self):
        flow = _mirrored(task_status="queued")
        result = self._sync(flow, "running")
        assert isinstance(result, TaskFlowSyncOk)
        assert result.flow is not None
        assert result.flow.status == "running"

    def test_mirrored_flow_becomes_succeeded(self):
        flow = _mirrored(task_status="running")
        result = self._sync(flow, "succeeded")
        assert isinstance(result, TaskFlowSyncOk)
        assert result.flow is not None
        assert result.flow.status == "succeeded"
        assert result.flow.ended_at is not None

    def test_mirrored_flow_becomes_blocked_on_blocked_outcome(self):
        flow = _mirrored(task_status="running")
        result = self._sync(flow, "succeeded", "blocked")
        assert isinstance(result, TaskFlowSyncOk)
        assert result.flow is not None
        assert result.flow.status == "blocked"

    def test_managed_flow_not_synced(self):
        flow = _managed()
        result = self._sync(flow, "succeeded")
        assert isinstance(result, TaskFlowSyncOk)
        assert result.flow is not None
        # Managed flow status unchanged
        assert result.flow.status == "queued"

    def test_no_flow_id_returns_ok_none(self):
        result = sync_flow_from_task_result(
            parent_flow_id=None,
            task_id="t", task_status="running",
            task_terminal_outcome=None, task_notify_policy="done_only",
            task_label=None, task_title="t",
            task_last_event_at=None, task_ended_at=None,
            task_terminal_summary=None, task_progress_summary=None,
        )
        assert isinstance(result, TaskFlowSyncOk)
        assert result.flow is None


# ---------------------------------------------------------------------------
# Read API
# ---------------------------------------------------------------------------

class TestReadAPI:
    def test_list_returns_newest_first(self):
        now = _ms()
        f1 = create_managed_task_flow(owner_key="o", controller_id="c", goal="old", created_at=now - 5000)
        f2 = create_managed_task_flow(owner_key="o", controller_id="c", goal="new", created_at=now)
        assert f1 and f2
        records = list_task_flow_records()
        assert records[0].flow_id == f2.flow_id
        assert records[1].flow_id == f1.flow_id

    def test_list_for_owner_key(self):
        f1 = _managed(owner_key="o-1")
        f2 = _managed(owner_key="o-2")
        flows = list_task_flows_for_owner_key("o-1")
        ids = [f.flow_id for f in flows]
        assert f1.flow_id in ids
        assert f2.flow_id not in ids

    def test_find_latest_for_owner_key(self):
        now = _ms()
        create_managed_task_flow(owner_key="o-x", controller_id="c", goal="old", created_at=now - 5000)
        newer = create_managed_task_flow(owner_key="o-x", controller_id="c", goal="new", created_at=now)
        assert newer is not None
        found = find_latest_task_flow_for_owner_key("o-x")
        assert found is not None
        assert found.flow_id == newer.flow_id

    def test_resolve_lookup_by_flow_id(self):
        flow = _managed()
        found = resolve_task_flow_for_lookup_token(flow.flow_id)
        assert found is not None and found.flow_id == flow.flow_id

    def test_resolve_lookup_by_owner_key(self):
        flow = _managed(owner_key="o-tok")
        found = resolve_task_flow_for_lookup_token("o-tok")
        assert found is not None and found.flow_id == flow.flow_id

    def test_delete_flow(self):
        flow = _managed()
        assert delete_task_flow_record_by_id(flow.flow_id) is True
        assert get_task_flow_by_id(flow.flow_id) is None

    def test_delete_nonexistent_returns_false(self):
        assert delete_task_flow_record_by_id("ghost") is False


# ---------------------------------------------------------------------------
# Owner-access guards
# ---------------------------------------------------------------------------

class TestOwnerAccess:
    def test_owner_can_read_own_flow(self):
        flow = _managed(owner_key="o-a")
        found = get_task_flow_by_id_for_owner(flow.flow_id, "o-a")
        assert found is not None

    def test_non_owner_cannot_read_flow(self):
        flow = _managed(owner_key="o-a")
        found = get_task_flow_by_id_for_owner(flow.flow_id, "o-b")
        assert found is None

    def test_owner_lookup_token_resolves_latest(self):
        flow = _managed(owner_key="o-tok-2")
        found = resolve_task_flow_for_lookup_token_for_owner("o-tok-2", "o-tok-2")
        assert found is not None and found.flow_id == flow.flow_id

    def test_mismatched_token_owner_returns_none(self):
        _managed(owner_key="o-a")
        found = resolve_task_flow_for_lookup_token_for_owner("o-a", "o-b")
        assert found is None


# ---------------------------------------------------------------------------
# Pruning
# ---------------------------------------------------------------------------

class TestShouldPruneFlow:
    def test_non_terminal_never_pruned(self):
        flow = _managed()
        assert not should_prune_flow(flow, _ms())

    def test_terminal_pruned_after_7_days(self):
        now = _ms()
        old = now - TASK_FLOW_RETENTION_MS - 1000
        flow = _managed(created_at=old)
        r = finish_flow(flow_id=flow.flow_id, expected_revision=0, ended_at=old)
        assert isinstance(r, TaskFlowUpdateApplied)
        assert should_prune_flow(r.flow, now)

    def test_terminal_not_pruned_within_7_days(self):
        now = _ms()
        flow = _managed()
        r = finish_flow(flow_id=flow.flow_id, expected_revision=0)
        assert isinstance(r, TaskFlowUpdateApplied)
        assert not should_prune_flow(r.flow, now)


# ---------------------------------------------------------------------------
# Audit findings
# ---------------------------------------------------------------------------

class TestTaskFlowAudit:
    def test_stale_running_is_error(self):
        now = _ms()
        stale = now - DEFAULT_FLOW_STALE_RUNNING_MS - 1000
        flow = _managed()
        # Force updated_at back
        from src.automation.task_flow_registry import _get_flow_registry
        from dataclasses import replace
        r = _get_flow_registry()
        r.flows[flow.flow_id] = replace(flow, status="running", updated_at=stale)
        findings = list_task_flow_audit_findings(now_ms=now)
        assert any(f.code == "stale_running" and f.severity == "error" for f in findings)

    def test_stale_waiting_is_warn(self):
        now = _ms()
        stale = now - DEFAULT_FLOW_STALE_WAITING_MS - 1000
        flow = _managed()
        from src.automation.task_flow_registry import _get_flow_registry
        from dataclasses import replace
        r = _get_flow_registry()
        r.flows[flow.flow_id] = replace(flow, status="waiting", updated_at=stale)
        findings = list_task_flow_audit_findings(now_ms=now)
        assert any(f.code == "stale_waiting" and f.severity == "warn" for f in findings)

    def test_cancel_stuck_warn(self):
        now = _ms()
        cancel_at = now - DEFAULT_FLOW_CANCEL_STUCK_MS - 1000
        flow = _managed()
        request_flow_cancel(flow_id=flow.flow_id, expected_revision=0, cancel_requested_at=cancel_at)
        findings = list_task_flow_audit_findings(
            now_ms=now,
            get_active_task_count_for_flow=lambda fid: 0,
        )
        assert any(f.code == "cancel_stuck" for f in findings)

    def test_blocked_task_missing_warn(self):
        now = _ms()
        flow = _mirrored(task_status="succeeded", task_terminal_outcome="blocked")
        findings = list_task_flow_audit_findings(
            flows=[flow],
            now_ms=now,
            get_blocked_task_exists=lambda tid: False,
        )
        assert any(f.code == "blocked_task_missing" for f in findings)

    def test_inconsistent_timestamps(self):
        now = _ms()
        flow = _managed()
        from src.automation.task_flow_registry import _get_flow_registry
        from dataclasses import replace
        r = _get_flow_registry()
        r.flows[flow.flow_id] = replace(flow, updated_at=flow.created_at - 1000)
        findings = list_task_flow_audit_findings(now_ms=now)
        assert any(f.code == "inconsistent_timestamps" for f in findings)

    def test_healthy_flow_has_no_findings(self):
        flow = _managed()
        findings = list_task_flow_audit_findings(flows=[flow], now_ms=_ms())
        assert len(findings) == 0

    def test_errors_sorted_before_warnings(self):
        now = _ms()
        stale_run = now - DEFAULT_FLOW_STALE_RUNNING_MS - 1
        stale_wait = now - DEFAULT_FLOW_STALE_WAITING_MS - 1
        from src.automation.task_flow_registry import _get_flow_registry
        from dataclasses import replace
        flow_run = _managed(owner_key="o-r", goal="running-stale")
        flow_wait = _managed(owner_key="o-w", goal="waiting-stale")
        r = _get_flow_registry()
        r.flows[flow_run.flow_id] = replace(flow_run, status="running", updated_at=stale_run)
        r.flows[flow_wait.flow_id] = replace(flow_wait, status="waiting", updated_at=stale_wait)
        findings = list_task_flow_audit_findings(now_ms=now)
        errors = [f for f in findings if f.severity == "error"]
        warns = [f for f in findings if f.severity == "warn"]
        if errors and warns:
            assert findings.index(errors[-1]) < findings.index(warns[0])


class TestFlowAuditSummary:
    def test_empty(self):
        s = build_task_flow_audit_summary([])
        assert s.total == 0

    def test_counts(self):
        flow = _managed()
        findings = [
            TaskFlowAuditFinding(severity="error", code="stale_running", detail="", flow=flow),
            TaskFlowAuditFinding(severity="warn",  code="stale_waiting", detail="", flow=flow),
            TaskFlowAuditFinding(severity="warn",  code="cancel_stuck",  detail="", flow=flow),
        ]
        s = build_task_flow_audit_summary(findings)
        assert s.total == 3
        assert s.errors == 1
        assert s.warnings == 2
        assert s.by_code["stale_running"] == 1
        assert s.by_code["cancel_stuck"] == 1
