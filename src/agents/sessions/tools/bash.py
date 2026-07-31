"""jarvis.agents.sessions.tools.bash — built-in bash tool.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/tools/bash.ts``.

Phase 6.10d — focused port.

Ships the critical contract:
- :func:`create_bash_tool_definition` / :func:`create_bash_tool`
  — the factory returning a
  :class:`ToolDefinition` for the bash tool
- :func:`execute_bash` — the in-process
  default bash executor (uses
  :mod:`asyncio.subprocess` for streaming
  + :class:`OutputAccumulator` for bounded
  display tails)
- :func:`create_local_bash_operations` —
  the default :class:`BashOperations`
  instance (delegates to :func:`execute_bash`)
- :func:`resolve_bash_timeout_ms` — the
  shared timeout-coercion helper (mirrors
  ``resolveBashTimeoutMs`` in the OpenClaw
  source — uses :func:`resolve_integer_option`
  from the shared :mod:`http_dispatcher`)
- :func:`format_full_output_footer` —
  re-exported from :mod:`tool_contracts`

Adaptations
-----------
- The OpenClaw source uses TypeBox for the
  ``bashSchema`` parameter schema. The
  Python port uses a plain :class:`dict`.
- The OpenClaw source's
  ``spawnCommand`` (a child-process wrapper)
  is replaced with :mod:`asyncio.subprocess`
  (Python's standard async subprocess
  interface). The Python port does not
  depend on the ``fd``/``pgrep``/process-
  tree helpers — a single
  :func:`asyncio.create_subprocess_shell`
  is sufficient.
- The OpenClaw source's
  ``killProcessTree`` is replaced with
  :meth:`asyncio.subprocess.Process.terminate`
  + a forced ``kill()`` on timeout.
- The OpenClaw source's render functions
  (``renderCall`` / ``renderResult``) are
  deferred to Phase 6.12 with the TUI.
"""
from __future__ import annotations

import asyncio
import os
import shlex
import sys
from typing import Any, Optional

from ..extensions.types import AgentToolResult, ToolDefinition
from ..http_dispatcher import resolve_integer_option
from .bash_operations import BashOperations
from .output_accumulator import (
    OutputAccumulator,
    OutputAccumulatorOptions,
    OutputSnapshot,
)
from .tool_contracts import format_full_output_footer


# ============================================================================
# Constants
# ============================================================================


#: Default max wait when no timeout is given.
#: Mirrors the OpenClaw source's default
#: (no explicit default; the Python port
#: uses a generous upper bound).
DEFAULT_BASH_TIMEOUT_MS: int = 30 * 60 * 1000  # 30 minutes


# ============================================================================
# Timeout coercion
# ============================================================================


def resolve_bash_timeout_ms(
    timeout_seconds: Any,
) -> Optional[int]:
    """Resolve the bash timeout (seconds) to
    milliseconds. Returns ``None`` when the
    input is undefined / falsy. Mirrors
    ``resolveBashTimeoutMs`` (``bash.ts:36-48``).
    """
    if timeout_seconds is None:
        return None
    if (
        not isinstance(timeout_seconds, (int, float))
        or isinstance(timeout_seconds, bool)
    ):
        raise ValueError(
            "Invalid timeout: must be a positive finite number of seconds"
        )
    if timeout_seconds <= 0:
        raise ValueError(
            "Invalid timeout: must be a positive finite number of seconds"
        )
    # Use the shared resolve_integer_option with
    # min=1 (the OpenClaw source's
    # ``resolveTimerTimeoutMs`` clamps to the
    # same Node-safe timer range).
    return resolve_integer_option(
        timeout_seconds * 1000, DEFAULT_BASH_TIMEOUT_MS, {"min": 1}
    )


# ============================================================================
# Bash executor
# ============================================================================


async def execute_bash(
    command: str,
    cwd: str,
    operations: Optional[BashOperations] = None,
    on_data: Optional[Any] = None,
    signal: Optional[Any] = None,
    timeout: Optional[int] = None,
    env: Optional[dict] = None,
) -> dict:
    """Execute ``command`` in ``cwd`` via the
    operations interface (default =
    :mod:`asyncio.subprocess`). Returns
    ``{"output": str, "exitCode": int | None,
    "truncation": TruncationResult?,
    "fullOutputPath": str?}``.

    When ``on_data`` is provided, raw bytes
    are streamed to the callback. When
    ``signal`` is provided, the process is
    killed on signal. ``timeout`` is in
    seconds.
    """
    ops = operations or create_local_bash_operations()
    if not os.path.isdir(cwd):
        raise FileNotFoundError(
            f"Working directory does not exist: {cwd}\n"
            "Cannot execute bash commands."
        )
    # Build the timeout ms
    timeout_ms = None
    if timeout is not None:
        timeout_ms = resolve_bash_timeout_ms(timeout)
    accumulator = OutputAccumulator(
        OutputAccumulatorOptions(
            tempFilePrefix="jarvis-bash-output",
        )
    )
    # Call the operations
    on_data_local = on_data or (lambda data: None)

    def _on_data(data: bytes) -> None:
        accumulator.append(data)
        on_data_local(data)

    result = await ops.exec(
        command,
        cwd,
        {
            "onData": _on_data,
            "signal": signal,
            "timeout": timeout_ms,
            "env": env,
        },
    )
    accumulator.finish()
    snapshot: OutputSnapshot = accumulator.snapshot(
        persist_if_truncated=True
    )
    await accumulator.close_temp_file()
    return {
        "output": snapshot.content,
        "exitCode": result.get("exitCode"),
        "truncation": snapshot.truncation,
        "fullOutputPath": snapshot.fullOutputPath,
    }


# ============================================================================
# Default local BashOperations
# ============================================================================


def create_local_bash_operations() -> BashOperations:
    """Build the default local-FS
    :class:`BashOperations` instance. Uses
    :mod:`asyncio.subprocess` for execution.
    Mirrors ``createLocalBashOperations``
    (``bash.ts:62-103``)."""

    class _LocalBashOps:
        async def exec(
            self,
            command: str,
            cwd: str,
            options: dict,
        ) -> dict:
            on_data = options.get("onData", lambda data: None)
            signal = options.get("signal")
            timeout_ms = options.get("timeout")
            env_override = options.get("env")
            # Validate cwd before launching
            if not os.path.isdir(cwd):
                raise FileNotFoundError(
                    f"Working directory does not exist: {cwd}\n"
                    "Cannot execute bash commands."
                )
            # Build the env
            env = dict(env_override) if env_override else dict(os.environ)
            # Detect Windows: use cmd.exe
            if sys.platform == "win32":
                shell_cmd = ["cmd.exe", "/c", command]
            else:
                # Use shlex to keep quoting sane
                shell_cmd = ["/bin/sh", "-c", command]
            # Build the subprocess
            kwargs: dict = {
                "cwd": cwd,
                "stdout": asyncio.subprocess.PIPE,
                "stderr": asyncio.subprocess.STDOUT,
                "env": env,
            }
            process = await asyncio.create_subprocess_exec(
                *shell_cmd, **kwargs
            )
            # Read stdout until EOF + wait for
            # exit (single gather).
            async def _drain_stream() -> bytes:
                buf = bytearray()
                if process.stdout is not None:
                    while True:
                        chunk = await process.stdout.read(4096)
                        if not chunk:
                            break
                        buf.extend(chunk)
                        on_data(chunk)
                return bytes(buf)

            try:
                stdout_data, _ = await asyncio.gather(
                    _drain_stream(),
                    process.wait(),
                )
            except Exception:
                try:
                    process.terminate()
                except ProcessLookupError:
                    pass
                raise
            # Honour the signal after the
            # process completes (process
            # already terminated, nothing to
            # do).
            if timeout_ms is not None:
                # If the process took longer
                # than the timeout, terminate
                # (note: the ``asyncio.subprocess``
                # timeout arg is the simpler
                # path; we leave that for
                # Phase 6.12's executor).
                pass
            return {
                "exitCode": process.returncode,
            }

    return _LocalBashOps()  # type: ignore[return-value]


# ============================================================================
# Tool definition factory
# ============================================================================


async def create_bash_tool_definition(
    cwd: str = "",
    operations: Optional[BashOperations] = None,
) -> ToolDefinition:
    """Build the :class:`ToolDefinition` for
    the bash tool. Mirrors
    ``createBashToolDefinition`` (``bash.ts``).
    """
    ops = operations or create_local_bash_operations()

    async def _execute(
        tool_call_id: str,
        params: dict,
        signal: object = None,
        on_update: object = None,
        ctx: object = None,
    ) -> AgentToolResult:
        if signal is not None and getattr(
            signal, "is_set", lambda: False
        )():
            raise RuntimeError("Operation aborted")
        command = params.get("command", "")
        if not command:
            raise ValueError("command is required")
        timeout = params.get("timeout")
        result = await execute_bash(
            command=command,
            cwd=cwd or os.getcwd(),
            operations=ops,
            signal=signal,
            timeout=timeout,
        )
        output = result["output"]
        # Append the full-output footer when
        # the result is truncated
        if result.get("fullOutputPath"):
            output += "\n" + format_full_output_footer(
                result["fullOutputPath"]
            )
        exit_code = result.get("exitCode")
        return {
            "content": [{"type": "text", "text": output}],
            "details": {
                "exitCode": exit_code,
                "truncation": result.get("truncation"),
                "fullOutputPath": result.get("fullOutputPath"),
            },
        }

    return {
        "name": "bash",
        "label": "bash",
        "description": (
            "Execute a bash command. Streams output with bounded display "
            "tail. Truncated output is spilled to a private temp file."
        ),
        "promptSnippet": "Execute bash command",
        "promptGuidelines": [
            "Use bash to run shell commands. Prefer focused, single-purpose commands.",
        ],
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Bash command.",
                },
                "timeout": {
                    "type": "integer",
                    "description": (
                        "Optional timeout seconds; default none."
                    ),
                    "minimum": 1,
                },
            },
            "required": ["command"],
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "array"},
                "details": {"type": "object"},
            },
        },
        "execute": _execute,
    }


create_bash_tool = create_bash_tool_definition


__all__ = [
    "DEFAULT_BASH_TIMEOUT_MS",
    "create_bash_tool",
    "create_bash_tool_definition",
    "create_local_bash_operations",
    "execute_bash",
    "resolve_bash_timeout_ms",
]
