"""jarvis.agents.sessions.tools.edit — edit tool.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/tools/edit.ts``.

Phase 6.10c — edit tool focused port.

Ships the critical contract:
- :func:`create_edit_tool` / :func:`create_edit_tool_definition`
  — the factory returning a
  :class:`ToolDefinition` for the edit tool
- :func:`edit_file` — apply a list of
  ``Edit`` operations to a file
- :func:`edit_file_returning_diff` —
  apply edits + return the unified diff
  + the first-changed-line number
- :class:`EditResult` — the edit return
  shape (matches :class:`EditToolDetails`)

Adaptations
-----------
- The OpenClaw source uses TypeBox for the
  ``editSchema`` parameter schema. The
  Python port uses a plain ``dict``.
- The OpenClaw source's edit-application
  logic (the fuzzy match + line-preserving
  rewrite) is preserved via the local
  :mod:`edit_diff` module.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from ..extensions.types import AgentToolResult, ToolDefinition
from .edit_diff import (
    Edit,
    EditNoChangeError,
    apply_edits,
    create_unified_patch,
)
from .file_mutation_queue import with_file_mutation_queue
from .path_utils import resolve_to_cwd


# ============================================================================
# Edit result
# ============================================================================


#: Edit result. Mirrors ``EditToolDetails``
#: (tool-contracts.ts:28-40): either
#: ``{"changed": false}`` or
#: ``{"changed": true, "diff": str, "patch": str,
#: "firstChangedLine": int?}``.
EditResult = dict


# ============================================================================
# Edit file helpers
# ============================================================================


async def edit_file(
    file_path: str,
    edits: list[Edit],
    cwd: Optional[str] = None,
) -> EditResult:
    """Apply ``edits`` to ``file_path`` (overwriting
    the file). Returns the edit result.

    When no edits change the content, returns
    ``{"changed": False}``. Otherwise returns
    ``{"changed": True, "diff": str,
    "patch": str, "firstChangedLine": int?}``.

    Mirrors the OpenClaw source's
    ``executeEdit`` path (``edit.ts``).
    """
    if not edits:
        raise ValueError("edits must be a non-empty list")
    resolved = (
        resolve_to_cwd(file_path, cwd or os.getcwd())
        if not os.path.isabs(file_path)
        else file_path
    )
    if not os.path.exists(resolved):
        raise FileNotFoundError(f"File not found: {resolved}")

    # Read existing content (binary → text;
    # preserves original line endings).
    original_bytes = Path(resolved).read_bytes()
    # Try UTF-8 first; fall back to latin-1
    # (latin-1 is the OpenClaw source's
    # fallback for arbitrary byte content).
    try:
        original_text = original_bytes.decode("utf-8")
        encoding = "utf-8"
    except UnicodeDecodeError:
        original_text = original_bytes.decode("latin-1")
        encoding = "latin-1"

    async def _do_edit() -> EditResult:
        try:
            new_text = apply_edits(original_text, edits)
        except EditNoChangeError:
            return {"changed": False}
        if new_text == original_text:
            return {"changed": False}
        # Write the new content (preserve
        # encoding).
        Path(resolved).write_bytes(
            new_text.encode(encoding, errors="replace")
        )
        # Build the unified patch
        patch = create_unified_patch(resolved, original_text, new_text)
        # Display-friendly diff (the OpenClaw
        # source uses a unified-diff for the
        # patch + a custom display diff).
        diff = patch
        # Find the first changed line.
        first_changed = _first_changed_line(original_text, new_text)
        return {
            "changed": True,
            "diff": diff,
            "patch": patch,
            "firstChangedLine": first_changed,
        }

    return await with_file_mutation_queue(resolved, _do_edit)


def _first_changed_line(old: str, new: str) -> Optional[int]:
    """Return the 1-based line number of the
    first changed line, or ``None`` if
    unchanged. Mirrors the OpenClaw source's
    ``firstChangedLine`` computation."""
    old_lines = old.splitlines()
    new_lines = new.splitlines()
    shared = min(len(old_lines), len(new_lines))
    for i in range(shared):
        if old_lines[i] != new_lines[i]:
            return i + 1
    # All shared lines match; the first
    # change is the line where lengths differ.
    if len(old_lines) != len(new_lines):
        return shared + 1
    return None


# ============================================================================
# Edit tool factory
# ============================================================================


async def create_edit_tool_definition(
    cwd: str = "",
) -> ToolDefinition:
    """Build the :class:`ToolDefinition` for
    the edit tool. Mirrors
    ``createEditToolDefinition`` (``edit.ts:392``).
    """
    async def _execute(
        tool_call_id: str,
        params: dict,
        signal: object = None,
        on_update: object = None,
        ctx: object = None,
    ) -> AgentToolResult:
        path = params.get("path", "")
        edits = params.get("edits", [])
        if not path:
            raise ValueError("path is required")
        if not edits:
            raise ValueError("edits must be a non-empty list")
        result = await edit_file(path, edits, cwd=cwd)
        if not result.get("changed"):
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "No changes (edits produced identical content).",
                    }
                ],
                "details": {"changed": False},
            }
        # Build the diff summary text
        diff_text = result.get("diff", "")
        first_line = result.get("firstChangedLine")
        summary = f"Applied {len(edits)} edit(s) to {path}."
        if first_line is not None:
            summary += f" First change at line {first_line}."
        return {
            "content": [{"type": "text", "text": summary + "\n" + diff_text}],
            "details": result,
        }

    return {
        "name": "edit",
        "label": "edit",
        "description": (
            "Apply a list of Edit operations (oldText/newText pairs) to a "
            "file. Tries exact match first, then falls back to fuzzy match "
            "(whitespace + Unicode quote tolerance)."
        ),
        "promptSnippet": "Edit file with oldText/newText pairs",
        "promptGuidelines": [
            "Use edit for targeted changes. Provide enough oldText context "
            "to disambiguate the match location.",
        ],
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to edit"},
                "edits": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "oldText": {"type": "string"},
                            "newText": {"type": "string"},
                        },
                        "required": ["oldText", "newText"],
                    },
                    "description": "List of oldText/newText pairs",
                },
            },
            "required": ["path", "edits"],
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


create_edit_tool = create_edit_tool_definition


__all__ = [
    "EditResult",
    "create_edit_tool",
    "create_edit_tool_definition",
    "edit_file",
]
