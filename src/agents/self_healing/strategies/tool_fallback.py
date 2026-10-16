"""src.agents.self_healing.strategies.tool_fallback — Dynamic tool fallback execution.

OpenClaw parity: alternative tool path resolution when a specialized tool fails.
"""

from __future__ import annotations

import os
import sys

from ..failure_event import ErrorCategory, FailureEvent
from .base import RecoveryResult, RecoveryStrategy


class ToolFallbackStrategy(RecoveryStrategy):
    """Provides alternative execution mechanisms when a specialized tool fails."""

    name: str = "tool_fallback"

    async def can_handle(self, event: FailureEvent) -> bool:
        """Handles tool execution errors where a suitable alternative tool exists."""
        if event.category not in (
            ErrorCategory.TOOL_EXECUTION_ERROR,
            ErrorCategory.SYSTEM_IO_ERROR,
        ):
            return False
        tool_name = event.context.get("tool_name")
        return tool_name in ("ls", "read")

    async def execute(self, event: FailureEvent) -> RecoveryResult:
        """Formulate a fallback tool execution plan."""
        tool_name = str(event.context.get("tool_name") or "")
        args = dict(event.context.get("args") or {})

        # Fallback 1: ls failure -> fallback to exec with dir / ls
        if tool_name == "ls":
            target_path = args.get("path") or "."
            if sys.platform == "win32":
                cmd = f'cmd.exe /c dir /b "{target_path}"'
            else:
                cmd = f'ls -1 "{target_path}"'

            return RecoveryResult(
                success=True,
                action_taken=f"Fallback tool: substitute 'ls' with 'exec' ({cmd})",
                repaired_args={"command": cmd},
                requires_retry=True,
                details={
                    "fallback_tool": "exec",
                    "fallback_args": {"command": cmd},
                    "original_tool": "ls",
                },
            )

        # Fallback 2: read failure -> fallback to ls if directory, or powershell / cat with encoding tolerance
        if tool_name == "read":
            target_path = args.get("path") or ""
            is_dir = False
            try:
                if target_path and os.path.isdir(target_path):
                    is_dir = True
            except Exception:
                pass
            err_msg = str(event.error_message or "").lower()
            if not is_dir and ("is a directory" in err_msg or "eisdir" in err_msg):
                is_dir = True

            if is_dir:
                return RecoveryResult(
                    success=True,
                    action_taken=f"Fallback tool: target path '{target_path}' is a directory, substituting 'read' with 'ls'",
                    repaired_args={"path": target_path},
                    requires_retry=True,
                    details={
                        "fallback_tool": "ls",
                        "fallback_args": {"path": target_path},
                        "original_tool": "read",
                    },
                )

            if sys.platform == "win32":
                cmd = (
                    f"powershell.exe -NoProfile -Command \"Get-Content -Path '{target_path}' -Raw\""
                )
            else:
                cmd = f'cat "{target_path}"'

            return RecoveryResult(
                success=True,
                action_taken=f"Fallback tool: substitute 'read' with 'exec' ({cmd})",
                repaired_args={"command": cmd},
                requires_retry=True,
                details={
                    "fallback_tool": "exec",
                    "fallback_args": {"command": cmd},
                    "original_tool": "read",
                },
            )

        return RecoveryResult(
            success=False,
            action_taken="No fallback tool available",
            error=f"No known fallback tool for '{tool_name}'",
        )


__all__ = [
    "ToolFallbackStrategy",
]
