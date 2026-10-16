from __future__ import annotations
import enum
import json
from dataclasses import dataclass
from typing import Any, Literal
from .evidence_model import ExperienceEvidence
from .recovery import RecoveryPlan


class CausalFailureType(str, enum.Enum):
    TOOL_EXECUTION_FAILURE = "tool_execution_failure"
    INVALID_ARGUMENTS = "invalid_arguments"
    POLICY_DENIED = "policy_denied"
    PERMISSION_DENIED = "permission_denied"
    RESOURCE_MISSING = "resource_missing"
    FALSE_COMPLETION = "false_completion"
    REDUNDANT_ACTION = "redundant_action"
    VERIFIER_ERROR = "verifier_error"
    TIMEOUT = "timeout"
    USER_ABORTED = "user_aborted"
    UNKNOWN = "unknown"

    # Canonical Phase 5 aliases
    PERMISSION_OR_AUTH_FAILURE = "permission_denied"
    TIMEOUT_OR_HANG = "timeout"
    DEVICE_DISCONNECTED = "resource_missing"
    RESOURCE_EXHAUSTED = "resource_missing"
    TARGET_NOT_FOUND = "resource_missing"


class AttributionStatus(str, enum.Enum):
    CONFIRMED = "CONFIRMED"
    PROBABLE = "PROBABLE"
    POSSIBLE = "POSSIBLE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    CONTRADICTED = "CONTRADICTED"


@dataclass(frozen=True, slots=True)
class CausalCritique:
    experience_id: str
    primary_cause: CausalFailureType
    alternative_causes: tuple[CausalFailureType, ...] = ()
    causal_confidence: float = 0.5
    attribution_status: AttributionStatus = AttributionStatus.INSUFFICIENT_EVIDENCE
    evidence_refs: tuple[str, ...] = ()
    missing_evidence: tuple[str, ...] = ()
    blame_assignment: Literal[
        "model_prediction", "tool_implementation", "environment_state", "user_input", "policy"
    ] = "tool_implementation"
    root_cause_explanation: str = ""
    is_retryable: bool = False
    suggested_recovery: RecoveryPlan | None = None
    scoped_pattern_needed: bool = False

    @property
    def primary_failure_type(self) -> CausalFailureType:
        return self.primary_cause

    @property
    def recovery_plan(self) -> RecoveryPlan | None:
        return self.suggested_recovery

    @property
    def recommended_recovery_action(self) -> str:
        return self.suggested_recovery.retry_policy if self.suggested_recovery else ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "experience_id": self.experience_id,
            "primary_cause": self.primary_cause.value,
            "alternative_causes": json.dumps([c.value for c in self.alternative_causes]),
            "causal_confidence": self.causal_confidence,
            "attribution_status": self.attribution_status.value,
            "evidence_refs": json.dumps(list(self.evidence_refs)),
            "missing_evidence": json.dumps(list(self.missing_evidence)),
            "blame_assignment": self.blame_assignment,
            "root_cause_explanation": self.root_cause_explanation,
            "is_retryable": 1 if self.is_retryable else 0,
            "suggested_recovery": json.dumps(self.suggested_recovery.to_dict())
            if self.suggested_recovery
            else "{}",
            "scoped_pattern_needed": 1 if self.scoped_pattern_needed else 0,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CausalCritique:
        alt_causes = data.get("alternative_causes", "[]")
        if isinstance(alt_causes, str):
            try:
                alt_causes = [CausalFailureType(c) for c in json.loads(alt_causes)]
            except Exception:
                alt_causes = []
        ev_refs = data.get("evidence_refs", "[]")
        if isinstance(ev_refs, str):
            try:
                ev_refs = json.loads(ev_refs)
            except Exception:
                ev_refs = []
        miss_ev = data.get("missing_evidence", "[]")
        if isinstance(miss_ev, str):
            try:
                miss_ev = json.loads(miss_ev)
            except Exception:
                miss_ev = []
        rec_data = data.get("suggested_recovery", "{}")
        recovery = None
        if isinstance(rec_data, str) and rec_data != "{}":
            try:
                recovery = RecoveryPlan.from_dict(json.loads(rec_data))
            except Exception:
                recovery = None
        return cls(
            experience_id=str(data["experience_id"]),
            primary_cause=CausalFailureType(str(data["primary_cause"])),
            alternative_causes=tuple(alt_causes),
            causal_confidence=float(data.get("causal_confidence", 0.5)),
            attribution_status=AttributionStatus(
                str(data.get("attribution_status", AttributionStatus.INSUFFICIENT_EVIDENCE.value))
            ),
            evidence_refs=tuple(ev_refs),
            missing_evidence=tuple(miss_ev),
            blame_assignment=data.get("blame_assignment", "tool_implementation"),
            root_cause_explanation=str(data.get("root_cause_explanation", "")),
            is_retryable=bool(data.get("is_retryable", False)),
            suggested_recovery=recovery,
            scoped_pattern_needed=bool(data.get("scoped_pattern_needed", False)),
        )


class CausalCritic:
    def analyze_experience(
        self,
        experience_id: str = "",
        tool_name: str = "",
        tool_args: dict[str, Any] | None = None,
        tool_result: Any = None,
        evidence_records: list[ExperienceEvidence] | None = None,
        user_feedback: str = "",
        policy_blocked: bool = False,
        policy_reason: str = "",
        error_message: str = "",
        verification_status: str = "",
    ) -> CausalCritique:
        evidence_records = evidence_records or []
        tool_args = tool_args or {}
        ev_ids = [e.evidence_id for e in evidence_records]
        trusted_evidence = [e for e in evidence_records if e.is_trusted()]

        err_lower = (error_message or "").lower()
        if "permission" in err_lower or "access denied" in err_lower:
            rec = RecoveryPlan(
                trigger_failure_type=CausalFailureType.PERMISSION_OR_AUTH_FAILURE,
                max_attempts=1,
                retry_policy="check credentials or elevated permissions",
            )
            return CausalCritique(
                experience_id=experience_id,
                primary_cause=CausalFailureType.PERMISSION_OR_AUTH_FAILURE,
                alternative_causes=(),
                causal_confidence=0.95,
                attribution_status=AttributionStatus.CONFIRMED,
                evidence_refs=tuple(ev_ids),
                blame_assignment="environment_state",
                root_cause_explanation=error_message,
                is_retryable=False,
                suggested_recovery=rec,
                scoped_pattern_needed=True,
            )
        elif "timeout" in err_lower or "timed out" in err_lower:
            rec = RecoveryPlan(
                trigger_failure_type=CausalFailureType.TIMEOUT_OR_HANG,
                max_attempts=2,
                retry_policy="retry with increased timeout and probe",
            )
            return CausalCritique(
                experience_id=experience_id,
                primary_cause=CausalFailureType.TIMEOUT_OR_HANG,
                alternative_causes=(),
                causal_confidence=0.90,
                attribution_status=AttributionStatus.PROBABLE,
                evidence_refs=tuple(ev_ids),
                blame_assignment="environment_state",
                root_cause_explanation=error_message,
                is_retryable=True,
                suggested_recovery=rec,
                scoped_pattern_needed=True,
            )

        # 1. Policy blocked check
        if policy_blocked:
            rec = RecoveryPlan(
                trigger_failure_type=CausalFailureType.POLICY_DENIED,
                max_attempts=0,
                retry_policy="stop",
                requires_confirmation=True,
                stop_conditions=("Action blocked by explicit security policy",),
            )
            return CausalCritique(
                experience_id=experience_id,
                primary_cause=CausalFailureType.POLICY_DENIED,
                alternative_causes=(),
                causal_confidence=1.0,
                attribution_status=AttributionStatus.CONFIRMED,
                evidence_refs=tuple(ev_ids),
                blame_assignment="policy",
                root_cause_explanation=policy_reason or "Action was blocked by safety policy",
                is_retryable=False,
                suggested_recovery=rec,
                scoped_pattern_needed=False,
            )

        # 2. Check for False Completion Claims
        for ev in evidence_records:
            if ev.verification_status in ("false_claim", "VERIFIER_CONTRADICTION"):
                rec = RecoveryPlan(
                    trigger_failure_type=CausalFailureType.FALSE_COMPLETION,
                    max_attempts=1,
                    retry_policy="probe_first",
                    requires_confirmation=False,
                    stop_conditions=("Physical verification contradicts claim",),
                )
                return CausalCritique(
                    experience_id=experience_id,
                    primary_cause=CausalFailureType.FALSE_COMPLETION,
                    alternative_causes=(CausalFailureType.TOOL_EXECUTION_FAILURE,),
                    causal_confidence=0.95,
                    attribution_status=AttributionStatus.CONFIRMED,
                    evidence_refs=tuple(ev_ids),
                    blame_assignment="model_prediction",
                    root_cause_explanation="Model claimed action succeeded but physical verifier proved state was unchanged",
                    is_retryable=False,
                    suggested_recovery=rec,
                    scoped_pattern_needed=True,
                )

        # 3. Analyze Error Text
        err_str = ""
        if isinstance(tool_result, dict):
            err_str = str(tool_result.get("error") or tool_result.get("message") or "")
        elif isinstance(tool_result, str):
            err_str = tool_result
        err_lower = err_str.lower()

        # Access denied ambiguity check
        if (
            "access denied" in err_lower
            or "permission denied" in err_lower
            or "unauthorized" in err_lower
        ):
            has_lock_probe = any(
                e.metadata.get("file_locked") is not None for e in trusted_evidence
            )
            has_acl_probe = any(
                e.metadata.get("permission_denied") is not None for e in trusted_evidence
            )

            if has_lock_probe and any(e.metadata.get("file_locked") for e in trusted_evidence):
                status = AttributionStatus.CONFIRMED
                conf = 0.90
                primary = CausalFailureType.PERMISSION_DENIED
                alts = (CausalFailureType.RESOURCE_MISSING,)
                explanation = "File handle is actively locked by another process"
                is_retry = True
            elif has_acl_probe:
                status = AttributionStatus.CONFIRMED
                conf = 0.95
                primary = CausalFailureType.PERMISSION_DENIED
                alts = ()
                explanation = "OS Access Control / ACL denied write operation"
                is_retry = False
            else:
                # Ambiguous without corroborating probe
                status = AttributionStatus.PROBABLE
                conf = 0.70
                primary = CausalFailureType.PERMISSION_DENIED
                alts = (CausalFailureType.RESOURCE_MISSING, CausalFailureType.INVALID_ARGUMENTS)
                explanation = "Access denied error string observed, but file-lock vs OS ACL was not independently confirmed by a probe"
                is_retry = False

            rec = RecoveryPlan(
                trigger_failure_type=primary,
                max_attempts=1,
                retry_policy="probe_first",
                requires_confirmation=True,
                stop_conditions=("Unresolvable permission barrier",),
            )
            return CausalCritique(
                experience_id=experience_id,
                primary_cause=primary,
                alternative_causes=alts,
                causal_confidence=conf,
                attribution_status=status,
                evidence_refs=tuple(ev_ids),
                missing_evidence=()
                if (has_lock_probe or has_acl_probe)
                else ("lock_inspection_probe", "acl_inspection_probe"),
                blame_assignment="environment_state",
                root_cause_explanation=explanation,
                is_retryable=is_retry,
                suggested_recovery=rec,
                scoped_pattern_needed=True,
            )

        # File not found / Resource missing check
        if (
            "not found" in err_lower
            or "no such file" in err_lower
            or "does not exist" in err_lower
            or "target closed" in err_lower
        ):
            rec = RecoveryPlan(
                trigger_failure_type=CausalFailureType.RESOURCE_MISSING,
                max_attempts=1,
                retry_policy="switch_target",
                requires_confirmation=False,
                stop_conditions=("Target resource not found",),
            )
            return CausalCritique(
                experience_id=experience_id,
                primary_cause=CausalFailureType.RESOURCE_MISSING,
                alternative_causes=(CausalFailureType.INVALID_ARGUMENTS,),
                causal_confidence=0.85,
                attribution_status=AttributionStatus.PROBABLE,
                evidence_refs=tuple(ev_ids),
                blame_assignment="environment_state",
                root_cause_explanation=f"Target resource missing or unreachable: {err_str[:200]}",
                is_retryable=False,
                suggested_recovery=rec,
                scoped_pattern_needed=True,
            )

        # Invalid arguments / schema violation check
        if (
            "validation error" in err_lower
            or "missing required" in err_lower
            or "type error" in err_lower
            or "invalid argument" in err_lower
        ):
            rec = RecoveryPlan(
                trigger_failure_type=CausalFailureType.INVALID_ARGUMENTS,
                max_attempts=1,
                retry_policy="narrow_query",
                requires_confirmation=False,
                stop_conditions=("Schema mismatch",),
            )
            return CausalCritique(
                experience_id=experience_id,
                primary_cause=CausalFailureType.INVALID_ARGUMENTS,
                alternative_causes=(CausalFailureType.TOOL_EXECUTION_FAILURE,),
                causal_confidence=0.90,
                attribution_status=AttributionStatus.CONFIRMED,
                evidence_refs=tuple(ev_ids),
                blame_assignment="model_prediction",
                root_cause_explanation=f"Argument schema validation failed: {err_str[:200]}",
                is_retryable=False,
                suggested_recovery=rec,
                scoped_pattern_needed=True,
            )

        # General tool execution crash or nonzero exit
        if err_str:
            rec = RecoveryPlan(
                trigger_failure_type=CausalFailureType.TOOL_EXECUTION_FAILURE,
                max_attempts=1,
                retry_policy="backoff",
                requires_confirmation=False,
                stop_conditions=("Tool process crashed",),
            )
            return CausalCritique(
                experience_id=experience_id,
                primary_cause=CausalFailureType.TOOL_EXECUTION_FAILURE,
                alternative_causes=(CausalFailureType.UNKNOWN,),
                causal_confidence=0.75,
                attribution_status=AttributionStatus.PROBABLE,
                evidence_refs=tuple(ev_ids),
                blame_assignment="tool_implementation",
                root_cause_explanation=f"Tool reported runtime execution error: {err_str[:200]}",
                is_retryable=False,
                suggested_recovery=rec,
                scoped_pattern_needed=True,
            )

        # If no error string, return unknown
        return CausalCritique(
            experience_id=experience_id,
            primary_cause=CausalFailureType.UNKNOWN,
            alternative_causes=(),
            causal_confidence=0.3,
            attribution_status=AttributionStatus.INSUFFICIENT_EVIDENCE,
            evidence_refs=tuple(ev_ids),
            blame_assignment="tool_implementation",
            root_cause_explanation="No conclusive error message or probe evidence found",
            is_retryable=False,
            suggested_recovery=None,
            scoped_pattern_needed=False,
        )
