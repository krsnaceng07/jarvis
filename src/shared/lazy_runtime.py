"""jarvis.shared.lazy_runtime — lazy runtime surface helpers.

OpenClaw parity: mirrors ``openclaw-main/src/shared/lazy-runtime.ts``.
"""
from __future__ import annotations

from typing import Awaitable, Callable, Generic, TypeVar

from .lazy_promise import create_lazy_promise_loader

TModule = TypeVar("TModule")
TSurface = TypeVar("TSurface")
TKey = TypeVar("TKey")


async def _resolve_runtime_surface(
    importer: Callable[[], Awaitable[TModule]],
    select: Callable[[TModule], TSurface],
) -> TSurface:
    return select(await importer())


def create_lazy_runtime_surface(
    importer: Callable[[], Awaitable[TModule]],
    select: Callable[[TModule], TSurface],
) -> Callable[[], Awaitable[TSurface]]:
    """Cache a dynamic-import runtime surface behind a stable loader.

    Mirrors :func:`createLazyRuntimeSurface` (``shared/lazy-runtime.ts``).
    """
    return create_lazy_promise_loader(
        lambda: _resolve_runtime_surface(importer, select),
        cache_rejections=True,
    ).load


def create_lazy_runtime_module(
    importer: Callable[[], Awaitable[TModule]],
) -> Callable[[], Awaitable[TModule]]:
    """Cache the raw dynamically imported runtime module.

    Mirrors :func:`createLazyRuntimeModule` (``shared/lazy-runtime.ts``).
    """
    return create_lazy_runtime_surface(importer, lambda m: m)


def create_lazy_runtime_named_export(
    importer: Callable[[], Awaitable[TModule]],
    key: TKey,
) -> Callable[[], Awaitable[TModule]]:
    """Cache a single named runtime export.

    Mirrors :func:`createLazyRuntimeNamedExport``
    (``shared/lazy-runtime.ts``).
    """
    return create_lazy_runtime_surface(importer, lambda m: m[key])


def create_lazy_runtime_method(load, select):
    """Build a method that lazily loads a surface then invokes the selector.

    Mirrors :func:`createLazyRuntimeMethod` (``shared/lazy-runtime.ts``).
    """
    async def invoke(*args):
        surface = await load()
        method = select(surface)
        return await method(*args)
    return invoke


def create_lazy_runtime_method_binder(load):
    """Bind a method factory to a fixed lazy surface loader.

    Mirrors :func:`createLazyRuntimeMethodBinder``
    (``shared/lazy-runtime.ts``).
    """
    def binder(select):
        return create_lazy_runtime_method(load, select)
    return binder


__all__ = [
    "create_lazy_runtime_surface",
    "create_lazy_runtime_module",
    "create_lazy_runtime_named_export",
    "create_lazy_runtime_method",
    "create_lazy_runtime_method_binder",
]
