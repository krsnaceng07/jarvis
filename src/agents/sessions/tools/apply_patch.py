"""jarvis.agents.sessions.tools.apply_patch -- built-in apply_patch tool.

OpenClaw parity: mirrors OpenClaw's applyPatch execution
(openclaw-main/src/agents/apply-patch.ts).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from .edit import edit_file
from .path_utils import resolve_to_cwd
from ..extensions.types import AgentToolResult, ToolDefinition


BEGIN_PATCH_MARKER = "*** Begin Patch"
END_PATCH_MARKER = "*** End Patch"
ADD_FILE_MARKER = "*** Add File: "
DELETE_FILE_MARKER = "*** Delete File: "
UPDATE_FILE_MARKER = "*** Update File: "
MOVE_TO_MARKER = "--- Move To: "
CHANGE_CONTEXT_MARKER = "@@ "
EMPTY_CHANGE_CONTEXT_MARKER = "@@"
EOF_MARKER = "\\ No newline at end of file"


def parse_patch_text(input_text: str) -> dict[str, Any]:
    """Parse a structured patch string into hunks."""
    trimmed = input_text.strip()
    if not trimmed:
        raise ValueError("Invalid patch: input is empty.")

    lines = trimmed.splitlines()
    validated = check_patch_boundaries_lenient(lines)
    hunks = []

    last_line_index = len(validated) - 1
    remaining = validated[1:last_line_index]
    line_number = 2

    while remaining:
        hunk, consumed = parse_one_hunk(remaining, line_number)
        hunks.append(hunk)
        line_number += consumed
        remaining = remaining[consumed:]

    return {"hunks": hunks, "patch": "\n".join(validated)}


def check_patch_boundaries_lenient(lines: list[str]) -> list[str]:
    strict_error = check_patch_boundaries_strict(lines)
    if not strict_error:
        return lines

    if len(lines) < 4:
        raise ValueError(strict_error)

    first = lines[0].strip()
    last = lines[-1].strip() if lines else ""

    if (first in ("<<EOF", "<<'EOF'", "<<\"EOF\"")) and last.endswith("EOF"):
        inner = lines[1:-1]
        inner_error = check_patch_boundaries_strict(inner)
        if not inner_error:
            return inner
        raise ValueError(inner_error)

    raise ValueError(strict_error)


def check_patch_boundaries_strict(lines: list[str]) -> Optional[str]:
    first_line = lines[0].strip() if lines else ""
    last_line = lines[-1].strip() if lines else ""

    if first_line == BEGIN_PATCH_MARKER and last_line == END_PATCH_MARKER:
        return None
    if first_line != BEGIN_PATCH_MARKER:
        return "The first line of the patch must be '*** Begin Patch'"
    return "The last line of the patch must be '*** End Patch'"


def parse_one_hunk(lines: list[str], line_number: int) -> tuple[dict, int]:
    if not lines:
        raise ValueError(f"Invalid patch hunk at line {line_number}: empty hunk")

    first_line = lines[0].strip()
    
    if first_line.startswith(ADD_FILE_MARKER):
        target_path = first_line[len(ADD_FILE_MARKER):]
        contents = ""
        consumed = 1
        for add_line in lines[1:]:
            if add_line.startswith("+"):
                contents += add_line[1:] + "\n"
                consumed += 1
            else:
                break
        return {"kind": "add", "path": target_path, "contents": contents}, consumed

    if first_line.startswith(DELETE_FILE_MARKER):
        target_path = first_line[len(DELETE_FILE_MARKER):]
        return {"kind": "delete", "path": target_path}, 1

    if first_line.startswith(UPDATE_FILE_MARKER):
        target_path = first_line[len(UPDATE_FILE_MARKER):]
        remaining = lines[1:]
        consumed = 1
        move_path = None

        if remaining:
            move_candidate = remaining[0].strip()
            if move_candidate.startswith(MOVE_TO_MARKER):
                move_path = move_candidate[len(MOVE_TO_MARKER):]
                remaining = remaining[1:]
                consumed += 1

        chunks = []
        while remaining:
            first_remaining = remaining[0]
            if first_remaining.strip() == "":
                remaining = remaining[1:]
                consumed += 1
                continue
            if first_remaining.startswith("***"):
                break

            chunk, chunk_lines = parse_update_file_chunk(
                remaining, line_number + consumed, len(chunks) == 0
            )
            chunks.append(chunk)
            remaining = remaining[chunk_lines:]
            consumed += chunk_lines

        if not chunks:
            raise ValueError(f"Invalid patch hunk at line {line_number}: Update file hunk for path '{target_path}' is empty")

        return {"kind": "update", "path": target_path, "movePath": move_path, "chunks": chunks}, consumed

    raise ValueError(f"Invalid patch hunk at line {line_number}: '{lines[0]}' is not a valid hunk header. Valid hunk headers: '*** Add File: {{path}}', '*** Delete File: {{path}}', '*** Update File: {{path}}'")


def parse_update_file_chunk(lines: list[str], line_number: int, allow_missing_context: bool) -> tuple[dict, int]:
    if not lines:
        raise ValueError(f"Invalid patch hunk at line {line_number}: Update hunk does not contain any lines")

    change_context = None
    start_index = 0
    first_line = lines[0]
    
    if first_line == EMPTY_CHANGE_CONTEXT_MARKER:
        start_index = 1
    elif first_line.startswith(CHANGE_CONTEXT_MARKER):
        change_context = first_line[len(CHANGE_CONTEXT_MARKER):]
        start_index = 1
    elif not allow_missing_context:
        raise ValueError(f"Invalid patch hunk at line {line_number}: Expected update hunk to start with a @@ context marker, got: '{first_line}'")

    if start_index >= len(lines):
        raise ValueError(f"Invalid patch hunk at line {line_number + 1}: Update hunk does not contain any lines")

    chunk = {
        "changeContext": change_context,
        "oldLines": [],
        "newLines": [],
        "isEndOfFile": False,
    }

    parsed_lines = 0
    for line in lines[start_index:]:
        if line == EOF_MARKER:
            if parsed_lines == 0:
                raise ValueError(f"Invalid patch hunk at line {line_number + 1}: Update hunk does not contain any lines")
            chunk["isEndOfFile"] = True
            parsed_lines += 1
            break

        if not line:
            chunk["oldLines"].append("")
            chunk["newLines"].append("")
            parsed_lines += 1
            continue

        marker = line[0]
        if marker == " ":
            content = line[1:]
            chunk["oldLines"].append(content)
            chunk["newLines"].append(content)
            parsed_lines += 1
            continue
        if marker == "+":
            chunk["newLines"].append(line[1:])
            parsed_lines += 1
            continue
        if marker == "-":
            chunk["oldLines"].append(line[1:])
            parsed_lines += 1
            continue

        if parsed_lines == 0:
            raise ValueError(f"Invalid patch hunk at line {line_number + 1}: Unexpected line found in update hunk: '{line}'. Every line should start with ' ' (context line), '+' (added line), or '-' (removed line)")
        break

    return chunk, parsed_lines + start_index


async def apply_patch(
    input_text: str,
    cwd: Optional[str] = None,
    workspace_only: bool = True,
    options: Optional[dict] = None,
    ctx: object = None,
) -> dict[str, Any]:
    parsed = parse_patch_text(input_text)
    cwd = cwd or os.getcwd()

    summary = {
        "addedFiles": 0,
        "updatedFiles": 0,
        "deletedFiles": 0,
        "details": []
    }

    for hunk in parsed["hunks"]:
        kind = hunk["kind"]
        path = hunk["path"]
        resolved_path = resolve_to_cwd(path, cwd)

        # Apply sandbox security floor and path containment
        from ...sandbox import guard_sandbox_tool_access
        _, validated = guard_sandbox_tool_access("apply_patch", resolved_path, cwd, options, ctx, is_mutation=True)
        if validated is not None:
            resolved_path = str(validated)
        
        if workspace_only:
            # Check if resolved_path escapes cwd
            try:
                rel = os.path.relpath(resolved_path, cwd)
                if rel.startswith(".."):
                    raise ValueError(f"Path escapes workspace: {path}")
            except ValueError:
                raise ValueError(f"Path escapes workspace: {path}")

        try:
            if kind == "add":
                os.makedirs(os.path.dirname(resolved_path), exist_ok=True)
                if os.path.exists(resolved_path):
                    raise FileExistsError(f"Cannot add file, it already exists: {path}")
                Path(resolved_path).write_text(hunk["contents"], encoding="utf-8")
                summary["addedFiles"] += 1
                summary["details"].append(f"Added {path}")
                
            elif kind == "delete":
                if not os.path.exists(resolved_path):
                    raise FileNotFoundError(f"Cannot delete file, it does not exist: {path}")
                os.remove(resolved_path)
                summary["deletedFiles"] += 1
                summary["details"].append(f"Deleted {path}")
                
            elif kind == "update":
                if not os.path.exists(resolved_path):
                    raise FileNotFoundError(f"Cannot update file, it does not exist: {path}")
                
                edits = []
                for chunk in hunk["chunks"]:
                    edits.append({
                        "oldText": "\n".join(chunk["oldLines"]),
                        "newText": "\n".join(chunk["newLines"])
                    })
                
                # Apply using edit_file
                result = await edit_file(resolved_path, edits, cwd=cwd)
                if result.get("changed"):
                    summary["updatedFiles"] += 1
                    summary["details"].append(f"Updated {path}")
                else:
                    summary["details"].append(f"No changes applied to {path} (identical content)")

        except Exception as e:
            raise RuntimeError(f"Failed to {kind} {path}: {str(e)}") from e

    return summary


def create_apply_patch_tool_definition(
    cwd: str = "",
    workspace_only: bool = True,
    options: Optional[dict] = None,
) -> ToolDefinition:
    """Build the ToolDefinition for the apply_patch tool."""
    
    async def _execute(
        tool_call_id: str,
        params: dict,
        signal: object = None,
        on_update: object = None,
        ctx: object = None,
    ) -> AgentToolResult:
        input_text = params.get("input", "")
        if not input_text:
            raise ValueError("input is required")

        # Apply sandbox tool policy check before parsing
        from ...sandbox import guard_sandbox_tool_access
        guard_sandbox_tool_access("apply_patch", None, cwd, options, ctx, is_mutation=True)

        try:
            summary = await apply_patch(
                input_text,
                cwd=cwd,
                workspace_only=workspace_only,
                options=options,
                ctx=ctx,
            )
            
            summary_text = (
                f"Applied patch: {summary['addedFiles']} added, "
                f"{summary['updatedFiles']} updated, {summary['deletedFiles']} deleted."
            )
            if summary["details"]:
                summary_text += "\n" + "\n".join(f"- {d}" for d in summary["details"])

            return {
                "content": [{"type": "text", "text": summary_text}],
                "details": summary,
            }
        except Exception as e:
            raise RuntimeError(f"Failed to apply patch: {str(e)}") from e

    return {
        "name": "apply_patch",
        "label": "apply_patch",
        "description": "Apply file changes using a structured patch format. Ideal for multi-file or multi-hunk edits.",
        "promptSnippet": "Apply file changes with patch text",
        "promptGuidelines": [
            "Always wrap patches in '*** Begin Patch' and '*** End Patch'.",
            "Use '*** Add File: path' for new files.",
            "Use '*** Update File: path' for modifications.",
            "Use '*** Delete File: path' for removals."
        ],
        "parameters": {
            "type": "object",
            "properties": {
                "input": {
                    "type": "string",
                    "description": "Full patch contents including '*** Begin Patch' and '*** End Patch'."
                }
            },
            "required": ["input"],
        },
        "execute": _execute,
        "optional": False,
    }

create_apply_patch_tool = create_apply_patch_tool_definition
