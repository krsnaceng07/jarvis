"""Tests for memory_host_read_retry — mirrors host/read-retry.ts.

Covers the transient-error predicate + the bounded retry helper.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pytest

# Make the SDK importable when running this file in isolation.
_PKG_ROOT = Path(__file__).resolve().parents[1]
_SRC = _PKG_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from jarvis_sdk.memory_host_read_retry import (  # noqa: E402
    is_transient_memory_read_error,
    retry_transient_memory_read,
)


# ── is_transient_memory_read_error ──────────────────────────────────


class _ErrnoError(Exception):
    """Minimal errno-shaped exception for tests."""

    def __init__(self, message: str, *, errno: int | None = None, code: str | None = None) -> None:
        super().__init__(message)
        self.errno = errno
        self.code = code


def test_transient_by_code_eagain() -> None:
    """EAGAIN code is transient."""
    err = _ErrnoError("resource temporarily unavailable", code="EAGAIN")
    assert is_transient_memory_read_error(err) is True


def test_transient_by_code_ewouldblock() -> None:
    """EWOULDBLOCK code is transient."""
    err = _ErrnoError("operation would block", code="EWOULDBLOCK")
    assert is_transient_memory_read_error(err) is True


def test_transient_by_code_edeadlk() -> None:
    """EDEADLK code is transient."""
    err = _ErrnoError("resource deadlock avoided", code="EDEADLK")
    assert is_transient_memory_read_error(err) is True


def test_transient_by_errno_minus_eleven() -> None:
    """errno == -11 is transient."""
    err = _ErrnoError("Unknown system error -11", errno=-11)
    assert is_transient_memory_read_error(err) is True


def test_transient_by_message_regex() -> None:
    """The "Unknown system error -11" message shape is transient."""
    err = _ErrnoError("Unknown system error -11")
    assert is_transient_memory_read_error(err) is True


def test_non_transient_other_code() -> None:
    """Codes outside the transient set are not transient."""
    err = _ErrnoError("not found", code="ENOENT")
    assert is_transient_memory_read_error(err) is False


def test_non_transient_other_errno() -> None:
    """Errno values other than -11 are not transient."""
    err = _ErrnoError("permission denied", errno=13)
    assert is_transient_memory_read_error(err) is False


def test_non_transient_plain_exception() -> None:
    """A bare exception with no errno/code is not transient."""
    assert is_transient_memory_read_error(ValueError("boom")) is False


def test_non_transient_string() -> None:
    """A plain string is not transient."""
    assert is_transient_memory_read_error("not an error") is False


def test_non_transient_none() -> None:
    """``None`` is not transient."""
    assert is_transient_memory_read_error(None) is False


# ── retry_transient_memory_read ─────────────────────────────────────


@pytest.mark.asyncio
async def test_retry_returns_value_on_first_success() -> None:
    """When the first attempt succeeds, return the value."""
    calls = {"count": 0}

    async def read() -> str:
        calls["count"] += 1
        return "ok"

    result = await retry_transient_memory_read(read)
    assert result == "ok"
    assert calls["count"] == 1


@pytest.mark.asyncio
async def test_retry_succeeds_after_transient_errors() -> None:
    """A transient error followed by success returns the success value."""
    calls = {"count": 0}

    async def read() -> str:
        calls["count"] += 1
        if calls["count"] < 3:
            raise _ErrnoError("Unknown system error -11", errno=-11)
        return "ok"

    result = await retry_transient_memory_read(read)
    assert result == "ok"
    assert calls["count"] == 3


@pytest.mark.asyncio
async def test_retry_raises_non_transient_immediately() -> None:
    """Non-transient errors propagate without retry."""
    calls = {"count": 0}

    async def read() -> str:
        calls["count"] += 1
        raise ValueError("permanent")

    with pytest.raises(ValueError, match="permanent"):
        await retry_transient_memory_read(read)
    assert calls["count"] == 1


@pytest.mark.asyncio
async def test_retry_exhausts_attempts() -> None:
    """After 3 transient failures, the last error is re-raised."""
    calls = {"count": 0}

    async def read() -> str:
        calls["count"] += 1
        raise _ErrnoError("Unknown system error -11", errno=-11)

    with pytest.raises(_ErrnoError):
        await retry_transient_memory_read(read)
    assert calls["count"] == 3


@pytest.mark.asyncio
async def test_retry_label_is_passed_through() -> None:
    """The label is forwarded to retry_async (no-op for the public API,
    but must not raise)."""
    calls = {"count": 0}

    async def read() -> int:
        calls["count"] += 1
        return 42

    result = await retry_transient_memory_read(read, label="my label")
    assert result == 42
    assert calls["count"] == 1


@pytest.mark.asyncio
async def test_retry_attempts_3_in_total() -> None:
    """Default ``attempts`` is 3 (matches OpenClaw)."""
    calls = {"count": 0}

    async def read() -> Any:
        calls["count"] += 1
        raise _ErrnoError("EAGAIN", code="EAGAIN")

    with pytest.raises(_ErrnoError):
        await retry_transient_memory_read(read)
    assert calls["count"] == 3


# ── Sanity: skip on platforms without EAGAIN semantics (best-effort) ─


def test_windows_errno_attribute_still_works() -> None:
    """On Windows, the ``code`` field is the canonical transient signal.

    We don't need a Windows-specific assertion — the code path is
    identical to POSIX — but having an explicit test makes the
    cross-platform intent visible.
    """
    if sys.platform != "win32":
        pytest.skip("Windows-only sanity check")
    err = _ErrnoError("transient", code="EAGAIN")
    assert is_transient_memory_read_error(err) is True


def test_env_var_does_not_leak_into_retry() -> None:
    """``PYTHONHASHSEED`` etc. do not affect the predicate."""
    # Set/unset a benign env var to make sure the module is pure.
    old = os.environ.get("JARVIS_TEST_NOISE")
    try:
        os.environ["JARVIS_TEST_NOISE"] = "1"
        err = _ErrnoError("noise", code="EAGAIN")
        assert is_transient_memory_read_error(err) is True
    finally:
        if old is None:
            os.environ.pop("JARVIS_TEST_NOISE", None)
        else:
            os.environ["JARVIS_TEST_NOISE"] = old
