"""jarvis_sdk.memory_host_read_file — secure markdown memory-file reader.

OpenClaw parity: mirrors
``packages/memory-host-sdk/src/host/read-file.ts`` (182 LOC).
Reads a memory file (markdown) from the workspace or
configured extra paths, with strict path-safety checks
(symlink parents rejected, escape attempts raise).

Public API:
- ``read_memory_file({workspace_dir, extra_paths, rel_path,
  from, lines, default_lines, max_chars})`` — read a single
  memory file.
- ``read_agent_memory_file({cfg, agent_id, rel_path, from,
  lines})`` — resolve agent config + read the file.

Key port decisions:
- All path safety checks (symlink-parent assertion, realpath
  containment) delegate to the ``memory_host_fs_utils``
  shim (port of ``@openclaw/fs-safe``).
- The read goes through ``retry_transient_memory_read`` so
  transient IO errors are retried with the standard
  3-attempt / 25-50 ms backoff.
- ``build_memory_read_result`` is reused from
  ``memory_host_read_file_shared`` to shape the final
  ``MemoryReadResult`` envelope (line slicing + char budget
  + continuation notice).
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, cast

from .memory_host_config_utils import (
    OpenClawConfig,
    resolve_memory_host_agent_context_limits,
    resolve_memory_host_agent_workspace_dir,
    resolve_memory_host_search_path_config,
)
from .memory_host_fs_utils import (
    assert_no_symlink_parents,
    is_file_missing_error,
    is_path_inside,
    is_path_inside_with_realpath,
    read_regular_file,
    root as _root,
    stat_regular_file,
)
from .memory_host_internal import (
    is_memory_path,
    normalize_extra_memory_paths,
)
from .memory_host_read_file_shared import (
    DEFAULT_MEMORY_READ_LINES,
    MemoryReadResult,
    build_memory_read_result,
)
from .memory_host_read_retry import retry_transient_memory_read

if TYPE_CHECKING:
    pass


async def _is_allowed_additional_directory_path(
    additional_path: str,
    abs_path: str,
) -> bool:
    """True when ``abs_path`` is inside ``additional_path`` (no symlink escapes)."""
    if not is_path_inside(additional_path, abs_path):
        return False
    try:
        # ``assert_no_symlink_parents`` is sync in the Python port.
        assert_no_symlink_parents(additional_path, abs_path)
    except Exception:  # noqa: BLE001
        return False
    if not is_path_inside_with_realpath(additional_path, abs_path):
        try:
            os.lstat(abs_path)
        except OSError as err:
            return is_file_missing_error(err)
        return False
    return True


def _is_file_disappeared_during_read_error(err: object) -> bool:
    """True when ``err`` indicates the file vanished mid-read."""
    if is_file_missing_error(err):
        return True
    code = getattr(err, "code", None)
    return code == "path-mismatch"


async def read_memory_file(
    workspace_dir: str,
    extra_paths: list[str] | None = None,
    *,
    rel_path: str,
    from_: int | None = None,
    lines: int | None = None,
    default_lines: int | None = None,
    max_chars: int | None = None,
) -> MemoryReadResult:
    """Read a single memory file with path safety + transient retry.

    Mirrors OpenClaw's ``readMemoryFile``. Returns a
    ``MemoryReadResult`` (see ``memory_host_read_file_shared``).
    """
    raw_path = rel_path.strip()
    if not raw_path:
        raise ValueError("path required")
    abs_path = (
        os.path.abspath(raw_path)
        if os.path.isabs(raw_path)
        else os.path.abspath(os.path.join(workspace_dir, raw_path))
    )
    rel = os.path.relpath(abs_path, workspace_dir).replace("\\", "/")
    in_workspace = bool(rel) and not rel.startswith("..") and not os.path.isabs(rel)
    allowed_workspace = bool(in_workspace and is_memory_path(rel))
    allowed_additional = False
    if not allowed_workspace and (extra_paths and len(extra_paths) > 0):
        additional_paths = normalize_extra_memory_paths(workspace_dir, extra_paths)
        for additional_path in additional_paths:
            try:
                os.lstat(additional_path)
            except OSError:
                continue
            if os.path.islink(additional_path):
                continue
            if os.path.isdir(additional_path):
                if await _is_allowed_additional_directory_path(additional_path, abs_path):
                    try:
                        candidate_stat = os.lstat(abs_path)
                    except OSError:
                        candidate_stat = None
                    if candidate_stat is not None and os.path.islink(abs_path):
                        continue
                    allowed_additional = True
                    break
                continue
            if (
                os.path.isfile(additional_path)
                and abs_path == additional_path
                and abs_path.endswith(".md")
            ):
                allowed_additional = True
                break
    if not allowed_workspace and not allowed_additional:
        raise ValueError("path required")
    if not abs_path.endswith(".md"):
        raise ValueError("path required")
    if allowed_workspace:
        try:
            workspace_root = _root(workspace_dir)
            workspace_root.resolve(rel)
        except FileNotFoundError:
            return {"text": "", "path": rel}
        except Exception as err:  # noqa: BLE001
            if is_file_missing_error(err):
                return {"text": "", "path": rel}
            raise
    stat_result = stat_regular_file(abs_path)
    if stat_result["missing"]:
        return {"text": "", "path": rel}

    async def _do_read() -> dict[str, Any]:
        return cast(dict[str, Any], read_regular_file(abs_path))

    try:
        read_result = cast(
            dict[str, Any],
            await retry_transient_memory_read(
                _do_read,
                f"read memory file {abs_path}",
            ),
        )
    except Exception as err:  # noqa: BLE001
        if _is_file_disappeared_during_read_error(err):
            return {"text": "", "path": rel}
        raise
    raw_buffer = read_result.get("buffer")
    if not isinstance(raw_buffer, (bytes, bytearray)):
        raise TypeError("memory file read result had no binary buffer")
    content = bytes(raw_buffer).decode("utf-8")
    return build_memory_read_result(
        content,
        rel,
        from_=from_,
        lines=lines,
        default_lines=default_lines if default_lines is not None else DEFAULT_MEMORY_READ_LINES,
        max_chars=max_chars,
        suggest_read_fallback=allowed_workspace,
    )


async def read_agent_memory_file(
    cfg: OpenClawConfig,
    agent_id: str,
    rel_path: str,
    *,
    from_: int | None = None,
    lines: int | None = None,
) -> MemoryReadResult:
    """Resolve agent config and read one memory file for that agent.

    Mirrors OpenClaw's ``readAgentMemoryFile``. Raises
    ``ValueError("memory search disabled")`` when the agent's
    memory-search is disabled.
    """
    settings = resolve_memory_host_search_path_config(cfg, agent_id)
    if not settings:
        raise ValueError("memory search disabled")
    context_limits = resolve_memory_host_agent_context_limits(cfg, agent_id)
    return await read_memory_file(
        resolve_memory_host_agent_workspace_dir(cfg, agent_id),
        settings.get("extraPaths"),
        rel_path=rel_path,
        from_=from_,
        lines=lines,
        default_lines=context_limits.get("memoryGetDefaultLines") if context_limits else None,
        max_chars=context_limits.get("memoryGetMaxChars") if context_limits else None,
    )


__all__ = [
    "read_memory_file",
    "read_agent_memory_file",
]
