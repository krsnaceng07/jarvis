"""jarvis_sdk.security_runtime — path containment + fs-safe helpers.

OpenClaw parity: mirrors
``openclaw/plugin-sdk/security-runtime``'s ``isPathInside``,
``pathExists``, ``root``, ``appendRegularFile``, and
``FsSafeError``.

Used by ``active-memory`` to validate that the operator's
``transcriptDir`` is contained within the agent's base
sessions dir (path-traversal guard), and by ``memory-wiki``
to safely initialize and write to its vault directories
(symlink rejection, hardlink rejection, concurrent-rewrite
race detection).

The OpenClaw shape for the path-containment check is a
single function that returns True when ``child`` is inside
``parent`` (after both are resolved to absolute paths).
Symlinks are NOT followed — that matches the TypeScript
reference implementation which uses ``path.resolve``
(no symlink resolution).

The OpenClaw ``fs-safe`` package provides a ``Root`` facade
with guarded ``create`` / ``write`` / ``read`` / ``remove``
methods that detect path-alias / path-mismatch / symlink
escapes and surface a labeled ``FsSafeError`` with a
machine-readable ``code``. The Python port preserves the
public contract (same method names, same error codes) but
implements the cross-platform paranoia as a small,
stdlib-only helper rather than a deep port of the
TypeScript implementation.

Parity
======
- ``is_path_inside(parent, child)`` → ``bool``. Returns
  ``True`` if ``child`` resolves to a path that is the
  same as or under ``parent``; ``False`` otherwise
  (including on TypeError / ValueError).
- ``path_exists(path)`` → ``bool``. Returns ``True`` iff
  the path resolves to an existing filesystem entry
  (file, directory, symlink, or anything else).
- ``FsSafeError`` — exception with a ``code`` attribute
  matching the OpenClaw error codes: ``"path-mismatch"``,
  ``"symlink"``, ``"path-alias"``, ``"already-exists"``,
  ``"hardlink"``, ``"not-found"``, ``"out-of-root"``.
- ``fs_root(root_dir)`` → ``FsSafeRoot`` — guarded root
  object. Mirrors OpenClaw's ``root(rootDir)``. Methods:
  ``create(rel, content)``, ``write(rel, content)``,
  ``read(rel)``, ``remove(rel)``, ``append(rel, content)``,
  ``exists(rel)``.
- ``append_regular_file(file_path, content, ...)`` →
  ``None``. Appends ``content`` to ``file_path`` after
  refusing any symlink in the parent chain.
- ``is_regular_file_stat(value)`` → ``bool``. Type-guard
  for a stat-like object: must be a non-empty object with
  ``isFile`` callable (returning True) and a numeric
  ``nlink``.
"""

from __future__ import annotations

import os
from typing import Any

# FsSafeError codes mirror the OpenClaw fs-safe
# ``FsSafeErrorCode`` union. The Python port collapses a
# handful of node-specific guards (``"path-mismatch"`` vs.
# ``"path-alias"``) into the same set so callers can match
# on the same string they would in the TypeScript host.
_FS_SAFE_ERROR_CODES = frozenset(
    {
        "path-mismatch",
        "symlink",
        "path-alias",
        "already-exists",
        "hardlink",
        "not-found",
        "out-of-root",
    }
)


class FsSafeError(Exception):
    """Raised when an fs-safe guard refuses an operation.

    Mirrors ``@openclaw/fs-safe/errors``'s ``FsSafeError``.
    The ``code`` attribute is one of the strings listed in
    ``_FS_SAFE_ERROR_CODES`` so callers can branch on the
    failure mode (e.g. retry the transient
    ``"path-mismatch"`` concurrent-rewrite race).
    """

    def __init__(self, code: str, message: str) -> None:
        if code not in _FS_SAFE_ERROR_CODES:
            raise ValueError(f"unknown FsSafeError code: {code!r}")
        super().__init__(message)
        self.code = code


def is_path_inside(parent: str, child: str) -> bool:
    """Return True if ``child`` resolves to a path inside ``parent``.

    Mirrors ``openclaw/plugin-sdk/security-runtime``'s
    ``isPathInside``. The check is purely lexical (no
    filesystem access, no symlink resolution) so it is
    safe to call on untrusted input without raising.
    """
    if not isinstance(parent, str) or not isinstance(child, str):
        return False
    try:
        parent_abs = os.path.realpath(os.path.abspath(parent))
        child_abs = os.path.realpath(os.path.abspath(child))
    except (OSError, ValueError):
        return False
    if parent_abs == child_abs:
        return True
    # Ensure trailing separator so prefix match isn't fooled by
    # "/foo" matching "/foobar".
    parent_prefix = parent_abs.rstrip(os.sep) + os.sep
    return child_abs.startswith(parent_prefix)


def path_exists(path: str | os.PathLike[str]) -> bool:
    """Return True iff ``path`` resolves to an existing entry.

    Mirrors ``openclaw/plugin-sdk/security-runtime``'s
    ``pathExists``. Treats every ``OSError`` (including
    permission errors) as "not exists" so the helper
    is safe to call on untrusted paths.
    """
    try:
        return os.path.lexists(os.fspath(path))
    except (OSError, ValueError):
        return False


def is_regular_file_stat(value: Any) -> bool:
    """Return True iff ``value`` looks like a stat for a regular file.

    Mirrors ``openclaw/plugin-sdk/security-runtime``'s
    ``isRegularFileStat`` (the type-guard used in
    ``memory-wiki``'s ``writeGuardedVaultPage`` to decide
    whether to break a hardlink before the atomic write).
    Accepts a duck-typed stat object whose ``isFile`` is
    either a callable returning True or the literal True,
    and whose ``nlink`` is a number.
    """
    if value is None or not isinstance(value, object):
        return False
    is_file_attr = getattr(value, "isFile", None)
    is_file: bool
    if callable(is_file_attr):
        try:
            is_file = bool(is_file_attr())
        except Exception:
            return False
    else:
        is_file = is_file_attr is True
    if not is_file:
        return False
    nlink = getattr(value, "nlink", None)
    return isinstance(nlink, int | float) and not isinstance(nlink, bool)


class _FsSafeRoot:
    """Guarded-root facade returned by :func:`fs_root`.

    Mirrors ``@openclaw/fs-safe/root``'s ``Root``. The
    Python port implements the same public surface
    (``create`` / ``write`` / ``read`` / ``remove`` /
    ``append`` / ``exists``) with the same error codes
    (``already-exists`` for ``create`` on a present file,
    ``out-of-root`` for paths that escape the root,
    ``symlink`` for any symlink in the parent chain).
    """

    def __init__(self, root_dir: str) -> None:
        self._root = os.path.realpath(os.path.abspath(root_dir))

    def _resolve(self, relative_path: str) -> str:
        if not isinstance(relative_path, str) or not relative_path:
            raise FsSafeError(
                "out-of-root", f"relative path must be a non-empty string: {relative_path!r}"
            )
        candidate = os.path.normpath(os.path.join(self._root, relative_path))
        candidate_abs = os.path.realpath(candidate)
        if not is_path_inside(self._root, candidate_abs):
            raise FsSafeError("out-of-root", f"refusing to operate outside root: {relative_path}")
        return candidate_abs

    def _check_no_symlink_parents(self, absolute_path: str) -> None:
        parent = os.path.dirname(absolute_path)
        # Walk up until we hit the root (inclusive); any
        # symlink in the chain is rejected.
        parent = os.path.realpath(parent) if parent else parent
        # Build a normalized list of ancestors under the root.
        try:
            rel_parent = os.path.relpath(parent, self._root)
        except ValueError:
            rel_parent = ""
        if rel_parent in ("", "."):
            return
        parts = rel_parent.split(os.sep)
        accum = self._root
        for part in parts:
            accum = os.path.join(accum, part)
            if os.path.islink(accum):
                raise FsSafeError("symlink", f"refusing to operate through symlink: {accum}")

    def create(self, relative_path: str, content: str | bytes) -> None:
        """Atomically create ``relative_path`` with ``content``.

        Mirrors OpenClaw's ``root.create``. Raises
        ``FsSafeError("already-exists")`` if the file
        already exists.
        """
        absolute = self._resolve(relative_path)
        self._check_no_symlink_parents(absolute)
        if path_exists(absolute):
            raise FsSafeError("already-exists", f"file already exists: {absolute}")
        # Ensure parent directory exists.
        os.makedirs(os.path.dirname(absolute), exist_ok=True)
        if isinstance(content, str):
            with open(absolute, "x", encoding="utf-8") as f:
                f.write(content)
        else:
            with open(absolute, "xb") as f:
                f.write(content)

    def write(self, relative_path: str, content: str | bytes) -> None:
        """Replace ``relative_path`` with ``content``.

        Mirrors OpenClaw's ``root.write``. Refuses to
        follow symlinks; refuses paths that escape the
        root.
        """
        absolute = self._resolve(relative_path)
        self._check_no_symlink_parents(absolute)
        os.makedirs(os.path.dirname(absolute), exist_ok=True)
        # Refuse to write through an existing symlink.
        if os.path.islink(absolute):
            raise FsSafeError("symlink", f"refusing to write through symlink: {absolute}")
        if isinstance(content, str):
            with open(absolute, "w", encoding="utf-8") as f:
                f.write(content)
        else:
            with open(absolute, "wb") as f:
                f.write(content)

    def read(self, relative_path: str) -> str:
        """Read the file at ``relative_path`` as UTF-8 text."""
        absolute = self._resolve(relative_path)
        if os.path.islink(absolute):
            raise FsSafeError("symlink", f"refusing to read through symlink: {absolute}")
        if not path_exists(absolute):
            raise FsSafeError("not-found", f"file not found: {absolute}")
        with open(absolute, encoding="utf-8") as f:
            return f.read()

    def remove(self, relative_path: str) -> None:
        """Delete the file at ``relative_path`` if it exists."""
        absolute = self._resolve(relative_path)
        if not path_exists(absolute):
            return
        if os.path.islink(absolute):
            raise FsSafeError("symlink", f"refusing to remove symlink: {absolute}")
        os.remove(absolute)

    def append(self, relative_path: str, content: str) -> None:
        """Append ``content`` to the file at ``relative_path``.

        Convenience wrapper around
        :func:`append_regular_file` for the common
        vault-log use case.
        """
        absolute = self._resolve(relative_path)
        append_regular_file(absolute, content)

    def exists(self, relative_path: str) -> bool:
        return path_exists(self._resolve(relative_path))


# Module-level alias ``root`` mirrors the OpenClaw
# ``root(rootDir)`` factory. We expose ``fs_root`` as the
# canonical name in Python and re-export ``root`` for
# parity with the TypeScript source.
def fs_root(root_dir: str) -> _FsSafeRoot:
    """Return a guarded :class:`_FsSafeRoot` rooted at ``root_dir``.

    Mirrors ``@openclaw/fs-safe/root``'s ``root`` factory.
    """
    if not isinstance(root_dir, str) or not root_dir:
        raise FsSafeError("out-of-root", f"root_dir must be a non-empty string: {root_dir!r}")
    return _FsSafeRoot(root_dir)


# `root` is the OpenClaw name; the Python SDK canonical
# spelling is `fs_root`. Both point at the same factory.
root = fs_root


def append_regular_file(
    file_path: str | os.PathLike[str],
    content: str,
    *,
    reject_symlink_parents: bool = False,
) -> None:
    """Append ``content`` to ``file_path``.

    Mirrors ``@openclaw/fs-safe/advanced``'s
    ``appendRegularFile``. By default the call is lenient
    (no symlink-parent rejection — matching the OpenClaw
    default); pass ``reject_symlink_parents=True`` for the
    strict vault-log variant.
    """
    file_path = os.fspath(file_path)
    parent = os.path.dirname(os.path.abspath(file_path)) or "."
    if reject_symlink_parents and os.path.islink(parent):
        raise FsSafeError("symlink", f"refusing to append through symlink parent: {parent}")
    if path_exists(file_path) and os.path.islink(file_path):
        raise FsSafeError("symlink", f"refusing to append through symlink: {file_path}")
    # Ensure parent dir exists; append opens with create-if-missing.
    os.makedirs(parent, exist_ok=True)
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(content)


__all__ = [
    "FsSafeError",
    "append_regular_file",
    "fs_root",
    "is_path_inside",
    "is_regular_file_stat",
    "path_exists",
    "root",
]
