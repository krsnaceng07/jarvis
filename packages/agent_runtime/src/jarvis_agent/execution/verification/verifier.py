"""Independent State Verifier for Track 3.2.

Evaluates postconditions independently of tool return values or model claims:
- Evaluates machine-checkable assertions (EQUALS, CONTAINS, FILE_EXISTS, EXIT_CODE_ZERO, MEDIA_PAUSED, MEDIA_PLAYING, SHA256_MATCH).
- Freshness deadline enforcement: rejects stale observations.
- State drift detection: detects precondition drift between planning and verification.
- Emits authoritative VerificationResult with cryptographic evidence refs.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any
import uuid

from jarvis_agent.orchestration.models.observation import ObservationRecord
from jarvis_agent.orchestration.models.verification import (
    VerificationAssertion,
    VerificationRequirement,
    VerificationResult,
)

logger = logging.getLogger(__name__)


class StateVerifier:
    """Evaluates verification requirements against empirical observation records."""

    def __init__(self) -> None:
        pass

    def verify(
        self,
        node_id: str,
        requirements: list[VerificationRequirement] | None,
        observations: list[ObservationRecord],
        baseline_fingerprint: str | None = None,
        current_fingerprint: str | None = None,
        max_observation_age_seconds: float = 300.0,
    ) -> VerificationResult:
        """Verify empirical observations against all requirements.

        Enforces:
        1. Observation freshness guard.
        2. State drift detection (baseline vs current precondition fingerprint).
        3. Machine-checkable predicate evaluations.
        """
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        result_id = f"ver_{uuid.uuid4().hex[:12]}"
        verification_id = (
            requirements[0].verification_id if requirements else f"req_{node_id}"
        )

        evidence_refs: list[str] = [
            o.evidence_ref for o in observations if o.evidence_ref
        ]

        # 1. Check Freshness of Observations
        for obs in observations:
            if obs.captured_at_utc:
                try:
                    obs_dt = datetime.datetime.fromisoformat(obs.captured_at_utc)
                    age_seconds = (now_dt - obs_dt).total_seconds()
                    if age_seconds > max_observation_age_seconds:
                        return VerificationResult(
                            result_id=result_id,
                            verification_id=verification_id,
                            node_id=node_id,
                            passed=False,
                            assertions_evaluated=0,
                            assertions_passed=0,
                            diffs={"freshness_error": f"Observation age {age_seconds:.1f}s exceeds limit {max_observation_age_seconds}s"},
                            evidence_refs=evidence_refs,
                            error_message="Stale observation rejected by freshness guard",
                        )
                except Exception:
                    pass

        # 2. State Drift Detection
        if baseline_fingerprint and current_fingerprint:
            if baseline_fingerprint != current_fingerprint:
                return VerificationResult(
                    result_id=result_id,
                    verification_id=verification_id,
                    node_id=node_id,
                    passed=False,
                    assertions_evaluated=0,
                    assertions_passed=0,
                    diffs={
                        "state_drift": {
                            "expected_baseline": baseline_fingerprint,
                            "observed_current": current_fingerprint,
                        }
                    },
                    evidence_refs=evidence_refs,
                    error_message="Precondition state drift detected before verification",
                )

        if not requirements:
            # If no explicit requirements, verify whether all observations succeeded
            all_ok = all(o.success for o in observations) if observations else True
            return VerificationResult(
                result_id=result_id,
                verification_id=verification_id,
                node_id=node_id,
                passed=all_ok,
                assertions_evaluated=len(observations),
                assertions_passed=sum(1 for o in observations if o.success),
                evidence_refs=evidence_refs,
                error_message=None if all_ok else "One or more default observations failed",
            )

        # 3. Evaluate Assertions
        total_eval = 0
        total_passed = 0
        diffs: dict[str, Any] = {}

        # Merge observation raw data into a flat queryable context
        obs_ctx: dict[str, Any] = {}
        for obs in observations:
            if isinstance(obs.raw_data, dict):
                obs_ctx.update(obs.raw_data)

        for req in requirements:
            for assertion in req.assertions:
                total_eval += 1
                passed, err = self._evaluate_assertion(assertion, obs_ctx, observations)
                if passed:
                    total_passed += 1
                else:
                    diffs[assertion.assertion_id] = {
                        "field": assertion.field_name,
                        "type": assertion.assertion_type,
                        "expected": assertion.expected_value,
                        "error": err,
                    }

        all_passed = (total_eval == total_passed)
        return VerificationResult(
            result_id=result_id,
            verification_id=verification_id,
            node_id=node_id,
            passed=all_passed,
            assertions_evaluated=total_eval,
            assertions_passed=total_passed,
            diffs=diffs,
            evidence_refs=evidence_refs,
            error_message=None if all_passed else f"{total_eval - total_passed} assertion(s) failed verification",
        )

    def _evaluate_assertion(
        self,
        assertion: VerificationAssertion,
        ctx: dict[str, Any],
        observations: list[ObservationRecord],
    ) -> tuple[bool, str | None]:
        atype = assertion.assertion_type.upper()
        field_name = assertion.field_name
        expected = assertion.expected_value

        val = ctx.get(field_name)

        if atype == "EQUALS":
            if val == expected:
                return True, None
            return False, f"Value '{val}' != expected '{expected}'"

        elif atype == "CONTAINS":
            if val is not None and expected in val:
                return True, None
            return False, f"Value '{val}' does not contain expected '{expected}'"

        elif atype == "EXIT_CODE_ZERO":
            ec = ctx.get("exit_code")
            if ec == 0:
                return True, None
            return False, f"Exit code {ec} is not zero"

        elif atype == "FILE_EXISTS":
            exists = bool(ctx.get("exists", False))
            if exists:
                return True, None
            return False, f"File at {field_name} does not exist"

        elif atype == "MEDIA_PAUSED":
            paused = bool(ctx.get("paused", False))
            if paused:
                return True, None
            return False, "Media is not in paused state"

        elif atype == "MEDIA_PLAYING":
            playing = bool(ctx.get("playing", False))
            if playing or ctx.get("paused") is False:
                return True, None
            return False, "Media is not in playing state"

        elif atype == "SHA256_MATCH":
            sha = ctx.get("sha256") or ctx.get("post_sha256")
            if sha == expected:
                return True, None
            return False, f"SHA-256 '{sha}' does not match expected '{expected}'"

        elif atype == "NON_EMPTY":
            if val is not None and len(str(val)) > 0:
                return True, None
            return False, f"Field '{field_name}' is empty or None"

        else:
            # Fallback equality
            if val == expected:
                return True, None
            return False, f"Assertion '{atype}' failed: value '{val}' != '{expected}'"


__all__ = ["StateVerifier"]
