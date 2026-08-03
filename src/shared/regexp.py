"""jarvis.shared.regexp — RegExp-safe text escaping.

OpenClaw parity: mirrors ``openclaw-main/src/shared/regexp.ts``.
"""
from __future__ import annotations

import re

#: Special regex metacharacters that must be escaped.
_REGEXP_META_RE = re.compile(r"[.*+?^${}()|[\]\\]")


def escape_reg_exp(value: str) -> str:
    """Escape text so it can be embedded literally inside a RegExp pattern.

    Mirrors :func:`escapeRegExp` (``shared/regexp.ts``).
    """
    if not isinstance(value, str):
        return value
    return _REGEXP_META_RE.sub(lambda m: "\\" + m.group(0), value)


__all__ = ["escape_reg_exp"]
