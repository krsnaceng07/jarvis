"""Minimal test-support for model discovery cache parity.

Provides a tiny in-memory cache and helpers so tests can seed/clear
the model discovery cache without the full OpenClaw runtime.
"""
from __future__ import annotations

from typing import Any, Dict


_MODEL_DISCOVERY_CACHE: Dict[str, Any] = {}


def seed_model_discovery_cache_for_test(key: str, value: Any) -> None:
    """Seed an entry into the in-memory model discovery cache used in tests."""
    _MODEL_DISCOVERY_CACHE[key] = value


def reset_model_discovery_cache_for_test() -> None:
    """Clear the in-memory model discovery cache."""
    _MODEL_DISCOVERY_CACHE.clear()


def get_model_discovery_cache_snapshot() -> Dict[str, Any]:
    """Return a shallow copy of the cache snapshot."""
    return dict(_MODEL_DISCOVERY_CACHE)


__all__ = [
    "seed_model_discovery_cache_for_test",
    "reset_model_discovery_cache_for_test",
    "get_model_discovery_cache_snapshot",
]
