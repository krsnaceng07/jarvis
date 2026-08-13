"""Compatibility wrapper: re-export the `_test_support` implementation.

The canonical Python test-support implementation lives in
``model_provider_runtime_test_support.py``; this module re-exports the
same symbols so code that expects the ``.test_support`` filename keeps
working.
"""
from __future__ import annotations

from .model_provider_runtime_test_support import (
    register_provider_runtime_mock,
    resolve_provider_runtime_for_test,
    get_registered_provider_ids,
    reset_provider_runtime_mocks_for_test,
)

__all__ = [
    "register_provider_runtime_mock",
    "resolve_provider_runtime_for_test",
    "get_registered_provider_ids",
    "reset_provider_runtime_mocks_for_test",
]
