"""jarvis_learning.task_continuity — Multi-step task continuity and lifecycle state tracking.

Maintains multi-step task state across interaction turns, distinguishing
evidence-based task continuation from new unrelated tasks, and enabling safe
resource target reuse (e.g. browser tabs, application processes, editor documents).
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(slots=True)
class TaskContinuityState:
    """Complete 16-field multi-step task continuity state."""

    task_id: str
    session_id: str
    run_id: str
    turn_id: str
    sequence_number: int
    agent_id: str
    parent_agent_id: Optional[str]
    channel_id: str
    workspace_id: str
    current_stage: str
    completed_stages: list[str] = field(default_factory=list)
    pending_stages: list[str] = field(default_factory=list)
    failed_stages: list[str] = field(default_factory=list)
    verification_status: str = "unverified"
    recovery_action: Optional[str] = None
    last_tool_call_id: Optional[str] = None

    # Contextual metadata and resource target tracking
    resource_target_id: Optional[str] = None
    resource_target_type: Optional[str] = None  # "browser_tab" | "process" | "file" | "window"
    intent_signature: Optional[str] = None
    last_updated_timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "turn_id": self.turn_id,
            "sequence_number": self.sequence_number,
            "agent_id": self.agent_id,
            "parent_agent_id": self.parent_agent_id,
            "channel_id": self.channel_id,
            "workspace_id": self.workspace_id,
            "current_stage": self.current_stage,
            "completed_stages": list(self.completed_stages),
            "pending_stages": list(self.pending_stages),
            "failed_stages": list(self.failed_stages),
            "verification_status": self.verification_status,
            "recovery_action": self.recovery_action,
            "last_tool_call_id": self.last_tool_call_id,
            "resource_target_id": self.resource_target_id,
            "resource_target_type": self.resource_target_type,
            "intent_signature": self.intent_signature,
            "last_updated_timestamp": self.last_updated_timestamp,
        }


@dataclass(frozen=True, slots=True)
class ContinuityEvaluationResult:
    """Outcome of disambiguating active-task continuation versus new task."""

    is_continuation: bool
    selection_reason: str
    confidence: float
    task_id: str
    current_stage: str
    pending_stages: tuple[str, ...]
    failed_stages: tuple[str, ...]
    resource_target_id: Optional[str] = None
    resource_target_type: Optional[str] = None
    last_tool_call_id: Optional[str] = None


# Patterns indicating continuation intent via pronouns or relative references
_CONTINUATION_PRONOUNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(?:it|that|this|there|them|the\s+same|again|next|previous)\b", re.IGNORECASE),
    re.compile(
        r"\b(?:send\s+it|save\s+it|close\s+it|open\s+it|play\s+it|pause\s+it|stop\s+it)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:on\s+that\s+tab|in\s+that\s+window|in\s+the\s+same\s+app)\b", re.IGNORECASE),
    re.compile(r"\b(?:now\s+(?:search|open|click|type|save|send|navigate))\b", re.IGNORECASE),
    re.compile(r"\b(?:pathaideu|save\s+gara|bhanda\s+gara|arko\s+baja)\b", re.IGNORECASE),
)

# Explicit new-task indicators or topic resets
_NEW_TASK_INDICATORS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(?:new\s+task|start\s+over|reset|forget\s+that|nevermind|ignore\s+that|different\s+thing)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:naya\s+kam|chhoddeu|birsyo|arko\s+kura)\b", re.IGNORECASE),
)


class TaskContinuityTracker:
    """Manages active task continuity states across multi-step turns."""

    def __init__(self) -> None:
        # Keyed by (session_id, workspace_id)
        self._active_tasks: dict[tuple[str, str], TaskContinuityState] = {}

    def get_active_task(
        self, session_id: str, workspace_id: str = "default"
    ) -> Optional[TaskContinuityState]:
        """Retrieve current active task for session."""
        return self._active_tasks.get((session_id, workspace_id))

    def evaluate_turn(
        self,
        user_input: str,
        session_id: str,
        context: Optional[dict[str, Any]] = None,
        workspace_id: str = "default",
        agent_id: str = "default",
        channel_id: str = "desktop:hud",
    ) -> ContinuityEvaluationResult:
        """Disambiguate continuation of active task versus new unrelated task."""
        context = context or {}
        key = (session_id, workspace_id)
        active = self._active_tasks.get(key)
        clean_input = user_input.strip()

        # 1. If no active task exists for this session, it must be a new task
        if active is None:
            new_task_id = f"task_{uuid.uuid4().hex[:8]}"
            state = TaskContinuityState(
                task_id=new_task_id,
                session_id=session_id,
                run_id=f"run_{uuid.uuid4().hex[:6]}",
                turn_id="turn_1",
                sequence_number=1,
                agent_id=agent_id,
                parent_agent_id=context.get("parent_agent_id"),
                channel_id=channel_id,
                workspace_id=workspace_id,
                current_stage="initiated",
                pending_stages=context.get("stages", ["execution"]),
                failed_stages=[],
                verification_status="unverified",
                resource_target_id=context.get("target_id") or context.get("tab_id"),
                resource_target_type=context.get("target_type"),
                intent_signature=clean_input[:50],
            )
            self._active_tasks[key] = state
            return ContinuityEvaluationResult(
                is_continuation=False,
                selection_reason="No existing active task in session lineage; initialized new task",
                confidence=1.0,
                task_id=new_task_id,
                current_stage=state.current_stage,
                pending_stages=tuple(state.pending_stages),
                failed_stages=tuple(state.failed_stages),
                resource_target_id=state.resource_target_id,
                resource_target_type=state.resource_target_type,
                last_tool_call_id=None,
            )

        # 2. Check for explicit reset/new-task indicators
        if any(p.search(clean_input) for p in _NEW_TASK_INDICATORS):
            # Terminate active task and start fresh
            new_task_id = f"task_{uuid.uuid4().hex[:8]}"
            new_state = TaskContinuityState(
                task_id=new_task_id,
                session_id=session_id,
                run_id=f"run_{uuid.uuid4().hex[:6]}",
                turn_id="turn_1",
                sequence_number=1,
                agent_id=agent_id,
                parent_agent_id=context.get("parent_agent_id"),
                channel_id=channel_id,
                workspace_id=workspace_id,
                current_stage="initiated",
                pending_stages=context.get("stages", ["execution"]),
                failed_stages=[],
                resource_target_id=None,
                intent_signature=clean_input[:50],
            )
            self._active_tasks[key] = new_state
            return ContinuityEvaluationResult(
                is_continuation=False,
                selection_reason="Explicit new task or topic reset indicator detected in user input",
                confidence=0.98,
                task_id=new_task_id,
                current_stage=new_state.current_stage,
                pending_stages=tuple(new_state.pending_stages),
                failed_stages=tuple(new_state.failed_stages),
                resource_target_id=None,
                resource_target_type=None,
                last_tool_call_id=None,
            )

        # 3. Check for explicit continuation indicators:
        # Pronouns, reference to active target resource, explicit task stage parameter
        has_pronoun = any(p.search(clean_input) for p in _CONTINUATION_PRONOUNS)
        context_target_id = (
            context.get("active_browser_target_id")
            or context.get("active_app_id")
            or context.get("target_id")
        )
        shares_resource_target = bool(
            active.resource_target_id
            and context_target_id
            and active.resource_target_id == context_target_id
        )
        task_stage_provided = bool(context.get("task_stage") or context.get("is_continuation"))

        # Time threshold: active task expires after 10 minutes of inactivity
        is_fresh = (time.time() - active.last_updated_timestamp) < 600.0

        if is_fresh and (
            has_pronoun
            or shares_resource_target
            or task_stage_provided
            or bool(active.pending_stages)
        ):
            # Valid continuation
            active.sequence_number += 1
            active.turn_id = f"turn_{active.sequence_number}"
            active.last_updated_timestamp = time.time()
            if context.get("task_stage"):
                active.current_stage = str(context["task_stage"])

            reasons = []
            if shares_resource_target:
                reasons.append(f"matched active resource target '{active.resource_target_id}'")
            if has_pronoun:
                reasons.append("detected multi-turn referential pronoun")
            if task_stage_provided:
                reasons.append("explicit task stage continuity context")
            if active.pending_stages:
                reasons.append(f"{len(active.pending_stages)} pending stages remaining")

            return ContinuityEvaluationResult(
                is_continuation=True,
                selection_reason="; ".join(reasons) or "active multi-step stage progression",
                confidence=0.95,
                task_id=active.task_id,
                current_stage=active.current_stage,
                pending_stages=tuple(active.pending_stages),
                failed_stages=tuple(active.failed_stages),
                resource_target_id=active.resource_target_id,
                resource_target_type=active.resource_target_type,
                last_tool_call_id=active.last_tool_call_id,
            )

        # 4. Otherwise, treat as new task
        new_task_id = f"task_{uuid.uuid4().hex[:8]}"
        fresh_state = TaskContinuityState(
            task_id=new_task_id,
            session_id=session_id,
            run_id=f"run_{uuid.uuid4().hex[:6]}",
            turn_id="turn_1",
            sequence_number=1,
            agent_id=agent_id,
            parent_agent_id=context.get("parent_agent_id"),
            channel_id=channel_id,
            workspace_id=workspace_id,
            current_stage="initiated",
            pending_stages=context.get("stages", ["execution"]),
            failed_stages=[],
            resource_target_id=context.get("target_id"),
            resource_target_type=context.get("target_type"),
            intent_signature=clean_input[:50],
        )
        self._active_tasks[key] = fresh_state
        return ContinuityEvaluationResult(
            is_continuation=False,
            selection_reason="Unrelated input with no active stage, target, or referential link to prior task",
            confidence=0.90,
            task_id=new_task_id,
            current_stage=fresh_state.current_stage,
            pending_stages=tuple(fresh_state.pending_stages),
            failed_stages=tuple(fresh_state.failed_stages),
            resource_target_id=fresh_state.resource_target_id,
            resource_target_type=fresh_state.resource_target_type,
            last_tool_call_id=None,
        )

    def record_stage_transition(
        self,
        session_id: str,
        stage_name: str,
        success: bool,
        tool_call_id: Optional[str] = None,
        verification_status: str = "verified",
        recovery_action: Optional[str] = None,
        workspace_id: str = "default",
    ) -> Optional[TaskContinuityState]:
        """Record stage execution outcome and update active continuity state."""
        key = (session_id, workspace_id)
        state = self._active_tasks.get(key)
        if not state:
            return None

        state.last_updated_timestamp = time.time()
        if tool_call_id:
            state.last_tool_call_id = tool_call_id
        state.verification_status = verification_status

        if success:
            if stage_name not in state.completed_stages:
                state.completed_stages.append(stage_name)
            if stage_name in state.pending_stages:
                state.pending_stages.remove(stage_name)
            # Advance stage
            state.current_stage = state.pending_stages[0] if state.pending_stages else "completed"
            state.recovery_action = None
        else:
            if stage_name not in state.failed_stages:
                state.failed_stages.append(stage_name)
            state.recovery_action = recovery_action or f"retry_{stage_name}"

        return state

    def bind_resource_target(
        self,
        session_id: str,
        target_id: str,
        target_type: str,
        workspace_id: str = "default",
    ) -> bool:
        """Bind verified physical resource target (e.g. browser tab, process ID) to active task."""
        key = (session_id, workspace_id)
        state = self._active_tasks.get(key)
        if not state:
            return False
        state.resource_target_id = target_id
        state.resource_target_type = target_type
        state.last_updated_timestamp = time.time()
        return True
