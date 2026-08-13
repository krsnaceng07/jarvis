"""Test-support for provider runtime behavior.

This module provides a simple in-memory provider runtime registry that
tests can use to register mock provider runtime handles, resolve them by
provider id, and reset the registry between tests.

API:
- `register_provider_runtime_mock(provider_id, runtime)`
- `resolve_provider_runtime_for_test(provider_id)`
- `get_registered_provider_ids()`
- `reset_provider_runtime_mocks_for_test()`
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Optional


_PROVIDER_RUNTIME_REGISTRY: Dict[str, Any] = {}


def register_provider_runtime_mock(provider_id: str, runtime: Any) -> None:
    """Register a provider runtime mock for `provider_id`.

    Provider ids are normalized to lowercase.
    """
    if not provider_id:
        return
    _PROVIDER_RUNTIME_REGISTRY[provider_id.lower()] = runtime


def resolve_provider_runtime_for_test(provider_id: Optional[str]) -> Optional[Any]:
    """Resolve the registered provider runtime for `provider_id` or None.

    This mirrors the test-support surface where tests can control how
    model/provider runtime resolution behaves.
    """
    if not provider_id:
        return None
    return _PROVIDER_RUNTIME_REGISTRY.get(provider_id.lower())


def get_registered_provider_ids() -> Iterable[str]:
    """Return the list of registered provider ids (lowercased)."""
    return list(_PROVIDER_RUNTIME_REGISTRY.keys())


def reset_provider_runtime_mocks_for_test() -> None:
    """Clear all registered provider runtime mocks."""
    _PROVIDER_RUNTIME_REGISTRY.clear()


__all__ = [
    "register_provider_runtime_mock",
    "resolve_provider_runtime_for_test",
    "get_registered_provider_ids",
    "reset_provider_runtime_mocks_for_test",
]

