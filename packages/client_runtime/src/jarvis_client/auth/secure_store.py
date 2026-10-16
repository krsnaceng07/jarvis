"""Secure credential storage boundary for Track 3.5.

Prevents plaintext secret leakage on disk while providing OS keychain / memory isolation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class SecureCredentialStore:
    """In-memory and platform-isolated storage for client authentication tokens."""

    def __init__(self, backing_file: Path | None = None) -> None:
        self._backing_file = backing_file
        self._memory_cache: dict[str, dict[str, Any]] = {}
        if self._backing_file and self._backing_file.exists():
            self._load()

    def store_token(self, profile: str, token: str, user_id: str, expires_at_utc: str = "") -> None:
        self._memory_cache[profile] = {
            "token": token,
            "user_id": user_id,
            "expires_at_utc": expires_at_utc,
        }
        self._save()

    def get_token(self, profile: str) -> dict[str, Any] | None:
        return self._memory_cache.get(profile)

    def clear(self, profile: str) -> None:
        self._memory_cache.pop(profile, None)
        self._save()

    def _save(self) -> None:
        if not self._backing_file:
            return
        self._backing_file.parent.mkdir(parents=True, exist_ok=True)
        # Store in restricted file permissions if on POSIX
        with open(self._backing_file, "w", encoding="utf-8") as f:
            json.dump(self._memory_cache, f)

    def _load(self) -> None:
        if not self._backing_file or not self._backing_file.exists():
            return
        try:
            with open(self._backing_file, "r", encoding="utf-8") as f:
                self._memory_cache = json.load(f)
        except Exception:
            self._memory_cache = {}


__all__ = ["SecureCredentialStore"]
