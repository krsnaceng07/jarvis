"""jarvis.routing.account_id — canonical account-id normalization.

OpenClaw parity: mirrors ``src/routing/account-id.ts`` exactly:
same regexes, same bounded FIFO caches (max 512), same
blocked-object-key handling.
"""

from __future__ import annotations

import re
from collections import OrderedDict

from .prototype_keys import is_blocked_object_key

DEFAULT_ACCOUNT_ID = "default"

_VALID_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$", re.IGNORECASE)
_INVALID_CHARS_RE = re.compile(r"[^a-z0-9_-]+")
_LEADING_DASH_RE = re.compile(r"^-+")
_TRAILING_DASH_RE = re.compile(r"-+$")

_MAX_CACHE_ENTRIES = 512
_normalize_cache: OrderedDict[str, str] = OrderedDict()
_optional_cache: OrderedDict[str, str | None] = OrderedDict()


def _cache_set(cache: OrderedDict, key: str, value: object) -> None:
    # Bounded FIFO (mirrors the TS Map + delete-oldest-key behavior).
    if key in cache:
        cache.pop(key)
    elif len(cache) >= _MAX_CACHE_ENTRIES:
        cache.popitem(last=False)
    cache[key] = value


def canonicalize_account_id(trimmed: str) -> str:
    """Canonicalize a pre-trimmed account id (may return "")."""
    if _VALID_ID_RE.match(trimmed):
        return trimmed.lower()
    cleaned = _INVALID_CHARS_RE.sub("-", trimmed.lower())
    cleaned = _LEADING_DASH_RE.sub("", cleaned)
    cleaned = _TRAILING_DASH_RE.sub("", cleaned)
    return cleaned[:64]


def _normalize_canonical_account_id(trimmed: str) -> str | None:
    canonical = canonicalize_account_id(trimmed)
    if not canonical or is_blocked_object_key(canonical):
        return None
    return canonical


def normalize_account_id(value: object) -> str:
    """Normalize to a canonical account id, falling back to ``"default"``.

    Mirrors ``normalizeAccountId``.
    """
    trimmed = (value if isinstance(value, str) else "").strip()
    if not trimmed:
        return DEFAULT_ACCOUNT_ID
    if trimmed in _normalize_cache:
        return _normalize_cache[trimmed]
    resolved = _normalize_canonical_account_id(trimmed) or DEFAULT_ACCOUNT_ID
    _cache_set(_normalize_cache, trimmed, resolved)
    return resolved


def normalize_optional_account_id(value: object) -> str | None:
    """Normalize to a canonical account id, or ``None`` when empty/invalid.

    Mirrors ``normalizeOptionalAccountId``.
    """
    trimmed = (value if isinstance(value, str) else "").strip()
    if not trimmed:
        return None
    if trimmed in _optional_cache:
        return _optional_cache[trimmed]
    resolved = _normalize_canonical_account_id(trimmed)
    _cache_set(_optional_cache, trimmed, resolved)
    return resolved


__all__ = [
    "DEFAULT_ACCOUNT_ID",
    "canonicalize_account_id",
    "normalize_account_id",
    "normalize_optional_account_id",
]
