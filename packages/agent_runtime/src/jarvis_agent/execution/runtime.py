"""Master Execution Runtime for Track 3.2.

Coordinates the end-to-end execution pipeline beneath Track 3.1 orchestration:
1. Admission validation (11-point gate).
2. Idempotency reservation and deduplication.
3. Sandbox isolation environment preparation (fail-closed).
4. Command dispatch to domain adapters.
5. Empirical observation collection with cryptographic digests.
6. Independent machine-checkable state verification.
7. Terminal idempotency ledger update and event store journaling.
"""

from __future__ import annotations

import datetime
import logging
from pathlib import Path
from typing import Any
import uuid

from jarvis_agent.execution.adapters.browser import BrowserAdapter
from jarvis_agent.execution.adapters.channels import ChannelAdapter
from jarvis_agent.execution.adapters.desktop import DesktopAdapter
from jarvis_agent.execution.adapters.filesystem import FilesystemAdapter
from jarvis_agent.execution.adapters.process import ProcessAdapter
from jarvis_agent.execution.adapters.system import SystemAdapter
from jarvis_agent.execution.dispatcher.admission import (
    AdmissionController,
    AdmissionResult,
)
from jarvis_agent.execution.dispatcher.dispatcher import CommandDispatcher
from jarvis_agent.execution.errors.taxonomy import ExecutionFailureClass
from jarvis_agent.execution.idempotency.ledger import IdempotencyLedger
from jarvis_agent.execution.models.execution_result import (
    ExecutionResult,
    ExecutionStatus,
)
from jarvis_agent.execution.models.idempotency_record import IdempotencyState
from jarvis_agent.execution.observation.collector import ObservationCollector
from jarvis_agent.execution.registry.capability_registry import CapabilityRegistry
from jarvis_agent.execution.sandbox.host_adapter import SandboxManager
from jarvis_agent.execution.verification.verifier import StateVerifier
from jarvis_agent.orchestration.models.approval import ApprovalRequest
from jarvis_agent.orchestration.models.command import ExecutionCommand
from jarvis_agent.orchestration.models.observation import (
    ObservationRequirement,
)
from jarvis_agent.orchestration.models.risk import RiskClass
from jarvis_agent.orchestration.models.verification import (
    VerificationRequirement,
)
from jarvis_agent.orchestration.state.event import DomainEvent, EventType
from jarvis_agent.orchestration.state.event_store import EventStore

logger = logging.getLogger(__name__)


class ExecutionRuntime:
    """Authoritative execution runtime for JARVIS."""

    def __init__(
        self,
        registry: CapabilityRegistry,
        idempotency_ledger: IdempotencyLedger,
        sandbox_manager: SandboxManager,
        dispatcher: CommandDispatcher,
        observation_collector: ObservationCollector,
        state_verifier: StateVerifier,
        event_store: EventStore | None = None,
    ) -> None:
        self.registry = registry
        self.idempotency_ledger = idempotency_ledger
        self.sandbox_manager = sandbox_manager
        self.dispatcher = dispatcher
        self.observation_collector = observation_collector
        self.state_verifier = state_verifier
        self.event_store = event_store
        self.admission = AdmissionController(
            registry=registry,
            idempotency_ledger=idempotency_ledger,
            sandbox_manager=sandbox_manager,
        )

    @classmethod
    def create_default(
        cls,
        state_dir: str | Path | None = None,
        event_store: EventStore | None = None,
        force_fail_sandbox_tiers: set[str] | None = None,
    ) -> ExecutionRuntime:
        """Construct a fully wired ExecutionRuntime with standard adapters and built-in registry."""
        base_dir = Path(state_dir or Path.home() / ".jarvis" / "state")
        base_dir.mkdir(parents=True, exist_ok=True)
        db_path = base_dir / "idempotency.sqlite"

        registry = CapabilityRegistry()
        ledger = IdempotencyLedger(db_path)
        sandbox = SandboxManager(force_fail_tiers=force_fail_sandbox_tiers)

        # Instantiate adapters
        fs_adapter = FilesystemAdapter(allowed_roots=[Path.cwd(), base_dir])
        proc_adapter = ProcessAdapter()
        browser_adapter = BrowserAdapter()
        desk_adapter = DesktopAdapter()
        sys_adapter = SystemAdapter()
        chan_adapter = ChannelAdapter()

        dispatcher = CommandDispatcher(
            adapters=[
                fs_adapter,
                proc_adapter,
                browser_adapter,
                desk_adapter,
                sys_adapter,
                chan_adapter,
            ]
        )

        collector = ObservationCollector()
        verifier = StateVerifier()

        return cls(
            registry=registry,
            idempotency_ledger=ledger,
            sandbox_manager=sandbox,
            dispatcher=dispatcher,
            observation_collector=collector,
            state_verifier=verifier,
            event_store=event_store,
        )

    def execute_command(
        self,
        command: ExecutionCommand,
        active_plan_revision: int | None = None,
        approval: ApprovalRequest | None = None,
        granted_permissions: set[str] | None = None,
        max_allowed_risk: RiskClass = RiskClass.CRITICAL,
        observation_requirements: list[ObservationRequirement] | None = None,
        verification_requirements: list[VerificationRequirement] | None = None,
        baseline_fingerprint: str | None = None,
        current_fingerprint: str | None = None,
    ) -> ExecutionResult:
        """Execute command through admission, sandbox, dispatch, observation, and verification."""
        started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Step 1: Admission check
        adm_result: AdmissionResult = self.admission.evaluate(
            command=command,
            active_plan_revision=active_plan_revision,
            approval=approval,
            granted_permissions=granted_permissions,
            max_allowed_risk=max_allowed_risk,
        )

        if not adm_result.admitted:
            if adm_result.cached_result is not None:
                # Idempotent replay of already completed command
                logger.info("Returning cached idempotent result for %s", command.command_id)
                return adm_result.cached_result

            fail_cls = (
                adm_result.failure_class.value
                if adm_result.failure_class
                else ExecutionFailureClass.INVALID_COMMAND.value
            )
            # Record failed terminal state in ledger
            self.idempotency_ledger.record_terminal(
                idempotency_key=command.idempotency_key,
                state=IdempotencyState.FAILED,
                error_message=adm_result.error_message,
            )

            res = ExecutionResult.create_terminal(
                command_id=command.command_id,
                task_id=command.task_id,
                plan_id=command.plan_id,
                plan_revision=command.plan_revision,
                node_id=command.node_id,
                attempt_id=command.attempt_id,
                execution_id=command.execution_id,
                status=ExecutionStatus.FAILED,
                started_at_utc=started_at,
                error_message=adm_result.error_message,
                failure_class=fail_cls,
                idempotency_key=command.idempotency_key,
            )
            self._journal_failure(command, res)
            return res

        cap_def = adm_result.capability_def or self.registry.get(command.capability_target)
        tier_required = cap_def.sandbox_tier_required if cap_def else "TIER_0_APP"

        # Step 2: Prepare Sandbox
        sb_ok, sb_ctx, sb_err = self.sandbox_manager.prepare_sandbox(
            capability_id=command.capability_target,
            tier_required=tier_required,
        )
        if not sb_ok:
            self.idempotency_ledger.record_terminal(
                idempotency_key=command.idempotency_key,
                state=IdempotencyState.FAILED,
                error_message=sb_err,
            )
            res = ExecutionResult.create_terminal(
                command_id=command.command_id,
                task_id=command.task_id,
                plan_id=command.plan_id,
                plan_revision=command.plan_revision,
                node_id=command.node_id,
                attempt_id=command.attempt_id,
                execution_id=command.execution_id,
                status=ExecutionStatus.FAILED,
                started_at_utc=started_at,
                error_message=sb_err or "Sandbox preparation failed closed",
                failure_class=ExecutionFailureClass.SANDBOX_DENIED.value,
                idempotency_key=command.idempotency_key,
                sandbox_tier_used=tier_required,
            )
            self._journal_failure(command, res)
            return res

        # Step 3: Journal NODE_STARTED
        self._journal_event(
            EventType.NODE_STARTED,
            command.task_id,
            {
                "node_id": command.node_id,
                "command_id": command.command_id,
                "attempt_id": command.attempt_id,
                "capability_target": command.capability_target,
                "sandbox_tier": tier_required,
            },
        )

        # Step 4: Dispatch command
        try:
            adapter_out = self.dispatcher.dispatch(command, sb_ctx)
        except Exception as ex:
            logger.exception("Adapter unhandled exception during command dispatch: %s", ex)
            self.idempotency_ledger.record_terminal(
                idempotency_key=command.idempotency_key,
                state=IdempotencyState.FAILED,
                error_message=str(ex),
            )
            res = ExecutionResult.create_terminal(
                command_id=command.command_id,
                task_id=command.task_id,
                plan_id=command.plan_id,
                plan_revision=command.plan_revision,
                node_id=command.node_id,
                attempt_id=command.attempt_id,
                execution_id=command.execution_id,
                status=ExecutionStatus.FAILED,
                started_at_utc=started_at,
                error_message=f"Adapter execution exception: {ex}",
                failure_class=ExecutionFailureClass.EXECUTION_FAILURE.value,
                idempotency_key=command.idempotency_key,
                sandbox_tier_used=tier_required,
            )
            self._journal_failure(command, res)
            return res

        # Step 5: Collect observations
        observations = self.observation_collector.collect(
            command=command,
            adapter_output=adapter_out,
            requirements=observation_requirements,
        )

        # Step 6: Journal NODE_OBSERVED
        for obs in observations:
            self._journal_event(
                EventType.NODE_OBSERVED,
                command.task_id,
                obs.to_dict(),
            )

        # Step 7: Independent State Verification
        ver_result = self.state_verifier.verify(
            node_id=command.node_id,
            requirements=verification_requirements,
            observations=observations,
            baseline_fingerprint=baseline_fingerprint,
            current_fingerprint=current_fingerprint,
        )

        # Step 8: Determine Terminal Status
        if adapter_out.success and ver_result.passed:
            status = ExecutionStatus.VERIFIED
            failure_class = None
            error_message = None
        elif adapter_out.success and not ver_result.passed:
            status = ExecutionStatus.VERIFICATION_FAILED
            failure_class = (
                ExecutionFailureClass.STATE_DRIFT.value
                if "state_drift" in ver_result.diffs
                else ExecutionFailureClass.VERIFICATION_FAILURE.value
            )
            error_message = ver_result.error_message or "Postcondition verification failed"
        else:
            status = ExecutionStatus.FAILED
            failure_class = ExecutionFailureClass.EXECUTION_FAILURE.value
            error_message = adapter_out.error_message or "Adapter command execution failed"

        res = ExecutionResult.create_terminal(
            command_id=command.command_id,
            task_id=command.task_id,
            plan_id=command.plan_id,
            plan_revision=command.plan_revision,
            node_id=command.node_id,
            attempt_id=command.attempt_id,
            execution_id=command.execution_id,
            status=status,
            started_at_utc=started_at,
            exit_code=adapter_out.exit_code,
            output_data=adapter_out.output_data,
            error_message=error_message,
            failure_class=failure_class,
            observations=observations,
            verification_result=ver_result,
            evidence_refs=ver_result.evidence_refs,
            idempotency_key=command.idempotency_key,
            sandbox_tier_used=tier_required,
        )

        # Step 9: Update Idempotency Ledger
        idem_state = (
            IdempotencyState.COMPLETED
            if status == ExecutionStatus.VERIFIED
            else IdempotencyState.FAILED
        )
        self.idempotency_ledger.record_terminal(
            idempotency_key=command.idempotency_key,
            state=idem_state,
            execution_result=res.to_dict(),
            error_message=error_message,
        )

        # Step 10: Journal terminal event
        if status == ExecutionStatus.VERIFIED:
            self._journal_event(
                EventType.NODE_VERIFIED,
                command.task_id,
                {
                    "node_id": command.node_id,
                    "command_id": command.command_id,
                    "verification": ver_result.to_dict(),
                },
            )
        else:
            self._journal_failure(command, res)

        return res

    def cancel_execution(self, execution_id: str) -> bool:
        """Cancel ongoing execution across all registered adapters."""
        return self.dispatcher.cancel(execution_id)

    def _journal_event(self, event_type: EventType, task_id: str, payload: dict[str, Any]) -> None:
        if not self.event_store:
            return
        try:
            seq = self.event_store.get_latest_sequence(task_id) + 1
            evt = DomainEvent(
                event_id=f"evt_{uuid.uuid4().hex[:12]}",
                task_id=task_id,
                conversation_id="",
                event_type=event_type,
                timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                payload=payload,
                sequence_number=seq,
            )
            self.event_store.append(evt)
        except Exception as ex:
            logger.error("Failed to append domain event %s: %s", event_type.value, ex)

    def _journal_failure(self, command: ExecutionCommand, result: ExecutionResult) -> None:
        self._journal_event(
            EventType.NODE_FAILED,
            command.task_id,
            {
                "node_id": command.node_id,
                "command_id": command.command_id,
                "error_message": result.error_message,
                "failure_class": result.failure_class,
            },
        )

    def close(self) -> None:
        """Release database connections and resources."""
        self.idempotency_ledger.close()


__all__ = ["ExecutionRuntime"]
