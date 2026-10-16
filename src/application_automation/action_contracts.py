"""jarvis.application_automation.action_contracts — Strict action contracts and precondition enforcement.

OpenClaw parity:
- src/agents/tools/computer-tool-guidance.ts (action preconditions & target contract)
- packages/agent-core/src/agent-loop.ts (beforeToolCall admission & turn cancellation)

Guarantees:
1. Every browser action must be structured as an ActionContract.
2. Actions are strictly validated against preconditions before execution.
3. Stale targets, stale observations, out-of-turn calls, cancelled tasks, and already-completed actions are rejected immediately.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from ..agents.task.runtime_state import RuntimeStateManager
from .browser_target_manager import BrowserTargetManager, ValidatedTargetContext
from .observation_manager import ObservationManager, PageObservation, SemanticElement


class ActionRejectionCode(str, Enum):
    """Reason codes for rejecting an action before execution."""

    STALE_TURN = "stale_turn"
    TASK_CANCELLED = "task_cancelled"
    TARGET_STALE = "target_stale"
    OBSERVATION_STALE = "observation_stale"
    WRONG_PAGE = "wrong_page"
    ELEMENT_NOT_FOUND = "element_not_found"
    ELEMENT_NOT_INTERACTABLE = "element_not_interactable"
    ALREADY_COMPLETED = "already_completed"
    UNAUTHORIZED = "unauthorized"


class ActionRejectedError(Exception):
    """Raised when an action fails precondition checks and cannot be safely executed."""

    def __init__(self, code: ActionRejectionCode, reason: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(f"ActionRejectedError[{code.value}]: {reason}")
        self.code = code
        self.reason = reason
        self.details = details or {}


@dataclass(slots=True)
class ActionTargetSpec:
    """Target element specification within an ActionContract."""

    ref: Optional[str] = None
    role: Optional[str] = None
    name: Optional[str] = None
    selector: Optional[str] = None
    coordinates: Optional[Dict[str, float]] = None


@dataclass(slots=True)
class ActionContract:
    """Strict structured contract governing every browser mutation or interaction."""

    action_id: str = field(default_factory=lambda: f"act_{int(time.time()*1000)}_{uuid.uuid4().hex[:6]}")
    task_id: str = ""
    stage_id: str = ""
    turn_id: str = ""
    target_id: str = ""
    observation_id: str = ""
    action_type: str = "click"  # click, fill, type, press, navigate, etc.
    target: ActionTargetSpec = field(default_factory=ActionTargetSpec)
    preconditions: List[str] = field(
        default_factory=lambda: [
            "active_user_turn",
            "not_cancelled",
            "target_exists",
            "correct_page",
            "observation_fresh",
            "target_visible",
            "not_already_completed",
        ]
    )
    expected_postconditions: List[str] = field(default_factory=list)
    verification_strategy: str = "fresh_snapshot_and_state_check"
    timeout_ms: int = 8000
    retry_policy: str = "safe_reobserve_then_recover"
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PreconditionChecker:
    """Validates ActionContracts against current runtime state and live page observations."""

    def __init__(
        self,
        state_mgr: Optional[RuntimeStateManager] = None,
        target_mgr: Optional[BrowserTargetManager] = None,
        obs_mgr: Optional[ObservationManager] = None,
    ) -> None:
        self.state_mgr = state_mgr or RuntimeStateManager.get_instance()
        self.target_mgr = target_mgr or BrowserTargetManager.get_instance()
        self.obs_mgr = obs_mgr or ObservationManager.get_instance()

    def validate_and_admit_action(
        self,
        contract: ActionContract,
        runtime_tabs: Optional[List[Dict[str, Any]]] = None,
        current_page_state: Optional[str] = None,
        is_already_completed: bool = False,
    ) -> tuple[ValidatedTargetContext, Optional[SemanticElement]]:
        """Validate all preconditions before action execution.

        Returns:
            (ValidatedTargetContext, resolved SemanticElement or None)

        Raises:
            ActionRejectedError: If any precondition fails.
        """
        # 1. Turn boundary check
        if "active_user_turn" in contract.preconditions:
            active_turn = self.state_mgr.state.active_user_turn_id
            if contract.turn_id and active_turn and contract.turn_id != active_turn:
                raise ActionRejectedError(
                    ActionRejectionCode.STALE_TURN,
                    f"Tool call turn_id '{contract.turn_id}' does not match active turn '{active_turn}'",
                )

        # 2. Cancellation check
        if "not_cancelled" in contract.preconditions:
            if self.state_mgr.state.cancellation_state:
                raise ActionRejectedError(
                    ActionRejectionCode.TASK_CANCELLED,
                    "Task has been cancelled by user or operator.",
                )

        # 3. Target health check
        if "target_exists" in contract.preconditions:
            try:
                target_ctx = self.target_mgr.validate_target(
                    target_id=contract.target_id,
                    runtime_tabs=runtime_tabs,
                )
            except Exception as e:
                raise ActionRejectedError(
                    ActionRejectionCode.TARGET_STALE,
                    f"Target validation failed: {e}",
                )
        else:
            target_ctx = ValidatedTargetContext(
                session_id="default",
                target_id=contract.target_id,
                tab_id=contract.target_id,
                url="",
                title="",
                domain="",
                app_type="generic",
            )

        # 4. Correct page check
        if "correct_page" in contract.preconditions and current_page_state:
            if current_page_state in ("google_login", "captcha", "blocked_page"):
                raise ActionRejectedError(
                    ActionRejectionCode.WRONG_PAGE,
                    f"Action cannot proceed on page state '{current_page_state}'",
                )

        # 5. Already completed check
        if "not_already_completed" in contract.preconditions and is_already_completed:
            raise ActionRejectedError(
                ActionRejectionCode.ALREADY_COMPLETED,
                "Requested action is already completed; skipping execution.",
                details={"action_type": contract.action_type, "target": asdict(contract.target)},
            )

        # 6. Element resolution & interactability (if target spec provided)
        resolved_elem: Optional[SemanticElement] = None
        if contract.target and (contract.target.ref or contract.target.name or contract.target.role or contract.target.selector):
            if "observation_fresh" in contract.preconditions:
                try:
                    resolved_elem = self.obs_mgr.resolve_element(
                        target_id=contract.target_id,
                        observation_id=contract.observation_id,
                        ref=contract.target.ref,
                        role=contract.target.role,
                        name=contract.target.name,
                        selector=contract.target.selector,
                    )
                except Exception as e:
                    raise ActionRejectedError(
                        ActionRejectionCode.OBSERVATION_STALE if "StaleObservationError" in str(type(e)) else ActionRejectionCode.ELEMENT_NOT_FOUND,
                        f"Failed to resolve target element: {e}",
                    )

            if "target_visible" in contract.preconditions and resolved_elem:
                if not resolved_elem.is_visible or not resolved_elem.is_enabled:
                    raise ActionRejectedError(
                        ActionRejectionCode.ELEMENT_NOT_INTERACTABLE,
                        f"Target element '{resolved_elem.name}' ({resolved_elem.role}) is hidden or disabled",
                    )

        return target_ctx, resolved_elem
