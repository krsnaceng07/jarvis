"""Operator control plane, audit trails, and atomic rollback for Phase 10."""

from __future__ import annotations

from jarvis_learning.control_plane.dashboard_sidecar import (
    DashboardSidecarService,
    DashboardSnapshot,
)
from jarvis_learning.control_plane.operator_auth import (
    ApprovalTokenPayload,
    OperatorAuthManager,
    OperatorRole,
    SignedApprovalToken,
    TokenExpiredError,
    TokenReplayError,
    UnauthorizedOperatorError,
)
from jarvis_learning.control_plane.rollback_engine import (
    RollbackClass,
    RollbackEngine,
    RollbackRecord,
)

__all__ = [
    "ApprovalTokenPayload",
    "DashboardSidecarService",
    "DashboardSnapshot",
    "OperatorAuthManager",
    "OperatorRole",
    "RollbackClass",
    "RollbackEngine",
    "RollbackRecord",
    "SignedApprovalToken",
    "TokenExpiredError",
    "TokenReplayError",
    "UnauthorizedOperatorError",
]
