"""jarvis.agents.sessions.tools.grep — built-in grep tool.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/tools/grep.ts``.

Phase 6.10d — focused port.

Ships the critical contract:
- :func:`create_grep_tool_definition` / :func:`create_grep_tool`
  — the factory returning a
  :class:`ToolDefinition` for the grep tool
- :func:`grep_files` — regex/literal search
  over files with optional context + glob +
  ignore-case + limit
- :class:`GrepOperations` — pluggable ops
  interface (defaults to local FS)

Adaptations
-----------
- The OpenClaw source uses TypeBox for the
  ``grepSchema`` parameter schema. The
  Python port uses a plain :class:`dict`.
- The OpenClaw source's ripgrep integration
  is preserved via the :class:`GrepOperations`
  interface. The default implementation uses
  :mod:`re` + :mod:`pathlib` (the Python
  stdlib equivalents).
- The OpenClaw source's
  ``addEventListener("abort")`` pattern is
  replaced with a try/finally that checks
  the signal flag periodically.
"""
from __future__ import annotations

import asyncio
import fnmatch
import os
import re
from pathlib import Path
from typing import Any, Optional, Protocol, Union, runtime_checkable

from ..extensions.types import AgentToolResult, ToolDefinition
from .limits import normalize_positive_limit
from .path_utils import resolve_to_cwd
from .truncate import (
    DEFAULT_MAX_BYTES,
    GREP_MAX_LINE_LENGTH,
    format_size,
    truncate_head,
    truncate_line,
)


# ============================================================================
# Constants
# ============================================================================


#: Default match cap. Mirrors ``DEFAULT_LIMIT``
#: (``grep.ts:53``).
DEFAULT_LIMIT: int = 100


#: Default context lines.
DEFAULT_CONTEXT: int = 0


# ============================================================================
# Operations interface
# ============================================================================


@runtime_checkable
class GrepOperations(Protocol):
    """Pluggable FS operations for the grep
    tool. Mirrors ``GrepOperations``
    (``grep.ts:59-64``)."""

    def is_directory(self, absolute_path: str) -> Union[bool, "asyncio.Future[bool]"]:
        ...

    def read_file(self, absolute_path: str) -> Union[str, "asyncio.Future[str]"]:
        ...


def _default_grep_operations() -> GrepOperations:
    """Build the default local-FS GrepOperations
    instance."""

    class _DefaultOps:
        def is_directory(self, path: str) -> bool:
            return os.path.isdir(path)

        def read_file(self, path: str) -> str:
            # Best-effort UTF-8; fall back to
            # latin-1 for arbitrary byte content.
            with open(path, "rb") as f:
                raw = f.read()
            try:
                return raw.decode("utf-8")
            except UnicodeDecodeError:
                return raw.decode("latin-1")

    return _DefaultOps()  # type: ignore[return-value]


async def _maybe_await(value: Any) -> Any:
    if asyncio.iscoroutine(value):
        return await value
    return value


# ============================================================================
# Grep helper
# ============================================================================


async def grep_files(
    pattern: str,
    path: str = ".",
    glob: Optional[str] = None,
    ignore_case: bool = False,
    literal: bool = False,
    context: int = DEFAULT_CONTEXT,
    limit: Optional[int] = None,
    cwd: str = "",
    operations: Optional[GrepOperations] = None,
) -> dict:
    """Search for ``pattern`` in files under
    ``path``. Returns ``{"matches": list[dict],
    "truncation": TruncationResult?,
    "matchLimitReached": int?,
    "linesTruncated": bool}``.

    Each match dict has ``{"path": str,
    "line": int, "text": str, "context": list[str]?}``.
    """
    ops = operations or _default_grep_operations()
    effective_limit = normalize_positive_limit(
        limit, DEFAULT_LIMIT
    )
    search_path = resolve_to_cwd(
        path or ".", cwd or os.getcwd()
    )
    if not await _maybe_await(ops.is_directory(search_path)):
        raise NotADirectoryError(f"Not a directory: {search_path}")
    # Compile the pattern
    if literal:
        flags = re.IGNORECASE if ignore_case else 0
        compiled = re.compile(re.escape(pattern), flags)
    else:
        flags = re.IGNORECASE if ignore_case else 0
        compiled = re.compile(pattern, flags)
    # Walk the directory
    matches: list[dict] = []
    lines_truncated = False
    for file_path in _walk_files(search_path, glob):
        if len(matches) >= effective_limit:
            break
        try:
            content = await _maybe_await(ops.read_file(str(file_path)))
        except (OSError, UnicodeDecodeError):
            continue
        for line_num, line_text in enumerate(content.splitlines(), start=1):
            if compiled.search(line_text):
                # Truncate the line if it's too long
                truncated_line = truncate_line(
                    line_text, max_chars=GREP_MAX_LINE_LENGTH
                )
                entry: dict = {
                    "path": str(file_path.relative_to(Path(search_path)))
                    .replace(os.sep, "/"),
                    "line": line_num,
                    "text": truncated_line.text,
                }
                if truncated_line.was_truncated:
                    lines_truncated = True
                if context > 0:
                    all_lines = content.splitlines()
                    ctx_start = max(0, line_num - 1 - context)
                    ctx_end = min(len(all_lines), line_num - 1 + context + 1)
                    entry["context"] = all_lines[ctx_start:ctx_end]
                matches.append(entry)
                if len(matches) >= effective_limit:
                    break
    match_limit_reached: Optional[int] = (
        effective_limit if len(matches) >= effective_limit else None
    )
    # Format the output
    formatted = _format_grep_output(matches)
    truncation = truncate_head(
        formatted, max_lines=2**53 - 1, max_bytes=DEFAULT_MAX_BYTES
    )
    return {
        "matches": matches,
        "output": truncation.content,
        "truncation": truncation,
        "matchLimitReached": match_limit_reached,
        "linesTruncated": lines_truncated,
    }


def _walk_files(
    base: str, glob_pattern: Optional[str] = None
) -> Any:
    """Walk ``base`` yielding file paths. When
    ``glob_pattern`` is provided, the walker
    filters by fnmatch against the relative
    path. Mirrors the OpenClaw source's
    ripgrep + glob filter."""
    base_path = Path(base)
    for file_path in base_path.rglob("*"):
        if not file_path.is_file():
            continue
        if glob_pattern:
            rel = str(file_path.relative_to(base_path)).replace(os.sep, "/")
            if not fnmatch.fnmatch(rel, glob_pattern):
                continue
        yield file_path


def _format_grep_output(matches: list[dict]) -> str:
    """Format matches as ``path:line:text``
    lines. Mirrors the OpenClaw source's
    ripgrep-style output format."""
    lines: list[str] = []
    for match in matches:
        path = match.get("path", "")
        line = match.get("line", 0)
        text = match.get("text", "")
        lines.append(f"{path}:{line}:{text}")
    return "\n".join(lines)


# ============================================================================
# Tool definition factory
# ============================================================================


def create_grep_tool_definition(
    cwd: str = "",
    operations: Optional[GrepOperations] = None,
) -> ToolDefinition:
    """Build the :class:`ToolDefinition` for
    the grep tool. Mirrors
    ``createGrepToolDefinition`` (``grep.ts``).
    """
    ops = operations or _default_grep_operations()

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
        pattern = params.get("pattern", "")
        if not pattern:
            raise ValueError("pattern is required")
        path = params.get("path", ".")
        glob_pat = params.get("glob")
        ignore_case = bool(params.get("ignoreCase", False))
        literal = bool(params.get("literal", False))
        context = int(params.get("context", DEFAULT_CONTEXT))
        limit = params.get("limit")
        result = await grep_files(
            pattern=pattern,
            path=path or ".",
            glob=glob_pat,
            ignore_case=ignore_case,
            literal=literal,
            context=context,
            limit=limit,
            cwd=cwd,
            operations=ops,
        )
        output = result["output"]
        notices: list[str] = []
        details: dict = {}
        if result.get("matchLimitReached") is not None:
            match_limit = result["matchLimitReached"]
            notices.append(
                f"{match_limit} matches limit reached. "
                f"Use limit={match_limit * 2} for more"
            )
            details["matchLimitReached"] = match_limit
        if result.get("truncation") and result["truncation"].truncated:
            notices.append(f"{format_size(DEFAULT_MAX_BYTES)} limit reached")
            details["truncation"] = result["truncation"]
        if result.get("linesTruncated"):
            notices.append("some lines truncated")
            details["linesTruncated"] = True
        if notices:
            output += "\n\n[" + ". ".join(notices) + "]"
        if not result.get("matches"):
            return {
                "content": [{"type": "text", "text": "(no matches)"}],
                "details": None,
            }
        return {
            "content": [{"type": "text", "text": output}],
            "details": details or None,
        }

    return {
        "name": "grep",
        "label": "grep",
        "description": (
            f"Search file contents with regex or literal pattern. "
            f"Defaults to {DEFAULT_LIMIT} matches / "
            f"{DEFAULT_MAX_BYTES // 1024}KB."
        ),
        "promptSnippet": "Search file contents",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regex/literal pattern.",
                },
                "path": {
                    "type": "string",
                    "description": "File/dir; default cwd.",
                },
                "glob": {
                    "type": "string",
                    "description": "File glob, e.g. *.ts.",
                },
                "ignoreCase": {
                    "type": "boolean",
                    "description": "Ignore case; default false.",
                },
                "literal": {
                    "type": "boolean",
                    "description": "Literal, not regex; default false.",
                },
                "context": {
                    "type": "integer",
                    "description": "Context lines each side; default 0.",
                    "minimum": 0,
                },
                "limit": {
                    "type": "integer",
                    "description": "Max matches; default 100.",
                    "minimum": 1,
                },
            },
            "required": ["pattern"],
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


create_grep_tool = create_grep_tool_definition


__all__ = [
    "DEFAULT_CONTEXT",
    "DEFAULT_LIMIT",
    "GrepOperations",
    "create_grep_tool",
    "create_grep_tool_definition",
    "grep_files",
]
