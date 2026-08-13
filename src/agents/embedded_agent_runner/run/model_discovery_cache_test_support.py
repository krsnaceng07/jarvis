"""Compatibility wrapper: re-export the implemented `.test_support` module.

The canonical implementation currently lives in
``model_discovery_cache.test_support.py``; re-export the public symbols
so imports using either filename work in tests.
"""
from __future__ import annotations

from .model_discovery_cache import (
    seed_model_discovery_cache_for_test,
    reset_model_discovery_cache_for_test,
    get_model_discovery_cache_snapshot,
)

__all__ = [
    "seed_model_discovery_cache_for_test",
    "reset_model_discovery_cache_for_test",
    "get_model_discovery_cache_snapshot",
]
