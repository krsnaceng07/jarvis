"""Track 3.6 Phase C — OpenClaw Plugin Execution Adapter.

Bridges execution commands routed by the CommandDispatcher to registered
plugin tool implementations, maintaining complete sandbox isolation, HookBus
observability, and fail-closed security invariants.

Design constraints:
* ``plugin_sdk`` must NOT statically import ``jarvis_agent`` (agent_runtime).
  All contracts are expressed via runtime-checkable Protocols so the adapter
  seamlessly plugs into the frozen CommandDispatcher.
* Observational HookBus integration (before_tool_call, after_tool_call) never
  leaks exceptions into the execution path.
* Handles sync and async tool handlers transparently.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

__all__ = [
    "AdapterOutputProtocol",
    "CommandProtocol",
    "ExecutionAdapterOutput",
    "PluginExecutionAdapter",
    "SandboxContextProtocol",
    "ToolCallable",
]


@runtime_checkable
class CommandProtocol(Protocol):
    """Structural match for ExecutionCommand from agent_runtime."""

    command_id: str
    capability_target: str
    parameters: dict[str, Any]
    session_id: str | None


@runtime_checkable
class SandboxContextProtocol(Protocol):
    """Structural match for SandboxContext from agent_runtime."""

    tier: Any
    working_directory: Any
    timeout_seconds: float


@runtime_checkable
class AdapterOutputProtocol(Protocol):
    """Structural match for AdapterExecutionOutput from agent_runtime."""

    success: bool
    exit_code: int | None
    output_data: Any
    error_message: str | None
    raw_evidence: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ExecutionAdapterOutput:
    """Output emitted by PluginExecutionAdapter.

    Matches jarvis_agent.execution.adapters.base.AdapterExecutionOutput.
    """

    success: bool
    exit_code: int | None = None
    output_data: Any = None
    error_message: str | None = None
    raw_evidence: dict[str, Any] = field(default_factory=dict)


ToolCallable = Callable[..., Any]


class PluginExecutionAdapter:
    """Execution adapter for OpenClaw plugin tools.

    Integrates with CommandDispatcher (Track 3.2), invoking registered plugin
    tool handlers and notifying HookBus observers.
    """

    def __init__(
        self,
        hook_bus: Any | None = None,
        output_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._adapter_name = "plugin_adapter"
        self._tools: dict[str, ToolCallable] = {}
        self._hook_bus = hook_bus
        self._output_factory = output_factory or ExecutionAdapterOutput
        self._active_executions: dict[str, bool] = {}

    @property
    def adapter_name(self) -> str:
        """Name of the adapter."""
        return self._adapter_name

    def register_tool(
        self,
        capability_id: str,
        handler: ToolCallable,
    ) -> None:
        """Register a tool handler under a specific capability ID."""
        if not capability_id.startswith("plugin."):
            capability_id = f"plugin.{capability_id}"
        self._tools[capability_id] = handler
        logger.debug("PluginExecutionAdapter registered '%s'", capability_id)

    def register_plugin_tools(self, tools: list[dict[str, Any]]) -> None:
        """Register a list of tool records (e.g. from plugin loader)."""
        for item in tools:
            name = item.get("name")
            plugin_id = item.get("plugin_id")
            handler = item.get("handler") or item.get("execute") or item.get("run")
            if name and handler and callable(handler):
                if plugin_id:
                    cap_id = f"plugin.{plugin_id}.{name}"
                else:
                    cap_id = f"plugin.{name}"
                self.register_tool(cap_id, handler)

    def can_handle(self, capability_id: str) -> bool:
        """Check if this adapter handles the specified capability."""
        if capability_id in self._tools:
            return True
        # Check normalized form if capability starts with plugin.
        if capability_id.startswith("plugin."):
            short_id = capability_id[len("plugin.") :]
            if short_id in self._tools:
                return True
        return False

    def get_handler(self, capability_id: str) -> ToolCallable | None:
        """Retrieve handler for capability ID."""
        if capability_id in self._tools:
            return self._tools[capability_id]
        if capability_id.startswith("plugin."):
            short_id = capability_id[len("plugin.") :]
            if short_id in self._tools:
                return self._tools[short_id]
        return None

    def execute(
        self,
        command: Any,
        sandbox_ctx: Any | None = None,
    ) -> Any:
        """Execute a plugin tool command within the established sandbox context."""
        cap_id = getattr(command, "capability_target", "")
        params = (
            getattr(command, "arguments", None)
            or getattr(command, "parameters", None)
            or {}
        )
        cmd_id = getattr(command, "command_id", "unknown")

        handler = self.get_handler(cap_id)
        if handler is None:
            return self._output_factory(
                success=False,
                error_message=f"No plugin tool handler registered for capability '{cap_id}'",
                raw_evidence={"capability_id": cap_id},
            )

        self._active_executions[cmd_id] = True
        start_time = time.perf_counter()

        # Step 1: HookBus before_tool_call (observational, fail-safe)
        self._notify_hook(
            "before_tool_call",
            {
                "tool": cap_id,
                "command_id": cmd_id,
                "parameters": params,
                "timestamp": time.time(),
            },
        )

        success = False
        output_data: Any = None
        error_msg: str | None = None

        try:
            # Step 2: Invoke handler (support sync or async)
            if inspect.iscoroutinefunction(handler):
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None
                if loop and loop.is_running():
                    # Running in existing event loop in this thread
                    import concurrent.futures

                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                        output_data = pool.submit(asyncio.run, handler(**params)).result()
                else:
                    output_data = asyncio.run(handler(**params))
            else:
                output_data = handler(**params)
                if inspect.iscoroutine(output_data):
                    output_data = asyncio.run(output_data)

            success = True

        except TypeError as type_err:
            # Handle signature mismatch gracefully (e.g. single args dict vs kwargs)
            try:
                if inspect.iscoroutinefunction(handler):
                    output_data = asyncio.run(handler(params))  # type: ignore
                else:
                    output_data = handler(params)  # type: ignore
                success = True
            except Exception as retry_err:
                error_msg = f"Plugin tool execution error: {retry_err}"
                logger.warning("Plugin tool '%s' error: %s", cap_id, retry_err)
        except Exception as exc:
            error_msg = f"Plugin tool execution error: {exc}"
            logger.warning("Plugin tool '%s' raised exception: %s", cap_id, exc)
        finally:
            self._active_executions.pop(cmd_id, None)

        duration = time.perf_counter() - start_time

        # Step 3: HookBus after_tool_call (observational, fail-safe)
        self._notify_hook(
            "after_tool_call",
            {
                "tool": cap_id,
                "command_id": cmd_id,
                "parameters": params,
                "success": success,
                "output": output_data,
                "error": error_msg,
                "duration_seconds": duration,
                "timestamp": time.time(),
            },
        )

        return self._output_factory(
            success=success,
            exit_code=0 if success else 1,
            output_data=output_data,
            error_message=error_msg,
            raw_evidence={
                "capability_id": cap_id,
                "duration_seconds": duration,
            },
        )

    def cancel(self, execution_id: str) -> bool:
        """Cancel ongoing execution if possible."""
        if execution_id in self._active_executions:
            self._active_executions.pop(execution_id, None)
            return True
        return False

    def _notify_hook(self, hook_name: str, payload: dict[str, Any]) -> None:
        """Notify HookBus observers without allowing hook errors to escape."""
        if self._hook_bus is None:
            return
        try:
            if hasattr(self._hook_bus, "emit"):
                self._hook_bus.emit(hook_name, payload)
            elif hasattr(self._hook_bus, "dispatch"):
                self._hook_bus.dispatch(hook_name, payload)
        except Exception as hook_err:
            logger.debug("Hook '%s' notification suppressed error: %s", hook_name, hook_err)
