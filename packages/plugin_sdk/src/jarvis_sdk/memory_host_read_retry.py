"""jarvis_sdk.memory_host_read_retry — retry helper for transient memory reads.

OpenClaw parity: mirrors
``packages/memory-host-sdk/src/host/read-retry.ts`` (51 LOC).
Retry helper for transient filesystem reads observed on memory
stores. The OpenClaw source targets a narrow set of errors
that look like EAGAIN / EWOULDBLOCK / EDEADLK and the Linux
errno ``-11`` (``Unknown system error -11``), retrying the
read up to 3 times with linear backoff in the 25-50 ms range.

Public API:
- ``is_transient_memory_read_error(error)`` — true for the
  narrow set of transient error shapes.
- ``retry_transient_memory_read(read, label)`` — async retry
  using the ``retry_async`` helper from ``jarvis_sdk.retry_runtime``.

Key port decisions:
- We delegate to the existing ``retry_async`` (from
  ``jarvis_sdk.retry_runtime``) so this module reuses the
  same bounded-retry machinery as the rest of the SDK
  (``openclaw/plugin-sdk/retry-runtime``'s ``retryAsync``).
- The transient-error predicate checks Node-style ``code`` /
  ``errno`` fields first, then falls back to the
  ``Unknown system error -11`` message regex. On Windows
  the ``code`` field is still present (e.g. ``EAGAIN``) so
  the portable path matches OpenClaw's intent.
- The Linux errno ``-11`` is platform-specific; we keep the
  message-regex fallback so non-Linux platforms still detect
  the translated "Unknown system error -11" string that some
  Windows / macOS runtimes surface.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, TypeVar

from .retry_runtime import retry_async

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

T = TypeVar("T")

# Mirrors OpenClaw's ``TRANSIENT_MEMORY_READ_ERRNO = -11``.
# Linux errno 11 is ``EAGAIN``; on other platforms it surfaces
# as the human-readable "Unknown system error -11" string.
_TRANSIENT_MEMORY_READ_ERRNO: int = -11

# Mirrors OpenClaw's ``TRANSIENT_MEMORY_READ_CODES`` set.
# These are the Node ``code`` values that indicate a transient
# resource-availability failure worth retrying.
_TRANSIENT_MEMORY_READ_CODES: frozenset[str] = frozenset(
    {"EAGAIN", "EWOULDBLOCK", "EDEADLK"}
)

# Mirrors OpenClaw's ``TRANSIENT_MEMORY_READ_MESSAGE`` regex.
# Some platforms (notably Windows + macOS) don't surface the
# raw errno; instead they put the translated errno message
# on the error. This regex matches that shape.
_TRANSIENT_MEMORY_READ_MESSAGE: re.Pattern[str] = re.compile(
    r"Unknown system error -11\b",
    re.IGNORECASE,
)


def _get_errno(error: object) -> int | None:
    """Extract ``errno`` from a Node-style filesystem error.

    Mirrors OpenClaw's ``getErrno`` helper. Returns ``None``
    when the object is not an errno-shaped error.
    """
    candidate: Any = error
    errno = getattr(candidate, "errno", None)
    if isinstance(errno, int):
        return errno
    return None


def _get_code(error: object) -> str | None:
    """Extract ``code`` from a Node-style filesystem error.

    Mirrors OpenClaw's ``getCode`` helper. Returns ``None``
    when the object is not a code-shaped error.
    """
    candidate: Any = error
    code = getattr(candidate, "code", None)
    if isinstance(code, str):
        return code
    return None


def is_transient_memory_read_error(error: object) -> bool:
    """Return ``True`` for transient memory-read failures.

    Mirrors OpenClaw's ``isTransientMemoryReadError``. Three
    shapes are recognized:
    1. The error has a Node ``code`` in
       ``{EAGAIN, EWOULDBLOCK, EDEADLK}``.
    2. The error has an ``errno`` equal to ``-11``.
    3. The error message matches
       ``/Unknown system error -11\\b/i``.

    All other errors are treated as non-transient and
    propagated immediately.
    """
    code = _get_code(error)
    if code is not None and code in _TRANSIENT_MEMORY_READ_CODES:
        return True

    errno = _get_errno(error)
    if errno == _TRANSIENT_MEMORY_READ_ERRNO:
        return True

    if isinstance(error, BaseException):
        message = str(error)
        if _TRANSIENT_MEMORY_READ_MESSAGE.search(message):
            return True

    return False


async def retry_transient_memory_read(
    read: Callable[[], Awaitable[T]],
    label: str = "memory read",
) -> T:
    """Retry a memory read with the narrow transient-error predicate.

    Mirrors OpenClaw's ``retryTransientMemoryRead``. Bounded
    to 3 attempts with 25-50 ms linear backoff (matches the
    source's ``minDelayMs: 25, maxDelayMs: 50``).
    """
    return await retry_async(
        read,
        {
            "attempts": 3,
            "minDelayMs": 25,
            "maxDelayMs": 50,
            "label": label,
            "shouldRetry": is_transient_memory_read_error,
        },
    )


__all__ = [
    "is_transient_memory_read_error",
    "retry_transient_memory_read",
]
