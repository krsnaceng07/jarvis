"""jarvis.shared.bounded_buffer — bounded buffer with overflow strategies.

OpenClaw parity: mirrors ``openclaw-main/src/shared/bounded-buffer.ts``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, List, Optional, TypeVar, Union

T = TypeVar("T")


@dataclass
class BoundedBufferLatch:
    mode: str = "latch"


@dataclass
class BoundedBufferDropOldest:
    mode: str = "drop-oldest"
    fit: Optional[Callable[[T, int], T]] = None


@dataclass
class BoundedBufferFailClosed:
    mode: str = "fail-closed"
    on_overflow: Callable[[], None] = lambda: None


BoundedBufferOverflow = Union[BoundedBufferLatch, BoundedBufferDropOldest, BoundedBufferFailClosed]


class BoundedBuffer(Generic[T]):
    """Bounded buffer that latches / drops-oldest / fails-closed on overflow.

    Mirrors :class:`BoundedBuffer` (``shared/bounded-buffer.ts``).
    """

    def __init__(
        self,
        capacity: int,
        overflow: BoundedBufferOverflow,
        measure: Optional[Callable[[T], int]] = None,
    ) -> None:
        self._capacity = capacity
        self._overflow = overflow
        self._measure: Callable[[T], int] = measure or (lambda _v: 1)
        self._values: List[T] = []
        self._size = 0
        self._closed = False

    def push(self, value: T) -> bool:
        """Push ``value`` if it fits. Returns False when the buffer is closed/overflows."""
        if self._closed:
            return False
        value_size = self._measure(value)
        if self._size + value_size <= self._capacity:
            self._values.append(value)
            self._size += value_size
            return True
        if self._overflow.mode == "latch":
            self._closed = True
            return False
        if self._overflow.mode == "fail-closed":
            self._values = []
            self._size = 0
            self._closed = True
            self._overflow.on_overflow()
            return False
        # drop-oldest
        self._values.append(value)
        self._size += value_size
        while self._size > self._capacity and len(self._values) > 1:
            dropped = self._values.pop(0)
            self._size -= self._measure(dropped)
        if self._size > self._capacity:
            drop_overflow = self._overflow
            fitted = drop_overflow.fit(value, self._capacity) if isinstance(drop_overflow, BoundedBufferDropOldest) else None
            self._values = [] if fitted is None else [fitted]
            self._size = 0 if fitted is None else self._measure(fitted)
        return True

    def drain(self) -> List[T]:
        """Drain and return all values, resetting the buffer."""
        values = self._values
        self._values = []
        self._size = 0
        return values

    @property
    def size(self) -> int:
        return self._size

    @property
    def closed(self) -> bool:
        return self._closed


__all__ = [
    "BoundedBuffer",
    "BoundedBufferLatch",
    "BoundedBufferDropOldest",
    "BoundedBufferFailClosed",
]
