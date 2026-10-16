"""HashiCorp Vault infra plugin for JARVIS / OpenClaw."""

from __future__ import annotations

from .plugin import VaultPlugin, entry, vault_plugin
from .src.auth import VaultAuthenticator
from .src.client import VaultClient
from .src.config import VaultConfig, resolve_vault_config
from .src.doctor import run_vault_doctor_checks
from .src.secretref import (
    VaultSecretRefResolver,
    VaultSetupPlan,
    build_vault_setup_plan,
    parse_vault_secret_ref,
)
from .src.types import (
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
    "VaultPlugin",
    "VaultSecretRefResolution",
    "VaultSecretRefResolver",
    "VaultSetupPlan",
    "build_vault_setup_plan",
    "entry",
    "parse_vault_secret_ref",
    "resolve_vault_config",
    "run_vault_doctor_checks",
    "vault_plugin",
]
