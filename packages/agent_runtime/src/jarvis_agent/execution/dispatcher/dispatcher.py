"""Command Dispatcher for Track 3.2.

Routes admitted ExecutionCommands to their appropriate domain adapter,
passing the established SandboxContext and managing execution cancellation.
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


class CommandDispatcher:
    """Dispatches execution commands to registered domain adapters."""

    def __init__(self, adapters: list[BaseExecutionAdapter] | None = None) -> None:
        self._adapters: list[BaseExecutionAdapter] = list(adapters or [])

    def register_adapter(self, adapter: BaseExecutionAdapter) -> None:
        """Register a new domain adapter."""
        self._adapters.append(adapter)
        logger.debug("Registered adapter '%s'", adapter.adapter_name)

    def find_adapter(self, capability_id: str) -> BaseExecutionAdapter | None:
        """Find an adapter capable of handling the capability."""
        for adapter in self._adapters:
            if adapter.can_handle(capability_id):
                return adapter
        return None

    def dispatch(
        self,
        command: ExecutionCommand,
        sandbox_ctx: SandboxContext | None = None,
    ) -> AdapterExecutionOutput:
        """Locate adapter and execute command."""
        adapter = self.find_adapter(command.capability_target)
        if not adapter:
            return AdapterExecutionOutput(
                success=False,
                error_message=f"No execution adapter found for capability '{command.capability_target}'",
            )

        logger.info(
            "Dispatching command %s (%s) to adapter '%s' under sandbox tier '%s'",
            command.command_id,
            command.capability_target,
            adapter.adapter_name,
            sandbox_ctx.tier if sandbox_ctx else "NONE",
        )
        return adapter.execute(command, sandbox_ctx)

    def cancel(self, execution_id: str) -> bool:
        """Attempt to cancel an ongoing execution across all adapters."""
        cancelled = False
        for adapter in self._adapters:
            if adapter.cancel(execution_id):
                cancelled = True
        return cancelled


__all__ = ["CommandDispatcher"]
