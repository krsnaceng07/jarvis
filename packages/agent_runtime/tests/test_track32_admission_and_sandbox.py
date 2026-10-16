"""Unit tests for 11-point AdmissionController and fail-closed SandboxManager."""

from __future__ import annotations

import datetime
from pathlib import Path
import tempfile

from jarvis_agent.execution.dispatcher.admission import AdmissionController
from jarvis_agent.execution.errors.taxonomy import ExecutionFailureClass
from jarvis_agent.execution.idempotency.ledger import IdempotencyLedger
from jarvis_agent.execution.registry.capability_registry import CapabilityRegistry
from jarvis_agent.execution.sandbox.host_adapter import SandboxManager
from jarvis_agent.orchestration.models.approval import ApprovalRequest, ApprovalStatus
from jarvis_agent.orchestration.models.command import ExecutionCommand
from jarvis_agent.orchestration.models.risk import RiskAssessment, RiskClass


def test_admission_pipeline_11_points() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "admission_idem.sqlite"
        ledger = IdempotencyLedger(db_path)
        registry = CapabilityRegistry()
        sandbox = SandboxManager()
        admission = AdmissionController(registry, ledger, sandbox)

        try:
            risk_low = RiskAssessment(
                risk_class=RiskClass.LOW,
                blast_radius="LOCAL",
                reversibility="REVERSIBLE",
                data_sensitivity="PUBLIC",
                external_effect="NONE",
                requires_operator_approval=False,
            )

            future_deadline = (
                datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
            ).isoformat()
            past_deadline = (
                datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
            ).isoformat()

            # Point 1: Structural validity
            cmd_bad_struct = ExecutionCommand(
                command_id="",
                task_id="t1",
                plan_id="p1",
                node_id="n1",
                execution_id="e1",
                attempt_id=1,
                plan_revision=1,
                capability_target="filesystem.read",
                arguments={"path": "x.txt"},
                arguments_hash="hash",
                idempotency_key="key1",
                issued_at_utc="now",
                deadline_utc=future_deadline,
                risk_assessment=risk_low,
            )
            res = admission.evaluate(cmd_bad_struct)
            assert res.admitted is False
            assert res.failure_class == ExecutionFailureClass.INVALID_COMMAND

            # Point 2: Stale plan revision
            cmd_stale = ExecutionCommand.create(
                command_id="c_stale",
                task_id="t1",
                plan_id="p1",
                node_id="n1",
                execution_id="e1",
                attempt_id=1,
                plan_revision=1,
                capability_target="filesystem.read",
                arguments={"path": "x.txt"},
                deadline_utc=future_deadline,
                risk_assessment=risk_low,
            )
            res = admission.evaluate(cmd_stale, active_plan_revision=2)
            assert res.admitted is False
            assert res.failure_class == ExecutionFailureClass.STALE_COMMAND

            # Point 3: Deadline expiration
            cmd_expired = ExecutionCommand.create(
                command_id="c_exp",
                task_id="t1",
                plan_id="p1",
                node_id="n1",
                execution_id="e1",
                attempt_id=1,
                plan_revision=1,
                capability_target="filesystem.read",
                arguments={"path": "x.txt"},
                deadline_utc=past_deadline,
                risk_assessment=risk_low,
            )
            res = admission.evaluate(cmd_expired)
            assert res.admitted is False
            assert res.failure_class == ExecutionFailureClass.TIMEOUT

            # Point 5: Unknown capability
            cmd_unknown = ExecutionCommand.create(
                command_id="c_unk",
                task_id="t1",
                plan_id="p1",
                node_id="n1",
                execution_id="e1",
                attempt_id=1,
                plan_revision=1,
                capability_target="nonexistent.tool",
                arguments={"path": "x.txt"},
                deadline_utc=future_deadline,
                risk_assessment=risk_low,
            )
            res = admission.evaluate(cmd_unknown)
            assert res.admitted is False
            assert res.failure_class == ExecutionFailureClass.UNKNOWN_CAPABILITY

            # Point 6: Invalid argument schema
            cmd_bad_args = ExecutionCommand.create(
                command_id="c_args",
                task_id="t1",
                plan_id="p1",
                node_id="n1",
                execution_id="e1",
                attempt_id=1,
                plan_revision=1,
                capability_target="filesystem.write",
                arguments={"path": "x.txt"},  # missing 'content'
                deadline_utc=future_deadline,
                risk_assessment=risk_low,
            )
            res = admission.evaluate(cmd_bad_args)
            assert res.admitted is False
            assert res.failure_class == ExecutionFailureClass.INVALID_ARGUMENTS

            # Point 7: Arguments hash mismatch (tampering)
            cmd_tampered = ExecutionCommand(
                command_id="c_tamp",
                task_id="t1",
                plan_id="p1",
                node_id="n1",
                execution_id="e1",
                attempt_id=1,
                plan_revision=1,
                capability_target="filesystem.read",
                arguments={"path": "x.txt"},
                arguments_hash="forged_bad_hash",
                idempotency_key="key_tamp",
                issued_at_utc="now",
                deadline_utc=future_deadline,
                risk_assessment=risk_low,
            )
            res = admission.evaluate(cmd_tampered)
            assert res.admitted is False
            assert res.failure_class == ExecutionFailureClass.INVALID_COMMAND
            assert "Arguments hash mismatch" in str(res.error_message)

            # Point 8: Missing required permissions
            cmd_perm = ExecutionCommand.create(
                command_id="c_perm",
                task_id="t1",
                plan_id="p1",
                node_id="n1",
                execution_id="e1",
                attempt_id=1,
                plan_revision=1,
                capability_target="filesystem.write",
                arguments={"path": "x.txt", "content": "hi"},
                deadline_utc=future_deadline,
                risk_assessment=risk_low,
            )
            # Granted empty permissions
            res = admission.evaluate(cmd_perm, granted_permissions=set())
            assert res.admitted is False
            assert res.failure_class == ExecutionFailureClass.PERMISSION_DENIED

            # Point 9: Approval requirement for high risk operations
            risk_high = RiskAssessment(
                risk_class=RiskClass.HIGH,
                blast_radius="SYSTEM",
                reversibility="IRREVERSIBLE",
                data_sensitivity="CONFIDENTIAL",
                external_effect="EXTERNAL_MUTATION",
                requires_operator_approval=True,
            )
            cmd_high = ExecutionCommand.create(
                command_id="c_high",
                task_id="t1",
                plan_id="p1",
                node_id="n1",
                execution_id="e1",
                attempt_id=1,
                plan_revision=1,
                capability_target="filesystem.delete",
                arguments={"path": "x.txt"},
                deadline_utc=future_deadline,
                risk_assessment=risk_high,
            )
            # Missing approval
            res = admission.evaluate(
                cmd_high, granted_permissions={"filesystem.delete"}
            )
            assert res.admitted is False
            assert res.failure_class == ExecutionFailureClass.APPROVAL_INVALID

            # Approval hash mismatch
            app_mismatch = ApprovalRequest(
                approval_id="app_1",
                task_id="t1",
                node_id="n1",
                capability_target="filesystem.delete",
                arguments_hash="wrong_hash",
                risk_assessment=risk_high,
                status=ApprovalStatus.GRANTED,
                requested_at_utc="now",
                expires_at_utc=future_deadline,
            )
            cmd_high_with_app = ExecutionCommand.create(
                command_id="c_high2",
                task_id="t1",
                plan_id="p1",
                node_id="n1",
                execution_id="e1",
                attempt_id=1,
                plan_revision=1,
                capability_target="filesystem.delete",
                arguments={"path": "x.txt"},
                deadline_utc=future_deadline,
                risk_assessment=risk_high,
                approval_id="app_1",
            )
            res = admission.evaluate(
                cmd_high_with_app,
                approval=app_mismatch,
                granted_permissions={"filesystem.delete"},
            )
            assert res.admitted is False
            assert res.failure_class == ExecutionFailureClass.APPROVAL_INVALID

            # Point 11: Sandbox Fail-Closed Invariant
            faulted_sandbox = SandboxManager(force_fail_tiers={"TIER_1_RESTRICTED_TOKEN"})
            admission_faulted_sb = AdmissionController(registry, ledger, faulted_sandbox)
            cmd_process = ExecutionCommand.create(
                command_id="c_proc",
                task_id="t1",
                plan_id="p1",
                node_id="n1",
                execution_id="e1",
                attempt_id=1,
                plan_revision=1,
                capability_target="process.spawn",
                arguments={"command": "python", "args": ["-c", "print(1)"]},
                deadline_utc=future_deadline,
                risk_assessment=risk_high,
                approval_id="app_valid",
            )
            valid_app = ApprovalRequest(
                approval_id="app_valid",
                task_id="t1",
                node_id="n1",
                capability_target="process.spawn",
                arguments_hash=cmd_process.arguments_hash,
                risk_assessment=risk_high,
                status=ApprovalStatus.GRANTED,
                requested_at_utc="now",
                expires_at_utc=future_deadline,
            )
            res = admission_faulted_sb.evaluate(
                cmd_process,
                approval=valid_app,
                granted_permissions={"process.spawn"},
            )
            assert res.admitted is False
            assert res.failure_class == ExecutionFailureClass.SANDBOX_DENIED
            assert "unavailable" in str(res.error_message)

        finally:
            ledger.close()
