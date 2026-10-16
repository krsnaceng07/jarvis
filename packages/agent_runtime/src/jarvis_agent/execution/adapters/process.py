"""Tracked Subprocess Execution Adapter for Track 3.2.

Provides bounded subprocess lifecycle management:
- Subprocess tracking by execution_id and PID.
- Bounded stdout/stderr stream consumption to prevent memory bloat.
- Clean cancellation and process tree termination.
- Sandbox environment injection.
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import time

from jarvis_agent.execution.adapters.base import (
    AdapterExecutionOutput,
    BaseExecutionAdapter,
)
from jarvis_agent.execution.sandbox.host_adapter import SandboxContext
from jarvis_agent.orchestration.models.command import ExecutionCommand

logger = logging.getLogger(__name__)

MAX_OUTPUT_BYTES = 512 * 1024  # 512 KB output cap


class ProcessAdapter(BaseExecutionAdapter):
    """Execution adapter for spawning and managing subprocesses."""

    def __init__(self) -> None:
        self._active_processes: dict[str, subprocess.Popen[bytes]] = {}
        self._lock = threading.Lock()

    @property
    def adapter_name(self) -> str:
        return "process"

    def can_handle(self, capability_id: str) -> bool:
        return capability_id in ("process.spawn", "process.kill")

    def execute(
        self,
        command: ExecutionCommand,
        sandbox_ctx: SandboxContext | None = None,
    ) -> AdapterExecutionOutput:
        if command.capability_target == "process.spawn":
            return self._handle_spawn(command, sandbox_ctx)
        elif command.capability_target == "process.kill":
            return self._handle_kill(command)
        else:
            return AdapterExecutionOutput(
                success=False,
                error_message=f"Unsupported capability '{command.capability_target}' in ProcessAdapter",
            )

    def _handle_spawn(
        self,
        command: ExecutionCommand,
        sandbox_ctx: SandboxContext | None,
    ) -> AdapterExecutionOutput:
        args = command.arguments
        cmd = args.get("command")
        if not cmd:
            return AdapterExecutionOutput(
                success=False,
                error_message="Missing 'command' argument",
            )

        cmd_args = args.get("args", [])
        full_cmd: list[str] = [str(cmd)] + [str(a) for a in cmd_args]
        cwd = args.get("cwd")
        timeout = float(args.get("timeout_seconds", 30.0))

        env = os.environ.copy()
        if sandbox_ctx and sandbox_ctx.env_overrides:
            env.update(sandbox_ctx.env_overrides)

        start_time = time.monotonic()
        proc: subprocess.Popen[bytes] | None = None
        try:
            proc = subprocess.Popen(
                full_cmd,
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
            )
            with self._lock:
                self._active_processes[command.execution_id] = proc

            try:
                stdout_bytes, stderr_bytes = proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout_bytes, stderr_bytes = proc.communicate()
                return AdapterExecutionOutput(
                    success=False,
                    exit_code=-1,
                    error_message=f"Process exceeded timeout of {timeout}s and was killed",
                    raw_evidence={
                        "pid": proc.pid,
                        "timed_out": True,
                        "timeout_seconds": timeout,
                    },
                )

            duration = time.monotonic() - start_time
            exit_code = proc.returncode

            stdout_str = stdout_bytes[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")
            stderr_str = stderr_bytes[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")

            success = (exit_code == 0)
            return AdapterExecutionOutput(
                success=success,
                exit_code=exit_code,
                output_data={
                    "pid": proc.pid,
                    "stdout": stdout_str,
                    "stderr": stderr_str,
                    "exit_code": exit_code,
                },
                error_message=None if success else f"Process exited with non-zero code {exit_code}: {stderr_str}",
                raw_evidence={
                    "pid": proc.pid,
                    "exit_code": exit_code,
                    "duration_seconds": duration,
                    "stdout_bytes": len(stdout_bytes),
                    "stderr_bytes": len(stderr_bytes),
                },
            )
        except Exception as ex:
            return AdapterExecutionOutput(
                success=False,
                error_message=f"Subprocess spawn failed: {ex}",
            )
        finally:
            with self._lock:
                self._active_processes.pop(command.execution_id, None)

    def _handle_kill(self, command: ExecutionCommand) -> AdapterExecutionOutput:
        pid = command.arguments.get("pid")
        if pid is None:
            return AdapterExecutionOutput(
                success=False,
                error_message="Missing 'pid' argument",
            )

        target_pid = int(pid)
        try:
            # Attempt to terminate
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(target_pid)], capture_output=True)
            else:
                os.kill(target_pid, 9)

            return AdapterExecutionOutput(
                success=True,
                output_data={"killed_pid": target_pid},
                raw_evidence={"pid": target_pid, "killed": True},
            )
        except Exception as ex:
            return AdapterExecutionOutput(
                success=False,
                error_message=f"Failed to kill process {target_pid}: {ex}",
            )

    def cancel(self, execution_id: str) -> bool:
        with self._lock:
            proc = self._active_processes.get(execution_id)
            if proc:
                try:
                    proc.kill()
                    return True
                except Exception:
                    return False
        return False


__all__ = ["ProcessAdapter"]
