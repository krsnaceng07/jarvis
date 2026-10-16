"""Data types, error codes, and models for HashiCorp Vault plugin.

OpenClaw parity: mirrors @openclaw/vault types, closed error codes,
and resolution shapes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AuthMethod = Literal["token", "token_file", "jwt", "kubernetes"]

# Error codes
VAULT_ADDR_MISSING = "VAULT_ADDR_MISSING"
AUTH_FAILED = "AUTH_FAILED"
SECRET_NOT_FOUND = "SECRET_NOT_FOUND"
FIELD_NOT_FOUND = "FIELD_NOT_FOUND"
TIMEOUT = "TIMEOUT"
VAULT_ERROR = "VAULT_ERROR"
INVALID_REF_ID = "INVALID_REF_ID"


@dataclass(frozen=True, slots=True)
class VaultAuthToken:
    """Acquired Vault client token with metadata."""

    token: str
    expires_at: float | None = None
    renewable: bool = False


@dataclass(frozen=True, slots=True)
class VaultSecretRefResolution:
    """Result of SecretRef resolution against Vault."""

    ref_id: str
    value: str | None = None
    cached: bool = False
    error: str | None = None
    error_code: str | None = None
