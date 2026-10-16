"""jarvis.application_automation.recovery_engine — Safe retry and self-healing recovery engine.

OpenClaw parity:
- src/agents/tools/computer-tool-guidance.ts: Never blind-retry a mutation.
  Honest structured refusals over repeated retries.
- extensions/browser/src/browser-tool.actions.ts: Target refresh & batch abort on navigation.

Guarantees:
1. Blind repeated retries are strictly prohibited (maximum 1 re-observation retry per action).
2. Side-effect actions (subscribe, like, send message, purchase) are protected against duplicate execution.
3. Errors are classified into structured recovery paths: Detect -> Classify -> Observe -> Reconcile -> Recover -> Verify.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from .action_contracts import ActionContract
from .observation_manager import PageObservation


class RetryClass(str, Enum):
    """Classification of retry safety and strategy."""

    SAFE_REOBSERVE = "safe_reobserve"
    SAFE_REFETCH_SNAPSHOT = "safe_refetch_snapshot"
    SAFE_TARGET_RECOVERY = "safe_target_recovery"
    SAFE_PAGE_WAIT = "safe_page_wait"
    SAFE_NAVIGATION_RECOVERY = "safe_navigation_recovery"
    UNSAFE_DUPLICATE_ACTION = "unsafe_duplicate_action"


class FailureClassification(str, Enum):
    """Root cause classifications for browser automation errors."""

    STALE_TARGET = "stale_target"
    STALE_OBSERVATION = "stale_observation"
    SELECTOR_NOT_FOUND = "selector_not_found"
    TIMEOUT = "timeout"
    AUTH_REDIRECT = "auth_redirect"
    MODAL_BLOCKING = "modal_blocking"
    BROWSER_DISCONNECTED = "browser_disconnected"
    SIDE_EFFECT_RISK = "side_effect_risk"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class RecoveryPlan:
    """Actionable plan for recovering from an automation failure."""

    failure_type: FailureClassification
    retry_class: RetryClass
    is_safe_to_retry: bool
    recommended_action: str
    recovery_steps: List[str] = field(default_factory=list)
    reason: str = ""


class RecoveryEngine:
    """Enforces retry budgets, side-effect idempotency guards, and self-healing recovery."""

    _instance: Optional[RecoveryEngine] = None

    SIDE_EFFECT_ACTIONS = frozenset(
        {
            "subscribe",
            "unsubscribe",
            "send_message",
            "like",
            "unlike",
            "follow",
            "unfollow",
            "purchase",
            "delete",
            "submit",
            "publish",
        }
    )

    MAX_RETRY_BUDGET = 1  # Exactly 1 safe re-observation retry allowed

    def __init__(self) -> None:
        self._action_retry_counts: Dict[str, int] = {}  # action_key -> count

    @classmethod
    def get_instance(cls) -> RecoveryEngine:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _get_action_key(self, contract: ActionContract) -> str:
        name = contract.target.name or ""
        role = contract.target.role or ""
        return f"{contract.task_id}:{contract.action_type}:{role}:{name}"

    def can_retry(self, contract: ActionContract) -> bool:
        """Check if action has remaining retry budget."""
        key = self._get_action_key(contract)
        count = self._action_retry_counts.get(key, 0)
        return count < self.MAX_RETRY_BUDGET

    def record_retry(self, contract: ActionContract) -> int:
        """Increment and return retry count."""
        key = self._get_action_key(contract)
        count = self._action_retry_counts.get(key, 0) + 1
        self._action_retry_counts[key] = count
        return count

    def reset_budget(self, task_id: Optional[str] = None) -> None:
        """Reset retry counters."""
        if task_id:
            self._action_retry_counts = {k: v for k, v in self._action_retry_counts.items() if not k.startswith(task_id)}
        else:
            self._action_retry_counts.clear()

    def analyze_failure(
        self,
        contract: ActionContract,
        error_msg: str,
        current_obs: Optional[PageObservation] = None,
        is_already_completed: bool = False,
    ) -> RecoveryPlan:
        """Analyze an observed error and generate a bounded, safe recovery plan."""
        err_lower = error_msg.lower()

        # 1. Action already complete check
        if is_already_completed or "already_completed" in err_lower:
            return RecoveryPlan(
                failure_type=FailureClassification.SIDE_EFFECT_RISK,
                retry_class=RetryClass.UNSAFE_DUPLICATE_ACTION,
                is_safe_to_retry=False,
                recommended_action="stop_already_completed",
                recovery_steps=["Report action was already completed; do not retry."],
                reason="Target state already exists; further actions would cause unwanted duplicate side-effects.",
            )

        # 2. Check retry budget
        if not self.can_retry(contract):
            return RecoveryPlan(
                failure_type=FailureClassification.UNKNOWN,
                retry_class=RetryClass.UNSAFE_DUPLICATE_ACTION,
                is_safe_to_retry=False,
                recommended_action="abort_and_report_honest_failure",
                recovery_steps=["Exhausted retry budget (max 1 retry allowed)."],
                reason="Repeated attempts failed. Refusing blind retries.",
            )

        # 3. Target stale or tab closed
        if "targetstale" in err_lower or "target not found" in err_lower or "tab not found" in err_lower:
            return RecoveryPlan(
                failure_type=FailureClassification.STALE_TARGET,
                retry_class=RetryClass.SAFE_TARGET_RECOVERY,
                is_safe_to_retry=True,
                recommended_action="rediscover_tabs_and_rebind",
                recovery_steps=[
                    "List current browser tabs",
                    "Match candidate tab by domain and URL",
                    "Re-bind target ID",
                    "Take fresh observation",
                ],
                reason="Target tab was closed, refreshed, or replaced.",
            )

        # 4. Observation stale
        if "staleobservation" in err_lower or "observation has been invalidated" in err_lower:
            return RecoveryPlan(
                failure_type=FailureClassification.STALE_OBSERVATION,
                retry_class=RetryClass.SAFE_REFETCH_SNAPSHOT,
                is_safe_to_retry=True,
                recommended_action="take_fresh_snapshot",
                recovery_steps=[
                    "Capture fresh accessibility snapshot",
                    "Generate new observation_id",
                    "Re-resolve element reference",
                ],
                reason="Page mutated or navigated since previous observation.",
            )

        # 5. Authentication redirect detected
        if (
            "accounts.google.com" in (current_obs.url if current_obs else "")
            or "signin" in err_lower
            or "login" in (current_obs.url if current_obs else "")
        ):
            return RecoveryPlan(
                failure_type=FailureClassification.AUTH_REDIRECT,
                retry_class=RetryClass.UNSAFE_DUPLICATE_ACTION,
                is_safe_to_retry=False,
                recommended_action="pause_for_human_auth",
                recovery_steps=[
                    "Detect Google Login / Auth boundary",
                    "Pause automation safely without guessing credentials",
                    "Request human sign-in confirmation",
                ],
                reason="Page redirected to an authentication boundary.",
            )

        # 6. Selector / Element not found or Timeout
        if "timeout" in err_lower or "not found" in err_lower or "locator.click" in err_lower:
            # Check if this is a side-effect action
            is_side_effect = contract.action_type in self.SIDE_EFFECT_ACTIONS or any(
                se in (contract.target.name or "").lower() for se in self.SIDE_EFFECT_ACTIONS
            )

            if is_side_effect:
                # Must re-observe first before even considering a retry!
                return RecoveryPlan(
                    failure_type=FailureClassification.SIDE_EFFECT_RISK,
                    retry_class=RetryClass.SAFE_REOBSERVE,
                    is_safe_to_retry=True,
                    recommended_action="reobserve_state_before_retry",
                    recovery_steps=[
                        "Take fresh snapshot to verify if action actually succeeded despite timeout",
                        "If target state reached -> report success",
                        "If not reached and within budget -> attempt re-resolved click once",
                    ],
                    reason="Side-effect action timed out; must inspect DOM before re-attempting.",
                )
            else:
                return RecoveryPlan(
                    failure_type=FailureClassification.SELECTOR_NOT_FOUND,
                    retry_class=RetryClass.SAFE_REFETCH_SNAPSHOT,
                    is_safe_to_retry=True,
                    recommended_action="reobserve_and_resolve_semantic_ref",
                    recovery_steps=[
                        "Take fresh ARIA snapshot",
                        "Locate semantic element via role and accessible name",
                        "Retry once with fresh ref",
                    ],
                    reason="Element was not interactable or selector timed out.",
                )

        # Default fallback
        return RecoveryPlan(
            failure_type=FailureClassification.UNKNOWN,
            retry_class=RetryClass.UNSAFE_DUPLICATE_ACTION,
            is_safe_to_retry=False,
            recommended_action="abort_safely",
            recovery_steps=["Report failure with captured diagnostics."],
            reason=f"Unclassified failure: {error_msg[:100]}",
        )
