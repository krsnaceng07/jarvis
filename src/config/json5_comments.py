"""jarvis.config.json5_comments — JSON5 comment-strip warning.

OpenClaw parity: mirrors
``openclaw-main/src/config/json5-comments.ts``.
"""
from __future__ import annotations

from typing import Callable, Optional


def _has_json5_comments(raw: str) -> bool:
    """Return whether ``raw`` contains ``//`` or ``/* */`` outside a string literal."""
    quote: Optional[str] = None
    for i, ch in enumerate(raw):
        if quote:
            if ch == "\\":
                # Skip escaped char; safe to advance by 1.
                continue
            if ch == quote:
                quote = None
            continue
        if ch in ('"', "'"):
            quote = ch
            continue
        if ch == "/" and i + 1 < len(raw) and raw[i + 1] in ("/", "*"):
            return True
    return False


def warn_if_json5_comments_will_be_stripped(params: dict) -> None:
    """Warn the operator when an about-to-be-written config contains JSON5 comments.

    Mirrors :func:`warnIfJSON5CommentsWillBeStripped`
    (``shared/config/json5-comments.ts``).
    """
    if params.get("skipOutputLogs"):
        return
    raw = params.get("raw")
    if not isinstance(raw, str) or not _has_json5_comments(raw):
        return
    warn = params.get("warn") or (lambda msg: print(msg))
    warn(f"Config write will strip JSON5 comments from {params['filePath']}.")


__all__ = ["warn_if_json5_comments_will_be_stripped"]
