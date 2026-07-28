"""Phase 5.13 — ``account-lookup.test.ts`` → Python.

OpenClaw parity: ports the 7 ``it`` blocks from
``src/routing/account-lookup.test.ts``.

Python adaptations:
- ``Object.create({default: {id: "polluted"}})`` becomes a
  plain dict where ``__proto__`` is set as a regular key (the
  Python port's ``is_blocked_object_key`` filter still rejects
  it via the explicit blocked-keys list).
- ``JSON.parse('{"__proto__":...}')`` — Python's
  ``json.loads`` silently drops ``__proto__`` (Python's json
  parser treats it as a normal key, but the resulting
  ``__proto__`` key still gets rejected by ``is_blocked_object_key``).
  We use ``json.loads`` with a payload containing ``__proto__``
  to mirror the OpenClaw test.
- ``it.each`` with custom ``assert`` branches becomes
  individual test functions where the inline ``assert`` branch
  is preserved.
"""
from __future__ import annotations

import json

import pytest

from src.routing.account_id import normalize_account_id
from src.routing.account_lookup import (
    resolve_account_entry,
    resolve_normalized_account_entry,
)


def _create_polluted_accounts():
    """Build a dict with a ``__proto__`` key (filtered by the implementation)."""
    return json.loads('{"__proto__": {"id": "polluted"}}')


def test_resolve_account_entry_resolves_default_account_key():
    accounts = {"default": {"id": "default"}, "Business": {"id": "business"}}
    assert resolve_account_entry(accounts, "default") == {"id": "default"}


def test_resolve_account_entry_resolves_normalized_business_key():
    accounts = {"default": {"id": "default"}, "Business": {"id": "business"}}
    # The Python port normalizes the input key before lookup, so
    # "Business" → "business" matches the "Business" key.
    assert resolve_account_entry(accounts, "business") == {"id": "business"}


def test_resolve_account_entry_ignores_prototype_chain_values():
    polluted = _create_polluted_accounts()
    assert resolve_account_entry(polluted, "default") is None


def test_resolve_normalized_account_entry_resolves_with_custom_normalizer():
    def _normalize(account_id: str) -> str:
        return account_id.strip().lower().replace(" ", "-")

    accounts = {"Ops Team": {"id": "ops"}}
    assert resolve_normalized_account_entry(accounts, "ops-team", _normalize) == {"id": "ops"}


def test_resolve_normalized_account_entry_blocks_raw_proto_key():
    accounts = json.loads('{"__proto__": {"id": "blocked"}}')
    assert resolve_normalized_account_entry(accounts, "default", normalize_account_id) is None


def test_resolve_normalized_account_entry_blocks_keys_normalizing_to_blocked():
    accounts = {"constructor ": {"id": "blocked"}}
    assert (
        resolve_normalized_account_entry(
            accounts, "constructor", lambda v: v.strip().lower()
        )
        is None
    )


def test_resolve_normalized_account_entry_blocks_default_fallback_for_invalid_keys():
    accounts = {"constructor ": {"id": "blocked"}}
    assert resolve_normalized_account_entry(accounts, "default", normalize_account_id) is None


def test_resolve_normalized_account_entry_ignores_prototype_chain_values():
    polluted = _create_polluted_accounts()
    assert resolve_normalized_account_entry(polluted, "default", lambda v: v) is None
