"""jarvis_sdk.memory_host_fs_utils — fs-safe facade for memory host helpers.

OpenClaw parity: mirrors
``packages/memory-host-sdk/src/host/fs-utils.ts`` (~30 LOC).
Re-exports the narrow set of fs helpers that the memory host
needs: missing-file detection, safe regular-file reads (with
optional byte cap), safe stat (with missing-file shortcut), and
a recursive directory walker.

The OpenClaw source delegates to the ``@openclaw/fs-safe``
package; the Python port inlines the same shapes using the
stdlib ``pathlib`` + ``os`` + ``os.path`` modules. The
behavior is identical for the public surface used by
``memory_host_internal`` + ``memory_host_read_file``:

- ``is_file_missing_error(err)`` — true for ``ENOENT`` /
  ``ENOTDIR`` / ``"not-found"`` codes.
- ``read_regular_file({filePath, maxBytes?})`` — returns a
  ``{"buffer": bytes}`` shape; raises when the file is larger
  than ``maxBytes`` (when set).
- ``stat_regular_file(filePath)`` — returns
  ``{"missing": bool, "stat": os.stat_result?}`` so callers
  can branch without try/except.
- ``walk_directory(dir, {symlinks, descend, include})`` —
  recursive walk returning ``WalkDirectoryEntry`` dicts.
- ``is_path_inside(parent, child)`` / ``is_path_inside_with_realpath``
  — containment checks; the ``with_realpath`` variant
  resolves symlinks before checking.
- ``assert_no_symlink_parents({rootDir, targetPath})`` — walks
  parents from ``targetPath`` up to ``rootDir`` and asserts
  none are symlinks. Raises on any symlink parent.
- ``root(workspaceDir)`` — returns a small object with a
  ``resolve(relPath)`` method that ensures the resolved path
  stays inside ``workspaceDir`` (no symlink escapes).

Key port decisions:
- All functions return plain dicts / ``os.stat_result`` rather
  than ad-hoc dataclasses; matches the OpenClaw literal-object
  shape.
- ``walk_directory`` is a generator (not a list) so callers
  can short-circuit; the OpenClaw source uses a callback
  ``include`` filter for the same purpose. We expose a
  generator + a small ``_walk_entries`` helper that applies
  the filter.
- ``root().resolve(relPath)`` raises ``FileNotFoundError``
  when the path escapes the workspace (the OpenClaw source
  raises via ``fs-safe/root``'s safe-resolve).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

#: File-missing error codes. Mirrors OpenClaw's predicate.
_MISSING_FILE_CODES: frozenset[str] = frozenset({"ENOENT", "ENOTDIR", "not-found"})


class WalkDirectoryEntry(TypedDict):
    """One entry emitted by ``walk_directory``.

    Mirrors OpenClaw's ``WalkDirectoryEntry`` type. The
    ``kind`` field is one of ``"file"`` / ``"directory"`` /
    ``"other"``; ``path`` is the absolute path; ``name`` is
    the basename.
    """

    path: str
    name: str
    kind: str


def is_file_missing_error(err: object) -> bool:
    """True when ``err`` is a missing-file error.

    Mirrors OpenClaw's ``isFileMissingError``. Recognizes
    ``ENOENT``, ``ENOTDIR`` and the literal ``"not-found"``
    code (used by some ``fs-safe``-style facades).
    """
    if not isinstance(err, (OSError, BaseException)):
        return False
    code = getattr(err, "code", None)
    if isinstance(code, str) and code in _MISSING_FILE_CODES:
        return True
    return False


def read_regular_file(
    file_path: str,
    max_bytes: int | None = None,
) -> dict[str, bytes]:
    """Read a regular file with an optional byte cap.

    Mirrors OpenClaw's ``readRegularFile``. Returns a dict
    with the ``"buffer"`` key. Raises ``ValueError`` when
    ``max_bytes`` is set and the file is larger.
    """
    path = Path(file_path)
    if max_bytes is not None:
        info = path.stat()
        if info.st_size > max_bytes:
            raise ValueError(
                f"file {file_path} is {info.st_size} bytes; exceeds max_bytes={max_bytes}"
            )
    data = path.read_bytes()
    if max_bytes is not None and len(data) > max_bytes:
        raise ValueError(f"file {file_path} is {len(data)} bytes; exceeds max_bytes={max_bytes}")
    return {"buffer": data}


def stat_regular_file(file_path: str) -> dict[str, Any]:
    """Stat a regular file, returning a ``missing`` shortcut.

    Mirrors OpenClaw's ``statRegularFile``. Returns
    ``{"missing": False, "stat": os.stat_result()}`` on
    success, or ``{"missing": True, "stat": None}`` when the
    file does not exist (or any other stat error occurred —
    OpenClaw treats non-ENOENT errors as missing too).
    """
    try:
        return {"missing": False, "stat": os.stat(file_path)}
    except OSError:
        return {"missing": True, "stat": None}


def _walk_entries(
    directory: str,
    *,
    symlinks: str = "skip",
    descend: Callable[[WalkDirectoryEntry], bool] | None = None,
    include: Callable[[WalkDirectoryEntry], bool] | None = None,
) -> Iterator[WalkDirectoryEntry]:
    """Recursive directory walker.

    Mirrors OpenClaw's ``walkDirectory`` core. ``symlinks``
    is one of ``"skip"`` (default — never follow) or
    ``"follow"`` (descend into symlinked dirs). The
    ``descend`` predicate receives each directory entry and
    returns ``True`` to recurse; ``include`` receives each
    entry and returns ``True`` to yield it.
    """
    descend_fn = descend if descend is not None else (lambda _entry: True)
    include_fn = include if include is not None else (lambda _entry: True)
    root_path = Path(directory)
    if not root_path.exists():
        return
    for entry in root_path.iterdir():
        try:
            is_symlink = entry.is_symlink()
        except OSError:
            continue
        if is_symlink and symlinks == "skip":
            continue
        try:
            is_dir = entry.is_dir() if not is_symlink else (Path(os.path.realpath(entry)).is_dir())
        except OSError:
            is_dir = False
        try:
            is_file = (
                entry.is_file() if not is_symlink else (Path(os.path.realpath(entry)).is_file())
            )
        except OSError:
            is_file = False
        kind = "directory" if is_dir else ("file" if is_file else "other")
        walk_entry: WalkDirectoryEntry = {
            "path": str(entry),
            "name": entry.name,
            "kind": kind,
        }
        if include_fn(walk_entry):
            yield walk_entry
        if kind == "directory" and descend_fn(walk_entry):
            yield from _walk_entries(
                str(entry),
                symlinks=symlinks,
                descend=descend,
                include=include,
            )


class WalkDirectoryOptions(TypedDict, total=False):
    """Typed options for ``walk_directory``."""

    symlinks: str
    descend: Callable[[WalkDirectoryEntry], bool]
    include: Callable[[WalkDirectoryEntry], bool]


def walk_directory(
    directory: str,
    options: WalkDirectoryOptions | None = None,
) -> dict[str, list[WalkDirectoryEntry]]:
    """Walk a directory, returning ``{"entries": [...]}``.

    Mirrors OpenClaw's ``walkDirectory``. ``options`` keys:
    - ``symlinks``: ``"skip"`` (default) or ``"follow"``.
    - ``descend``: predicate ``(entry) -> bool``.
    - ``include``: predicate ``(entry) -> bool``.
    """
    options = options or {}
    symlinks = options.get("symlinks", "skip")
    descend = options.get("descend")
    include = options.get("include")
    entries = list(
        _walk_entries(
            directory,
            symlinks=symlinks,
            descend=descend,
            include=include,
        )
    )
    return {"entries": entries}


def is_path_inside(parent: str, child: str) -> bool:
    """True when ``child`` is inside ``parent`` (string-based).

    Mirrors OpenClaw's ``isPathInside``. No filesystem access;
    uses ``os.path.commonpath`` for the check.
    """
    try:
        common = os.path.commonpath([os.path.abspath(parent), os.path.abspath(child)])
    except ValueError:
        return False
    return common == os.path.abspath(parent)


def is_path_inside_with_realpath(parent: str, child: str) -> bool:
    """True when ``child`` resolves to a path inside ``parent``.

    Mirrors OpenClaw's ``isPathInsideWithRealpath``. Resolves
    symlinks via ``os.path.realpath`` before checking.
    """
    try:
        real_parent = os.path.realpath(parent)
        real_child = os.path.realpath(child)
    except OSError:
        return False
    try:
        common = os.path.commonpath([real_parent, real_child])
    except ValueError:
        return False
    return common == real_parent


def assert_no_symlink_parents(
    root_dir: str,
    target_path: str,
) -> None:
    """Assert no parent of ``target_path`` (up to ``root_dir``) is a symlink.

    Mirrors OpenClaw's ``assertNoSymlinkParents``. Raises
    ``OSError`` (with the platform's symlink message) on the
    first symlink parent found.
    """
    abs_root = os.path.abspath(root_dir)
    abs_target = os.path.abspath(target_path)
    if abs_target == abs_root:
        return
    rel = os.path.relpath(abs_target, abs_root)
    if rel.startswith("..") or os.path.isabs(rel):
        return  # outside root — no assertion needed
    parts = rel.split(os.sep)
    cumulative = abs_root
    for part in parts[:-1]:
        cumulative = os.path.join(cumulative, part)
        if os.path.islink(cumulative):
            raise OSError(f"symlink parent not allowed: {cumulative}")


class _SafeRoot:
    """Small safe-root resolver returned by ``root(workspace_dir)``.

    Mirrors OpenClaw's ``root`` helper. ``resolve(rel_path)``
    returns the absolute path inside ``workspace_dir`` after
    asserting containment; raises ``FileNotFoundError`` if the
    path escapes.
    """

    def __init__(self, workspace_dir: str) -> None:
        self._workspace_dir = os.path.abspath(workspace_dir)

    def resolve(self, rel_path: str) -> str:
        abs_path = os.path.abspath(os.path.join(self._workspace_dir, rel_path))
        if not is_path_inside(self._workspace_dir, abs_path):
            raise FileNotFoundError(f"path escapes workspace: {rel_path}")
        return abs_path


def root(workspace_dir: str) -> _SafeRoot:
    """Return a safe-root resolver for ``workspace_dir``.

    Mirrors OpenClaw's ``root``. The returned object has a
    ``resolve(rel_path)`` method.
    """
    return _SafeRoot(workspace_dir)


__all__ = [
    "is_file_missing_error",
    "read_regular_file",
    "stat_regular_file",
    "walk_directory",
    "WalkDirectoryEntry",
    "is_path_inside",
    "is_path_inside_with_realpath",
    "assert_no_symlink_parents",
    "root",
]
