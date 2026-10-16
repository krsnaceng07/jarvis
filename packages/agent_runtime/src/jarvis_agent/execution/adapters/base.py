"""Base Execution Adapter interface and output models for Track 3.2.

Defines the contract that all domain adapters (filesystem, process, browser,
desktop, system, channels) must implement.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from jarvis_agent.execution.sandbox.host_adapter import SandboxContext
from jarvis_agent.orchestration.models.command import ExecutionCommand


@dataclass(frozen=True, slots=True)
class AdapterExecutionOutput:
    """Standardized output emitted by an adapter after command execution."""

    success: bool
    exit_code: int | None = None
    output_data: Any = None
    error_message: str | None = None
    raw_evidence: dict[str, Any] = field(default_factory=dict)


class BaseExecutionAdapter(ABC):
    """Abstract base class for all execution adapters."""

    @property
    @abstractmethod
    def adapter_name(self) -> str:
        """Name of the adapter."""
        ...

    @abstractmethod
    def can_handle(self, capability_id: str) -> bool:
        """Check if this adapter handles the specified capability."""
        ...

    @abstractmethod
    def execute(
        self,
        command: ExecutionCommand,
        sandbox_ctx: SandboxContext | None = None,
    ) -> AdapterExecutionOutput:
        """Execute the command within the provided sandbox context."""
        ...

    def cancel(self, execution_id: str) -> bool:
        """Cancel ongoing execution if supported by adapter."""
        return False


__all__ = ["AdapterExecutionOutput", "BaseExecutionAdapter"]
