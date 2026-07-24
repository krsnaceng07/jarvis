"""jarvis_sdk.memory_host_runtime_memory — root memory file helpers.

OpenClaw parity: mirrors
``openclaw/src/memory/root-memory-files.ts`` (~75 LOC).
Locates the canonical root memory file (e.g. ``MEMORY.md``)
and skips legacy / repair paths when scanning workspace
memory files.

Public API:
- ``CANONICAL_ROOT_MEMORY_FILENAME = "MEMORY.md"``.
- ``LEGACY_ROOT_MEMORY_FILENAME = "memory.md"``.
- ``resolve_canonical_root_memory_path(workspace_dir)`` —
  absolute path to ``MEMORY.md`` (regardless of existence).
- ``resolve_legacy_root_memory_path(workspace_dir)`` —
  absolute path to ``memory.md`` (regardless of existence).
- ``resolve_canonical_root_memory_file(workspace_dir)`` —
  async; returns the path only if the file exists and is a
  regular file (not a symlink); ``None`` otherwise.
- ``should_skip_root_memory_auxiliary_path(workspace_dir, abs_path)``
  — ``True`` for legacy / repair paths.
- ``exact_workspace_entry_exists(dir, name)`` — true when
  ``dir`` contains an entry named exactly ``name`` (no
  case-folding).

Key port decisions:
- The original OpenClaw source uses ``fs.readdir`` with
  ``withFileTypes`` to inspect each entry; the Python port
  uses ``os.scandir`` for the same effect.
- Symlink detection uses ``os.path.islink`` (equivalent to
  ``DirEntry.is_symlink()`` for a non-following scan).
- ``should_skip_root_memory_auxiliary_path`` is synchronous
  in the Python port (the OpenClaw source is also sync).
"""
from __future__ import annotations

import os

#: Mirrors OpenClaw's ``CANONICAL_ROOT_MEMORY_FILENAME``.
CANONICAL_ROOT_MEMORY_FILENAME: str = "MEMORY.md"
#: Mirrors OpenClaw's ``LEGACY_ROOT_MEMORY_FILENAME``.
LEGACY_ROOT_MEMORY_FILENAME: str = "memory.md"
#: Mirrors OpenClaw's ``ROOT_MEMORY_REPAIR_RELATIVE_DIR``.
ROOT_MEMORY_REPAIR_RELATIVE_DIR: str = ".openclaw-repair/root-memory"


def resolve_canonical_root_memory_path(workspace_dir: str) -> str:
    """Return the canonical root memory file path for ``workspace_dir``.

    Mirrors OpenClaw's ``resolveCanonicalRootMemoryPath``.
    Does not check existence — returns the absolute path
    regardless.
    """
    return os.path.join(workspace_dir, CANONICAL_ROOT_MEMORY_FILENAME)


def resolve_legacy_root_memory_path(workspace_dir: str) -> str:
    """Return the legacy root memory file path for ``workspace_dir``.

    Mirrors OpenClaw's ``resolveLegacyRootMemoryPath``.
    """
    return os.path.join(workspace_dir, LEGACY_ROOT_MEMORY_FILENAME)


def resolve_root_memory_repair_dir(workspace_dir: str) -> str:
    """Return the repair dir for migrating root memory files.

    Mirrors OpenClaw's ``resolveRootMemoryRepairDir``.
    """
    return os.path.join(workspace_dir, ".openclaw-repair", "root-memory")


def _normalize_workspace_relative_path(value: str) -> str:
    """Normalize a workspace-relative path.

    Mirrors OpenClaw's ``normalizeWorkspaceRelativePath``:
    strip, swap backslashes for forward slashes, drop a
    leading ``./``.
    """
    return value.strip().replace("\\", "/").lstrip("./").removeprefix("./")


async def exact_workspace_entry_exists(dir: str, name: str) -> bool:  # noqa: A002
    """Check for an exact directory entry without case-folded lookup.

    Mirrors OpenClaw's ``exactWorkspaceEntryExists``. Returns
    ``False`` on any read error.
    """
    try:
        with os.scandir(dir) as it:
            for entry in it:
                if entry.name == name:
                    return True
    except OSError:
        return False
    return False


async def resolve_canonical_root_memory_file(workspace_dir: str) -> str | None:
    """Return the canonical root memory file only when it is a real file.

    Mirrors OpenClaw's ``resolveCanonicalRootMemoryFile``.
    Returns ``None`` when the file doesn't exist, when it
    can't be read, or when it's a symlink.
    """
    try:
        with os.scandir(workspace_dir) as it:
            for entry in it:
                if (
                    entry.name == CANONICAL_ROOT_MEMORY_FILENAME
                    and entry.is_file()
                    and not entry.is_symlink()
                ):
                    return os.path.join(workspace_dir, entry.name)
    except OSError:
        return None
    return None


def should_skip_root_memory_auxiliary_path(
    workspace_dir: str,
    abs_path: str,
) -> bool:
    """Skip legacy / repair root memory paths during workspace scans.

    Mirrors OpenClaw's ``shouldSkipRootMemoryAuxiliaryPath``.
    Returns ``True`` for the legacy ``memory.md`` file and
    for the ``.openclaw-repair/root-memory`` directory (and
    anything inside it).
    """
    try:
        relative = os.path.relpath(abs_path, workspace_dir)
    except ValueError:
        return False
    if relative.startswith("..") or os.path.isabs(relative):
        return False
    normalized = _normalize_workspace_relative_path(relative)
    return (
        normalized == LEGACY_ROOT_MEMORY_FILENAME
        or normalized == ROOT_MEMORY_REPAIR_RELATIVE_DIR
        or normalized.startswith(f"{ROOT_MEMORY_REPAIR_RELATIVE_DIR}/")
    )


__all__ = [
    "CANONICAL_ROOT_MEMORY_FILENAME",
    "LEGACY_ROOT_MEMORY_FILENAME",
    "ROOT_MEMORY_REPAIR_RELATIVE_DIR",
    "resolve_canonical_root_memory_path",
    "resolve_legacy_root_memory_path",
    "resolve_root_memory_repair_dir",
    "exact_workspace_entry_exists",
    "resolve_canonical_root_memory_file",
    "should_skip_root_memory_auxiliary_path",
]
