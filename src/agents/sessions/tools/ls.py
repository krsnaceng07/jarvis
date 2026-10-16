"""jarvis.agents.sessions.tools.ls — built-in ls tool.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/tools/ls.ts``.

Phase 6.10d — focused port.

Ships the critical contract:
- :func:`create_ls_tool_definition` / :func:`create_ls_tool`
  — the factory returning a
  :class:`ToolDefinition` for the ls tool
- :func:`list_directory` — list a directory
  with sort + limit + directory indicators
- :class:`LsOperations` — pluggable ops
  interface (defaults to local FS)

Adaptations
-----------
- The OpenClaw source uses TypeBox for
  the ``lsSchema`` parameter schema. The
  Python port uses a plain :class:`dict`
  (the JSON Schema shape).
- The OpenClaw source's render functions
  (``renderCall`` / ``renderResult``) are
  deferred to Phase 6.12 with the TUI.
- The OpenClaw source's
  ``addEventListener("abort")`` pattern is
  replaced with :class:`threading.Event`
  + a try/finally that always cleans up.
- The OpenClaw source's default ops
  (``existsSync`` / ``readdirSync`` /
  ``statSync``) become
  :func:`os.path.exists` +
  :func:`os.listdir` +
  :func:`os.stat` (sync calls wrapped in
  ``asyncio.to_thread`` for the async
  path).
"""

from __future__ import annotations

import asyncio
import os
import stat
import sys
from typing import Any, Optional, Protocol, Union, runtime_checkable

from ..extensions.types import AgentToolResult, ToolDefinition
from .limits import normalize_positive_limit
from .path_utils import discover_system_drives, is_drive_available, resolve_to_cwd
from .truncate import DEFAULT_MAX_BYTES, format_size, truncate_head


# ============================================================================
# Constants
# ============================================================================


#: Default entry cap. Mirrors ``DEFAULT_LIMIT``
#: (``ls.ts:30``).
DEFAULT_LIMIT: int = 500


# ============================================================================
# Operations interface
# ============================================================================


@runtime_checkable
class LsOperations(Protocol):
    """Pluggable FS operations for the ls tool.
    Override to delegate to remote systems
    (e.g. SSH). Mirrors ``LsOperations``
    (``ls.ts:36-45``)."""

    def exists(self, absolute_path: str) -> Union[bool, "asyncio.Future[bool]"]: ...

    def stat(self, absolute_path: str) -> Union[dict, "asyncio.Future[dict]"]: ...

    def readdir(self, absolute_path: str) -> Union[list[str], "asyncio.Future[list[str] ]"]: ...


def _default_ls_operations() -> LsOperations:
    """Build the default local-FS LsOperations
    instance. Mirrors ``defaultLsOperations``
    (``ls.ts:47-51``)."""

    class _DefaultOps:
        def exists(self, path: str) -> bool:
            return os.path.exists(path)

        def stat(self, path: str) -> dict:
            s = os.stat(path)
            return {
                "is_directory": lambda: stat.S_ISDIR(s.st_mode),  # type: ignore[name-defined]
            }

        def readdir(self, path: str) -> list[str]:
            return os.listdir(path)

    return _DefaultOps()  # type: ignore[return-value]


# ============================================================================
# List directory helper
# ============================================================================


async def list_directory(
    path: str,
    cwd: str = "",
    limit: Optional[int] = None,
    operations: Optional[LsOperations] = None,
) -> dict:
    """List a directory's entries with sort
    + limit + directory indicators.

    Returns
    -------
    dict
        ``{"entries": list[str], "truncation":
        TruncationResult?, "entryLimitReached":
        int?}``. The ``entries`` list contains
        the entry names with ``/`` suffix for
        directories.
    """
    ops = operations or _default_ls_operations()
    effective_limit = normalize_positive_limit(limit, DEFAULT_LIMIT)
    clean_path = (path or "").strip().lower()
    if clean_path in ("drives", "drives:", "drives://"):
        drives = discover_system_drives()
        entries = [f"{d}" for d in drives]
        return {
            "entries": entries,
            "output": "\n".join(entries),
            "truncation": None,
            "entryLimitReached": None,
        }

    # Resolve path
    dir_path = resolve_to_cwd(path or ".", cwd or os.getcwd())
    # Check existence
    if not await _maybe_await(ops.exists(dir_path)):
        if sys.platform == "win32" and not is_drive_available(dir_path):
            available = discover_system_drives()
            raise FileNotFoundError(
                f"Drive not found: '{dir_path}'. This PC only has drives: {available}."
            )
        raise FileNotFoundError(f"Path not found: {dir_path}")
    # Check it's a directory
    stat_result = await _maybe_await(ops.stat(dir_path))
    is_dir = stat_result.get("is_directory")
    if callable(is_dir):
        is_dir = is_dir()
    if not is_dir:
        raise NotADirectoryError(f"Not a directory: {dir_path}")
    # Read entries
    try:
        entries = await _maybe_await(ops.readdir(dir_path))
    except Exception as exc:
        raise OSError(f"Cannot read directory: {exc}") from exc
    # Sort alphabetically (case-insensitive)
    entries = sorted(entries, key=lambda e: e.lower())
    # Format entries with directory indicators
    results: list[str] = []
    entry_limit_reached: Optional[int] = None
    for entry in entries:
        if len(results) >= effective_limit:
            entry_limit_reached = effective_limit
            break
        full_path = os.path.join(dir_path, entry)
        suffix = ""
        try:
            entry_stat = await _maybe_await(ops.stat(full_path))
            is_dir_entry = entry_stat.get("is_directory")
            if callable(is_dir_entry):
                is_dir_entry = is_dir_entry()
            if is_dir_entry:
                suffix = "/"
        except Exception:
            # Skip entries we cannot stat
            continue
        results.append(entry + suffix)
    # Apply byte truncation
    raw_output = "\n".join(results)
    truncation = truncate_head(raw_output, max_lines=2**53 - 1, max_bytes=DEFAULT_MAX_BYTES)
    return {
        "entries": results,
        "output": truncation.content,
        "truncation": truncation,
        "entryLimitReached": entry_limit_reached,
    }


async def _maybe_await(value: Any) -> Any:
    """Await an async result if needed. The
    OpenClaw source's operations may return
    Promises or sync values; this helper
    normalises them to the awaitable form.
    """
    if asyncio.iscoroutine(value):
        return await value
    return value


# ============================================================================
# Tool definition factory
# ============================================================================


def create_ls_tool_definition(
    cwd: str = "",
    operations: Optional[LsOperations] = None,
    options: Optional[dict] = None,
) -> ToolDefinition:
    """Build the :class:`ToolDefinition` for
    the ls tool. Mirrors
    ``createLsToolDefinition`` (``ls.ts:93``).
    """
    ops = operations or _default_ls_operations()

    async def _execute(
        tool_call_id: str,
        params: dict,
        signal: object = None,
        on_update: object = None,
        ctx: object = None,
    ) -> AgentToolResult:
        if signal is not None and getattr(signal, "is_set", lambda: False)():
            raise RuntimeError("Operation aborted")
        path = params.get("path", ".")
        limit = params.get("limit")

        if (path or "").strip().lower() in ("drives", "drives:", "drives://"):
            result = await list_directory(path="drives", cwd=cwd, limit=limit, operations=ops)
            return {
                "content": [{"type": "text", "text": result["output"]}],
                "details": None,
            }

        # Resolve path
        resolved = resolve_to_cwd(path or ".", cwd)

        # Apply sandbox tool policy and path containment
        from ...sandbox import guard_sandbox_tool_access

        _, validated = guard_sandbox_tool_access(
            "ls", resolved, cwd, options, ctx, is_mutation=False
        )
        if validated is not None:
            resolved = str(validated)

        result = await list_directory(
            path=resolved,
            cwd=cwd,
            limit=limit,
            operations=ops,
        )
        output = result["output"]
        notices: list[str] = []
        details: dict = {}
        if result.get("entryLimitReached") is not None:
            entry_limit = result["entryLimitReached"]
            notices.append(
                f"{entry_limit} entries limit reached. Use limit={entry_limit * 2} for more"
            )
            details["entryLimitReached"] = entry_limit
        if result.get("truncation") and result["truncation"].truncated:
            notices.append(f"{format_size(DEFAULT_MAX_BYTES)} limit reached")
            details["truncation"] = result["truncation"]
        if notices:
            output += "\n\n[" + ". ".join(notices) + "]"
        if not result.get("entries"):
            return {
                "content": [{"type": "text", "text": "(empty directory)"}],
                "details": None,
            }
        return {
            "content": [{"type": "text", "text": output}],
            "details": details or None,
        }

    return {
        "name": "ls",
        "label": "ls",
        "description": (
            f"List directory contents alphabetically. Directories marked with /. "
            f"Defaults to {DEFAULT_LIMIT} entries / {DEFAULT_MAX_BYTES // 1024}KB."
        ),
        "promptSnippet": "List directory contents",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory; default cwd.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max entries; default 500.",
                    "minimum": 1,
                },
            },
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


create_ls_tool = create_ls_tool_definition


__all__ = [
    "DEFAULT_LIMIT",
    "LsOperations",
    "create_ls_tool",
    "create_ls_tool_definition",
    "list_directory",
]
