"""jarvis.shared.tilde_path — home-prefix expansion for path lists.

OpenClaw parity: mirrors ``openclaw-main/src/shared/tilde-path.ts``.
"""
from __future__ import annotations

import os
import posixpath


def expand_tilde_path(input_str: str) -> str:
    """Expand a leading ``~`` against the OS home dir, keeping relatives relative.

    Unlike ``resolveHomeRelativePath``, ``~name`` is treated as
    ``<home>/name`` (shipped loader behavior for prompt/skill path lists).

    Mirrors :func:`expandTildePath` (``shared/tilde-path.ts``).
    """
    if not isinstance(input_str, str):
        return input_str
    trimmed = input_str.strip()
    home = os.path.expanduser("~")
    if trimmed == "~":
        return home
    if trimmed.startswith("~/"):
        return posixpath.join(home, trimmed[2:].replace("\\", "/"))
    if trimmed.startswith("~"):
        return posixpath.join(home, trimmed[1:].replace("\\", "/"))
    return trimmed


__all__ = ["expand_tilde_path"]
