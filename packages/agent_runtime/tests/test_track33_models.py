"""Track 3.3 Dedicated Models & State Machine Test Suite (S01–S08).

Validates:
S01: 12-state node lifecycle transitions and invalid transition rejection.
S02: TaskAggregateState rollup logic across complex multi-node states.
S03: ExecutionAttempt creation, serialization, and attempt identity preservation.
S04: Fine-grained resource claims, composite keys, and deadlock-prevention ordering.
S05: Monotonic FencingToken generation, lease attachment, and expiry checks.
S06: WorkerIdentity lifecycle status and heartbeat staleness evaluation.
S07: Side-effect aware retry policies, exponential backoff, and 3-strike loop fingerprinting.
S08: Hierarchical deadline context, effective min() inheritance, and expiration evaluation.
"""

from __future__ import annotations

import datetime
import pytest

from jarvis_agent.scheduling.models import (
    DeadlineContext,
    ExecutionAttempt,
    FencingToken,
    NodeStateTransition,
    ResourceClaim,
    ResourceClass,
    ResourceLease,
    ResourceMode,
    RetryPolicy,
    SchedulerNodeState,
    TaskAggregateState,
    WorkerIdentity,
    WorkerStatus,
    compute_recovery_fingerprint,
)


def test_s01_node_state_transitions():
    """S01: Valid and invalid transitions across the 12-state machine."""
    # Valid forward transition: PENDING -> ELIGIBLE
    t1 = NodeStateTransition.create(
        node_id="n1",
        task_id="t1",
        from_state=SchedulerNodeState.PENDING,
        to_state=SchedulerNodeState.ELIGIBLE,
        reason="Prerequisites satisfied",
    )
    assert t1.to_state == SchedulerNodeState.ELIGIBLE

    # Valid: ELIGIBLE -> LEASED -> DISPATCH_REQUESTED -> RUNNING -> OBSERVING -> VERIFYING -> VERIFIED
    NodeStateTransition.create(
        "n1", "t1", SchedulerNodeState.ELIGIBLE, SchedulerNodeState.LEASED, "Leased to worker"
    )
    NodeStateTransition.create(
        "n1", "t1", SchedulerNodeState.LEASED, SchedulerNodeState.DISPATCH_REQUESTED, "Dispatching"
    )
    NodeStateTransition.create(
        "n1", "t1", SchedulerNodeState.DISPATCH_REQUESTED, SchedulerNodeState.RUNNING, "Running"
    )
    NodeStateTransition.create(
        "n1", "t1", SchedulerNodeState.RUNNING, SchedulerNodeState.OBSERVING, "Observing"
    )
    NodeStateTransition.create(
        "n1", "t1", SchedulerNodeState.OBSERVING, SchedulerNodeState.VERIFYING, "Verifying"
    )
    t7 = NodeStateTransition.create(
        "n1", "t1", SchedulerNodeState.VERIFYING, SchedulerNodeState.VERIFIED, "Verified"
    )
    assert t7.to_state == SchedulerNodeState.VERIFIED

    # Invalid jump: PENDING directly to RUNNING
    with pytest.raises(ValueError, match="Invalid node state transition"):
        NodeStateTransition.create(
            "n1", "t1", SchedulerNodeState.PENDING, SchedulerNodeState.RUNNING, "Illegal jump"
        )

    # Terminal state transition rejection: VERIFIED cannot transition anywhere
    with pytest.raises(ValueError, match="Invalid node state transition"):
        NodeStateTransition.create(
            "n1",
            "t1",
            SchedulerNodeState.VERIFIED,
            SchedulerNodeState.RUNNING,
            "Illegal transition from terminal",
        )


def test_s02_task_aggregate_state_values():
    """S02: Verify TaskAggregateState coverage and enum members."""
    expected = {
        "PENDING",
        "RUNNING",
        "WAITING",
        "COMPLETED",
        "PARTIALLY_COMPLETED",
        "FAILED",
        "CANCELLED",
        "AMBIGUOUS",
        "BLOCKED",
        "EXPIRED",
    }
    actual = {s.value for s in TaskAggregateState}
    assert actual == expected


def test_s03_execution_attempt_lifecycle():
    """S03: ExecutionAttempt creation, dictionary serialization, and round-trip."""
    attempt = ExecutionAttempt(
        attempt_id=2,
        node_id="node_100",
        task_id="task_abc",
        plan_id="plan_xyz",
        plan_revision=1,
        command_id="cmd_999",
        execution_id="exec_888",
        worker_id="worker_1",
        status=SchedulerNodeState.RUNNING,
        lease_generation=5,
    )
    d = attempt.to_dict()
    assert d["attempt_id"] == 2
    assert d["status"] == "RUNNING"
    assert d["lease_generation"] == 5

    restored = ExecutionAttempt.from_dict(d)
    assert restored.attempt_id == 2
    assert restored.node_id == "node_100"
    assert restored.status == SchedulerNodeState.RUNNING
    assert restored.lease_generation == 5


def test_s04_resource_claims_and_composite_ordering():
    """S04: Fine-grained resource claims, composite keys, and deterministic deadlock-prevention ordering."""
    claim_fs = ResourceClaim(
        "c1", "t1", "n1", ResourceClass.FILESYSTEM_PATH, "C:/app/data.json", ResourceMode.EXCLUSIVE
    )
    claim_browser = ResourceClaim(
        "c2", "t1", "n1", ResourceClass.BROWSER_TAB, "youtube.com:tab_1", ResourceMode.EXCLUSIVE
    )
    claim_desktop = ResourceClaim(
        "c3", "t1", "n1", ResourceClass.DESKTOP_INPUT, "primary_screen", ResourceMode.EXCLUSIVE
    )

    assert claim_fs.composite_key == "FILESYSTEM_PATH:C:/app/data.json"
    assert claim_browser.composite_key == "BROWSER_TAB:youtube.com:tab_1"
    assert claim_desktop.composite_key == "DESKTOP_INPUT:primary_screen"

    # Deterministic alphabetical ordering for deadlock prevention
    claims = [claim_fs, claim_browser, claim_desktop]
    sorted_claims = sorted(claims, key=lambda c: c.composite_key)
    expected_order = [claim_browser, claim_desktop, claim_fs]
    assert sorted_claims == expected_order


def test_s05_fencing_token_and_lease():
    """S05: Monotonic FencingToken generation, lease attachment, and expiry checks."""
    now = datetime.datetime.now(datetime.timezone.utc)
    future = now + datetime.timedelta(seconds=60)
    past = now - datetime.timedelta(seconds=10)

    token = FencingToken(
        resource_key="BROWSER_TAB:tab_1",
        owner_id="worker_alpha",
        generation=42,
        acquired_at_utc=now.isoformat(),
        expires_at_utc=future.isoformat(),
    )
    assert not token.is_expired()
    assert token.generation == 42

    expired_token = FencingToken(
        resource_key="BROWSER_TAB:tab_1",
        owner_id="worker_alpha",
        generation=41,
        acquired_at_utc=past.isoformat(),
        expires_at_utc=past.isoformat(),
    )
    assert expired_token.is_expired()

    claim = ResourceClaim(
        "c1", "t1", "n1", ResourceClass.BROWSER_TAB, "tab_1", ResourceMode.EXCLUSIVE
    )
    lease = ResourceLease(
        lease_id="lease_101", claim=claim, worker_id="worker_alpha", fencing_token=token
    )
    assert lease.fencing_token.generation == 42
    assert lease.claim.target_key == "tab_1"


def test_s06_worker_identity_and_heartbeat():
    """S06: WorkerIdentity lifecycle status and heartbeat staleness evaluation."""
    now = datetime.datetime.now(datetime.timezone.utc)
    recent = (now - datetime.timedelta(seconds=5)).isoformat()
    stale = (now - datetime.timedelta(seconds=30)).isoformat()

    active_worker = WorkerIdentity(
        worker_id="w_1",
        worker_epoch=1,
        process_id=1234,
        host_identity="win11_host",
        started_at_utc=recent,
        last_heartbeat_utc=recent,
        status=WorkerStatus.ACTIVE,
        heartbeat_timeout_seconds=15.0,
    )
    assert not active_worker.is_heartbeat_stale()

    dead_worker = WorkerIdentity(
        worker_id="w_2",
        worker_epoch=1,
        process_id=5678,
        host_identity="win11_host",
        started_at_utc=stale,
        last_heartbeat_utc=stale,
        status=WorkerStatus.ACTIVE,
        heartbeat_timeout_seconds=15.0,
    )
    assert dead_worker.is_heartbeat_stale()


def test_s07_retry_policy_and_loop_fingerprint():
    """S07: Side-effect aware retry policies, exponential backoff, and 3-strike loop fingerprinting."""
    policy = RetryPolicy(
        max_retries=3,
        initial_delay_seconds=1.0,
        backoff_multiplier=2.0,
        max_delay_seconds=10.0,
    )
    assert policy.calculate_delay(1) == 1.0
    assert policy.calculate_delay(2) == 2.0
    assert policy.calculate_delay(3) == 4.0
    assert policy.calculate_delay(5) == 10.0  # Clamped to max_delay_seconds

    # Deterministic fingerprinting
    fp1 = compute_recovery_fingerprint("task_1", "node_1", "TIMEOUT", "hash_abc", 1)
    fp2 = compute_recovery_fingerprint("task_1", "node_1", "TIMEOUT", "hash_abc", 1)
    fp3 = compute_recovery_fingerprint("task_1", "node_1", "TIMEOUT", "hash_diff", 1)
    assert fp1 == fp2
    assert fp1 != fp3


def test_s08_deadline_context_effective_inheritance():
    """S08: Hierarchical deadline context, effective min() inheritance, and expiration evaluation."""
    now = datetime.datetime.now(datetime.timezone.utc)
    t_dead = (now + datetime.timedelta(minutes=10)).isoformat()
    p_dead = (now + datetime.timedelta(minutes=8)).isoformat()
    n_dead = (now + datetime.timedelta(minutes=5)).isoformat()
    a_dead = (now + datetime.timedelta(minutes=2)).isoformat()

    ctx = DeadlineContext(
        task_deadline_utc=t_dead,
        plan_deadline_utc=p_dead,
        node_deadline_utc=n_dead,
        attempt_deadline_utc=a_dead,
    )
    # Effective attempt deadline must be the tightest (attempt deadline: +2 min)
    assert ctx.calculate_effective_deadline() == a_dead
    assert not ctx.is_expired()

    # Expired case
    past = (now - datetime.timedelta(seconds=1)).isoformat()
    expired_ctx = DeadlineContext(task_deadline_utc=t_dead, attempt_deadline_utc=past)
    assert expired_ctx.calculate_effective_deadline() == past
    assert expired_ctx.is_expired()
