"""Result type — discriminated union for fallible operations.

Mirrors OpenClaw's `Result` from `packages/normalization-core/src/result.ts`.
A tool returns ``Ok(value)`` on success and ``Err(message, code=...)`` on
known failure. The host maps this to the LLM's tool-response shape.

Example:

    from jarvis_sdk import Result, Ok, Err

    def divide(a: float, b: float) -> Result[float]:
        if b == 0:
            return Err("division by zero", code="DIV_BY_ZERO")
        return Ok(a / b)

    match divide(10, 0):
        case Ok(value):   print(value)
        case Err(error):  print(f"failed: {error}")
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


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


#: A result is either an ``Ok`` wrapping a value or an ``Err`` wrapping a failure.
Result = Ok[T] | Err[T]

__all__ = ["Err", "Ok", "Result"]
