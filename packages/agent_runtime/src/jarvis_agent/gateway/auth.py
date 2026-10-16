"""Authentication, credential verification, and rate limiting for Track 3.4."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import datetime
import hashlib
import time

from jarvis_agent.gateway.errors import GatewayErrorCode, GatewayException
from jarvis_agent.gateway.models import ClientIdentity


@dataclass(frozen=True, slots=True)
class CredentialRecord:
    """Stored credential metadata."""

    credential_id: str
    token_hash: str  # SHA-256 hash of secret token
    user_id: str
    client_type: str
    auth_tier: str = "user"
    scopes: frozenset[str] = field(default_factory=lambda: frozenset(["read", "write"]))
    issued_at_utc: str = ""
    expires_at_utc: str | None = None
    revoked_at_utc: str | None = None

    def is_valid(self, now_utc: datetime.datetime | None = None) -> bool:
        """Check if credential is not revoked and not expired."""
        if self.revoked_at_utc:
            return False
        if self.expires_at_utc:
            now = now_utc or datetime.datetime.now(datetime.timezone.utc)
            try:
                exp = datetime.datetime.fromisoformat(self.expires_at_utc)
                if now >= exp:
                    return False
            except Exception:
                return False
        return True


class CredentialStore:
    """Thread-safe credential repository for Gateway authentication."""

    def __init__(self) -> None:
        self._credentials: dict[str, CredentialRecord] = {}

    def register_credential(
        self,
        raw_token: str,
        user_id: str,
        client_type: str,
        auth_tier: str = "user",
        scopes: frozenset[str] | None = None,
        expires_at_utc: str | None = None,
    ) -> CredentialRecord:
        """Register a new secret token and store its hash."""
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        cred_id = f"cred_{token_hash[:12]}"
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        rec = CredentialRecord(
            credential_id=cred_id,
            token_hash=token_hash,
            user_id=user_id,
            client_type=client_type,
            auth_tier=auth_tier,
            scopes=scopes or frozenset(["read", "write"]),
            issued_at_utc=now_str,
            expires_at_utc=expires_at_utc,
        )
        self._credentials[token_hash] = rec
        return rec

    def revoke_credential(self, token_hash_or_id: str) -> bool:
        """Revoke a credential by hash or ID."""
        for h, rec in list(self._credentials.items()):
            if h == token_hash_or_id or rec.credential_id == token_hash_or_id:
                now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
                revoked = CredentialRecord(
                    credential_id=rec.credential_id,
                    token_hash=rec.token_hash,
                    user_id=rec.user_id,
                    client_type=rec.client_type,
                    auth_tier=rec.auth_tier,
                    scopes=rec.scopes,
                    issued_at_utc=rec.issued_at_utc,
                    expires_at_utc=rec.expires_at_utc,
                    revoked_at_utc=now_str,
                )
                self._credentials[h] = revoked
                return True
        return False

    def authenticate(self, raw_token: str) -> ClientIdentity:
        """Verify token and return ClientIdentity, or raise GatewayException."""
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        rec = self._credentials.get(token_hash)
        if not rec or not rec.is_valid():
            raise GatewayException(
                code=GatewayErrorCode.AUTH_FAILED,
                message="Invalid, expired, or revoked authentication credentials.",
            )
        return ClientIdentity(
            user_id=rec.user_id,
            client_id=rec.credential_id,
            client_type=rec.client_type,
            auth_tier=rec.auth_tier,
            scopes=rec.scopes,
        )


class SlidingWindowRateLimiter:
    """Sliding-window rate limiter per identity and method."""

    def __init__(self, default_limit: int = 100, window_seconds: float = 60.0) -> None:
        self.default_limit = default_limit
        self.window_seconds = window_seconds
        # key -> list of timestamp floats
        self._history: dict[str, list[float]] = defaultdict(list)

    def check_and_record(
        self,
        identifier: str,
        method: str,
        limit: int | None = None,
    ) -> None:
        """Check if request is within rate limit; raises GatewayException if exceeded."""
        effective_limit = limit if limit is not None else self.default_limit
        now = time.monotonic()
        key = f"{identifier}:{method}"
        history = self._history[key]

        # Evict timestamps outside the window
        cutoff = now - self.window_seconds
        self._history[key] = [t for t in history if t > cutoff]

        if len(self._history[key]) >= effective_limit:
            raise GatewayException(
                code=GatewayErrorCode.RATE_LIMITED,
                message=f"Rate limit exceeded for method '{method}' ({effective_limit} req/{int(self.window_seconds)}s).",
                data={"method": method, "limit": effective_limit, "window": self.window_seconds},
            )

        self._history[key].append(now)


__all__ = [
    "CredentialRecord",
    "CredentialStore",
    "SlidingWindowRateLimiter",
]
