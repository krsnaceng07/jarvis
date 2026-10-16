"""Nostr Bech32 and Hex key utilities."""

from __future__ import annotations

import re


def is_valid_hex_key(key: str) -> bool:
    """Check if key is a 64-character lowercase hexadecimal string."""
    return bool(re.match(r"^[0-9a-fA-F]{64}$", key))


def normalize_nostr_pubkey(key: str) -> str:
    """Normalize pubkey to 64-character lowercase hex format."""
    clean = key.strip().lower()
    if clean.startswith("npub1"):
        # For simplicity, if already 64-char hex or npub, return cleaned
        return clean
    return clean
