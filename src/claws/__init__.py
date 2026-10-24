"""Autonomous Claws & Background Worker Daemons Subsystem — JARVIS Autonomous Architecture (Section 8).

Autonomous background worker agents that execute scheduled jobs without user intervention.
"""

from .base import Claw, ClawExecutionContext
from .builtins import (
    DatabaseMaintenanceClaw,
    DigestClaw,
    RepositoryHealthClaw,
    SystemMonitorClaw,
    WebMonitorClaw,
)
from .engine import ClawsEngine, get_claws_engine
from .task_queue import ClawTaskQueue
from .types import ClawJob, ClawJobStatus, ClawPriority, ClawResult
from .worker_pool import ClawWorkerPool

__all__ = [
    "Claw",
    "ClawExecutionContext",
    "ClawJob",
    "ClawJobStatus",
    "ClawPriority",
    "ClawResult",
    "ClawTaskQueue",
    "ClawWorkerPool",
    "ClawsEngine",
    "DatabaseMaintenanceClaw",
    "DigestClaw",
    "RepositoryHealthClaw",
    "SystemMonitorClaw",
    "WebMonitorClaw",
    "get_claws_engine",
]
