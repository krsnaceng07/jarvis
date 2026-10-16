"""jarvis.agents.task.runtime_state — Authoritative central runtime state model.

Implements OpenClaw parity:
Maintains one unified, authoritative source of truth across voice, text,
GUI, console, channels, browser tools, desktop tools, agents, and subagents.
Replaces reliance on conversational model memory alone with observable,
structured state tracking.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from threading import RLock
from typing import Any, Optional


class TaskStatus(str, Enum):
    """Allowed states for an authoritative agent task."""

    CREATED = "created"
    UNDERSTANDING = "understanding"
    PLANNING = "planning"
    WAITING_FOR_PRECONDITION = "waiting_for_precondition"
    WAITING_FOR_CONTEXT = "waiting_for_context"
    EXECUTING = "executing"
    OBSERVING = "observing"
    VERIFYING = "verifying"
    PAUSED = "paused"
    WAITING_FOR_CONFIRMATION = "waiting_for_confirmation"
    RECOVERING = "recovering"
    COMPLETED_VERIFIED = "completed_verified"
    ALREADY_COMPLETED = "already_completed"
    COMPLETED_UNVERIFIED = "completed_unverified"
    PARTIALLY_COMPLETED = "partially_completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"
    UNSUPPORTED = "unsupported"


@dataclass(slots=True)
class RuntimeState:
    """Central authoritative execution state of JARVIS."""

    active_user_turn_id: str = ""
    active_task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    active_session_id: str = "desktop:hud"
    parent_task_id: Optional[str] = None
    task_status: TaskStatus = TaskStatus.CREATED
    current_stage: str = "initial"
    current_goal: str = ""
    current_subgoal: str = ""
    completed_stages: list[str] = field(default_factory=list)
    pending_stages: list[str] = field(default_factory=list)
    failed_stages: list[str] = field(default_factory=list)
    last_verified_stage: Optional[str] = None
    next_required_stage: Optional[str] = None

    # Application & Browser context
    active_application: str = ""
    active_window_handle: Optional[int] = None
    active_window_title: str = ""
    active_process_id: Optional[int] = None
    current_target: str = ""
    expected_context: dict[str, Any] = field(default_factory=dict)
    active_browser_session: str = "default"
    active_browser_target_id: str = ""
    active_tab_url: str = ""
    active_tab_title: str = ""
    active_page_type: str = "unknown"
    active_page_state: str = "unknown"

    # Observation & Action tracking
    last_observation_id: str = ""
    last_observed_state: dict[str, Any] = field(default_factory=dict)
    last_action_id: str = ""
    last_successful_action: Optional[str] = None
    pending_action: Optional[dict[str, Any]] = None
    action_owner: str = ""
    tool_call_id: str = ""
    tool_call_status: str = ""
    verification_status: str = ""
    recovery_attempts: int = 0
    last_action_result: Optional[dict[str, Any]] = None
    last_verified_result: Optional[dict[str, Any]] = None

    # Intent, Lifecycle & Continuity
    pending_user_instruction: str = ""
    command_origin: str = "voice"  # voice, text, channel, cli, scheduled
    cancellation_state: bool = False
    cancellation_status: str = ""
    continuation_confidence: float = 0.0

    # Timestamps
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Convert state to JSON-serializable dictionary."""
        d = asdict(self)
        d["task_status"] = self.task_status.value
        return d


class RuntimeStateManager:
    """Thread-safe singleton managing the authoritative runtime state."""

    _instance: Optional[RuntimeStateManager] = None
    _lock = RLock()

    def __init__(self) -> None:
        self._state = RuntimeState()
        self._history: list[dict[str, Any]] = []

    @classmethod
    def get_instance(cls) -> RuntimeStateManager:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @property
    def state(self) -> RuntimeState:
        with self._lock:
            return self._state

    def begin_user_turn(
        self,
        turn_id: str,
        user_instruction: str,
        origin: str = "voice",
        application: str = "",
        session_id: str = "desktop:hud",
    ) -> RuntimeState:
        """Initialize or advance to a new user turn."""
        with self._lock:
            self._state.active_user_turn_id = turn_id
            self._state.active_session_id = session_id
            self._state.pending_user_instruction = user_instruction
            self._state.command_origin = origin
            self._state.cancellation_state = False
            self._state.cancellation_status = ""
            self._state.task_status = TaskStatus.UNDERSTANDING
            self._state.current_goal = user_instruction
            self._state.updated_at = time.time()
            if application:
                self._state.active_application = application
            return self._state

    def is_turn_active(self, turn_id: str) -> bool:
        """Check if a tool call belongs to the currently active user turn."""
        with self._lock:
            if not turn_id:
                return False
            return (
                self._state.active_user_turn_id == turn_id
                and not self._state.cancellation_state
            )

    def transition_stage(
        self,
        new_stage: str,
        status: Optional[TaskStatus] = None,
        verified: bool = False,
    ) -> None:
        """Advance the current task stage in a validated sequence."""
        with self._lock:
            if self._state.current_stage and self._state.current_stage != new_stage:
                if verified:
                    if self._state.current_stage not in self._state.completed_stages:
                        self._state.completed_stages.append(self._state.current_stage)
                    self._state.last_verified_stage = self._state.current_stage
                elif self._state.current_stage in self._state.pending_stages:
                    self._state.pending_stages.remove(self._state.current_stage)

            self._state.current_stage = new_stage
            if status:
                self._state.task_status = status
            self._state.updated_at = time.time()

    def admit_tool_call(
        self,
        *,
        turn_id: str,
        tool_call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        session_id: str = "desktop:hud",
    ) -> tuple[bool, dict[str, Any]]:
        """Record and admit a tool call only when it belongs to the live turn."""
        with self._lock:
            if self._state.cancellation_state:
                return False, self._structured_block(
                    tool_name,
                    "cancelled",
                    "task_cancelled",
                    "Task was cancelled before this tool call could run.",
                )
            if turn_id and self._state.active_user_turn_id and turn_id != self._state.active_user_turn_id:
                return False, self._structured_block(
                    tool_name,
                    "context_invalid",
                    "stale_action",
                    "Tool call belongs to an older turn and was rejected.",
                )
            if self._state.task_status in {
                TaskStatus.COMPLETED_VERIFIED,
                TaskStatus.ALREADY_COMPLETED,
                TaskStatus.CANCELLED,
            }:
                return False, self._structured_block(
                    tool_name,
                    "context_invalid",
                    "task_not_active",
                    f"Task is already {self._state.task_status.value}.",
                )
            self._state.active_session_id = session_id
            self._state.tool_call_id = tool_call_id
            self._state.tool_call_status = "admitted"
            self._state.pending_action = {"tool": tool_name, "arguments": dict(arguments)}
            self._state.action_owner = session_id
            self._state.task_status = TaskStatus.EXECUTING
            self._state.updated_at = time.time()
            return True, {}

    def observe_environment(self, observed_state: dict[str, Any]) -> None:
        """Attach current host/browser observation to the active task."""
        with self._lock:
            self._state.last_observed_state = dict(observed_state)
            if "application" in observed_state:
                self._state.active_application = str(observed_state["application"] or "")
            if "window_handle" in observed_state:
                self._state.active_window_handle = observed_state["window_handle"]
            if "window_title" in observed_state:
                self._state.active_window_title = str(observed_state["window_title"] or "")
            if "process_id" in observed_state:
                self._state.active_process_id = observed_state["process_id"]
            self._state.task_status = TaskStatus.OBSERVING
            self._state.updated_at = time.time()

    def update_browser_context(
        self,
        target_id: str,
        url: str,
        title: str = "",
        page_type: str = "",
        page_state: str = "",
        session_id: str = "default",
    ) -> None:
        """Update active browser tab and page metadata."""
        with self._lock:
            self._state.active_browser_target_id = target_id
            self._state.active_tab_url = url
            if title:
                self._state.active_tab_title = title
            if page_type:
                self._state.active_page_type = page_type
            if page_state:
                self._state.active_page_state = page_state
            if session_id:
                self._state.active_browser_session = session_id
            self._state.updated_at = time.time()

    def record_observation(self, observation_id: str) -> None:
        """Register a newly generated observation ID."""
        with self._lock:
            self._state.last_observation_id = observation_id
            self._state.task_status = TaskStatus.OBSERVING
            self._state.updated_at = time.time()

    def record_action(self, action_id: str, result: dict[str, Any]) -> None:
        """Record dispatched action and raw tool result."""
        with self._lock:
            self._state.last_action_id = action_id
            self._state.last_action_result = result
            self._state.tool_call_status = str(result.get("status") or "finished")
            self._state.task_status = TaskStatus.VERIFYING
            self._state.updated_at = time.time()

    def record_verified_result(
        self,
        status: TaskStatus,
        verification_details: dict[str, Any],
    ) -> None:
        """Record authoritative verification outcome."""
        with self._lock:
            self._state.task_status = status
            self._state.verification_status = status.value
            self._state.last_verified_result = verification_details
            if status == TaskStatus.COMPLETED_VERIFIED:
                self._state.last_successful_action = self._state.last_action_id
                if self._state.current_stage not in self._state.completed_stages:
                    self._state.completed_stages.append(self._state.current_stage)
                self._state.last_verified_stage = self._state.current_stage
            elif status == TaskStatus.FAILED:
                if self._state.current_stage not in self._state.failed_stages:
                    self._state.failed_stages.append(self._state.current_stage)
            self._state.updated_at = time.time()

    def cancel_active_task(self, reason: str = "user_cancellation") -> None:
        """Cancel current task and reject any pending or delayed tool calls."""
        with self._lock:
            self._state.cancellation_state = True
            self._state.cancellation_status = reason
            self._state.task_status = TaskStatus.CANCELLED
            self._state.updated_at = time.time()

    def reset(self) -> None:
        """Reset state for a fresh session."""
        with self._lock:
            self._state = RuntimeState()

    @staticmethod
    def _structured_block(
        tool_name: str,
        status: str,
        error_type: str,
        reason: str,
    ) -> dict[str, Any]:
        return {
            "status": status,
            "command_accepted": False,
            "effect_verified": False,
            "target_valid": False,
            "state_changed": False,
            "requires_recovery": status != "cancelled",
            "error_type": error_type,
            "observed_state": {},
            "expected_state": {},
            "evidence": [reason],
            "next_recommended_action": "reobserve_environment" if status != "cancelled" else None,
            "result": reason,
            "error": True,
        }
