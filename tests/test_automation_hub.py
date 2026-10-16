"""Tests for src/automation/automation_hub.py.

Mirrors tests of docs/automation/background-work.md,
src/tasks/task-flow-registry.types.ts, and src/infra/heartbeat-schedule.ts in OpenClaw.
"""

from __future__ import annotations

import pytest

from src.automation.automation_hub import (
    HEARTBEAT_DEFAULT_INTERVAL_MS,
    compute_next_heartbeat_phase_due_ms,
    parse_optional_task_flow_sync_mode,
    parse_task_flow_status,
    recommend_automation_mechanism,
    resolve_heartbeat_phase_ms,
)


def test_parse_task_flow_status_valid():
    assert parse_task_flow_status("running") == "running"
    assert parse_task_flow_status("succeeded") == "succeeded"


def test_parse_task_flow_status_invalid():
    with pytest.raises(ValueError, match="Invalid persisted task flow status"):
        parse_task_flow_status("unknown-status")


def test_parse_optional_task_flow_sync_mode():
    assert parse_optional_task_flow_sync_mode("managed") == "managed"
    assert parse_optional_task_flow_sync_mode("task_mirrored") == "task_mirrored"
    assert parse_optional_task_flow_sync_mode(None) is None
    assert parse_optional_task_flow_sync_mode("") is None


def test_resolve_heartbeat_phase_ms_deterministic():
    phase1 = resolve_heartbeat_phase_ms("seed-abc", "agent-1", HEARTBEAT_DEFAULT_INTERVAL_MS)
    phase2 = resolve_heartbeat_phase_ms("seed-abc", "agent-1", HEARTBEAT_DEFAULT_INTERVAL_MS)
    assert phase1 == phase2
    assert 0 <= phase1 < HEARTBEAT_DEFAULT_INTERVAL_MS


def test_compute_next_heartbeat_phase_due_ms():
    interval_ms = 30 * 60 * 1000
    phase_ms = 5 * 60 * 1000
    now_ms = 0
    next_due = compute_next_heartbeat_phase_due_ms(now_ms, interval_ms, phase_ms)
    assert next_due == phase_ms


def test_recommend_automation_mechanism():
    assert recommend_automation_mechanism(needs_exact_timing=True) == "automations"
    assert recommend_automation_mechanism(needs_session_context=True) == "heartbeat"
    assert recommend_automation_mechanism(needs_event_driven=True) == "hooks"
    assert recommend_automation_mechanism(needs_multi_step=True) == "taskflow"
    assert recommend_automation_mechanism(needs_persistent_instructions=True) == "standing_orders"
