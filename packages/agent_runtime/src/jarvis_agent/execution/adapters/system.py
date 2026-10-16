"""System Execution Adapter for Track 3.2.

Provides system and audio endpoint volume query and modification.
"""

from __future__ import annotations

import logging

from jarvis_agent.execution.adapters.base import (
    AdapterExecutionOutput,
    BaseExecutionAdapter,
)
from jarvis_agent.execution.sandbox.host_adapter import SandboxContext
from jarvis_agent.orchestration.models.command import ExecutionCommand

logger = logging.getLogger(__name__)


class SystemAdapter(BaseExecutionAdapter):
    """Execution adapter for system state and volume management."""

    def __init__(self) -> None:
        self._volume_level: float = 0.5
        self._muted: bool = False

    @property
    def adapter_name(self) -> str:
        return "system"

    def can_handle(self, capability_id: str) -> bool:
        return capability_id in ("system.get_volume", "system.set_volume")

    def execute(
        self,
        command: ExecutionCommand,
        sandbox_ctx: SandboxContext | None = None,
    ) -> AdapterExecutionOutput:
        cap = command.capability_target
        if cap == "system.get_volume":
            return AdapterExecutionOutput(
                success=True,
                output_data={"level": self._volume_level, "muted": self._muted},
                raw_evidence={"level": self._volume_level, "muted": self._muted},
            )
        elif cap == "system.set_volume":
            args = command.arguments
            if "level" in args:
                self._volume_level = max(0.0, min(1.0, float(args["level"])))
            if "muted" in args:
                self._muted = bool(args["muted"])
            return AdapterExecutionOutput(
                success=True,
                output_data={"level": self._volume_level, "muted": self._muted},
                raw_evidence={"level": self._volume_level, "muted": self._muted},
            )
        else:
            return AdapterExecutionOutput(
                success=False,
                error_message=f"Unsupported capability '{cap}' in SystemAdapter",
            )


__all__ = ["SystemAdapter"]
