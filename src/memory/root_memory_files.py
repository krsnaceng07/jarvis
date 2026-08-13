"""memory.root_memory_files — canonical root memory file resolution.

OpenClaw parity: 1:1 port of ``src/memory/root-memory-files.ts``.

Resolves the workspace-root memory file (``MEMORY.md``), its legacy
lowercase variant (``memory.md``), and the repair directory used when
root-memory files need restoration.
"""
from __future__ import annotations

import os

CANONICAL_ROOT_MEMORY_FILENAME = "MEMORY.md"
LEGACY_ROOT_MEMORY_FILENAME = "memory.md"
ROOT_MEMORY_REPAIR_RELATIVE_DIR = ".openclaw-repair/root-memory"


def resolve_canonical_root_memory_path(workspace_dir: str) -> str:
    """Mirrors ``resolveCanonicalRootMemoryPath``."""
    return os.path.join(workspace_dir, CANONICAL_ROOT_MEMORY_FILENAME)


def resolve_legacy_root_memory_path(workspace_dir: str) -> str:
    """Mirrors ``resolveLegacyRootMemoryPath``."""
    return os.path.join(workspace_dir, LEGACY_ROOT_MEMORY_FILENAME)


def resolve_root_memory_repair_dir(workspace_dir: str) -> str:
    """Mirrors ``resolveRootMemoryRepairDir``."""
    return os.path.join(workspace_dir, ROOT_MEMORY_REPAIR_RELATIVE_DIR)


def normalize_workspace_relative_path(value: str) -> str:
    """Mirrors ``normalizeWorkspaceRelativePath``.

    Trims, converts backslashes to forward slashes, and strips a
    leading ``./`` segment.
    """
    normalized = value.strip().replace("\\", "/")
    if normalized.startswith("./"):
        return normalized[2:]
    return normalized


async def exact_workspace_entry_exists(workspace_dir: str, name: str) -> bool:
    """Mirrors ``exactWorkspaceEntryExists``.

    Case-exact directory-entry membership check; any read error
    resolves to ``False``.
    """
    try:
        entries = os.listdir(workspace_dir)
    except OSError:
        return False
    return name in entries


async def resolve_canonical_root_memory_file(workspace_dir: str) -> str | None:
    """Mirrors ``resolveCanonicalRootMemoryFile``.

    Returns the joined canonical path only when a real (non-symlink)
    file entry named ``MEMORY.md`` exists in the workspace root.
    """
    try:
        entries = os.scandir(workspace_dir)
    except OSError:
        return None
    try:
        for entry in entries:
            if entry.name != CANONICAL_ROOT_MEMORY_FILENAME:
                continue
            if entry.is_file(follow_symlinks=False) and not entry.is_symlink():
                return os.path.join(workspace_dir, CANONICAL_ROOT_MEMORY_FILENAME)
            return None
    finally:
        entries.close()
    return None


def should_skip_root_memory_auxiliary_path(params: dict) -> bool:
    """Mirrors ``shouldSkipRootMemoryAuxiliaryPath``.

    ``params`` keys: ``workspaceDir``, ``absolutePath``. Skips the
    legacy root memory file and anything inside the repair dir.
    """
    workspace_dir = params["workspaceDir"]
    absolute_path = params["absolutePath"]

    try:
        relative = os.path.relpath(absolute_path, workspace_dir)
    except ValueError:
        return False

    if relative.startswith("..") or os.path.isabs(relative):
        return False

    normalized = normalize_workspace_relative_path(relative)
    if normalized == LEGACY_ROOT_MEMORY_FILENAME:
        return True
    return normalized == ROOT_MEMORY_REPAIR_RELATIVE_DIR or normalized.startswith(
        ROOT_MEMORY_REPAIR_RELATIVE_DIR + "/"
    )


__all__ = [
    "CANONICAL_ROOT_MEMORY_FILENAME",
    "LEGACY_ROOT_MEMORY_FILENAME",
    "ROOT_MEMORY_REPAIR_RELATIVE_DIR",
    "resolve_canonical_root_memory_path",
    "resolve_legacy_root_memory_path",
    "resolve_root_memory_repair_dir",
    "normalize_workspace_relative_path",
    "exact_workspace_entry_exists",
    "resolve_canonical_root_memory_file",
    "should_skip_root_memory_auxiliary_path",
]
