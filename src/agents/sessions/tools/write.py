"""jarvis.agents.sessions.tools.write — write tool.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/tools/write.ts``.

Phase 6.10c — write tool focused port.

Ships the critical contract:
- :func:`create_write_tool` / :func:`create_write_tool_definition`
  — the factory returning a
  :class:`ToolDefinition` for the write tool
- :func:`write_file` — write content to a
  file (creates parent dirs + uses the
  per-file mutation queue)

Adaptations
-----------
- The OpenClaw source uses TypeBox for the
  ``writeSchema`` parameter schema. The
  Python port uses a plain ``dict``.
- The OpenClaw source's
  ``createPrivateTempWriteStream`` /
  ``withFileMutationQueue`` paths are
  preserved via the local ``private_temp_file``
  + ``file_mutation_queue`` modules.
- The OpenClaw source's
  ``detectLineEnding`` /
  ``restoreLineEndings`` are preserved via
  the ``edit_diff`` module.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from ..extensions.types import AgentToolResult, ToolDefinition
from .edit_diff import detect_line_ending, restore_line_endings
from .file_mutation_queue import with_file_mutation_queue
from .path_utils import resolve_to_cwd


# ============================================================================
# Write helper
# ============================================================================


async def write_file(
    file_path: str,
    content: str,
    cwd: Optional[str] = None,
    line_ending: Optional[str] = None,
) -> None:
    """Write ``content`` to ``file_path``,
    creating parent directories as needed.
    Uses the per-file mutation queue for
    serialisation. Mirrors the write path
    of the OpenClaw source's ``write.ts``
    execute function.

    Parameters
    ----------
    file_path : str
        Target file path (resolved against
        ``cwd`` if relative).
    content : str
        The file content.
    cwd : str, optional
        Working directory.
    line_ending : str, optional
        ``"\\r\\n"`` or ``"\\n"``. When ``None``,
        auto-detects from the existing file
        (or defaults to ``"\\n"`` for a new
        file).
    """
    resolved = (
        resolve_to_cwd(file_path, cwd or os.getcwd())
        if not os.path.isabs(file_path)
        else file_path
    )

    async def _do_write() -> None:
        parent = os.path.dirname(resolved)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)
        # Determine the line ending (existing
        # file → preserve; new file → default).
        if line_ending is not None:
            ending = line_ending
        elif os.path.exists(resolved):
            with open(resolved, "r", encoding="utf-8", newline="") as f:
                existing = f.read()
            ending = detect_line_ending(existing)
        else:
            ending = "\n"
        # Restore the line ending
        final = restore_line_endings(content, ending)
        # Atomic write: write to a temp file
        # then rename. The OpenClaw source's
        # ``createPrivateTempWriteStream``
        # path is the equivalent — we use
        # :func:`tempfile.NamedTemporaryFile`
        # in the same dir for atomicity.
        import tempfile
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=parent or ".",
            prefix=os.path.basename(resolved) + ".",
            suffix=".tmp",
            delete=False,
            newline="",
        ) as tmp:
            tmp_path = tmp.name
            tmp.write(final)
        # Rename (atomic on POSIX, mostly
        # atomic on Windows when the target
        # doesn't exist).
        try:
            os.replace(tmp_path, resolved)
        except OSError:
            # Fallback: copy + remove
            with open(tmp_path, "w", encoding="utf-8", newline="") as src, \
                 open(resolved, "w", encoding="utf-8", newline="") as dst:
                dst.write(src.read())
            os.unlink(tmp_path)

    await with_file_mutation_queue(resolved, _do_write)


# ============================================================================
# Write tool factory
# ============================================================================


async def create_write_tool_definition(
    cwd: str = "",
) -> ToolDefinition:
    """Build the :class:`ToolDefinition` for
    the write tool. Mirrors
    ``createWriteToolDefinition`` (``write.ts:382``).
    """
    async def _execute(
        tool_call_id: str,
        params: dict,
        signal: object = None,
        on_update: object = None,
        ctx: object = None,
    ) -> AgentToolResult:
        path = params.get("path", "")
        content = params.get("content", "")
        if not path:
            raise ValueError("path is required")
        await write_file(path, content, cwd=cwd)
        return {
            "content": [
                {"type": "text", "text": f"Wrote {len(content)} bytes to {path}"}
            ],
            "details": {},
        }

    return {
        "name": "write",
        "label": "write",
        "description": (
            "Write content to a file. Creates parent directories. "
            "Overwrites existing content."
        ),
        "promptSnippet": "Write file content",
        "promptGuidelines": [
            "Use write to create new files or fully replace existing content.",
        ],
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to write"},
                "content": {"type": "string", "description": "File content"},
            },
            "required": ["path", "content"],
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


create_write_tool = create_write_tool_definition


__all__ = [
    "create_write_tool",
    "create_write_tool_definition",
    "write_file",
]
