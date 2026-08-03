"""jarvis.shared.global_singleton — process-local singleton helpers.

OpenClaw parity: mirrors ``openclaw-main/src/shared/global-singleton.ts``.

Keys must be unique Python objects (typically class/function) so unrelated
modules cannot collide on ``globalThis`` attribute names.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, TypeVar

T = TypeVar("T")
TKey = TypeVar("TKey")
TValue = TypeVar("TValue")


def resolve_global_singleton(key: Any, create: Callable[[], T]) -> T:
    """Resolve a process-local singleton on ``globalThis`` keyed by ``key``.

    Mirrors :func:`resolveGlobalSingleton` (``shared/global-singleton.ts``).
    """
    store = globals()
    if key in store:
        return store[key]
    created = create()
    store[key] = created
    return created


def resolve_global_map(key: Any):
    """Resolve a process-local :class:`dict` singleton keyed by ``key``.

    Mirrors :func:`resolveGlobalMap` (``shared/global-singleton.ts``).
    """
    return resolve_global_singleton(key, dict)


__all__ = ["resolve_global_singleton", "resolve_global_map"]
