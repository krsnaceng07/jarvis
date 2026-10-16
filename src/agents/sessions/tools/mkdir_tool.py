"""jarvis.agents.sessions.tools.mkdir_tool — Built-in mkdir tool.

Provides explicit directory/folder creation capability on host drives (e.g. E:\\, C:\\)
and sandbox workspaces, giving JARVIS 1:1 behavioral parity with desktop host control.
"""

from __future__ import annotations

import os
from typing import Optional

from ..extensions.types import AgentToolResult, ToolDefinition
from .path_utils import is_drive_available, resolve_unicode_path


def create_mkdir_tool_definition(
    cwd: str = "",
    options: Optional[dict] = None,
) -> ToolDefinition:
    """Build the :class:`ToolDefinition` for the mkdir tool."""

    async def _execute(
        tool_call_id: str,
        params: dict,
        signal: object = None,
        on_update: object = None,
        ctx: object = None,
    ) -> AgentToolResult:
        if signal is not None and getattr(signal, "is_set", lambda: False)():
            raise RuntimeError("Operation aborted")

        path = params.get("path", "")
        if not path:
            raise ValueError("path is required")

        # 1. Resolve path against cwd or expand ~ with Unicode, user home normalization & slash hygiene
        resolved = resolve_unicode_path(path, cwd or os.getcwd())

        # 2. Check drive availability on Windows
        if not is_drive_available(resolved):
            raise FileNotFoundError(
                f"Drive not available on this host: {resolved}. "
                f"Please verify available drives with 'ls(path=\"drives\")'."
            )

        # 3. Apply sandbox and tool policy security floor if applicable
        from ...sandbox import guard_sandbox_tool_access

        _, validated = guard_sandbox_tool_access(
            "mkdir", resolved, cwd, options, ctx, is_mutation=True
        )
        if validated is not None:
            resolved = str(validated)

        # 4. Recursively create directory with resilient error handling
        try:
            os.makedirs(resolved, exist_ok=True)
        except PermissionError as exc:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Permission denied creating directory '{resolved}': {exc}. "
                                "Directory is protected or requires administrator privileges.",
                    }
                ],
                "details": {
                    "path": resolved,
                    "created": False,
                    "error": str(exc),
                },
            }
        except OSError as exc:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Failed to create directory '{resolved}': {exc}",
                    }
                ],
                "details": {
                    "path": resolved,
                    "created": False,
                    "error": str(exc),
                },
            }

        if not os.path.isdir(resolved):
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Failed to create directory at: {resolved}",
                    }
                ],
                "details": {
                    "path": resolved,
                    "created": False,
                },
            }

        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Directory created successfully: {resolved}",
                }
            ],
            "details": {
                "path": resolved,
                "created": True,
            },
        }

    return {
        "name": "mkdir",
        "description": (
            "Create a directory or folder on the host PC (e.g. 'E:\\my_folder' or 'C:\\Users\\...\\Downloads\\new_dir'). "
            "Creates all parent directories automatically if they do not exist. "
            "Verified on disk upon creation."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {
                    "type": "STRING",
                    "description": "Path of the directory/folder to create (absolute or relative to current workspace).",
                },
            },
            "required": ["path"],
        },
        "execute": _execute,
    }


def create_mkdir_tool(
    cwd: str = "",
    options: Optional[dict] = None,
) -> ToolDefinition:
    """Convenience alias matching create_write_tool / create_ls_tool naming."""
    return create_mkdir_tool_definition(cwd=cwd, options=options)


__all__ = [
    "create_mkdir_tool",
    "create_mkdir_tool_definition",
]
