"""Process-local singleton helpers for registries, caches, and shared state.

OpenClaw parity: ``src/shared/global-singleton.ts``. TS keys singletons on
``globalThis`` with ``Symbol.for`` so duplicated dist chunks share one
registry map; Python has no chunk duplication, but the keyed store is kept
so registries stay process-global regardless of import path (``src.shared``
vs ``shared``) — the same aliasing hazard, one module apart.
"""
from __future__ import annotations

import builtins
from typing import Any, Callable, TypeVar

_T = TypeVar("_T")

# Stored on ``builtins`` so every import alias of this module resolves the
# same table — the Python analogue of ``globalThis[Symbol.for(key)]``.
_STORE_ATTR = "_jarvis_global_singletons"


def _store() -> dict[str, Any]:
    store = getattr(builtins, _STORE_ATTR, None)
    if store is None:
        store = {}
        setattr(builtins, _STORE_ATTR, store)
    return store


def resolve_global_singleton(key: str, create: Callable[[], _T]) -> _T:
    """Resolve a process-local singleton for caches and registries."""
    store = _store()
    if key in store:
        return store[key]
    created = create()
    store[key] = created
    return created


def resolve_global_map(key: str) -> dict[Any, Any]:
    """Resolve a process-local dict singleton keyed on ``key``."""
    return resolve_global_singleton(key, dict)


__all__ = ["resolve_global_map", "resolve_global_singleton"]
