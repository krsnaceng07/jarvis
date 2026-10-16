"""jarvis.application_automation.state_machine — Observable application state machine.

Provides a robust, observable finite state machine for multi-step application
automation workflows (e.g. YouTube HOME -> SEARCHING -> SEARCH_RESULTS -> VIDEO_PLAYING).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set


@dataclass(slots=True)
class StateTransition:
    """Record of a single state transition."""

    from_state: str
    to_state: str
    trigger: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


class ApplicationStateMachine:
    """Observable finite state machine for application lifecycle workflows."""

    def __init__(
        self,
        initial_state: str = "UNINITIALIZED",
        valid_transitions: Optional[Dict[str, Set[str]]] = None,
    ) -> None:
        self._current_state: str = initial_state
        self._valid_transitions: Dict[str, Set[str]] = valid_transitions or {}
        self._history: List[StateTransition] = []
        self._listeners: List[Callable[[StateTransition], None]] = []

    @property
    def current_state(self) -> str:
        return self._current_state

    @property
    def history(self) -> List[StateTransition]:
        return list(self._history)

    def add_listener(self, listener: Callable[[StateTransition], None]) -> None:
        self._listeners.append(listener)

    def can_transition_to(self, new_state: str) -> bool:
        """Check if transition from current state to new_state is valid."""
        if not self._valid_transitions:
            return True
        allowed = self._valid_transitions.get(self._current_state, set())
        return new_state in allowed

    def transition_to(
        self,
        new_state: str,
        trigger: str = "action",
        metadata: Optional[Dict[str, Any]] = None,
        force: bool = False,
    ) -> bool:
        """Transition to a new state if allowed or forced.
        
        Returns:
            True if transition succeeded, False if rejected by transition rules.
        """
        if not force and not self.can_transition_to(new_state):
            return False

        transition = StateTransition(
            from_state=self._current_state,
            to_state=new_state,
            trigger=trigger,
            metadata=metadata or {},
        )
        self._current_state = new_state
        self._history.append(transition)

        # Keep transition history bounded
        if len(self._history) > 50:
            self._history = self._history[-50:]

        for listener in self._listeners:
            try:
                listener(transition)
            except Exception:
                pass

        return True

    def reset(self, initial_state: str = "UNINITIALIZED") -> None:
        self._current_state = initial_state
        self._history.clear()
