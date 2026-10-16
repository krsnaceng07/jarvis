"""Track 3.3 Retry, Cancellation, and Deadline Test Suite (S41–S50).

Validates:
S41: READ_ONLY execution failures retry with exponential backoff delay.
S42: Non-retryable failure classes (SANDBOX_DENIED, INVALID_COMMAND) trigger FAIL without retry.
S43: NON_IDEMPOTENT_MUTATION side-effect class failures trigger REPLAN, preventing replay loops.
S44: EXTERNAL_TRANSACTION side-effect class failures trigger ESCALATE.
S45: 3-Strike recovery loop detector triggers ESCALATE upon third identical failure fingerprint.
S46: Max attempts exhaustion terminates with FAIL.
S47: Two-phase cancellation emits structured CancellationRequest and confirms abort.
S48: Failed abort leaves cancellation in FAILED_TO_TERMINATE rather than falsely claiming CANCELLED.
S49: Strict deadline inheritance derives effective_attempt_deadline = min(attempt, node, plan, task).
S50: DeadlineManager correctly flags expired deadlines against current UTC time.
"""

from __future__ import annotations

import datetime

from jarvis_agent.execution.errors.taxonomy import ExecutionFailureClass
from jarvis_agent.execution.models.capability_definition import SideEffectClass
from jarvis_agent.execution.models.execution_result import ExecutionResult, ExecutionStatus
from jarvis_agent.scheduling.cancellation.cancellation_manager import CancellationManager
from jarvis_agent.scheduling.deadline.deadline_manager import DeadlineManager
from jarvis_agent.scheduling.models.cancellation import CancellationConfirmationStatus
from jarvis_agent.scheduling.models.retry import RecoveryAction
from jarvis_agent.scheduling.retry.retry_manager import RetryManager


def _make_res(
    task_id: str = "t1",
    node_id: str = "n1",
    status: ExecutionStatus = ExecutionStatus.FAILED,
    failure_class: str = ExecutionFailureClass.TIMEOUT.value,
) -> ExecutionResult:
    return ExecutionResult.create_terminal(
        command_id="cmd_1",
        task_id=task_id,
        plan_id="p1",
        plan_revision=1,
        node_id=node_id,
        attempt_id=1,
        execution_id="exec_1",
        status=status,
        started_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        failure_class=failure_class,
        error_message="Simulated error",
    )


def test_s41_read_only_exponential_backoff_retry():
    """S41: READ_ONLY execution failures retry with exponential backoff delay."""
    mgr = RetryManager()
    res = _make_res(failure_class=ExecutionFailureClass.TIMEOUT.value)

    dec = mgr.evaluate_failure(
        result=res,
        side_effect_class=SideEffectClass.READ_ONLY,
        arguments_hash="hash_abc",
        current_attempt=1,
        max_attempts=3,
    )
    assert dec.action == RecoveryAction.RETRY
    assert dec.delay_seconds > 0.0
    assert dec.next_attempt_id == 2


def test_s42_non_retryable_failure_class():
    """S42: Non-retryable failure classes (SANDBOX_DENIED) trigger FAIL without retry."""
    mgr = RetryManager()
    res = _make_res(failure_class=ExecutionFailureClass.SANDBOX_DENIED.value)

    dec = mgr.evaluate_failure(
        result=res,
        side_effect_class=SideEffectClass.READ_ONLY,
        arguments_hash="hash_abc",
        current_attempt=1,
        max_attempts=3,
    )
    assert dec.action == RecoveryAction.FAIL
    assert "SANDBOX_DENIED is non-retryable" in dec.reason


def test_s43_non_idempotent_mutation_triggers_replan():
    """S43: NON_IDEMPOTENT_MUTATION side-effect class failures trigger REPLAN."""
    mgr = RetryManager()
    res = _make_res(failure_class=ExecutionFailureClass.EXECUTION_FAILURE.value)

    dec = mgr.evaluate_failure(
        result=res,
        side_effect_class=SideEffectClass.NON_IDEMPOTENT_MUTATION,
        arguments_hash="hash_abc",
        current_attempt=1,
        max_attempts=3,
    )
    assert dec.action == RecoveryAction.REPLAN
    assert "NON_IDEMPOTENT_MUTATION" in dec.reason


def test_s44_external_transaction_triggers_escalate():
    """S44: EXTERNAL_TRANSACTION side-effect class failures trigger ESCALATE."""
    mgr = RetryManager()
    res = _make_res(failure_class=ExecutionFailureClass.EXECUTION_FAILURE.value)

    dec = mgr.evaluate_failure(
        result=res,
        side_effect_class=SideEffectClass.EXTERNAL_TRANSACTION,
        arguments_hash="hash_abc",
        current_attempt=1,
        max_attempts=3,
    )
    assert dec.action == RecoveryAction.ESCALATE
    assert "EXTERNAL_TRANSACTION" in dec.reason


def test_s45_three_strike_loop_detector():
    """S45: 3-Strike recovery loop detector triggers ESCALATE upon third identical failure fingerprint."""
    mgr = RetryManager(max_loop_count=3)
    res = _make_res(failure_class=ExecutionFailureClass.NETWORK_FAILURE.value)

    # Attempt 1 -> RETRY
    d1 = mgr.evaluate_failure(res, SideEffectClass.READ_ONLY, "hash_123", 1, 5)
    assert d1.action == RecoveryAction.RETRY

    # Attempt 2 -> RETRY
    d2 = mgr.evaluate_failure(res, SideEffectClass.READ_ONLY, "hash_123", 2, 5)
    assert d2.action == RecoveryAction.RETRY

    # Attempt 3 -> 3rd strike triggers ESCALATE
    d3 = mgr.evaluate_failure(res, SideEffectClass.READ_ONLY, "hash_123", 3, 5)
    assert d3.action == RecoveryAction.ESCALATE
    assert "3-strike recovery loop detected" in d3.reason


def test_s46_max_attempts_exhaustion():
    """S46: Max attempts exhaustion terminates with FAIL."""
    mgr = RetryManager()
    res = _make_res(failure_class=ExecutionFailureClass.TIMEOUT.value)

    dec = mgr.evaluate_failure(
        result=res,
        side_effect_class=SideEffectClass.READ_ONLY,
        arguments_hash="hash_different",
        current_attempt=3,
        max_attempts=3,
    )
    assert dec.action == RecoveryAction.FAIL
    assert "Max attempts exceeded" in dec.reason


def test_s47_cancellation_manager_abort_confirmation():
    """S47: Two-phase cancellation emits structured CancellationRequest and confirms abort."""
    mgr = CancellationManager(execution_runtime=None)
    req = mgr.request_cancellation(
        target_id="task_99", target_type="TASK", reason="User requested stop"
    )
    assert req.target_id == "task_99"
    assert req.reason == "User requested stop"

    rec = mgr.abort_execution(execution_id="exec_99", node_id="node_1")
    assert rec.status == CancellationConfirmationStatus.CONFIRMED_TERMINATED


def test_s48_failed_abort_reports_status():
    """S48: Failed abort leaves cancellation in FAILED_TO_TERMINATE rather than claiming CANCELLED."""

    class MockRuntime:
        def cancel_execution(self, exec_id: str) -> bool:
            return False  # Failed to stop process

    mgr = CancellationManager(execution_runtime=MockRuntime())
    rec = mgr.abort_execution(execution_id="exec_unresponsive", node_id="node_x")
    assert rec.status == CancellationConfirmationStatus.FAILED_TO_TERMINATE


def test_s49_strict_deadline_inheritance():
    """S49: Strict deadline inheritance derives effective_attempt_deadline = min(attempt, node, plan, task)."""
    now = datetime.datetime.now(datetime.timezone.utc)
    t_dead = (now + datetime.timedelta(minutes=30)).isoformat()
    p_dead = (now + datetime.timedelta(minutes=20)).isoformat()
    n_dead = (now + datetime.timedelta(minutes=10)).isoformat()
    a_dead = (now + datetime.timedelta(minutes=5)).isoformat()

    eff = DeadlineManager.compute_effective_deadline(
        attempt_deadline_utc=a_dead,
        node_deadline_utc=n_dead,
        plan_deadline_utc=p_dead,
        task_deadline_utc=t_dead,
    )
    assert eff == a_dead

    # When child attempt has no deadline, tightest parent (node: 10m) is inherited
    eff2 = DeadlineManager.compute_effective_deadline(
        attempt_deadline_utc=None,
        node_deadline_utc=n_dead,
        plan_deadline_utc=p_dead,
        task_deadline_utc=t_dead,
    )
    assert eff2 == n_dead


def test_s50_deadline_expiration_check():
    """S50: DeadlineManager correctly flags expired deadlines against current UTC time."""
    now = datetime.datetime.now(datetime.timezone.utc)
    past = (now - datetime.timedelta(seconds=5)).isoformat()
    future = (now + datetime.timedelta(seconds=60)).isoformat()

    assert DeadlineManager.is_expired(past)
    assert not DeadlineManager.is_expired(future)
    assert not DeadlineManager.is_expired(None)
