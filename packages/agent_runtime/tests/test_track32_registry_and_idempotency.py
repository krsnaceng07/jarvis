"""Unit tests for CapabilityRegistry and IdempotencyLedger."""

from __future__ import annotations

from pathlib import Path
import tempfile

from jarvis_agent.execution.idempotency.ledger import IdempotencyLedger
from jarvis_agent.execution.models.idempotency_record import IdempotencyState
from jarvis_agent.execution.registry.capability_registry import CapabilityRegistry
from jarvis_agent.orchestration.models.command import ExecutionCommand
from jarvis_agent.orchestration.models.risk import RiskAssessment, RiskClass


def test_capability_registry_builtins_and_schema_validation() -> None:
    reg = CapabilityRegistry()
    assert reg.has("browser.open")
    assert reg.has("filesystem.write")
    assert reg.has("process.spawn")
    assert reg.has("channels.send_message")

    # Valid arguments for filesystem.write
    valid, err = reg.validate_arguments(
        "filesystem.write", {"path": "foo.txt", "content": "hello"}
    )
    assert valid is True
    assert err is None

    # Missing required argument for filesystem.write
    valid, err = reg.validate_arguments("filesystem.write", {"path": "foo.txt"})
    assert valid is False
    assert "Missing required argument 'content'" in str(err)

    # Type mismatch
    valid, err = reg.validate_arguments(
        "filesystem.write", {"path": 12345, "content": "hello"}
    )
    assert valid is False
    assert "must be a string" in str(err)


def test_idempotency_ledger_lifecycle_and_deduplication() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_idempotency.sqlite"
        ledger = IdempotencyLedger(db_path)

        risk = RiskAssessment(
            risk_class=RiskClass.LOW,
            blast_radius="LOCAL",
            reversibility="REVERSIBLE",
            data_sensitivity="INTERNAL",
            external_effect="NONE",
            requires_operator_approval=False,
        )
        cmd = ExecutionCommand.create(
            command_id="cmd_001",
            task_id="task_001",
            plan_id="plan_001",
            node_id="node_001",
            execution_id="exec_001",
            attempt_id=1,
            plan_revision=1,
            capability_target="filesystem.read",
            arguments={"path": "test.txt"},
            deadline_utc="2030-01-01T00:00:00Z",
            risk_assessment=risk,
        )

        # 1. First reservation must succeed
        reserved, rec = ledger.reserve(cmd)
        assert reserved is True
        assert rec.state == IdempotencyState.IN_PROGRESS

        # 2. Immediate second reservation must fail with existing IN_PROGRESS record
        reserved2, rec2 = ledger.reserve(cmd)
        assert reserved2 is False
        assert rec2.state == IdempotencyState.IN_PROGRESS

        # 3. Record terminal completion
        ledger.record_terminal(
            idempotency_key=cmd.idempotency_key,
            state=IdempotencyState.COMPLETED,
            execution_result={"status": "VERIFIED", "exit_code": 0},
        )

        rec_term = ledger.get(cmd.idempotency_key)
        assert rec_term is not None
        assert rec_term.state == IdempotencyState.COMPLETED
        assert rec_term.execution_result == {"status": "VERIFIED", "exit_code": 0}

        # 4. Third reservation returns False with COMPLETED record (enabling cached replay)
        reserved3, rec3 = ledger.reserve(cmd)
        assert reserved3 is False
        assert rec3.state == IdempotencyState.COMPLETED

        ledger.close()

        # 5. Persistence across reopen
        ledger_reopened = IdempotencyLedger(db_path)
        persisted = ledger_reopened.get(cmd.idempotency_key)
        assert persisted is not None
        assert persisted.state == IdempotencyState.COMPLETED
        ledger_reopened.close()
