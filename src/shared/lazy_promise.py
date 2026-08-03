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
from typing import Any, Awaitable, Callable, Dict, Generic, Optional, TypeVar, Union


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
    """Manual-control promise cache for lazy runtime resources."""

    def __init__(self, load: Callable[[], Union[T, Awaitable[T]]], cache_rejections: bool = False) -> None:
        self._load = load
        self._cache_rejections = cache_rejections
        self._promise: Optional[Any] = None

    def _create_promise(self) -> Any:
        if asyncio.iscoroutinefunction(self._load):
            coro = self._load()
            try:
                running_loop = asyncio.get_running_loop()
            except RuntimeError:
                running_loop = None
            if running_loop is not None:
                # Bind to the currently running loop for proper task semantics.
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", DeprecationWarning)
                    loaded = asyncio.ensure_future(coro)
            else:
                # No running loop (sync test/script context). Return the raw
                # coroutine — the caller can `await` it on any loop later.
                loaded = coro
        else:
            loaded = self._load()
        if not self._cache_rejections:
            def _on_reject(_exc: Any) -> None:
                if self._promise is loaded:
                    self._promise = None
            try:
                loaded.add_done_callback(_on_reject)
            except AttributeError:
                pass
        return loaded

    def load(self) -> Any:
        if self._promise is None:
            self._promise = self._create_promise()
        return self._promise

    def peek(self) -> Optional[Any]:
        return self._promise

    def clear(self) -> None:
        self._promise = None


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
