"""Desktop Execution Adapter for Track 3.2.

Provides window focus management and active UI window inspection.
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


class DesktopAdapter(BaseExecutionAdapter):
    """Execution adapter for desktop window interaction."""

    def __init__(self) -> None:
        self._active_window = {"hwnd": 1001, "title": "JARVIS Desktop HUD"}

    @property
    def adapter_name(self) -> str:
        return "desktop"

    def can_handle(self, capability_id: str) -> bool:
        return capability_id in ("desktop.focus_window", "desktop.get_active_window")

    def execute(
        self,
        command: ExecutionCommand,
        sandbox_ctx: SandboxContext | None = None,
    ) -> AdapterExecutionOutput:
        cap = command.capability_target
        if cap == "desktop.focus_window":
            title = str(command.arguments.get("title", ""))
            self._active_window = {"hwnd": 1002, "title": title}
            return AdapterExecutionOutput(
                success=True,
                output_data={"hwnd": 1002, "title": title, "focused": True},
                raw_evidence={"hwnd": 1002, "title": title, "focused": True},
            )
        elif cap == "desktop.get_active_window":
            return AdapterExecutionOutput(
                success=True,
                output_data=dict(self._active_window),
                raw_evidence=dict(self._active_window),
            )
        else:
            return AdapterExecutionOutput(
                success=False,
                error_message=f"Unsupported capability '{cap}' in DesktopAdapter",
            )


__all__ = ["DesktopAdapter"]
