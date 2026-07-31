"""jarvis.agents.sessions.tools.find — built-in find tool.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/tools/find.ts``.

Phase 6.10d — focused port.

Ships the critical contract:
- :func:`create_find_tool_definition` / :func:`create_find_tool`
  — the factory returning a
  :class:`ToolDefinition` for the find tool
- :func:`find_files` — glob-based file search
  (uses :mod:`pathlib` for the local-FS path;
  the OpenClaw source's ``fd`` integration
  is preserved via the optional
  :class:`FindOperations` interface)
- :class:`FindOperations` — pluggable ops
  interface (defaults to local FS)

Adaptations
-----------
- The OpenClaw source uses TypeBox for the
  ``findSchema`` parameter schema. The
  Python port uses a plain :class:`dict`.
- The OpenClaw source's ``fd`` integration
  is preserved via the :class:`FindOperations`
  interface. The default implementation uses
  :func:`pathlib.Path.glob` + recursive
  walk (the OpenClaw source uses ``fd``;
  the Python port falls back to Python's
  :mod:`pathlib` which ships with the stdlib).
- ``**/*.ts`` glob patterns work out of
  the box (the OpenClaw source's ``fd``
  has the same semantics).
"""
from __future__ import annotations

import asyncio
import fnmatch
import os
from pathlib import Path
from typing import Any, Optional, Protocol, Union, runtime_checkable

from ..extensions.types import AgentToolResult, ToolDefinition
from .limits import normalize_positive_limit
from .path_utils import resolve_to_cwd
from .truncate import DEFAULT_MAX_BYTES, format_size, truncate_head


# ============================================================================
# Constants
# ============================================================================


#: Default result cap. Mirrors ``DEFAULT_LIMIT``
#: (``find.ts:50``).
DEFAULT_LIMIT: int = 1000


#: Common gitignore-style patterns to skip
#: when walking the filesystem (the OpenClaw
#: source's ``fd`` invocation auto-loads
#: ``.gitignore``; the Python port applies
#: a small built-in list for parity with
#: the most common cases).
DEFAULT_IGNORE_PATTERNS: list[str] = [
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "target",
    "dist",
    "build",
    ".next",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
]


# ============================================================================
# Operations interface
# ============================================================================


@runtime_checkable
class FindOperations(Protocol):
    """Pluggable FS operations for the find tool.
    Mirrors ``FindOperations``
    (``find.ts:56-65``)."""

    def exists(self, absolute_path: str) -> Union[bool, "asyncio.Future[bool]"]:
        ...

    def glob(
        self,
        pattern: str,
        cwd: str,
        options: dict,
    ) -> Union[list[str], "asyncio.Future[list[str] ]"]:
        ...


def _default_find_operations() -> FindOperations:
    """Build the default local-FS FindOperations
    instance. Uses :mod:`pathlib` for globbing
    + a simple :func:`fnmatch` filter for
    filename patterns.
    """

    class _DefaultOps:
        def exists(self, path: str) -> bool:
            return os.path.exists(path)

        def glob(self, pattern: str, cwd: str, options: dict) -> list[str]:
            return _default_glob(pattern, cwd, options)

    return _DefaultOps()  # type: ignore[return-value]


def _default_glob(pattern: str, cwd: str, options: dict) -> list[str]:
    """Default glob implementation. The
    OpenClaw source's ``fd`` invocation
    recurses by default + supports ``**``
    for explicit recursion. The Python port
    uses :mod:`pathlib`'s recursive glob
    (``**/*.py`` style) for the explicit
    case + a manual walk for the simple
    pattern (``*.py`` recurses by default,
    matching ``fd``'s behaviour).

    Returns paths relative to ``cwd`` (the
    OpenClaw source's fd does the same).
    """
    ignore = set(options.get("ignore") or DEFAULT_IGNORE_PATTERNS)
    limit = options.get("limit", DEFAULT_LIMIT)
    cwd_path = Path(cwd)
    if not cwd_path.is_dir():
        return []
    matches: list[str] = []
    # Detect ``**`` (explicit recursive)
    is_recursive = "**" in pattern
    # For non-recursive patterns (``*.py``),
    # the OpenClaw source's ``fd`` recurses
    # by default. Match that.
    if is_recursive:
        iterator = cwd_path.glob(pattern)
    else:
        # Use rglob to recurse (the OpenClaw
        # source's default).
        iterator = cwd_path.rglob(pattern)
    for match in iterator:
        if not match.is_file():
            continue
        # Skip ignored directories + files
        try:
            rel = match.relative_to(cwd_path)
        except ValueError:
            # match is not under cwd_path
            continue
        parts = rel.parts
        if any(p in ignore for p in parts):
            continue
        # Apply a fnmatch filter as a safety net
        # (pathlib's glob is path-style; the
        # ``fd``-style glob is more permissive).
        if not _matches_glob(str(rel), pattern):
            continue
        matches.append(str(rel).replace(os.sep, "/"))
        if len(matches) >= limit:
            break
    return matches


def _matches_glob(path: str, pattern: str) -> bool:
    """Check whether ``path`` matches the
    ``pattern`` (translated from ``fd``-style
    to :mod:`fnmatch` semantics). The pattern
    is the last segment of the user's glob."""
    # Strip ``**/`` prefix recursively
    name = path.rsplit("/", 1)[-1]
    if "**" in pattern:
        return True
    # Translate the pattern to fnmatch
    # (replace ``*`` with the fnmatch ``*``).
    return fnmatch.fnmatch(name, pattern)


async def _maybe_await(value: Any) -> Any:
    if asyncio.iscoroutine(value):
        return await value
    return value


# ============================================================================
# Find helper
# ============================================================================


async def find_files(
    pattern: str,
    cwd: str = "",
    limit: Optional[int] = None,
    operations: Optional[FindOperations] = None,
) -> dict:
    """Find files matching ``pattern`` under
    ``cwd``. Returns ``{"paths": list[str],
    "truncation": TruncationResult?,
    "resultLimitReached": int?}``.
    """
    ops = operations or _default_find_operations()
    effective_limit = normalize_positive_limit(
        limit, DEFAULT_LIMIT
    )
    search_path = resolve_to_cwd(cwd or ".", os.getcwd())
    if not await _maybe_await(ops.exists(search_path)):
        raise FileNotFoundError(f"Path not found: {search_path}")
    raw_results = await _maybe_await(
        ops.glob(
            pattern,
            search_path,
            {
                "ignore": DEFAULT_IGNORE_PATTERNS,
                "limit": effective_limit,
            },
        )
    )
    # Apply limit (the glob may have returned
    # more than the limit; the limit is
    # also reported when we hit it).
    if len(raw_results) >= effective_limit:
        result_limit_reached: Optional[int] = effective_limit
    else:
        result_limit_reached = None
    if len(raw_results) > effective_limit:
        raw_results = raw_results[:effective_limit]
    # Build the output + truncation
    raw_output = "\n".join(raw_results)
    truncation = truncate_head(
        raw_output, max_lines=2**53 - 1, max_bytes=DEFAULT_MAX_BYTES
    )
    return {
        "paths": raw_results,
        "output": truncation.content,
        "truncation": truncation,
        "resultLimitReached": result_limit_reached,
    }


# ============================================================================
# Tool definition factory
# ============================================================================


async def create_find_tool_definition(
    cwd: str = "",
    operations: Optional[FindOperations] = None,
) -> ToolDefinition:
    """Build the :class:`ToolDefinition` for
    the find tool. Mirrors
    ``createFindToolDefinition`` (``find.ts:149``).
    """
    ops = operations or _default_find_operations()

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
        # The user's ``path`` overrides the
        # tool's default cwd; if neither is
        # set, we use the tool's cwd.
        tool_path = params.get("path", ".")
        # The user's ``path`` (if relative)
        # is resolved against the tool's cwd
        # so the search starts in the right
        # place.
        search_cwd = tool_path if os.path.isabs(tool_path) else (
            os.path.join(cwd, tool_path) if cwd else tool_path
        )
        if not os.path.isabs(search_cwd):
            search_cwd = os.path.abspath(search_cwd)
        limit = params.get("limit")
        result = await find_files(
            pattern=pattern,
            cwd=search_cwd,
            limit=limit,
            operations=ops,
        )
        output = result["output"]
        notices: list[str] = []
        details: dict = {}
        if result.get("resultLimitReached") is not None:
            result_limit = result["resultLimitReached"]
            notices.append(
                f"{result_limit} results limit reached. "
                f"Use limit={result_limit * 2} for more"
            )
            details["resultLimitReached"] = result_limit
        if result.get("truncation") and result["truncation"].truncated:
            notices.append(f"{format_size(DEFAULT_MAX_BYTES)} limit reached")
            details["truncation"] = result["truncation"]
        if notices:
            output += "\n\n[" + ". ".join(notices) + "]"
        if not result.get("paths"):
            return {
                "content": [{"type": "text", "text": "(no matches)"}],
                "details": None,
            }
        return {
            "content": [{"type": "text", "text": output}],
            "details": details or None,
        }

    return {
        "name": "find",
        "label": "find",
        "description": (
            f"Find files by glob pattern. Defaults to {DEFAULT_LIMIT} results "
            f"/ {DEFAULT_MAX_BYTES // 1024}KB. Common ignores (.git, node_modules, "
            "__pycache__, .venv, etc.) are applied automatically."
        ),
        "promptSnippet": "Find files by glob",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "File glob, e.g. **/*.ts.",
                },
                "path": {
                    "type": "string",
                    "description": "Search dir; default cwd.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results; default 1000.",
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


create_find_tool = create_find_tool_definition


__all__ = [
    "DEFAULT_IGNORE_PATTERNS",
    "DEFAULT_LIMIT",
    "FindOperations",
    "create_find_tool",
    "create_find_tool_definition",
    "find_files",
]
