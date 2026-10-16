"""Hard planning limits and execution budgets for PlanDAGs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PlanLimits:
    """Hard boundaries preventing unbounded plan decomposition or infinite execution."""

    max_nodes: int = 50
    max_depth: int = 10
    max_retries_per_node: int = 3
    max_replans: int = 5
    max_execution_timeout_seconds: float = 3600.0
    max_node_timeout_seconds: float = 300.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlanLimits:
        return cls(
            max_nodes=int(data.get("max_nodes", 50)),
            max_depth=int(data.get("max_depth", 10)),
            max_retries_per_node=int(data.get("max_retries_per_node", 3)),
            max_replans=int(data.get("max_replans", 5)),
            max_execution_timeout_seconds=float(data.get("max_execution_timeout_seconds", 3600.0)),
            max_node_timeout_seconds=float(data.get("max_node_timeout_seconds", 300.0)),
        )


__all__ = ["PlanLimits"]
