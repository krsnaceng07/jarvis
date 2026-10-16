r"""jarvis.agents.sessions.tools.rename_path_tool — Built-in rename_path tool.

Provides explicit file and directory renaming/moving capability on host drives (e.g. E:\\, C:\\)
and sandbox workspaces, giving JARVIS 1:1 behavioral parity with desktop host control.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from ..extensions.types import AgentToolResult, ToolDefinition
from .path_utils import is_drive_available, resolve_unicode_path


def create_rename_path_tool_definition(
    cwd: str = "",
    options: Optional[dict] = None,
) -> ToolDefinition:
    """Build the :class:`ToolDefinition` for the rename_path tool."""

    async def _execute(
        tool_call_id: str,
        params: dict,
        signal: object = None,
        on_update: object = None,
        ctx: object = None,
    ) -> AgentToolResult:
        if signal is not None and getattr(signal, "is_set", lambda: False)():
            raise RuntimeError("Operation aborted")

        old_path = params.get("old_path", "")
        new_path = params.get("new_path", "")
        if not old_path:
            raise ValueError("old_path is required")
        if not new_path:
            raise ValueError("new_path is required")

        # 1. Resolve old_path against cwd with Unicode & home normalization
        old_resolved = resolve_unicode_path(old_path, cwd or os.getcwd())

        # 2. Resolve new_path:
        # If new_path is a simple filename/foldername without directory separators,
        # resolve relative to old_resolved's parent directory.
        if not os.path.isabs(new_path) and not any(sep in new_path for sep in ("/", "\\")):
            parent_dir = os.path.dirname(old_resolved)
            new_resolved = os.path.normpath(os.path.join(parent_dir, new_path))
        else:
            new_resolved = resolve_unicode_path(new_path, cwd or os.getcwd())

        # 3. Check drive availability on Windows for both paths
        for p in (old_resolved, new_resolved):
            if not is_drive_available(p):
                raise FileNotFoundError(
                    f"Drive not available on this host: {p}. "
                    "Please verify available drives with ls(path='drives')."
                )

        # 4. Apply sandbox and tool policy security floor if applicable
        from ...sandbox import guard_sandbox_tool_access

        _, old_val = guard_sandbox_tool_access(
            "rename_path", old_resolved, cwd, options, ctx, is_mutation=True
        )
        if old_val is not None:
            old_resolved = str(old_val)

        _, new_val = guard_sandbox_tool_access(
            "rename_path", new_resolved, cwd, options, ctx, is_mutation=True
        )
        if new_val is not None:
            new_resolved = str(new_val)

        old_target = Path(old_resolved)
        new_target = Path(new_resolved)

        if not old_target.exists() and not old_target.is_symlink():
            raise FileNotFoundError(f"Source path does not exist: {old_resolved}")

        if new_target.exists():
            raise FileExistsError(f"Destination path already exists: {new_resolved}")

        # Ensure destination parent directory exists
        dest_parent = os.path.dirname(new_resolved)
        try:
            if dest_parent and not os.path.exists(dest_parent):
                os.makedirs(dest_parent, exist_ok=True)

            # 5. Rename / move
            os.rename(old_resolved, new_resolved)
        except PermissionError as exc:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Permission denied renaming '{old_resolved}' to '{new_resolved}': {exc}",
                    }
                ],
                "details": {
                    "old_path": old_resolved,
                    "new_path": new_resolved,
                    "renamed": False,
                    "error": str(exc),
                },
            }
        except OSError as exc:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Failed to rename '{old_resolved}' to '{new_resolved}': {exc}",
                    }
                ],
                "details": {
                    "old_path": old_resolved,
                    "new_path": new_resolved,
                    "renamed": False,
                    "error": str(exc),
                },
            }

        # 6. Verify on OS
        if os.path.exists(old_resolved) or not os.path.exists(new_resolved):
            raise OSError(f"Failed to rename '{old_resolved}' to '{new_resolved}'")

        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Successfully renamed '{old_resolved}' to '{new_resolved}'",
                }
            ],
            "details": {
                "old_path": old_resolved,
                "new_path": new_resolved,
                "renamed": True,
            },
        }

    return {
        "name": "rename_path",
        "description": (
            "Rename or move a file or directory/folder on the host PC (e.g. rename 'E:\\old_folder' to 'E:\\new_folder'). "
            "Verified on disk upon renaming."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "old_path": {
                    "type": "STRING",
                    "description": "Current path of the file or directory/folder to rename.",
                },
                "new_path": {
                    "type": "STRING",
                    "description": "New path or new name for the file or directory/folder.",
                },
            },
            "required": ["old_path", "new_path"],
        },
        "execute": _execute,
    }


def create_rename_path_tool(
    cwd: str = "",
    options: Optional[dict] = None,
) -> ToolDefinition:
    """Convenience alias matching create_write_tool / create_mkdir_tool naming."""
    return create_rename_path_tool_definition(cwd=cwd, options=options)


__all__ = [
    "create_rename_path_tool",
    "create_rename_path_tool_definition",
]
