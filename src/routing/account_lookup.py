"""jarvis.routing.account_lookup — account entry resolution.

OpenClaw parity: mirrors ``src/routing/account-lookup.ts``.
Python dicts have no prototype chain, but the blocked-key contract
(``__proto__`` / ``prototype`` / ``constructor``) is preserved so
lookups stay wire-compatible with OpenClaw configs.
"""

from __future__ import annotations

from typing import Any, Callable

from jarvis_normalization_core.string_coerce import normalize_lowercase_string_or_empty

from .account_id import normalize_optional_account_id
from .prototype_keys import is_blocked_object_key


def resolve_account_entry(accounts: object, account_id: str) -> Any | None:
    """Case-insensitive account lookup for config maps that may preserve user
    casing. Exact keys win so callers can still distinguish intentional entries."""
    if not accounts or not isinstance(accounts, dict):
        return None
    if account_id in accounts:
        return accounts[account_id]
    normalized = normalize_lowercase_string_or_empty(account_id)
    for key in accounts:
        if normalize_lowercase_string_or_empty(key) == normalized:
            return accounts[key]
    return None


def resolve_normalized_account_entry(
    accounts: object,
    account_id: str,
    normalize_account_id: Callable[[str], str],
) -> Any | None:
    """Lookup variant for account ids with a channel-specific normalization rule.

    Used when config keys should match the same canonical id as routing state.
    """
    if not accounts or not isinstance(accounts, dict):
        return None
    if account_id in accounts and not is_blocked_object_key(account_id):
        return accounts[account_id]
    normalized = normalize_account_id(account_id)
    for key in accounts:
        if is_blocked_object_key(key):
            continue
        if not isinstance(key, str):
            continue
        candidate = normalize_account_id(key)
        if (
            bool(normalize_optional_account_id(key))
            and not is_blocked_object_key(candidate)
            and candidate == normalized
        ):
            return accounts[key]
    return None


__all__ = ["resolve_account_entry", "resolve_normalized_account_entry"]
