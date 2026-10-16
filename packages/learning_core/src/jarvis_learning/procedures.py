"""jarvis_learning.procedures — procedural memory for multi-step tasks.

A ``Procedure`` captures a proven sequence of steps that JARVIS has
successfully executed.  When a similar task is encountered, the
procedure can be proposed as a plan.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from .experience import generate_id, now_ms

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ProcedureStep:
    """One step within a learned procedure."""

    step_index: int
    action: str
    tool: str = ""
    argument_template: dict[str, Any] = field(default_factory=dict)
    expected_outcome: str = ""
    fallback_action: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_index": self.step_index,
            "action": self.action,
            "tool": self.tool,
            "argument_template": self.argument_template,
            "expected_outcome": self.expected_outcome,
            "fallback_action": self.fallback_action,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProcedureStep:
        return cls(
            step_index=data.get("step_index", 0),
            action=data.get("action", ""),
            tool=data.get("tool", ""),
            argument_template=data.get("argument_template", {}),
            expected_outcome=data.get("expected_outcome", ""),
            fallback_action=data.get("fallback_action", ""),
        )


@dataclass(frozen=True, slots=True)
class Procedure:
    """A learned multi-step procedure with preconditions and fallback."""

    id: str
    created_at: int
    updated_at: int
    name: str
    preconditions: dict[str, Any] = field(default_factory=dict)
    steps: tuple[ProcedureStep, ...] = ()
    fallback: str = ""
    success_count: int = 0
    failure_count: int = 0
    confidence: float = 0.5

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.0
        return self.success_count / total

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "name": self.name,
            "preconditions": json.dumps(self.preconditions),
            "steps": json.dumps([s.to_dict() for s in self.steps]),
            "fallback": self.fallback,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Procedure:
        preconditions = data.get("preconditions", "{}")
        if isinstance(preconditions, str):
            preconditions = json.loads(preconditions)
        steps_raw = data.get("steps", "[]")
        if isinstance(steps_raw, str):
            steps_raw = json.loads(steps_raw)
        steps = tuple(ProcedureStep.from_dict(s) for s in steps_raw)
        return cls(
            id=data["id"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            name=data["name"],
            preconditions=preconditions,
            steps=steps,
            fallback=data.get("fallback", ""),
            success_count=data.get("success_count", 0),
            failure_count=data.get("failure_count", 0),
            confidence=float(data.get("confidence", 0.5)),
        )


class ProcedureStore:
    """In-memory + SQLite store for learned procedures."""

    def __init__(self) -> None:
        self._procedures: dict[str, Procedure] = {}
        self._by_name: dict[str, str] = {}  # name → id

    def add(self, procedure: Procedure) -> None:
        self._procedures[procedure.id] = procedure
        self._by_name[procedure.name.lower()] = procedure.id
        logger.debug("procedure stored: id=%s name=%s", procedure.id, procedure.name)

    def get(self, procedure_id: str) -> Procedure | None:
        return self._procedures.get(procedure_id)

    def get_by_name(self, name: str) -> Procedure | None:
        pid = self._by_name.get(name.lower())
        if pid is not None:
            return self._procedures.get(pid)
        return None

    def find_matching(self, intent: str) -> list[Procedure]:
        """Find procedures whose name matches the intent (substring)."""
        intent_lower = intent.lower()
        return sorted(
            [
                p
                for p in self._procedures.values()
                if intent_lower in p.name.lower() or p.name.lower() in intent_lower
            ],
            key=lambda p: p.confidence * p.success_rate,
            reverse=True,
        )

    def record_outcome(self, procedure_id: str, *, succeeded: bool) -> Procedure | None:
        old = self._procedures.get(procedure_id)
        if old is None:
            return None
        ts = now_ms()
        new_success = old.success_count + (1 if succeeded else 0)
        new_failure = old.failure_count + (0 if succeeded else 1)
        total = new_success + new_failure
        updated = Procedure(
            id=old.id,
            created_at=old.created_at,
            updated_at=ts,
            name=old.name,
            preconditions=old.preconditions,
            steps=old.steps,
            fallback=old.fallback,
            success_count=new_success,
            failure_count=new_failure,
            confidence=new_success / total if total > 0 else 0.5,
        )
        self._procedures[procedure_id] = updated
        self._by_name[updated.name.lower()] = updated.id
        return updated

    def create_from_episode(
        self,
        name: str,
        steps: list[ProcedureStep],
        *,
        preconditions: dict[str, Any] | None = None,
        fallback: str = "",
    ) -> Procedure:
        """Create a new procedure from a successful task episode."""
        ts = now_ms()
        proc = Procedure(
            id=generate_id(),
            created_at=ts,
            updated_at=ts,
            name=name,
            preconditions=preconditions or {},
            steps=tuple(steps),
            fallback=fallback,
            success_count=1,
            failure_count=0,
            confidence=0.5,
        )
        self.add(proc)
        return proc

    def all_procedures(self) -> list[Procedure]:
        return list(self._procedures.values())

    def load(self, procedures: list[Procedure]) -> None:
        for p in procedures:
            self._procedures[p.id] = p
            self._by_name[p.name.lower()] = p.id
        logger.info("loaded %d procedures", len(procedures))
