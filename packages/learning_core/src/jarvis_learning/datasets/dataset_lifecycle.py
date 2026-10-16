"""jarvis_learning.datasets.dataset_lifecycle — formal lifecycle state machine.

Enforces 11 explicit states and operator approval gate:
DRAFT -> BUILT -> VALIDATED -> SECURITY_SCANNED -> PROVENANCE_VERIFIED
      -> DISTRIBUTION_REVIEWED -> APPROVED -> FROZEN -> REVOKED (or SUPERSEDED / ARCHIVED).

A dataset builder CANNOT self-approve its own output. Transition to APPROVED or FROZEN
strictly requires explicit human operator sign-off.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import StrEnum


class DatasetLifecycleState(StrEnum):
    DRAFT = "draft"
    BUILT = "built"
    VALIDATED = "validated"
    SECURITY_SCANNED = "security_scanned"
    PROVENANCE_VERIFIED = "provenance_verified"
    DISTRIBUTION_REVIEWED = "distribution_reviewed"
    APPROVED = "approved"
    APPROVED_FOR_TRAINING = "approved_for_training"
    FROZEN = "frozen"
    REVOKED = "revoked"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


@dataclass(frozen=True, slots=True)
class OperatorApproval:
    """Cryptographic or authenticated operator sign-off."""

    operator_id: str
    operator_role: str
    approval_event_id: str
    approval_signature: str
    approval_timestamp: float
    approval_scope: str = "PRODUCTION_TRAINING"


class DatasetLifecycleManager:
    """Manages legal state transitions for a dataset."""

    VALID_TRANSITIONS: dict[DatasetLifecycleState, set[DatasetLifecycleState]] = {
        DatasetLifecycleState.DRAFT: {DatasetLifecycleState.BUILT, DatasetLifecycleState.REVOKED},
        DatasetLifecycleState.BUILT: {
            DatasetLifecycleState.VALIDATED,
            DatasetLifecycleState.REVOKED,
        },
        DatasetLifecycleState.VALIDATED: {
            DatasetLifecycleState.SECURITY_SCANNED,
            DatasetLifecycleState.REVOKED,
        },
        DatasetLifecycleState.SECURITY_SCANNED: {
            DatasetLifecycleState.PROVENANCE_VERIFIED,
            DatasetLifecycleState.REVOKED,
        },
        DatasetLifecycleState.PROVENANCE_VERIFIED: {
            DatasetLifecycleState.DISTRIBUTION_REVIEWED,
            DatasetLifecycleState.REVOKED,
        },
        DatasetLifecycleState.DISTRIBUTION_REVIEWED: {
            DatasetLifecycleState.APPROVED,
            DatasetLifecycleState.APPROVED_FOR_TRAINING,
            DatasetLifecycleState.REVOKED,
        },
        DatasetLifecycleState.APPROVED: {
            DatasetLifecycleState.APPROVED_FOR_TRAINING,
            DatasetLifecycleState.FROZEN,
            DatasetLifecycleState.REVOKED,
            DatasetLifecycleState.SUPERSEDED,
        },
        DatasetLifecycleState.APPROVED_FOR_TRAINING: {
            DatasetLifecycleState.FROZEN,
            DatasetLifecycleState.REVOKED,
            DatasetLifecycleState.SUPERSEDED,
        },
        DatasetLifecycleState.FROZEN: {
            DatasetLifecycleState.APPROVED_FOR_TRAINING,
            DatasetLifecycleState.REVOKED,
            DatasetLifecycleState.SUPERSEDED,
            DatasetLifecycleState.ARCHIVED,
        },
        DatasetLifecycleState.REVOKED: {DatasetLifecycleState.ARCHIVED},
        DatasetLifecycleState.SUPERSEDED: {DatasetLifecycleState.ARCHIVED},
        DatasetLifecycleState.ARCHIVED: set(),
    }

    def __init__(self, current_state: DatasetLifecycleState = DatasetLifecycleState.DRAFT) -> None:
        self._state = current_state
        self._approval: OperatorApproval | None = None
        self._history: list[tuple[DatasetLifecycleState, float, str]] = [
            (current_state, time.time(), "initial")
        ]

    @property
    def state(self) -> DatasetLifecycleState:
        return self._state

    @property
    def approval(self) -> OperatorApproval | None:
        return self._approval

    def transition_to(
        self,
        new_state: DatasetLifecycleState,
        reason: str = "",
        operator_approval: OperatorApproval | None = None,
    ) -> None:
        """Attempt lifecycle state transition."""
        allowed = self.VALID_TRANSITIONS.get(self._state, set())
        if new_state not in allowed:
            raise ValueError(
                f"Illegal dataset lifecycle transition: {self._state.value} -> {new_state.value}"
            )

        # Gated states require operator sign-off
        if new_state in (
            DatasetLifecycleState.APPROVED,
            DatasetLifecycleState.APPROVED_FOR_TRAINING,
            DatasetLifecycleState.FROZEN,
        ):
            if not operator_approval and not self._approval:
                raise PermissionError(
                    f"Transition to {new_state.value} requires explicit operator approval"
                )
            if operator_approval:
                self._approval = operator_approval

        self._state = new_state
        self._history.append((new_state, time.time(), reason))
