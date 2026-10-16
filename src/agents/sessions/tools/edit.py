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

import json
import os
from pathlib import Path
from typing import Any, Optional, Protocol, runtime_checkable

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
# EditOperations protocol — mirrors OpenClaw EditOperations interface
# ============================================================================


@runtime_checkable
class EditOperations(Protocol):
    """Pluggable filesystem operations for the edit tool.

    Override to delegate file editing to remote systems (e.g. SSH).
    """

    async def read_file(self, absolute_path: str) -> bytes: ...
    async def write_file(self, absolute_path: str, content: str) -> None: ...
    async def access(self, absolute_path: str) -> None: ...


class _LocalEditOperations:
    """Default local filesystem implementation of EditOperations."""

    async def read_file(self, absolute_path: str) -> bytes:
        return Path(absolute_path).read_bytes()

    async def write_file(self, absolute_path: str, content: str) -> None:
        Path(absolute_path).write_text(content, encoding="utf-8")

    async def access(self, absolute_path: str) -> None:
        if not os.access(absolute_path, os.R_OK | os.W_OK):
            raise PermissionError(f"File is not readable+writable: {absolute_path}")


default_edit_operations = _LocalEditOperations()


class EditToolOptions:
    """Options for create_edit_tool_definition."""

    def __init__(self, operations: Any = None) -> None:
        self.operations = operations or default_edit_operations


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
        resolve_to_cwd(file_path, cwd or os.getcwd()) if not os.path.isabs(file_path) else file_path
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
        Path(resolved).write_bytes(new_text.encode(encoding, errors="replace"))
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


def create_edit_tool_definition(
    cwd: str = "",
    options: Optional[dict] = None,
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
        params = prepare_edit_arguments(params)
        path = params.get("path", "")
        edits = params.get("edits", [])
        if not path:
            raise ValueError("path is required")
        if not edits:
            raise ValueError("edits must be a non-empty list")

        # Resolve path against cwd
        resolved = resolve_to_cwd(path, cwd or os.getcwd()) if not os.path.isabs(path) else path

        # Apply sandbox and tool policy security floor
        from ...sandbox import guard_sandbox_tool_access

        _, validated = guard_sandbox_tool_access(
            "edit", resolved, cwd, options, ctx, is_mutation=True
        )
        if validated is not None:
            resolved = str(validated)

        result = await edit_file(resolved, edits, cwd=cwd)
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


# ============================================================================
# Constants (mirrors openclaw edit.ts)
# ============================================================================

#: Maximum number of surrounding-context lines to include in the mismatch hint
#: shown to the model when an oldContent block does not match the file.
EDIT_MISMATCH_HINT_LIMIT: int = 5

#: Error message prefix emitted to the model when oldContent does not match.
EDIT_MISMATCH_MESSAGE: str = (
    "The content to replace was not found in the file. "
    "Ensure oldContent exactly matches a contiguous block of lines in the file."
)


# ============================================================================
# edit_file_returning_diff — convenience wrapper
# ============================================================================


async def edit_file_returning_diff(
    file_path: str,
    edits: list[Edit],
    cwd: Optional[str] = None,
) -> tuple[EditResult, str | None, int | None]:
    """Apply edits and return (result, unified_diff, first_changed_line).

    Mirrors OpenClaw's ``editFileReturningDiff``:
    - If no content changed: returns (result, None, None).
    - If content changed: returns (result, diff_text, first_changed_line).
    """
    result = await edit_file(file_path, edits, cwd=cwd)
    if not result.get("changed"):
        return result, None, None
    return result, result.get("patch") or result.get("diff"), result.get("firstChangedLine")


# ============================================================================
# Helper functions — mirrors OpenClaw edit.ts helpers
# ============================================================================


def prepare_edit_arguments(input_raw: Any) -> dict[str, Any]:
    """Normalise raw tool input to {path, edits}.

    Some models send ``edits`` as a JSON string; others use the legacy
    ``oldText``/``newText`` top-level fields. This function tolerates both.
    """
    if not input_raw or not isinstance(input_raw, dict):
        return input_raw  # type: ignore[return-value]

    args: dict[str, Any] = dict(input_raw)

    # Some models send edits as a JSON string instead of an array.
    if isinstance(args.get("edits"), str):
        try:
            parsed = json.loads(args["edits"])
            if isinstance(parsed, list):
                args["edits"] = parsed
        except Exception:
            pass

    # Legacy single-edit top-level fields (supports camelCase and snake_case).
    old_text = args.get("oldText") or args.get("old_text")
    new_text = args.get("newText") or args.get("new_text")
    if isinstance(old_text, str) and isinstance(new_text, str):
        existing = args.get("edits") or []
        if not isinstance(existing, list):
            existing = []
        args["edits"] = [*existing, {"oldText": old_text, "newText": new_text}]

    # Keep only canonical fields; strip extra metadata.
    edits = args.get("edits")
    if isinstance(edits, list):
        args["edits"] = [
            {"oldText": e.get("oldText", ""), "newText": e.get("newText", "")}
            for e in edits
            if isinstance(e, dict)
        ]

    return {"path": args.get("path"), "edits": args.get("edits")}


def validate_edit_input(input_data: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    """Validate edit tool input. Returns (path, edits) or raises ValueError."""
    edits = input_data.get("edits")
    if not isinstance(edits, list) or len(edits) == 0:
        raise ValueError("Edit tool input is invalid. edits must contain at least one replacement.")
    path = input_data.get("path") or ""
    return path, edits


def remove_exact_occurrences(content: str, needle: str) -> str:
    """Remove all exact occurrences of needle from content."""
    if not needle:
        return content
    return content.replace(needle, "")


def did_edit_likely_apply(
    original_content: str,
    current_content: str,
    edits: list[dict[str, str]],
) -> bool:
    """Heuristic: did the edits likely get applied to current_content?"""
    if not edits:
        return False
    if original_content == current_content:
        return False

    without_inserted = current_content
    for edit in edits:
        new_text = edit.get("newText", "")
        if new_text and new_text not in current_content:
            return False
        without_inserted = remove_exact_occurrences(without_inserted, new_text)

    return all(edit.get("oldText", "") not in without_inserted for edit in edits)


def append_mismatch_hint(error: Exception, current_content: str) -> Exception:
    """Append a snippet of current file content to a mismatch error."""
    snippet = (
        current_content
        if len(current_content) <= EDIT_MISMATCH_HINT_LIMIT
        else current_content[:EDIT_MISMATCH_HINT_LIMIT] + "…"
    )
    new_msg = f"{error}\n\nFile content (snippet):\n{snippet}"
    return type(error)(new_msg)


__all__ = [
    "EDIT_MISMATCH_HINT_LIMIT",
    "EDIT_MISMATCH_MESSAGE",
    "Edit",
    "EditOperations",
    "EditResult",
    "EditToolOptions",
    "append_mismatch_hint",
    "create_edit_tool",
    "create_edit_tool_definition",
    "default_edit_operations",
    "did_edit_likely_apply",
    "edit_file",
    "edit_file_returning_diff",
    "prepare_edit_arguments",
    "remove_exact_occurrences",
    "validate_edit_input",
]
