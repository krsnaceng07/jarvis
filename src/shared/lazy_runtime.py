"""Lazy runtime-module loading for heavy, optional runtime boundaries.

OpenClaw parity: ``src/shared/lazy-runtime.ts`` \u2014
``createLazyRuntimeModule`` caches one dynamic import per loader so the
embedded runner graph gains no source-level static edges.
"""
from __future__ import annotations

import importlib
from typing import Any, Callable

__all__ = ["create_lazy_runtime_module"]


def create_lazy_runtime_module(load: Callable[[], Any]) -> Callable[[], Any]:
    """Cache one dynamic module load; ``load`` runs at most once."""
    cache: dict[str, Any] = {}

    def resolve() -> Any:
        if "module" not in cache:
            cache["module"] = load()
        return cache["module"]

    return resolve


def import_runtime_module(name: str) -> Any:
    """Import helper used by lazy loaders (kept separate for test patching)."""
    return importlib.import_module(name)
