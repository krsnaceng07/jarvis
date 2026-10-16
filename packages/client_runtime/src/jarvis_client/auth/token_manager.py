"""Credential lifecycle and token management for Track 3.5.

Enforces 6-state lifecycle:
ISSUED -> ACTIVE -> EXPIRING -> REFRESHING -> EXPIRED / REVOKED / INVALID.
Zero plaintext secret leakage into logs or exceptions.
"""

from __future__ import annotations

import datetime
from enum import Enum
import hashlib
from typing import Callable


class CredentialState(str, Enum):
    """Lifecycle state of an authentication token."""

    ISSUED = "issued"
    ACTIVE = "active"
    EXPIRING = "expiring"
    REFRESHING = "refreshing"
    EXPIRED = "expired"
    REVOKED = "revoked"
    INVALID = "invalid"


class TokenManager:
    """Safely manages authentication tokens, expiry detection, and refresh workflows."""

    def __init__(
        self,
        token: str,
        user_id: str,
        expires_at_utc: str | None = None,
        refresh_threshold_seconds: float = 60.0,
        refresh_cb: Callable[[], str | None] | None = None,
    ) -> None:
        self._token = token
        self.user_id = user_id
        self.expires_at_utc = expires_at_utc
        self.refresh_threshold_seconds = refresh_threshold_seconds
        self.refresh_cb = refresh_cb
        self._state = CredentialState.ACTIVE

    @property
    def token_masked(self) -> str:
        """Safe masked fingerprint for logs and diagnostics (e.g. 'tok_abc...f92')."""
        if not self._token:
            return "[NO_TOKEN]"
        digest = hashlib.sha256(self._token.encode("utf-8")).hexdigest()[:8]
        return f"tok_{self._token[:4]}...{digest}"

    masked_token = token_masked

    @property
    def current_state(self) -> CredentialState:
        self._evaluate_state()
        return self._state

    @property
    def state(self) -> CredentialState:
        return self.current_state

    def get_token(self) -> str:
        """Obtain raw token for authenticated frame construction."""
        self._evaluate_state()
        if self._state in (
            CredentialState.EXPIRED,
            CredentialState.REVOKED,
            CredentialState.INVALID,
        ):
            raise PermissionError(f"Token is unusable ({self._state.value}).")
        return self._token

    def _evaluate_state(self) -> None:
        if not self.expires_at_utc:
            return
        now = datetime.datetime.now(datetime.timezone.utc)
        try:
            exp = datetime.datetime.fromisoformat(self.expires_at_utc)
        except Exception:
            self._state = CredentialState.INVALID
            return

        remaining = (exp - now).total_seconds()
        if remaining <= 0:
            self._state = CredentialState.EXPIRED
        elif remaining <= self.refresh_threshold_seconds:
            self._state = CredentialState.EXPIRING

    def refresh(self) -> bool:
        """Attempt to refresh token before expiry."""
        if not self.refresh_cb:
            return False
        self._state = CredentialState.REFRESHING
        try:
            new_token = self.refresh_cb()
            if new_token:
                self._token = new_token
                self._state = CredentialState.ACTIVE
                return True
            else:
                self._state = CredentialState.EXPIRED
                return False
        except Exception:
            self._state = CredentialState.EXPIRED
            return False

    def revoke(self) -> None:
        self._state = CredentialState.REVOKED
        self._token = ""


__all__ = ["CredentialState", "TokenManager"]
