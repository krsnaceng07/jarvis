"""jarvis.agents.sessions.path_utils — path normalization helpers.

OpenClaw parity: mirrors
``openclaw-main/src/agents/utils/paths.js``
+ the ``toPosixPath`` helper from
``openclaw-main/src/shared/ignore-rules.js``.

Phase 6.11a — small helpers used by the
package manager + resource loader.

Ships:
- :func:`canonicalize_path` — resolve symlinks
  + normalise to a canonical absolute path
  (mirrors ``canonicalizePath``
  ``paths.js``)
- :func:`is_local_path` — check whether a
  source string is a local path (relative
  or absolute) vs an npm/git spec
  (mirrors ``isLocalPath`` ``paths.js``)
- :func:`to_posix_path` — convert ``\\`` to
  ``/`` for cross-platform path
  comparison (mirrors ``toPosixPath``
  ``ignore-rules.js``)

Adaptations
-----------
- The OpenClaw source uses Node's
  ``realpathSync`` + ``normalize`` for
  canonical paths. The Python port uses
  :func:`os.path.realpath` (which resolves
  symlinks) + :func:`os.path.normpath`.
- The OpenClaw source's
  ``isLocalPath`` uses the ``file://``
  protocol + a path-resolution check. The
  Python port uses the same approach:
  reject anything starting with ``npm:``
  or ``git:``; treat everything else as a
  local path.
"""
from __future__ import annotations

import os


def canonicalize_path(path: str) -> str:
    """Resolve symlinks + normalise to a
    canonical absolute path. Mirrors
    ``canonicalizePath``
    (``paths.js``).

    Uses :func:`os.path.realpath` which
    resolves symlinks. Falls back to
    :func:`os.path.normpath` + :func:`os.path.abspath`
    if the file doesn't exist.
    """
    try:
        return os.path.realpath(path)
    except (OSError, ValueError):
        return os.path.normpath(os.path.abspath(path))


def is_local_path(source: str) -> bool:
    """Check whether ``source`` is a local
    path vs an ``npm:`` / ``git:`` /
    ``github:`` / ``http(s):`` / ``ssh:``
    spec. Mirrors ``isLocalPath``
    (``paths.js``).

    The OpenClaw source rejects every
    explicit URL scheme + the ``github:``
    shorthand. SSH-short-form sources like
    ``git@host:user/repo`` are treated as
    local (they don't start with ``git:``).
    """
    if not source:
        return False
    trimmed = source.strip()
    if not trimmed:
        return False
    lowered = trimmed.lower()
    if (
        lowered.startswith("npm:")
        or lowered.startswith("git:")
        or lowered.startswith("github:")
        or lowered.startswith("http:")
        or lowered.startswith("https:")
        or lowered.startswith("ssh:")
    ):
        return False
    return True


#: POSIX path separator.
POSIX_SEP = "/"


def to_posix_path(path: str) -> str:
    """Convert a path to POSIX-style (forward
    slashes) for cross-platform comparison.
    Mirrors ``toPosixPath``
    (``ignore-rules.js``)."""
    if not path:
        return path
    return path.replace(os.sep, POSIX_SEP).replace("\\", POSIX_SEP)


__all__ = [
    "POSIX_SEP",
    "canonicalize_path",
    "is_local_path",
    "to_posix_path",
]
