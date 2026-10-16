"""11-Point Command Admission Pipeline for Track 3.2.

Enforces strict pre-execution admission criteria:
1. Structural integrity and non-empty IDs.
2. Active task and plan revision validation.
3. Deadline and expiration check.
4. Idempotency ledger reservation / duplicate detection.
5. Capability existence in authoritative registry.
6. Argument schema validation.
7. Cryptographic argument hash integrity verification.
8. Permission validation.
9. Operator approval binding and argument hash match.
10. System risk policy verification.
11. Sandbox tier capability and fail-closed readiness.
"""

from __future__ import annotations

from dataclasses import dataclass
import datetime
import hashlib
import json
import logging

from jarvis_agent.execution.errors.taxonomy import ExecutionFailureClass
from jarvis_agent.execution.idempotency.ledger import IdempotencyLedger
from jarvis_agent.execution.models.capability_definition import CapabilityDefinition
from jarvis_agent.execution.models.execution_result import ExecutionResult
from jarvis_agent.execution.models.idempotency_record import IdempotencyState
from jarvis_agent.execution.registry.capability_registry import CapabilityRegistry
from jarvis_agent.execution.sandbox.host_adapter import SandboxManager
from jarvis_agent.orchestration.models.approval import ApprovalRequest, ApprovalStatus
from jarvis_agent.orchestration.models.command import ExecutionCommand
from jarvis_agent.orchestration.models.risk import RiskClass

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AdmissionResult:
    """Result of evaluating command against the 11-point admission pipeline."""

    admitted: bool
    failure_class: ExecutionFailureClass | None = None
    error_message: str | None = None
    cached_result: ExecutionResult | None = None
    capability_def: CapabilityDefinition | None = None


class AdmissionController:
    """Evaluates incoming ExecutionCommands prior to dispatch."""

    def __init__(
        self,
        registry: CapabilityRegistry,
        idempotency_ledger: IdempotencyLedger,
        sandbox_manager: SandboxManager,
    ) -> None:
        self.registry = registry
        self.idempotency_ledger = idempotency_ledger
        self.sandbox_manager = sandbox_manager

    def evaluate(
        self,
        command: ExecutionCommand,
        active_plan_revision: int | None = None,
        approval: ApprovalRequest | None = None,
        granted_permissions: set[str] | None = None,
        max_allowed_risk: RiskClass = RiskClass.CRITICAL,
    ) -> AdmissionResult:
        """Run the full 11-point admission checks against command."""
        # 1. Structural integrity
        if not command.command_id or not command.task_id or not command.plan_id or not command.node_id:
            return AdmissionResult(
                admitted=False,
                failure_class=ExecutionFailureClass.INVALID_COMMAND,
                error_message="Command missing required structural identifiers (command_id, task_id, plan_id, node_id)",
            )

        # 2. Task & Plan Revision match
        if active_plan_revision is not None and command.plan_revision < active_plan_revision:
            return AdmissionResult(
                admitted=False,
                failure_class=ExecutionFailureClass.STALE_COMMAND,
                error_message=f"Command plan revision {command.plan_revision} is superseded by active revision {active_plan_revision}",
            )

        # 3. Deadline check
        if command.deadline_utc:
            try:
                deadline_dt = datetime.datetime.fromisoformat(command.deadline_utc)
                now_dt = datetime.datetime.now(datetime.timezone.utc)
                if now_dt > deadline_dt:
                    return AdmissionResult(
                        admitted=False,
                        failure_class=ExecutionFailureClass.TIMEOUT,
                        error_message=f"Command deadline expired at {command.deadline_utc} (current: {now_dt.isoformat()})",
                    )
            except Exception as ex:
                return AdmissionResult(
                    admitted=False,
                    failure_class=ExecutionFailureClass.INVALID_COMMAND,
                    error_message=f"Invalid deadline format: {ex}",
                )

        # 4. Idempotency check
        existing = self.idempotency_ledger.get(command.idempotency_key)
        if existing:
            if existing.state == IdempotencyState.COMPLETED and existing.execution_result:
                # Return cached terminal result directly without re-executing
                cached_res = ExecutionResult.from_dict(existing.execution_result)
                return AdmissionResult(
                    admitted=False,
                    cached_result=cached_res,
                    error_message="Command already completed; returning cached idempotent result",
                )
            elif existing.state == IdempotencyState.IN_PROGRESS:
                return AdmissionResult(
                    admitted=False,
                    failure_class=ExecutionFailureClass.IDEMPOTENCY_CONFLICT,
                    error_message=f"Command {command.command_id} with key {command.idempotency_key} is already in progress",
                )
            else:
                return AdmissionResult(
                    admitted=False,
                    failure_class=ExecutionFailureClass.IDEMPOTENCY_CONFLICT,
                    error_message=f"Duplicate command attempt in state {existing.state.value}",
                )

        # 5. Capability resolution
        cap_def = self.registry.get(command.capability_target)
        if not cap_def:
            return AdmissionResult(
                admitted=False,
                failure_class=ExecutionFailureClass.UNKNOWN_CAPABILITY,
                error_message=f"Capability '{command.capability_target}' is not registered",
            )

        # 6. Argument schema validation
        valid_args, schema_err = self.registry.validate_arguments(
            command.capability_target, command.arguments
        )
        if not valid_args:
            return AdmissionResult(
                admitted=False,
                failure_class=ExecutionFailureClass.INVALID_ARGUMENTS,
                error_message=schema_err or "Invalid command arguments",
            )

        # 7. Cryptographic argument hash integrity
        canonical_args = json.dumps(command.arguments, sort_keys=True, separators=(",", ":"))
        computed_hash = hashlib.sha256(canonical_args.encode("utf-8")).hexdigest()
        if computed_hash != command.arguments_hash:
            return AdmissionResult(
                admitted=False,
                failure_class=ExecutionFailureClass.INVALID_COMMAND,
                error_message=f"Arguments hash mismatch: expected {command.arguments_hash}, computed {computed_hash}",
            )

        # 8. Permission check
        if cap_def.required_permissions:
            granted = granted_permissions or set()
            missing = [p for p in cap_def.required_permissions if p not in granted]
            if missing:
                return AdmissionResult(
                    admitted=False,
                    failure_class=ExecutionFailureClass.PERMISSION_DENIED,
                    error_message=f"Missing required permissions for {cap_def.capability_id}: {missing}",
                )

        # 9. Approval binding & hash check
        needs_approval = (
            cap_def.risk_class in (RiskClass.HIGH, RiskClass.CRITICAL)
            or bool(command.approval_id)
        )
        if needs_approval:
            if not command.approval_id or not approval:
                return AdmissionResult(
                    admitted=False,
                    failure_class=ExecutionFailureClass.APPROVAL_INVALID,
                    error_message=f"Capability '{cap_def.capability_id}' with risk {cap_def.risk_class.value} requires operator approval",
                )
            if approval.status != ApprovalStatus.GRANTED:
                return AdmissionResult(
                    admitted=False,
                    failure_class=ExecutionFailureClass.APPROVAL_INVALID,
                    error_message=f"Approval {approval.approval_id} is in status {approval.status.value}, not GRANTED",
                )
            if approval.arguments_hash != command.arguments_hash:
                return AdmissionResult(
                    admitted=False,
                    failure_class=ExecutionFailureClass.APPROVAL_INVALID,
                    error_message=f"Approval arguments hash {approval.arguments_hash} does not match command {command.arguments_hash}",
                )
            if approval.is_expired():
                return AdmissionResult(
                    admitted=False,
                    failure_class=ExecutionFailureClass.APPROVAL_INVALID,
                    error_message=f"Approval {approval.approval_id} expired at {approval.expires_at_utc}",
                )

        # 10. Risk policy ceiling check
        risk_precedence = {
            RiskClass.READ_ONLY: 0,
            RiskClass.LOW: 1,
            RiskClass.MEDIUM: 2,
            RiskClass.HIGH: 3,
            RiskClass.CRITICAL: 4,
        }
        if risk_precedence.get(cap_def.risk_class, 99) > risk_precedence.get(max_allowed_risk, 99):
            return AdmissionResult(
                admitted=False,
                failure_class=ExecutionFailureClass.POLICY_DENIED,
                error_message=f"Capability risk {cap_def.risk_class.value} exceeds policy ceiling {max_allowed_risk.value}",
            )

        # 11. Sandbox tier capability & fail-closed check
        tier_ok, sandbox_err = self.sandbox_manager.check_tier_available(
            cap_def.sandbox_tier_required
        )
        if not tier_ok:
            return AdmissionResult(
                admitted=False,
                failure_class=ExecutionFailureClass.SANDBOX_DENIED,
                error_message=f"Required sandbox {cap_def.sandbox_tier_required} unavailable: {sandbox_err}",
            )

        # 12. Reserve execution in idempotency ledger
        reserved, record = self.idempotency_ledger.reserve(command)
        if not reserved:
            return AdmissionResult(
                admitted=False,
                failure_class=ExecutionFailureClass.IDEMPOTENCY_CONFLICT,
                error_message=f"Failed to reserve idempotency key: already in state {record.state.value}",
            )

        return AdmissionResult(
            admitted=True,
            capability_def=cap_def,
        )


__all__ = ["AdmissionController", "AdmissionResult"]
