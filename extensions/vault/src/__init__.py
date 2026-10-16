"""HashiCorp Vault plugin implementation package."""

from __future__ import annotations

from .auth import VaultAuthenticator
from .client import VaultClient
from .config import VaultConfig, resolve_vault_config
from .doctor import run_vault_doctor_checks
from .secretref import (
    VaultSecretRefResolver,
    VaultSetupPlan,
    build_vault_setup_plan,
    parse_vault_secret_ref,
)
from .types import (
    AUTH_FAILED,
    FIELD_NOT_FOUND,
    INVALID_REF_ID,
    SECRET_NOT_FOUND,
    TIMEOUT,
    VAULT_ADDR_MISSING,
    VAULT_ERROR,
    AuthMethod,
    VaultAuthToken,
    VaultSecretRefResolution,
)

__all__ = [
    "AUTH_FAILED",
    "AuthMethod",
    "FIELD_NOT_FOUND",
    "INVALID_REF_ID",
    "SECRET_NOT_FOUND",
    "TIMEOUT",
    "VAULT_ADDR_MISSING",
    "VAULT_ERROR",
    "VaultAuthToken",
    "VaultAuthenticator",
    "VaultClient",
    "VaultConfig",
    "VaultSecretRefResolution",
    "VaultSecretRefResolver",
    "VaultSetupPlan",
    "build_vault_setup_plan",
    "parse_vault_secret_ref",
    "resolve_vault_config",
    "run_vault_doctor_checks",
]
