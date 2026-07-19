"""Result type — discriminated union for fallible operations.

Mirrors OpenClaw's ``Result`` from
``packages/normalization-core/src/result.ts``. A tool returns
``Ok(value)`` on success and ``Err(message, code=...)`` on known failure.
The host maps this to the LLM's tool-response shape.

Example:

    from jarvis_sdk import Result, Ok, Err

    def divide(a: float, b: float) -> Result[float]:
        if b == 0:
            return Err("division by zero", code="DIV_BY_ZERO")
        return Ok(a / b)

    # 1. ``match`` ergonomics (Python 3.10+):
    match divide(10, 0):
        case Ok(value):  print(value)
        case Err(_):     print("failed")

    # 2. Imperative ergonomics:
    result = divide(10, 2)
    match result.is_ok, result.is_err:
        case True, _:    print(result.value)
        case _, True:    print(result.error)
        case _:          raise RuntimeError("unreachable")

    # 3. Functional ergonomics:
    msg = result.match(
        ok=lambda v: f"answer: {v}",
        err=lambda e, c: f"failed: {e} ({c})",
    )
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Generic, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable

T = TypeVar("T")
R = TypeVar("R")


@dataclass(frozen=True, slots=True)
class Ok(Generic[T]):
    """Successful result wrapping a value of type ``T``."""

    value: T

    @property
    def is_ok(self) -> bool:
        return True

    @property
    def is_err(self) -> bool:
        return False

    def match(self, *, ok: Callable[[T], R], err: Callable[[str, str], R]) -> R:
        """Dispatch on the variant. Mirrors Rust's ``Result::match``.

        Example::

            Ok(42).match(ok=lambda v: f"got {v}", err=lambda e, c: e)
            # => "got 42"
        """
        return ok(self.value)


@dataclass(frozen=True, slots=True)
class Err(Generic[T]):
    """Failed result with a human-readable message and a stable error code.

    The ``code`` is a short stable identifier (``"DIV_BY_ZERO"``,
    ``"HTTP_503"``, etc.) the LLM can use to branch. The ``message`` is
    user-facing text.
    """

    error: str
    code: str = "ERR"

    @property
    def is_ok(self) -> bool:
        return False

    @property
    def is_err(self) -> bool:
        return True

    def match(self, *, ok: Callable[[T], R], err: Callable[[str, str], R]) -> R:
        """Dispatch on the variant. Mirrors Rust's ``Result::match``.

        Example::

            Err("oops", code="E_FOO").match(
                ok=lambda v: v,
                err=lambda e, c: f"{c}: {e}",
            )
            # => "E_FOO: oops"
        """
        return err(self.error, self.code)


#: A result is either an ``Ok`` wrapping a value or an ``Err`` wrapping a failure.
Result = Ok[T] | Err[T]


# ── Common typed aliases (mirror OpenClaw's specialized Result variants) ─
#: Result that signals "did the operation succeed?" (no payload).
ResultNone = Ok[None] | Err  # type: ignore[type-arg]


__all__ = ["Err", "Ok", "Result", "ResultNone"]
