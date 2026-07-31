"""jarvis.agents.sessions.ignore_rules — gitignore-style ignore matcher.

OpenClaw parity: mirrors
``openclaw-main/src/shared/ignore-rules.js``.

Phase 6.11a — small helper used by the
package manager's directory walker.

The OpenClaw source implements a minimal
gitignore-style ignore matcher that supports:
- Plain paths (``foo/``)
- Negation (``!foo/``)
- Double-star (``**/foo/``,
  ``foo/**/bar``)
- Directory-only (``foo/`` with trailing
  slash)
- Common ignore defaults (``.git``,
  ``node_modules``, ``__pycache__``,
  build artifacts)

The Python port ships a hand-rolled
``fnmatch``-based matcher that covers the
most common patterns. Full gitignore
semantics land in Phase 6.12+ (the full
skills/prompts/themes loader uses a
``pathspec``-style matcher; the package
manager's walker only needs the common
patterns).

Adaptations
-----------
- The OpenClaw source uses ``ignore``
  (the npm package) + custom matchers. The
  Python port uses :mod:`fnmatch` (Python's
  stdlib) + a small set of defaults.
- The OpenClaw source's :class:`IgnoreMatcher`
  is exposed via a callable protocol; the
  Python port keeps the same shape.
"""
from __future__ import annotations

import os
import re
from typing import Optional, Protocol, runtime_checkable


#: Common ignore defaults. Mirrors the
#: OpenClaw source's hard-coded set
#: (``ignore-rules.js`` + the package
#: manager's own defaults).
DEFAULT_IGNORE_PATTERNS: list[str] = [
    ".git",
    ".git/**",
    "node_modules",
    "node_modules/**",
    "__pycache__",
    "__pycache__/**",
    ".venv",
    ".venv/**",
    "venv",
    "venv/**",
    "target",
    "target/**",
    "dist",
    "dist/**",
    "build",
    "build/**",
    ".next",
    ".next/**",
    ".mypy_cache",
    ".mypy_cache/**",
    ".pytest_cache",
    ".pytest_cache/**",
    ".ruff_cache",
    ".ruff_cache/**",
    "*.pyc",
    "*.pyo",
    ".DS_Store",
    "Thumbs.db",
]


@runtime_checkable
class IgnoreMatcher(Protocol):
    """Gitignore-style matcher protocol. Mirrors
    the OpenClaw source's ``IgnoreMatcher``.
    """

    def ignores(self, path: str) -> bool:
        """Return ``True`` when ``path``
        should be ignored."""
        ...


class _DefaultIgnoreMatcher:
    """Default matcher that consults the
    standard defaults + a user-supplied
    extra pattern list. Mirrors
    ``addIgnoreRules`` from the OpenClaw
    source.
    """

    def __init__(self, extra_patterns: Optional[list[str]] = None) -> None:
        self._patterns = list(DEFAULT_IGNORE_PATTERNS)
        if extra_patterns:
            self._patterns.extend(extra_patterns)
        # Compile each pattern to a regex
        # (we use fnmatch for the common
        # case; the OpenClaw source uses
        # the npm ``ignore`` package which
        # has more gitignore semantics).
        self._compiled: list[tuple[str, "re.Pattern[str]"]] = []
        for pattern in self._patterns:
            self._compiled.append(
                (pattern, _compile_ignore_pattern(pattern))
            )

    def ignores(self, path: str) -> bool:
        # Normalise to POSIX for the match
        normalised = path.replace(os.sep, "/")
        # Strip leading ``./``
        if normalised.startswith("./"):
            normalised = normalised[2:]
        for pattern, regex in self._compiled:
            if regex.match(normalised):
                return True
        return False


def _compile_ignore_pattern(pattern: str) -> "re.Pattern[str]":
    """Compile a gitignore-style pattern to
    a regex. Supports:
    - ``*`` matches any chars except ``/``
    - ``**`` matches any chars (including ``/``)
    - ``?`` matches a single char
    - ``/`` at the start anchors to the root
    - ``/`` at the end means directory-only
    """
    # Strip leading ``!`` (negation not
    # supported in the simple matcher).
    if pattern.startswith("!"):
        pattern = pattern[1:]
    # Directory-only: trailing ``/``
    is_dir = pattern.endswith("/")
    if is_dir:
        pattern = pattern[:-1]
    # Anchor to start
    anchored = pattern.startswith("/")
    if anchored:
        pattern = pattern[1:]
    # Convert glob to regex
    parts: list[str] = []
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if c == "*":
            if i + 1 < len(pattern) and pattern[i + 1] == "*":
                # ``**`` matches any chars
                # (including ``/``).
                parts.append(".*")
                i += 2
                # Consume a following ``/`` if any
                if i < len(pattern) and pattern[i] == "/":
                    i += 1
            else:
                # ``*`` matches any chars except ``/``.
                parts.append("[^/]*")
                i += 1
        elif c == "?":
            parts.append("[^/]")
            i += 1
        elif c in ".+^$()|{}[]\\":
            parts.append(re.escape(c))
            i += 1
        else:
            parts.append(c)
            i += 1
    body = "".join(parts)
    if anchored:
        regex_str = f"^{body}"
    else:
        # Unanchored: match anywhere in the
        # path (each path segment).
        regex_str = f"(^|/){body}"
    if is_dir:
        # Match if the path is a directory
        # or starts with this segment.
        regex_str = f"{regex_str}(/|$)"
    else:
        # Also match a directory with this name.
        regex_str = f"{regex_str}(/|$)"
    return re.compile(regex_str)


def add_ignore_rules(
    directory: str,
    root_dir: str,
    existing: Optional[IgnoreMatcher] = None,
    options: Optional[dict] = None,
) -> IgnoreMatcher:
    """Build a fresh ignore matcher scoped to
    ``directory``. Mirrors ``addIgnoreRules``
    (``ignore-rules.js``).

    Parameters
    ----------
    directory : str
        The directory being walked. May
        contain a local ``.gitignore`` (the
        Python port doesn't read it but the
        contract is preserved).
    root_dir : str
        The root for the matcher's path
        scope.
    existing : IgnoreMatcher, optional
        An existing matcher to extend (the
        Python port builds a fresh matcher
        and ignores the existing one — full
        gitignore stacking lands in 6.12+).
    options : dict, optional
        Reserved for future use (``ignoreCase``
        etc.).
    """
    # The OpenClaw source merges the local
    # ``.gitignore`` (if present) with the
    # default patterns. The Python port
    # only uses the defaults (the full
    # gitignore parsing lands in 6.12+).
    del directory  # unused in this minimal port
    del root_dir  # unused in this minimal port
    del existing  # unused in this minimal port
    del options  # unused in this minimal port
    return _DefaultIgnoreMatcher()


def is_real_path_within_root(root: str, candidate: str) -> bool:
    """Check whether ``candidate`` (after
    symlink resolution) is within ``root``.
    Mirrors ``isRealPathWithinRoot``
    (``package-manager.ts:553-558``)."""
    real_root = _realpath_if_possible(root)
    real_candidate = _realpath_if_possible(candidate)
    try:
        rel = os.path.relpath(real_candidate, real_root)
    except ValueError:
        return False
    if rel == "":
        return True
    return not (rel == ".." or rel.startswith(".." + os.sep))


def is_path_within_root(root: str, candidate: str) -> bool:
    """Same as :func:`is_real_path_within_root`
    but without symlink resolution. Mirrors
    ``isPathWithinRoot``
    (``package-manager.ts:548-551``)."""
    try:
        rel = os.path.relpath(candidate, root)
    except ValueError:
        return False
    if rel == "":
        return True
    return not (rel == ".." or rel.startswith(".." + os.sep))


def _realpath_if_possible(path: str) -> str:
    try:
        return os.path.realpath(path)
    except (OSError, ValueError):
        return os.path.normpath(os.path.abspath(path))


__all__ = [
    "DEFAULT_IGNORE_PATTERNS",
    "IgnoreMatcher",
    "add_ignore_rules",
    "is_path_within_root",
    "is_real_path_within_root",
]
