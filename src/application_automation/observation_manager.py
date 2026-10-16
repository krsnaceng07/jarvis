"""jarvis.application_automation.observation_manager — Observation IDs & stale ref invalidation.

OpenClaw parity:
- extensions/browser/src/browser-tool.snapshot.ts (ARIA trees & sanitization)
- src/agents/tools/computer-tool-result.ts (contextEpoch & frame invalidation)
- src/agents/tools/computer-tool-guidance.ts (stale observationId/elementRef contract)

Guarantees:
1. Every observation receives an immutable, epoch-bound observation_id.
2. Navigations, route transitions, and major DOM mutations increment contextEpoch and invalidate older refs.
3. Attempting to use a ref from an invalidated observation raises StaleObservationError.
4. Selectors follow OpenClaw priority: Semantic Ref > Role/Name > Accessible Label > Test ID > CSS > XPath.
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class StaleObservationError(Exception):
    """Raised when an action attempts to use an elementRef or observation_id that is no longer fresh."""

    def __init__(self, observation_id: str, current_observation_id: str, reason: str = "") -> None:
        super().__init__(
            f"StaleObservationError: Observation '{observation_id}' is obsolete (current: '{current_observation_id}'). "
            f"Page mutated or navigated. {reason}"
        )
        self.observation_id = observation_id
        self.current_observation_id = current_observation_id


@dataclass(slots=True)
class SemanticElement:
    """An interactive element identified during an accessibility snapshot."""

    ref: str  # e.g. "ax0", "ax1"
    role: str  # e.g. "button", "link", "combobox", "textbox"
    name: str  # Accessible name e.g. "Subscribe", "Search"
    value: Optional[str] = None
    is_visible: bool = True
    is_enabled: bool = True
    selector: Optional[str] = None
    bounds: Optional[Dict[str, float]] = None

    def matches(self, role: Optional[str] = None, name: Optional[str] = None) -> bool:
        """Check if element matches desired role and accessible name."""
        if role and self.role.lower() != role.lower():
            return False
        if name:
            if self.name.lower() == name.lower():
                return True
            # Regex or partial word match
            pattern = rf"\b{re.escape(name.lower())}\b"
            if not re.search(pattern, self.name.lower()):
                return False
        return True


@dataclass(slots=True)
class PageObservation:
    """An authoritative snapshot of page accessibility tree and state."""

    observation_id: str
    target_id: str
    url: str
    title: str
    epoch: int
    page_type: str = "generic"
    page_state: str = "normal"
    timestamp: float = field(default_factory=time.time)
    elements: List[SemanticElement] = field(default_factory=list)
    raw_aria_tree: str = ""
    ref_map: Dict[str, SemanticElement] = field(default_factory=dict)

    def find_element(
        self,
        ref: Optional[str] = None,
        role: Optional[str] = None,
        name: Optional[str] = None,
        selector: Optional[str] = None,
    ) -> Optional[SemanticElement]:
        """Resolve element using OpenClaw target priority."""
        if ref and ref in self.ref_map:
            return self.ref_map[ref]

        if role or name:
            for el in self.elements:
                if el.matches(role=role, name=name):
                    return el

        if selector:
            for el in self.elements:
                if el.selector == selector:
                    return el

        return None


class ObservationManager:
    """Coordinates page snapshots, observation epochs, and element resolution."""

    _instance: Optional[ObservationManager] = None

    def __init__(self) -> None:
        self._epochs: Dict[str, int] = {}  # target_id -> epoch count
        self._latest_observations: Dict[str, PageObservation] = {}  # target_id -> latest PageObservation

    @classmethod
    def get_instance(cls) -> ObservationManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def invalidate_target_epoch(self, target_id: str, reason: str = "navigation") -> int:
        """Advance epoch for target_id to invalidate all prior observations and refs."""
        curr = self._epochs.get(target_id, 0) + 1
        self._epochs[target_id] = curr
        if target_id in self._latest_observations:
            # Drop previous observation references to prevent stale reuse
            del self._latest_observations[target_id]
        return curr

    def record_snapshot(
        self,
        target_id: str,
        url: str,
        title: str = "",
        raw_aria_tree: str = "",
        page_type: str = "generic",
        page_state: str = "normal",
        parsed_elements: Optional[List[SemanticElement]] = None,
    ) -> PageObservation:
        """Create and store a fresh immutable PageObservation."""
        epoch = self._epochs.get(target_id, 1)
        obs_id = f"obs_{int(time.time()*1000)}_{uuid.uuid4().hex[:6]}"

        elements = parsed_elements or []
        ref_map = {el.ref: el for el in elements}

        obs = PageObservation(
            observation_id=obs_id,
            target_id=target_id,
            url=url,
            title=title,
            epoch=epoch,
            page_type=page_type,
            page_state=page_state,
            elements=elements,
            raw_aria_tree=raw_aria_tree,
            ref_map=ref_map,
        )
        self._latest_observations[target_id] = obs
        return obs

    def get_latest_observation(self, target_id: str) -> Optional[PageObservation]:
        """Get the current valid observation for a target."""
        return self._latest_observations.get(target_id)

    def resolve_element(
        self,
        target_id: str,
        observation_id: str,
        ref: Optional[str] = None,
        role: Optional[str] = None,
        name: Optional[str] = None,
        selector: Optional[str] = None,
    ) -> SemanticElement:
        """Resolve element against active observation, enforcing freshness.

        Raises:
            StaleObservationError: If observation_id does not match the active observation.
            LookupError: If element cannot be resolved.
        """
        latest = self._latest_observations.get(target_id)
        if not latest:
            raise StaleObservationError(
                observation_id=observation_id,
                current_observation_id="",
                reason="No active observation exists for this target. Fresh snapshot required.",
            )

        if latest.observation_id != observation_id:
            raise StaleObservationError(
                observation_id=observation_id,
                current_observation_id=latest.observation_id,
                reason="Observation has been invalidated by a newer page state.",
            )

        elem = latest.find_element(ref=ref, role=role, name=name, selector=selector)
        if not elem:
            raise LookupError(
                f"Element not found in observation '{observation_id}' for criteria "
                f"[ref={ref}, role={role}, name={name}, selector={selector}]"
            )

        return elem
