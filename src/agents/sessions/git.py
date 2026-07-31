"""jarvis.agents.sessions.git — git URL parsing helpers.

OpenClaw parity: mirrors
``openclaw-main/src/agents/utils/git.js``.

Phase 6.11a — small helper used by the
package manager to identify ``git:``
source specifiers.

Ships:
- :func:`parse_git_url` — parse a git URL
  into a :class:`GitSource` (host + path
  + optional ref). Mirrors ``parseGitUrl``
  in the OpenClaw source.

Adaptations
-----------
- The OpenClaw source uses a hand-rolled
  regex. The Python port uses
  :class:`urllib.parse.urlparse` for the
  common schemes (``https://``, ``ssh://``,
  ``git://``) + a regex fallback for the
  ``git@host:path`` SSH syntax.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse


@dataclass(frozen=True, slots=True)
class GitSource:
    """A parsed git source. Mirrors
    ``GitSource`` (``git.ts``)."""

    host: str
    path: str
    ref: Optional[str] = None


#: Regex for the ``git@host:path`` SSH syntax
#: (the OpenClaw source's first parse step).
#: The body may contain an ``@ref`` suffix
#: (e.g. ``repo.git@v1.0.0``) + a trailing
#: ``.git`` suffix; both are stripped in
#: code below.
_SSH_SHORT_RE = re.compile(
    r"^([\w.\-]+):([/~]?[^?#]+)$"
)


def _strip_git_suffix(path: str) -> str:
    """Strip a trailing ``.git`` suffix. Mirrors
    the OpenClaw source's ``normalizeGitPath``
    (which removes the suffix)."""
    if path.endswith(".git"):
        return path[: -len(".git")]
    return path


def parse_git_url(source: str) -> Optional[GitSource]:
    """Parse a git URL. Returns ``None`` when
    the source is not a recognisable git URL.
    Mirrors ``parseGitUrl`` (``git.js``).

    Recognised forms:
    - ``https://host/path``
    - ``http://host/path``
    - ``ssh://[user@]host[:port]/path``
    - ``git://host/path``
    - ``git@host:path`` (SSH short form)
    - ``path/to/repo`` (bare local path —
      returns ``None``; this is treated as
      a local source by the package
      manager)

    The path is always returned without the
    trailing ``.git`` suffix (mirrors
    ``normalizeGitPath`` in the OpenClaw
    source). An optional ``@ref`` suffix is
    split out into :attr:`GitSource.ref`.
    """
    if not source:
        return None
    if source.startswith("npm:"):
        return None
    if source.startswith("file://") or source.startswith("~"):
        return None
    if os.path.isabs(source):
        return None
    # Try the SSH short form (``git@host:path``)
    # but only when the source has no explicit
    # ``://`` scheme prefix. ``ssh://`` /
    # ``https://`` / ``http://`` / ``git://`` URLs
    # are handled by the URL parser below.
    if source.startswith("git@") or (
        "@" in source
        and ":" in source
        and "/" not in source.split(":", 1)[0]
        and "://" not in source
    ):
        # Strip the optional ``git@`` prefix
        body = source[4:] if source.startswith("git@") else source
        match = _SSH_SHORT_RE.match(body)
        if match:
            host, path = match.groups()
            return _split_path(host, path)
    # Standard URL schemes
    if "://" in source:
        try:
            parsed = urlparse(source)
        except ValueError:
            return None
        if parsed.scheme in ("https", "http", "ssh", "git"):
            host = parsed.hostname or ""
            path = parsed.path.lstrip("/")
            return _split_path(host, path)
    return None


def _split_path(host: str, path: str) -> GitSource:
    """Strip the ``.git`` suffix + split the
    ``@ref`` suffix from a parsed git path.

    The OpenClaw source's ``stripRef`` +
    ``normalizeGitPath`` produce the same
    shape (``host`` + ``user/repo`` +
    optional ``ref``); the Python port
    collapses both into one helper.
    """
    # Split the ref first (the path may
    # contain ``@``).
    if "@" in path:
        idx = path.rfind("@")
        ref = path[idx + 1 :]
        path = path[:idx]
    else:
        ref = None
    # Then strip the ``.git`` suffix.
    path = _strip_git_suffix(path)
    return GitSource(host=host, path=path, ref=ref)


__all__ = [
    "GitSource",
    "parse_git_url",
]
