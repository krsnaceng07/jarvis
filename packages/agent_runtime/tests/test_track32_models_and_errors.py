"""Unit tests for Track 3.2 execution models, error taxonomy, and action mappings."""

from __future__ import annotations

import datetime

from jarvis_agent.execution.errors.taxonomy import (
    FAILURE_TO_ACTION_MAP,
    ActionRecommendation,
    ExecutionErrorDetail,
    ExecutionFailureClass,
)
from jarvis_agent.execution.models.capability_definition import (
    CapabilityDefinition,
    SideEffectClass,
)
from jarvis_agent.execution.models.execution_result import (
    ExecutionResult,
    ExecutionStatus,
)
from jarvis_agent.execution.models.idempotency_record import (
    IdempotencyRecord,
    IdempotencyState,
)
from jarvis_agent.orchestration.models.risk import RiskClass


def test_execution_result_lifecycle_and_serialization() -> None:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    res = ExecutionResult.create_terminal(
        command_id="cmd_001",
        task_id="task_001",
        plan_id="plan_001",
        plan_revision=1,
        node_id="node_001",
        attempt_id=1,
        execution_id="exec_001",
        status=ExecutionStatus.VERIFIED,
        started_at_utc=now,
        exit_code=0,
        output_data={"foo": "bar"},
        idempotency_key="key_123",
        sandbox_tier_used="TIER_0_APP",
    )
    assert res.status == ExecutionStatus.VERIFIED
    assert res.status.is_terminal is True
    assert res.exit_code == 0
    assert res.output_data == {"foo": "bar"}

    d = res.to_dict()
    assert d["status"] == "VERIFIED"
    assert d["idempotency_key"] == "key_123"

    deserialized = ExecutionResult.from_dict(d)
    assert deserialized.command_id == res.command_id
    assert deserialized.status == ExecutionStatus.VERIFIED
    assert deserialized.output_data == {"foo": "bar"}


def test_capability_definition_serialization() -> None:
    cap = CapabilityDefinition(
        capability_id="test.tool",
        version="1.2.0",
        description="A test tool",
        input_schema={"type": "object", "properties": {"val": {"type": "integer"}}},
        output_schema={"type": "object"},
        risk_class=RiskClass.MEDIUM,
        required_permissions=["test.perm"],
        sandbox_tier_required="TIER_1_RESTRICTED_TOKEN",
        side_effect_class=SideEffectClass.IDEMPOTENT_MUTATION,
        timeout_seconds=45.0,
        supports_cancellation=True,
    )
    d = cap.to_dict()
    assert d["capability_id"] == "test.tool"
    assert d["risk_class"] == "MEDIUM"
    assert d["side_effect_class"] == "IDEMPOTENT_MUTATION"

    deserialized = CapabilityDefinition.from_dict(d)
    assert deserialized.capability_id == "test.tool"
    assert deserialized.risk_class == RiskClass.MEDIUM
    assert deserialized.side_effect_class == SideEffectClass.IDEMPOTENT_MUTATION
    assert deserialized.timeout_seconds == 45.0


def test_idempotency_record_model() -> None:
    rec = IdempotencyRecord.create_new(
        idempotency_key="idem_abc",
        task_id="task_1",
        plan_id="plan_1",
        plan_revision=1,
        node_id="node_1",
        attempt_id=1,
        command_id="cmd_1",
        arguments_hash="hash_1",
        capability_target="filesystem.read",
        state=IdempotencyState.IN_PROGRESS,
    )
    assert rec.state == IdempotencyState.IN_PROGRESS
    d = rec.to_dict()
    assert d["state"] == "IN_PROGRESS"

    restored = IdempotencyRecord.from_dict(d)
    assert restored.idempotency_key == "idem_abc"
    assert restored.state == IdempotencyState.IN_PROGRESS


def test_error_taxonomy_and_action_mappings() -> None:
    # All failure classes must have explicit recovery action mappings
    for fc in ExecutionFailureClass:
        action = FAILURE_TO_ACTION_MAP.get(fc)
        assert action is not None, f"Missing action mapping for {fc}"
        assert isinstance(action, ActionRecommendation)

    err = ExecutionErrorDetail.create(
        failure_class=ExecutionFailureClass.SANDBOX_DENIED,
        message="Sandbox tier TIER_1_RESTRICTED_TOKEN unavailable",
    )
    assert err.failure_class == ExecutionFailureClass.SANDBOX_DENIED
    assert err.recommended_action == ActionRecommendation.FAIL
    assert "Sandbox" in err.message
