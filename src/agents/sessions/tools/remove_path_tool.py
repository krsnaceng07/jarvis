r"""jarvis.agents.sessions.tools.remove_path_tool — Built-in remove_path tool.

Provides explicit file and directory deletion capability on host drives (e.g. E:\\, C:\\)
and sandbox workspaces, giving JARVIS 1:1 behavioral parity with desktop host control.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import stat
from typing import Any, Optional

from ..extensions.types import AgentToolResult, ToolDefinition
from .path_utils import is_drive_available, resolve_unicode_path


def _handle_remove_readonly(func: Any, path: str, exc: Any) -> None:
    """Clear the read-only attribute and retry removal on Windows."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass


def create_remove_path_tool_definition(
    cwd: str = "",
    options: Optional[dict] = None,
) -> ToolDefinition:
    """Build the :class:`ToolDefinition` for the remove_path tool."""

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

        recursive = bool(params.get("recursive", True))

        # 1. Resolve path against cwd with Unicode & slash hygiene (handles Nepali / non-ASCII)
        resolved = resolve_unicode_path(path, cwd or os.getcwd())

        # Protected system directory guard (WindowsApps, System32, etc.)
        norm_lower = os.path.normcase(os.path.normpath(resolved))
        protected_patterns = [
            "windowsapps",
            "system32",
            "winsxs",
            "system volume information",
        ]
        if any(pat in norm_lower for pat in protected_patterns):
            raise PermissionError(
                f"Access denied: '{resolved}' is a protected Windows system directory and cannot be removed."
            )

        # 2. Check drive availability on Windows
        if not is_drive_available(resolved):
            raise FileNotFoundError(
                f"Drive not available on this host: {resolved}. "
                "Please verify available drives with ls(path='drives')."
            )

        # 3. Apply sandbox and tool policy security floor if applicable
        from ...sandbox import guard_sandbox_tool_access

        _, validated = guard_sandbox_tool_access(
            "remove_path", resolved, cwd, options, ctx, is_mutation=True
        )
        if validated is not None:
            resolved = str(validated)

        target = Path(resolved)
        if not target.exists() and not target.is_symlink():
            raise FileNotFoundError(f"Path does not exist on disk: {resolved}")

        # 4. Remove file, symlink, or directory
        try:
            if target.is_dir() and not target.is_symlink():
                if recursive:
                    try:
                        shutil.rmtree(resolved, onexc=_handle_remove_readonly)
                    except TypeError:
                        shutil.rmtree(resolved, onerror=_handle_remove_readonly)
                else:
                    os.rmdir(resolved)
            else:
                try:
                    os.remove(resolved)
                except PermissionError:
                    try:
                        os.chmod(resolved, stat.S_IWRITE)
                        os.remove(resolved)
                    except Exception:
                        raise
        except PermissionError as perm_err:
            if any(pat in norm_lower for pat in protected_patterns):
                msg = f"Access denied: '{resolved}' is a protected Windows system directory and cannot be removed."
            else:
                msg = f"Access denied removing '{resolved}': {perm_err}"
            return {
                "content": [{"type": "text", "text": msg}],
                "details": {"path": resolved, "removed": False, "error": str(perm_err)},
            }
        except OSError as os_err:
            return {
                "content": [{"type": "text", "text": f"Failed to remove '{resolved}': {os_err}"}],
                "details": {"path": resolved, "removed": False, "error": str(os_err)},
            }

        # 5. Verify removal on OS
        if os.path.exists(resolved) or target.is_symlink():
            return {
                "content": [{"type": "text", "text": f"Failed to remove path from disk: {resolved}"}],
                "details": {"path": resolved, "removed": False},
            }

        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Path removed successfully from disk: {resolved}",
                }
            ],
            "details": {
                "path": resolved,
                "removed": True,
            },
        }

    return {
        "name": "remove_path",
        "description": (
            "Remove or delete a file or directory/folder on the host PC (e.g. 'E:\\my_folder' or 'C:\\Users\\...\\file.txt'). "
            "If the path is a directory, recursive=true (default) deletes the directory and all of its contents. "
            "Verified on disk upon removal."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {
                    "type": "STRING",
                    "description": "Path of the file or directory/folder to remove (absolute or relative to current workspace).",
                },
                "recursive": {
                    "type": "BOOLEAN",
                    "description": "If true and path is a directory, remove recursively with all contents (default: true).",
                },
            },
            "required": ["path"],
        },
        "execute": _execute,
    }


def create_remove_path_tool(
    cwd: str = "",
    options: Optional[dict] = None,
) -> ToolDefinition:
    """Convenience alias matching create_write_tool / create_mkdir_tool naming."""
    return create_remove_path_tool_definition(cwd=cwd, options=options)


__all__ = [
    "create_remove_path_tool",
    "create_remove_path_tool_definition",
]
