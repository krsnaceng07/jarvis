"""src.agents.subagents.types
Canonical multi-agent data types and contracts.

Matches OpenClaw parity:
- src/agents/subagents/spawn/subagent-spawn-contract.ts
- src/agents/subagents/spawn/subagent-capabilities.ts
- src/agents/subagents/registry/subagent-registry.types.ts
- src/agents/subagents/announce/subagent-announce-output.ts
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SubagentRole(str, Enum):
    """Resolved role for a main session, orchestrating subagent, or leaf subagent."""

    MAIN = "main"
    ORCHESTRATOR = "orchestrator"
    LEAF = "leaf"


class SubagentStatus(str, Enum):
    """Lifecycle status for a subagent run record."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    YIELDED = "yielded"


class SubagentSpawnContextMode(str, Enum):
    """Context construction mode when creating a subagent."""

    ISOLATED = "isolated"
    FORK = "fork"


@dataclass
class SubagentRunRecord:
    """Persistent tracking record for a spawned subagent execution."""

    run_id: str
    child_session_key: str
    parent_session_key: str
    task: str
    label: str = ""
    task_id: str = ""
    role: SubagentRole = SubagentRole.LEAF
    depth: int = 1
    status: SubagentStatus = SubagentStatus.QUEUED
    started_at: float = field(default_factory=time.time)
    ended_at: float | None = None
    result_text: str | None = None
    error: str | None = None
    tangible_artifacts: list[str] = field(default_factory=list)
    generation: int = 1
    model: str | None = None
    timeout_seconds: float = 60.0
    context_mode: SubagentSpawnContextMode = SubagentSpawnContextMode.ISOLATED
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "child_session_key": self.child_session_key,
            "parent_session_key": self.parent_session_key,
            "task": self.task,
            "label": self.label,
            "task_id": self.task_id,
            "role": self.role.value,
            "depth": self.depth,
            "status": self.status.value,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "result_text": self.result_text,
            "error": self.error,
            "tangible_artifacts": list(self.tangible_artifacts),
            "generation": self.generation,
            "model": self.model,
            "timeout_seconds": self.timeout_seconds,
            "context_mode": self.context_mode.value,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SubagentRunRecord:
        return cls(
            run_id=data.get("run_id", ""),
            child_session_key=data.get("child_session_key", ""),
            parent_session_key=data.get("parent_session_key", ""),
            task=data.get("task", ""),
            label=data.get("label", ""),
            task_id=data.get("task_id", ""),
            role=SubagentRole(data.get("role", "leaf")),
            depth=int(data.get("depth", 1)),
            status=SubagentStatus(data.get("status", "queued")),
            started_at=float(data.get("started_at", time.time())),
            ended_at=float(data["ended_at"]) if data.get("ended_at") is not None else None,
            result_text=data.get("result_text"),
            error=data.get("error"),
            tangible_artifacts=list(data.get("tangible_artifacts") or []),
            generation=int(data.get("generation", 1)),
            model=data.get("model"),
            timeout_seconds=float(data.get("timeout_seconds", 60.0)),
            context_mode=SubagentSpawnContextMode(data.get("context_mode", "isolated")),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class SpawnSubagentParams:
    """Parameters passed to spawn a subagent."""

    task: str
    label: str = ""
    task_name: str = ""
    agent_id: str = "subagent"
    model: str | None = None
    thinking: str | None = None
    run_timeout_seconds: float = 60.0
    context: SubagentSpawnContextMode = SubagentSpawnContextMode.ISOLATED
    parent_session_key: str = "desktop:hud"
    parent_depth: int = 0
    cwd: str | None = None
    attachments: list[dict[str, Any]] | None = None
    expects_completion_message: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SpawnSubagentResult:
    """Outcome returned from a spawn operation."""

    status: str  # "accepted" | "forbidden" | "error"
    child_session_key: str | None = None
    run_id: str | None = None
    task_id: str | None = None
    role: str | None = None
    context: str | None = None
    error: str | None = None
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        res: dict[str, Any] = {"status": self.status}
        if self.child_session_key:
            res["child_session_key"] = self.child_session_key
        if self.run_id:
            res["run_id"] = self.run_id
        if self.task_id:
            res["task_id"] = self.task_id
        if self.role:
            res["role"] = self.role
        if self.context:
            res["context"] = self.context
        if self.error:
            res["error"] = self.error
        if self.note:
            res["note"] = self.note
        return res
