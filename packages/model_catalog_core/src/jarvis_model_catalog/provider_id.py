"""Provider-id normalization (single owner).

OpenClaw parity: ``packages/model-catalog-core/src/provider-id.ts``.
Every provider lookup in core goes through :func:`normalize_provider_id`
so ``OpenAI``, `` openai ``, and ``openai`` resolve to one key. Auth-alias
lookup uses the same normalization via :func:`normalize_provider_id_for_auth`.
"""

from __future__ import annotations

from typing import TypeVar

from jarvis_normalization_core.string_coerce import normalize_lowercase_string_or_empty

T = TypeVar("T")


def normalize_provider_id(provider: object) -> str:
    """Lowercase/trim ``provider``; ``""`` for non-strings."""
    return normalize_lowercase_string_or_empty(provider)


def normalize_provider_id_for_auth(provider: object) -> str:
    """Normalize a provider id before manifest-owned auth alias lookup."""
    return normalize_provider_id(provider)


def find_normalized_provider_value(entries: dict[str, T] | None, provider: str) -> T | None:
    """Return the value whose key matches ``provider`` case-insensitively."""
    if not entries:
        return None
    wanted = normalize_provider_id(provider)
    for key, value in entries.items():
        if normalize_provider_id(key) == wanted:
            return value
    return None


def find_normalized_provider_key(entries: dict[str, object] | None, provider: str) -> str | None:
    """Return the declared key matching ``provider`` case-insensitively."""
    if not entries:
        return None
    wanted = normalize_provider_id(provider)
    for key in entries:
        if normalize_provider_id(key) == wanted:
            return key
    return None


__all__ = [
    "find_normalized_provider_key",
    "find_normalized_provider_value",
    "normalize_provider_id",
    "normalize_provider_id_for_auth",
]
