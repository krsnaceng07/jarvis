"""jarvis_sdk.memory_host_error_utils — error formatting with secret redaction.

OpenClaw parity: mirrors
``packages/memory-host-sdk/src/host/error-utils.ts`` (~70 LOC).
Redacts common token / key / secret shapes from error
messages before they leave memory host internals, then
formats the (now-safe) error through the canonical
``formatErrorMessage`` helper.

Public API:
- ``format_error_message(err)`` — format an error through
  the canonical formatter and apply local redaction.

Key port decisions:
- The OpenClaw source uses ``formatErrorMessage`` from
  ``@openclaw/normalization-core/error-coercion``; the
  Python port uses a small built-in equivalent that
  extracts the ``str(err)`` shape (with the exception
  type and message). The redaction policy is the same.
- ``findLast`` from JS is implemented as
  ``next((v for v in reversed(groups) if isinstance(v, str) and v), match)``.
- ``sliceUtf16Safe`` (used by ``maskToken``) is reused
  from ``jarvis_normalization_core.text_utility``.
- All ``SECRET_PATTERNS`` are preserved verbatim from
  the OpenClaw source (the list is the entire security
  perimeter; even small tweaks matter for parity).
"""
from __future__ import annotations

import re
from typing import Match

from jarvis_normalization_core.text_utility import truncate_utf16_safe

# Mirrors OpenClaw's ``SECRET_PATTERNS``. Each regex matches
# a common token / key / secret shape. The list is the
# entire security perimeter; preserving the exact regexes
# keeps the port a drop-in replacement.
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    # KEY= / TOKEN= / SECRET= / PASSWORD= / PASSWD= (with optional quotes)
    re.compile(
        r"""\b[A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD)\b\s*[=:]\s*(["']?)([^\s"'\\]+)\1""",
    ),
    # ?access_token=... &auth=... etc. in query strings
    re.compile(
        r"""[?&](?:access[-_]?token|auth[-_]?token|hook[-_]?token|refresh[-_]?token|api[-_]?key|client[-_]?secret|token|key|secret|password|pass|passwd|auth|signature)=([^&\s"'<>]+)""",
        re.IGNORECASE,
    ),
    # JSON-style "apiKey": "..." / "token": "..." / etc.
    re.compile(
        r'"(?:apiKey|token|secret|password|passwd|accessToken|refreshToken)"\s*:\s*"([^"]+)"',
    ),
    # CLI flags: --api-key X / --token X / etc.
    re.compile(
        r"""--(?:api[-_]?key|hook[-_]?token|token|secret|password|passwd)\s+(["']?)([^\s"']+)\1""",
    ),
    # Authorization: Bearer <token>
    re.compile(
        r"""Authorization\s*[:=]\s*Bearer\s+([A-Za-z0-9._\-+=]+)""",
    ),
    # Free-standing Bearer <token> (long, 18+ chars)
    re.compile(
        r"""\bBearer\s+([A-Za-z0-9._\-+=]{18,})\b""",
    ),
    # Bare token= / secret= / password= in text
    re.compile(
        r"""(^|[\s,;])(?:access_token|refresh_token|api[-_]?key|token|secret|password|passwd)=([^\s&#]+)""",
    ),
    # PEM private key blocks
    re.compile(
        r"""-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z ]*PRIVATE KEY-----""",
    ),
    # Vendor-specific prefixes
    re.compile(r"""\b(sk-[A-Za-z0-9_-]{8,})\b"""),
    re.compile(r"""\b(ghp_[A-Za-z0-9]{20,})\b"""),
    re.compile(r"""\b(github_pat_[A-Za-z0-9_]{20,})\b"""),
    re.compile(r"""\b(xox[baprs]-[A-Za-z0-9-]{10,})\b"""),
    re.compile(r"""\b(xapp-[A-Za-z0-9-]{10,})\b"""),
    re.compile(r"""\b(gsk_[A-Za-z0-9_-]{10,})\b"""),
    re.compile(r"""\b(AIza[0-9A-Za-z\-_]{20,})\b"""),
    re.compile(r"""\b(pplx-[A-Za-z0-9_-]{10,})\b"""),
    re.compile(r"""\b(npm_[A-Za-z0-9]{10,})\b"""),
    # Telegram-style bot tokens
    re.compile(r"""\bbot(\d{6,}:[A-Za-z0-9_-]{20,})\b"""),
    re.compile(r"""\b(\d{6,}:[A-Za-z0-9_-]{20,})\b"""),
)


def _last_n_chars(text: str, n: int) -> str:
    """Return the last ``n`` code points of ``text`` (UTF-16 safe).

    Mirrors JS ``sliceUtf16Safe(text, -n)`` semantics. The
    Python port keeps this as a tiny helper rather than
    extending ``truncate_utf16_safe`` (which is a forward-
    only truncation helper).
    """
    if n <= 0:
        return ""
    if len(text) <= n:
        return text
    return text[-n:]


def _mask_token(token: str) -> str:
    """Mask a token. Mirrors OpenClaw's ``maskToken``.

    Tokens shorter than 18 chars become ``"***"``;
    longer tokens show the first 6 + ``"..."`` + last 4
    chars (UTF-16 safe slicing).
    """
    if len(token) < 18:
        return "***"
    head = truncate_utf16_safe(token, 6)
    tail = _last_n_chars(token, 4) if len(token) > 4 else ""
    return f"{head}...{tail}"


def _redact_pem_block(block: str) -> str:
    """Redact the body of a PEM private key block.

    Mirrors OpenClaw's ``redactPemBlock``. Keeps the first
    and last lines (the ``-----BEGIN ...`` / ``-----END ...``
    markers) and replaces the middle with ``...redacted...``.
    Returns ``"***"`` for blocks with < 2 lines.
    """
    lines = [line for line in block.splitlines() if line]
    if len(lines) < 2:
        return "***"
    return f"{lines[0]}\n...redacted...\n{lines[-1]}"


def _redact_match(match: Match[str]) -> str:
    """Redact a single regex match. Mirrors OpenClaw's ``redactMatch``.

    The replacement strategy depends on the match shape:
    - PEM private key blocks: keep the first + last lines,
      replace the middle.
    - Other matches: find the last non-empty group
      (``findLast`` semantics) and mask it in place; if no
      group matched, mask the whole match.
    """
    full = match.group(0)
    if "PRIVATE KEY-----" in full:
        return _redact_pem_block(full)
    groups: tuple[str, ...] = match.groups()
    # ``findLast`` from JS — find the last non-empty string
    # group; fall back to the full match.
    token: str = full
    for value in reversed(groups):
        if isinstance(value, str) and value:
            token = value
            break
    masked = _mask_token(token)
    if token == full:
        return masked
    token_offset = full.rfind(token)
    if token_offset < 0:
        return "***"
    return f"{full[:token_offset]}{masked}{full[token_offset + len(token):]}"


def redact_sensitive_text(text: str) -> str:
    """Redact common token / key / secret shapes from ``text``.

    Mirrors OpenClaw's ``redactSensitiveText``. Applies
    every regex in ``_SECRET_PATTERNS`` in order.
    """
    next_text = text
    for pattern in _SECRET_PATTERNS:
        next_text = pattern.sub(_redact_match, next_text)
    return next_text


def _format_shared_error_message(err: object) -> str:
    """Format an error message through a canonical formatter.

    The OpenClaw source uses
    ``formatErrorMessage`` from
    ``@openclaw/normalization-core/error-coercion``. The
    Python port uses a small built-in equivalent: extract
    the ``str(err)`` shape, prefixed with the exception
    type when ``err`` is an instance of ``BaseException``.
    """
    if isinstance(err, BaseException):
        return f"{type(err).__name__}: {err}"
    return str(err)


def format_error_message(err: object) -> str:
    """Format a memory-host error with local redaction applied.

    Mirrors OpenClaw's ``formatErrorMessage``. The
    canonical formatter runs first; the result is then
    passed through ``redact_sensitive_text`` so any
    tokens / keys / secrets inside the formatted message
    are masked before the error leaves memory host
    internals.
    """
    formatted = _format_shared_error_message(err)
    return redact_sensitive_text(formatted)


__all__ = [
    "format_error_message",
    "redact_sensitive_text",
]
