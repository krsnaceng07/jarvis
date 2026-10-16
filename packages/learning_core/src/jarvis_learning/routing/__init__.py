"""jarvis_learning.routing — hybrid model routing, safety guards, and shadow execution."""

from __future__ import annotations

from .guard import GuardDecision, LocalDecisionGuard
from .health import ExecutionHealthRecord, HealthDecision, RuntimeHealthMonitor
from .ood import DistributionGuard, OODResult
from .promotion import PromotionDecision, PromotionManager, ShadowQualification
from .router import ModelRouter, RouterConfig, RoutingResult, RoutingState
from .shadow import ShadowExecutor, ShadowObservation, ShadowPerformanceMetrics

__all__ = [
    "DistributionGuard",
    "ExecutionHealthRecord",
    "GuardDecision",
    "HealthDecision",
    "LocalDecisionGuard",
    "ModelRouter",
    "OODResult",
    "PromotionDecision",
    "PromotionManager",
    "RouterConfig",
    "RoutingResult",
    "RoutingState",
    "RuntimeHealthMonitor",
    "ShadowExecutor",
    "ShadowObservation",
    "ShadowPerformanceMetrics",
    "ShadowQualification",
]
