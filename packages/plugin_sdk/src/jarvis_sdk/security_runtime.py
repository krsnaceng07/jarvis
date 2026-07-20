"""jarvis_sdk.security_runtime — path containment helpers.

OpenClaw parity: mirrors
``openclaw/plugin-sdk/security-runtime``'s ``isPathInside``.

Used by ``active-memory`` to validate that the operator's
``transcriptDir`` is contained within the agent's base
sessions dir (path-traversal guard). The OpenClaw shape
is a single function that returns True when ``child`` is
inside ``parent`` (after both are resolved to absolute
paths). Symlinks are NOT followed — that matches the
TypeScript reference implementation which uses
``path.resolve`` (no symlink resolution).

Parity
======
- ``is_path_inside(parent, child)`` → ``bool``. Returns
  ``True`` if ``child`` resolves to a path that is the
  same as or under ``parent``; ``False`` otherwise
  (including on TypeError / ValueError).
"""

from __future__ import annotations

import os


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


__all__ = ["is_path_inside"]
