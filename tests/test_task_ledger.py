"""Tests for the background task ledger (task_types, task_retention, task_registry).

OpenClaw parity: mirrors behaviour of
  src/tasks/task-registry.types.ts
  src/tasks/task-retention.ts
  src/tasks/task-registry-records.ts
  src/tasks/task-registry.summary.ts
  src/tasks/task-registry.audit.ts
  src/tasks/task-registry.process-state.ts
"""

from __future__ import annotations

import time

import pytest

# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------
from src.automation.task_types import (
    DEFAULT_NOTIFY_POLICY_BY_RUNTIME,
    TASK_DELIVERY_STATUSES,
    TASK_NOTIFY_POLICIES,
    TASK_RUNTIMES,
    TASK_SCOPE_KINDS,
    TASK_STATUSES,
    TaskRecord,
    is_active_task_status,
    is_failure_task_status,
    is_terminal_task_status,
    parse_optional_task_terminal_outcome,
    parse_task_delivery_status,
    parse_task_notify_policy,
    parse_task_runtime,
    parse_task_scope_kind,
    parse_task_status,
)
from src.automation.task_retention import (
    DEFAULT_TASK_RETENTION_MS,
    LOST_TASK_RETENTION_MS,
    RECENT_TERMINAL_MS,
    STALE_QUEUED_MS,
    STALE_RUNNING_MS,
    is_expired_task,
    is_recent_terminal_task,
    resolve_effective_task_cleanup_after,
    resolve_task_cleanup_after,
)
from src.automation.task_registry import (
    TaskAuditFinding,
    _reset_registry_for_testing,
    build_task_audit_summary,
    build_task_status_snapshot,
    find_task_by_run_id,
    get_task_by_id,
    list_task_audit_findings,
    list_task_records,
    list_tasks_for_flow,
    list_tasks_for_owner_key,
    list_tasks_for_session_key,
    normalize_task_timestamps,
    remove_task,
    summarize_task_records,
    upsert_task,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ms() -> float:
    return time.time() * 1000


def _make_task(
    task_id: str = "task-1",
    runtime: str = "subagent",
    status: str = "queued",
    delivery_status: str = "pending",
    notify_policy: str = "done_only",
    created_at: float | None = None,
    **kwargs,
) -> TaskRecord:
    return TaskRecord(
        task_id=task_id,
        runtime=runtime,  # type: ignore[arg-type]
        requester_session_key="sess-req",
        owner_key="owner-1",
        scope_kind="session",
        task="Test background task",
        status=status,  # type: ignore[arg-type]
        delivery_status=delivery_status,  # type: ignore[arg-type]
        notify_policy=notify_policy,  # type: ignore[arg-type]
        created_at=created_at if created_at is not None else _ms(),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# task_types: parse helpers
# ---------------------------------------------------------------------------

class TestParseHelpers:
    def test_parse_task_runtime_valid(self):
        for rt in TASK_RUNTIMES:
            assert parse_task_runtime(rt) == rt

    def test_parse_task_runtime_invalid(self):
        with pytest.raises(ValueError, match="runtime"):
            parse_task_runtime("unknown")

    def test_parse_task_status_valid(self):
        for s in TASK_STATUSES:
            assert parse_task_status(s) == s

    def test_parse_task_status_invalid(self):
        with pytest.raises(ValueError, match="status"):
            parse_task_status("pending")

    def test_parse_task_delivery_status_valid(self):
        for ds in TASK_DELIVERY_STATUSES:
            assert parse_task_delivery_status(ds) == ds

    def test_parse_task_notify_policy_valid(self):
        for p in TASK_NOTIFY_POLICIES:
            assert parse_task_notify_policy(p) == p

    def test_parse_task_scope_kind_valid(self):
        for k in TASK_SCOPE_KINDS:
            assert parse_task_scope_kind(k) == k

    def test_parse_optional_task_terminal_outcome_none(self):
        assert parse_optional_task_terminal_outcome(None) is None
        assert parse_optional_task_terminal_outcome("") is None

    def test_parse_optional_task_terminal_outcome_valid(self):
        assert parse_optional_task_terminal_outcome("succeeded") == "succeeded"
        assert parse_optional_task_terminal_outcome("blocked") == "blocked"

    def test_parse_optional_task_terminal_outcome_invalid(self):
        with pytest.raises(ValueError):
            parse_optional_task_terminal_outcome("failed")


class TestStatusPredicates:
    @pytest.mark.parametrize("status", ["queued", "running"])
    def test_active_statuses(self, status):
        assert is_active_task_status(status)  # type: ignore[arg-type]
        assert not is_terminal_task_status(status)  # type: ignore[arg-type]

    @pytest.mark.parametrize("status", ["succeeded", "failed", "timed_out", "cancelled", "lost"])
    def test_terminal_statuses(self, status):
        assert is_terminal_task_status(status)  # type: ignore[arg-type]
        assert not is_active_task_status(status)  # type: ignore[arg-type]

    @pytest.mark.parametrize("status", ["failed", "timed_out", "lost"])
    def test_failure_statuses(self, status):
        assert is_failure_task_status(status)  # type: ignore[arg-type]

    @pytest.mark.parametrize("status", ["queued", "running", "succeeded", "cancelled"])
    def test_non_failure_statuses(self, status):
        assert not is_failure_task_status(status)  # type: ignore[arg-type]


class TestDefaultNotifyPolicy:
    def test_cron_silent(self):
        assert DEFAULT_NOTIFY_POLICY_BY_RUNTIME["cron"] == "silent"

    def test_cli_silent(self):
        assert DEFAULT_NOTIFY_POLICY_BY_RUNTIME["cli"] == "silent"

    def test_subagent_done_only(self):
        assert DEFAULT_NOTIFY_POLICY_BY_RUNTIME["subagent"] == "done_only"

    def test_acp_done_only(self):
        assert DEFAULT_NOTIFY_POLICY_BY_RUNTIME["acp"] == "done_only"


# ---------------------------------------------------------------------------
# task_retention
# ---------------------------------------------------------------------------

class TestRetentionWindows:
    def test_default_7_days(self):
        assert DEFAULT_TASK_RETENTION_MS == 7 * 24 * 60 * 60 * 1000

    def test_lost_24_hours(self):
        assert LOST_TASK_RETENTION_MS == 24 * 60 * 60 * 1000

    def test_stale_queued_10_min(self):
        assert STALE_QUEUED_MS == 10 * 60 * 1000

    def test_stale_running_30_min(self):
        assert STALE_RUNNING_MS == 30 * 60 * 1000

    def test_recent_terminal_5_min(self):
        assert RECENT_TERMINAL_MS == 5 * 60 * 1000


class TestResolveTaskCleanupAfter:
    def test_cron_non_lost_returns_none(self):
        task = _make_task(runtime="cron", status="succeeded")
        assert resolve_task_cleanup_after(task) is None

    def test_cron_lost_returns_value(self):
        now = _ms()
        task = _make_task(runtime="cron", status="lost", created_at=now)
        result = resolve_task_cleanup_after(task)
        assert result is not None
        assert result == pytest.approx(now + LOST_TASK_RETENTION_MS, rel=0.01)

    def test_subagent_succeeded_7_day_window(self):
        now = _ms()
        task = _make_task(runtime="subagent", status="succeeded", created_at=now)
        result = resolve_task_cleanup_after(task)
        assert result == pytest.approx(now + DEFAULT_TASK_RETENTION_MS, rel=0.01)

    def test_lost_uses_ended_at(self):
        now = _ms()
        ended = now - 1000
        task = _make_task(runtime="subagent", status="lost", created_at=now - 5000, ended_at=ended)
        result = resolve_task_cleanup_after(task)
        assert result == pytest.approx(ended + LOST_TASK_RETENTION_MS, rel=0.01)


class TestEffectiveCleanupAfter:
    def test_uses_stamped_when_not_lost(self):
        now = _ms()
        task = _make_task(status="succeeded", created_at=now - 1000, cleanup_after=now + 99999)
        result = resolve_effective_task_cleanup_after(task)
        assert result == now + 99999

    def test_lost_takes_minimum(self):
        now = _ms()
        stamped = now + 1000
        task = _make_task(
            runtime="subagent", status="lost", created_at=now,
            cleanup_after=stamped
        )
        status_derived = resolve_task_cleanup_after(task)
        assert status_derived is not None
        result = resolve_effective_task_cleanup_after(task)
        assert result == min(stamped, status_derived)

    def test_none_when_cron_non_lost(self):
        task = _make_task(runtime="cron", status="succeeded")
        assert resolve_effective_task_cleanup_after(task) is None


class TestIsExpiredTask:
    def test_not_expired_active(self):
        task = _make_task(status="running")
        assert not is_expired_task(task, _ms())

    def test_expired_after_cleanup(self):
        past = _ms() - DEFAULT_TASK_RETENTION_MS - 1000
        task = _make_task(runtime="subagent", status="succeeded", created_at=past)
        assert is_expired_task(task, _ms())

    def test_not_expired_cron_non_lost(self):
        task = _make_task(runtime="cron", status="succeeded", created_at=0)
        # cron non-lost has no cleanup window → never expired by this check
        assert not is_expired_task(task, _ms())


class TestIsRecentTerminalTask:
    def test_recent_terminal_succeeded(self):
        now = _ms()
        task = _make_task(status="succeeded", ended_at=now - 60_000)
        assert is_recent_terminal_task(task, now)

    def test_not_recent_terminal_old(self):
        now = _ms()
        task = _make_task(status="succeeded", ended_at=now - RECENT_TERMINAL_MS - 1000)
        assert not is_recent_terminal_task(task, now)

    def test_active_not_recent_terminal(self):
        task = _make_task(status="running")
        assert not is_recent_terminal_task(task, _ms())


# ---------------------------------------------------------------------------
# task_registry
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def fresh_registry():
    _reset_registry_for_testing()
    yield
    _reset_registry_for_testing()


class TestNormalizeTimestamps:
    def test_lowers_created_at_to_earliest_timestamp(self):
        # OpenClaw: keep createdAt as the LOWEST visible lifecycle floor.
        # If started_at is BEFORE created_at, created_at is pulled DOWN.
        now = 1_700_000_000_000.0
        task = _make_task(created_at=now, started_at=now - 1000)
        result = normalize_task_timestamps(task)
        # created_at is pulled down to started_at (earliest timestamp)
        assert result.created_at == now - 1000
        # started_at is clamped up to the new created_at floor
        assert result.started_at == now - 1000

    def test_no_change_when_timestamps_fine(self):
        now = _ms()
        task = _make_task(created_at=now - 2000, started_at=now - 1000, ended_at=now)
        result = normalize_task_timestamps(task)
        assert result is task  # same object returned

    def test_ended_at_clamped_to_started_at(self):
        now = _ms()
        task = _make_task(
            created_at=now - 3000,
            started_at=now - 2000,
            ended_at=now - 2500,   # before started_at → wrong
        )
        result = normalize_task_timestamps(task)
        assert result.ended_at >= result.started_at  # type: ignore[operator]


class TestUpsertAndLookup:
    def test_upsert_and_get(self):
        task = _make_task("t-1", run_id="run-abc")
        upsert_task(task)
        assert get_task_by_id("t-1") is task

    def test_find_by_run_id(self):
        task = _make_task("t-2", run_id="run-xyz")
        upsert_task(task)
        found = find_task_by_run_id("run-xyz")
        assert found is not None
        assert found.task_id == "t-2"

    def test_list_returns_newest_first(self):
        now = _ms()
        upsert_task(_make_task("old", created_at=now - 5000))
        upsert_task(_make_task("new", created_at=now))
        records = list_task_records()
        assert records[0].task_id == "new"
        assert records[1].task_id == "old"

    def test_remove_task(self):
        task = _make_task("t-3")
        upsert_task(task)
        assert remove_task("t-3") is True
        assert get_task_by_id("t-3") is None
        assert remove_task("t-3") is False

    def test_list_for_session_key(self):
        t = _make_task("ts-1")
        t.requester_session_key = "s-abc"
        upsert_task(t)
        found = list_tasks_for_session_key("s-abc")
        assert any(x.task_id == "ts-1" for x in found)

    def test_list_for_owner_key(self):
        t = _make_task("to-1")
        t.owner_key = "owner-xyz"
        upsert_task(t)
        found = list_tasks_for_owner_key("owner-xyz")
        assert any(x.task_id == "to-1" for x in found)

    def test_list_for_flow(self):
        t = _make_task("tf-1")
        t.parent_flow_id = "flow-abc"
        upsert_task(t)
        found = list_tasks_for_flow("flow-abc")
        assert any(x.task_id == "tf-1" for x in found)

    def test_upsert_replaces_existing(self):
        task = _make_task("t-4", status="queued")
        upsert_task(task)
        task2 = _make_task("t-4", status="running")
        upsert_task(task2)
        assert get_task_by_id("t-4").status == "running"  # type: ignore[union-attr]


class TestSummarizeTaskRecords:
    def test_empty(self):
        s = summarize_task_records([])
        assert s.total == 0
        assert s.active == 0

    def test_counts_correctly(self):
        tasks = [
            _make_task("t1", runtime="subagent", status="running"),
            _make_task("t2", runtime="acp", status="queued"),
            _make_task("t3", runtime="cron", status="succeeded"),
            _make_task("t4", runtime="cli", status="failed"),
            _make_task("t5", runtime="subagent", status="lost"),
        ]
        s = summarize_task_records(tasks)
        assert s.total == 5
        assert s.active == 2       # running + queued
        assert s.terminal == 3     # succeeded + failed + lost
        assert s.failures == 2     # failed + lost
        assert s.by_status.running == 1
        assert s.by_status.queued == 1
        assert s.by_status.succeeded == 1
        assert s.by_runtime.subagent == 2
        assert s.by_runtime.acp == 1


class TestBuildTaskStatusSnapshot:
    def test_active_tasks_included(self):
        now = _ms()
        t = _make_task("ta-1", status="running", created_at=now)
        snap = build_task_status_snapshot([t], now_ms=now)
        assert snap.active_count == 1
        assert snap.focus is t

    def test_recent_terminal_included(self):
        now = _ms()
        t = _make_task("tt-1", status="succeeded", created_at=now - 60_000, ended_at=now - 30_000)
        snap = build_task_status_snapshot([t], now_ms=now)
        assert snap.recent_terminal == [t]
        assert snap.active_count == 0

    def test_expired_excluded(self):
        old = _ms() - DEFAULT_TASK_RETENTION_MS - 1
        t = _make_task("te-1", runtime="subagent", status="succeeded", created_at=old)
        snap = build_task_status_snapshot([t], now_ms=_ms())
        assert snap.total_count == 0

    def test_focus_prefers_failure(self):
        now = _ms()
        ok = _make_task("ok", status="succeeded", ended_at=now - 10_000)
        fail = _make_task("fail", status="failed", ended_at=now - 5_000)
        snap = build_task_status_snapshot([ok, fail], now_ms=now)
        assert snap.focus is fail


class TestAuditFindings:
    def test_stale_queued(self):
        created = _ms() - STALE_QUEUED_MS - 1000
        t = _make_task("aq-1", status="queued", created_at=created)
        findings = list_task_audit_findings([t])
        assert any(f.code == "stale_queued" for f in findings)

    def test_stale_running(self):
        created = _ms() - STALE_RUNNING_MS - 1000
        t = _make_task("ar-1", status="running", created_at=created)
        findings = list_task_audit_findings([t])
        codes = [f.code for f in findings]
        assert "stale_running" in codes

    def test_stale_running_is_error(self):
        created = _ms() - STALE_RUNNING_MS - 1000
        t = _make_task("ar-2", status="running", created_at=created)
        findings = list_task_audit_findings([t])
        sev = {f.code: f.severity for f in findings}
        assert sev.get("stale_running") == "error"

    def test_lost_finding(self):
        t = _make_task("al-1", status="lost")
        findings = list_task_audit_findings([t])
        assert any(f.code == "lost" for f in findings)

    def test_delivery_failed_non_silent(self):
        t = _make_task("ad-1", status="succeeded", delivery_status="failed", notify_policy="done_only")
        findings = list_task_audit_findings([t])
        assert any(f.code == "delivery_failed" for f in findings)

    def test_delivery_failed_silent_not_flagged(self):
        t = _make_task("ad-2", status="succeeded", delivery_status="failed", notify_policy="silent")
        findings = list_task_audit_findings([t])
        assert not any(f.code == "delivery_failed" for f in findings)

    def test_inconsistent_timestamps_started_before_created(self):
        now = _ms()
        t = _make_task("ats-1", status="running", created_at=now, started_at=now - 500)
        # normalize_task_timestamps would fix this, but audit checks raw record
        t.started_at = now - 500  # bypass dataclass validation
        t.created_at = now
        findings = list_task_audit_findings([t])
        assert any(f.code == "inconsistent_timestamps" for f in findings)

    def test_no_findings_for_healthy_task(self):
        t = _make_task("ah-1", status="running")
        findings = list_task_audit_findings([t])
        # A freshly-running task has no stale, no lost, no delivery issue
        codes = [f.code for f in findings]
        assert "stale_running" not in codes
        assert "lost" not in codes

    def test_errors_sorted_first(self):
        created_stale = _ms() - STALE_RUNNING_MS - 1000
        t1 = _make_task("as-1", status="running", created_at=created_stale)  # error
        t2 = _make_task("as-2", status="queued",
                         created_at=_ms() - STALE_QUEUED_MS - 1000)          # warn
        findings = list_task_audit_findings([t1, t2])
        errors = [f for f in findings if f.severity == "error"]
        warns = [f for f in findings if f.severity == "warn"]
        if errors and warns:
            # All errors appear before all warns in sorted output
            assert findings.index(errors[-1]) < findings.index(warns[0])


class TestBuildAuditSummary:
    def test_empty(self):
        s = build_task_audit_summary([])
        assert s.total == 0
        assert s.errors == 0
        assert s.warnings == 0

    def test_counts(self):
        t = _make_task()
        findings = [
            TaskAuditFinding(severity="error", code="stale_running", task=t, age_ms=None, detail=""),
            TaskAuditFinding(severity="warn",  code="lost",          task=t, age_ms=None, detail=""),
            TaskAuditFinding(severity="warn",  code="lost",          task=t, age_ms=None, detail=""),
        ]
        s = build_task_audit_summary(findings)
        assert s.total == 3
        assert s.errors == 1
        assert s.warnings == 2
        assert s.by_code["stale_running"] == 1
        assert s.by_code["lost"] == 2
