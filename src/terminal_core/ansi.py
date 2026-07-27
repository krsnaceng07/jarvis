"""ANSI stripping and log sanitization for untrusted text.

OpenClaw parity: ``sanitizeForLog`` in ``src/terminal-core/ansi.ts`` —
strip ANSI escape sequences, then drop C0 controls (except nothing — all
of 0x00–0x1f), DEL (0x7f), and C1 controls (0x80–0x9f) so engine ids,
owners, and error reasons cannot smuggle escape sequences into logs.
"""
from __future__ import annotations

import re

__all__ = ["sanitize_for_log", "strip_ansi"]

_ANSI_PATTERN = re.compile(
    r"[\x1b\x9b][\[\]()#;?]*"
    r"(?:(?:(?:(?:;[-a-zA-Z\d\/#&.:=?%@~_]+)*|[a-zA-Z\d]+(?:;[-a-zA-Z\d\/#&.:=?%@~_]*)*)?"
    r"(?:\x07|\x1b\x5c|\x9c))"
    r"|(?:(?:\d{1,4}(?:;\d{0,4})*)?[\dA-PR-TZcf-nq-uy=><~]))"
)
_CONTROL_PATTERN = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from ``text``."""
    return _ANSI_PATTERN.sub("", text)


def sanitize_for_log(text: str) -> str:
    """Strip ANSI sequences and control characters for safe logging."""
    return _CONTROL_PATTERN.sub("", strip_ansi(str(text)))
