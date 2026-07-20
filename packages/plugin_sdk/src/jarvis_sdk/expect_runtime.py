"""jarvis_sdk.expect_runtime — strict unwrap helpers.

OpenClaw parity: mirrors ``openclaw/plugin-sdk/expect-runtime``'s
``expectDefined``. Used to convince pyright that an
``Optional[T]`` value is non-None in a context where TypeScript's
flow analysis would have already narrowed the type.

In Python we use ``assert`` + a runtime check, then return the
value. Pyright / mypy narrow the type after the assert.

Architecture
============
``expectDefined`` is one of the most-called helpers in
``memory-lancedb`` because the OpenClaw plugin code base
frequently uses ``match[1]`` from a regex where the previous
``if (!match) return null`` check has already proven the capture
is present. The Python equivalent is the same pattern: a
``match = re.search(...)`` followed by an early ``return None``
on miss, and ``expect_defined(match[1], "ctx")`` on the
capture that pyright would otherwise still type as
``Optional[str]``.

Parity
======
- ``expect_defined(value, ctx)`` raises ``AssertionError`` if
  value is None. Returns the value unchanged otherwise.
- ``expect_truthy(value, ctx)`` is the same but for falsy
  values (None, empty string, 0, empty list).
"""

from __future__ import annotations

from typing import NoReturn, TypeVar

_T = TypeVar("_T")


def expect_defined(value: _T | None, context: str) -> _T:
    """Assert value is not None; return it.

    Parameters
    ----------
    value
        The value to check. Typically the capture of a regex match
        or the result of a dict lookup.
    context
        Human-readable label used in the AssertionError message.
        OpenClaw uses the same label so tracebacks map 1:1.

    Raises
    ------
    AssertionError
        If ``value`` is None.
    """
    if value is None:
        _fail(f"expected {context} to be defined, got None")
    return value  # type: ignore[no-any-return]


def expect_truthy(value: _T, context: str) -> _T:
    """Assert value is truthy; return it."""
    if not value:
        _fail(f"expected {context} to be truthy, got {value!r}")
    return value


def _fail(message: str) -> NoReturn:
    raise AssertionError(message)


__all__ = ["expect_defined", "expect_truthy"]
