"""jarvis.shared.lazy_promise — lazy promise cache helpers.

OpenClaw parity: mirrors ``openclaw-main/src/shared/lazy-promise.ts``.

Public surface:

- :func:`get_or_create_promise`
- :func:`create_lazy_promise_loader`
- :func:`create_lazy_promise`
- :func:`create_lazy_import_loader`
- :class:`LazyPromiseLoader`
"""
from __future__ import annotations

import asyncio
import warnings
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    Generic,
    Optional,
    TypeVar,
    Union,
    cast,
)


K = TypeVar("K")
T = TypeVar("T")


def get_or_create_promise(
    cache: Dict[K, Any],
    key: K,
    create: Callable[[], Any],
) -> Any:
    """Return the cached promise for ``key``, creating and storing one if absent.

    Mirrors :func:`getOrCreatePromise` (``shared/lazy-promise.ts``).
    """
    cached = cache.get(key)
    if cached is not None:
        return cached
    created = create()
    cache[key] = created
    return created


class LazyPromiseLoader(Generic[T]):
    """Manual-control promise cache for lazy runtime resources.

    The Python port stores the resolved value (or a wrapper that re-emits it)
    so multiple ``load()`` calls return awaitables that can each be awaited.
    """

    def __init__(self, load: Callable[[], Union[T, Awaitable[T]]], cache_rejections: bool = False) -> None:
        self._load = load
        self._cache_rejections = cache_rejections
        self._resolved: Optional[T] = None
        self._resolved_sentinel = object()
        self._has_resolved = False
        self._rejected: Optional[BaseException] = None
        self._has_rejected = False
        self._promise: Optional[Awaitable[T]] = None

    async def _awaitable_for(self) -> T:
        try:
            if self._has_resolved:
                return self._resolved  # type: ignore[return-value]
            if self._has_rejected and self._cache_rejections:
                raise self._rejected  # type: ignore[misc]
            loaded = self._load()
            if asyncio.iscoroutine(loaded) or asyncio.isfuture(loaded):
                value = cast(T, await loaded)
            else:
                value = cast(T, loaded)
            if not self._cache_rejections and isinstance(value, BaseException):
                self._has_rejected = True
                self._rejected = value
                raise value
            self._resolved = value
            self._has_resolved = True
            return value
        finally:
            # Keep only the in-flight coroutine. Once it resolves, a later
            # caller may await the cached value from a different event loop.
            self._promise = None

    def load(self) -> Awaitable[T]:
        if self._promise is not None:
            return self._promise
        self._promise = self._awaitable_for()
        return self._promise

    def peek(self) -> Optional[Any]:
        """Return the current in-flight promise when present, else the resolved value.

        Mirrors ``loader.peek()`` in OpenClaw, where the underlying promise is
        exposed until the loader is cleared.
        """
        if self._promise is not None:
            return self._promise
        if self._has_resolved:
            return self._resolved
        return None

    def clear(self) -> None:
        """Drop the cached value so the next ``load()`` calls the loader again."""
        self._promise = None
        self._resolved = None
        self._has_resolved = False
        self._rejected = None
        self._has_rejected = False


def create_lazy_promise_loader(
    load: Callable[[], Union[T, Awaitable[T]]],
    cache_rejections: bool = False,
) -> LazyPromiseLoader[T]:
    """Create a small promise cache that dedupes concurrent loads.

    Mirrors :func:`createLazyPromiseLoader` (``shared/lazy-promise.ts``).
    """
    return LazyPromiseLoader(load, cache_rejections)


def create_lazy_promise(
    load: Callable[[], Union[T, Awaitable[T]]],
    cache_rejections: bool = False,
) -> Callable[[], Any]:
    """Wrap :func:`create_lazy_promise_loader` for a no-arg load function.

    Mirrors :func:`createLazyPromise` (``shared/lazy-promise.ts``).
    """
    loader = create_lazy_promise_loader(load, cache_rejections)
    return lambda: loader.load()


def create_lazy_import_loader(
    load: Callable[[], Awaitable[T]],
    cache_rejections: bool = False,
) -> LazyPromiseLoader[T]:
    """Convenience wrapper for dynamic-import-shaped loaders.

    Mirrors :func:`createLazyImportLoader` (``shared/lazy-promise.ts``).
    """
    return create_lazy_promise_loader(load, cache_rejections)


__all__ = [
    "LazyPromiseLoader",
    "get_or_create_promise",
    "create_lazy_promise_loader",
    "create_lazy_promise",
    "create_lazy_import_loader",
]
