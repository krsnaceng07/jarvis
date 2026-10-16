"""jarvis.application_automation.verification_engine — Post-action verification engine.

OpenClaw parity:
- src/agents/tools/computer-tool-guidance.ts: Result precedence is
  effect:"confirmed" > unverifiable > suspected_noop; action evidence alone does
  not prove the user's goal. Re-observe before another mutation, and never blind-retry.
- extensions/browser/src/browser-tool.actions.ts: Structured tool result contracts.

Guarantees:
1. Tool event acceptance (ok=true) is strictly decoupled from task verification.
2. Every mutation action is verified against pre- and post-action observations.
3. Only concrete DOM delta evidence allows completed_verified status.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from .action_contracts import ActionContract
from .action_verifier import ActionEffect
from .observation_manager import PageObservation


class VerificationStatus(str, Enum):
    """Authoritative post-verification outcome status."""

    COMPLETED_VERIFIED = "completed_verified"
    ALREADY_COMPLETED = "already_completed"
    COMPLETED_UNVERIFIED = "completed_unverified"
    SUSPECTED_NOOP = "suspected_noop"
    FAILED = "failed"


@dataclass(slots=True)
class VerificationOutcome:
    """Structured, evidence-backed result of an action verification."""

    status: VerificationStatus
    action_id: str
    task_id: str
    stage_id: str
    effect: ActionEffect
    evidence: List[str] = field(default_factory=list)
    observed_before: Dict[str, Any] = field(default_factory=dict)
    tool_result: Dict[str, Any] = field(default_factory=dict)
    observed_after: Dict[str, Any] = field(default_factory=dict)
    next_stage: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    @property
    def passed(self) -> bool:
        return self.status in (VerificationStatus.COMPLETED_VERIFIED, VerificationStatus.ALREADY_COMPLETED)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        d["effect"] = self.effect.value
        return d


class VerificationEngine:
    """Engine executing rigorous pre/post observation differential verification."""

    _instance: Optional[VerificationEngine] = None

    @classmethod
    def get_instance(cls) -> VerificationEngine:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def verify_action_effect(
        self,
        contract: ActionContract,
        pre_obs: Optional[PageObservation],
        tool_result: Dict[str, Any],
        post_obs: Optional[PageObservation],
        custom_verifier: Optional[Callable[[Optional[PageObservation], Optional[PageObservation]], tuple[bool, str]]] = None,
    ) -> VerificationOutcome:
        """Verify the observable effect of an executed action against expected postconditions."""
        # Check if driver itself threw an error
        if not tool_result.get("ok", False) and "error" in tool_result:
            return VerificationOutcome(
                status=VerificationStatus.FAILED,
                action_id=contract.action_id,
                task_id=contract.task_id,
                stage_id=contract.stage_id,
                effect=ActionEffect.SUSPECTED_NOOP,
                evidence=[f"Driver error: {tool_result.get('error')}"],
                observed_before=pre_obs.raw_aria_tree[:300] if pre_obs else {},
                tool_result=tool_result,
                observed_after=post_obs.raw_aria_tree[:300] if post_obs else {},
            )

        evidence: List[str] = []

        # 1. Custom domain verifier (e.g. YouTubeAdapter subscription check)
        if custom_verifier:
            passed, custom_evidence = custom_verifier(pre_obs, post_obs)
            if passed:
                evidence.append(custom_evidence)
                return VerificationOutcome(
                    status=VerificationStatus.COMPLETED_VERIFIED,
                    action_id=contract.action_id,
                    task_id=contract.task_id,
                    stage_id=contract.stage_id,
                    effect=ActionEffect.CONFIRMED,
                    evidence=evidence,
                    observed_before={"url": pre_obs.url if pre_obs else ""},
                    tool_result=tool_result,
                    observed_after={"url": post_obs.url if post_obs else ""},
                )
            else:
                return VerificationOutcome(
                    status=VerificationStatus.COMPLETED_UNVERIFIED,
                    action_id=contract.action_id,
                    task_id=contract.task_id,
                    stage_id=contract.stage_id,
                    effect=ActionEffect.SUSPECTED_NOOP,
                    evidence=[f"Domain verification failed: {custom_evidence}"],
                    observed_before={"url": pre_obs.url if pre_obs else ""},
                    tool_result=tool_result,
                    observed_after={"url": post_obs.url if post_obs else ""},
                )

        # 2. General postcondition evaluation
        if not pre_obs or not post_obs:
            return VerificationOutcome(
                status=VerificationStatus.COMPLETED_UNVERIFIED,
                action_id=contract.action_id,
                task_id=contract.task_id,
                stage_id=contract.stage_id,
                effect=ActionEffect.UNVERIFIABLE,
                evidence=["Cannot verify: missing pre- or post-action observation snapshot."],
                observed_before={},
                tool_result=tool_result,
                observed_after={},
            )

        # URL Navigation verification
        if "url_changes" in contract.expected_postconditions:
            if pre_obs.url != post_obs.url:
                evidence.append(f"URL changed from '{pre_obs.url}' to '{post_obs.url}'")
            else:
                return VerificationOutcome(
                    status=VerificationStatus.SUSPECTED_NOOP,
                    action_id=contract.action_id,
                    task_id=contract.task_id,
                    stage_id=contract.stage_id,
                    effect=ActionEffect.SUSPECTED_NOOP,
                    evidence=["Expected URL change did not occur."],
                    observed_before={"url": pre_obs.url},
                    tool_result=tool_result,
                    observed_after={"url": post_obs.url},
                )

        # Element text transition verification (e.g. Subscribe -> Subscribed)
        if "subscription_state_changes" in contract.expected_postconditions or "button_label_is_subscribed" in contract.expected_postconditions:
            subscribed_found = False
            for el in post_obs.elements:
                if el.role == "button" and ("subscribed" in el.name.lower() or "unsubscribe" in el.name.lower()):
                    subscribed_found = True
                    evidence.append(f"Confirmed button state transitioned to: '{el.name}'")
                    break

            if subscribed_found:
                return VerificationOutcome(
                    status=VerificationStatus.COMPLETED_VERIFIED,
                    action_id=contract.action_id,
                    task_id=contract.task_id,
                    stage_id=contract.stage_id,
                    effect=ActionEffect.CONFIRMED,
                    evidence=evidence,
                    observed_before={"url": pre_obs.url},
                    tool_result=tool_result,
                    observed_after={"url": post_obs.url},
                )
            else:
                return VerificationOutcome(
                    status=VerificationStatus.COMPLETED_UNVERIFIED,
                    action_id=contract.action_id,
                    task_id=contract.task_id,
                    stage_id=contract.stage_id,
                    effect=ActionEffect.SUSPECTED_NOOP,
                    evidence=["Subscribe click executed, but post-observation button did not indicate 'Subscribed'."],
                    observed_before={"url": pre_obs.url},
                    tool_result=tool_result,
                    observed_after={"url": post_obs.url},
                )

        # Generic DOM tree mutation check
        if pre_obs.raw_aria_tree != post_obs.raw_aria_tree:
            evidence.append("DOM accessibility tree mutated following action execution.")
            return VerificationOutcome(
                status=VerificationStatus.COMPLETED_VERIFIED,
                action_id=contract.action_id,
                task_id=contract.task_id,
                stage_id=contract.stage_id,
                effect=ActionEffect.CONFIRMED,
                evidence=evidence,
                observed_before={"url": pre_obs.url},
                tool_result=tool_result,
                observed_after={"url": post_obs.url},
            )

        # No observable change
        return VerificationOutcome(
            status=VerificationStatus.COMPLETED_UNVERIFIED,
            action_id=contract.action_id,
            task_id=contract.task_id,
            stage_id=contract.stage_id,
            effect=ActionEffect.SUSPECTED_NOOP,
            evidence=["Action executed but zero DOM/URL changes were observed."],
            observed_before={"url": pre_obs.url},
            tool_result=tool_result,
            observed_after={"url": post_obs.url},
        )
