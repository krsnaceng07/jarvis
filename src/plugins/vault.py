"""jarvis.plugins.vault — HashiCorp Vault plugin & SecretRef resolver integration.

OpenClaw parity: mirrors
``openclaw-main/extensions/vault/src/cli.ts`` and
``openclaw-main/extensions/vault/vault-secret-id.d.ts``.

Features:
- `VAULT_PLUGIN_ID`: `"vault"`
- `VaultAuthMethod`: `"token"` | `"token_file"` | `"jwt"` | `"kubernetes"`
- `parse_vault_secret_id()`: Parses `<vault-secret-path>/<field>` into `(secret_path, field_name)`.
- `build_vault_kv_read_path()`: Formats Vault API HTTP endpoint for KV v1 or KV v2.
- `VaultConfig`: Dataclass resolving Vault environment variables & auth mode.
- `resolve_vault_config()`: Resolves Vault configuration from environment variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

VAULT_PLUGIN_ID: str = "vault"
VaultAuthMethod = Literal["token", "token_file", "jwt", "kubernetes"]


@dataclass
class VaultConfig:
    addr: str
    auth_method: VaultAuthMethod = "token"
    token: str | None = None
    token_file: str | None = None
    jwt_file: str | None = None
    auth_role: str | None = None
    auth_mount: str | None = None
    kv_mount: str = "secret"
    kv_version: int = 2
    namespace: str | None = None


def parse_vault_secret_id(secret_id: str) -> tuple[str, str]:
    """Parse a Vault SecretRef id '<path>/<field>' into (secret_path, field_name)."""
    if not secret_id or not isinstance(secret_id, str):
        raise ValueError("Vault SecretRef id must be a non-empty string")

    clean = secret_id.strip()
    if "/" not in clean:
        raise ValueError(
            f"Invalid Vault SecretRef id '{secret_id}'. Expected format '<secret-path>/<field>'."
        )

    slash_idx = clean.rfind("/")
    secret_path = clean[:slash_idx].strip()
    field_name = clean[slash_idx + 1 :].strip()

    if not secret_path or not field_name:
        raise ValueError(
            f"Invalid Vault SecretRef id '{secret_id}'. Path and field name cannot be empty."
        )

    return secret_path, field_name


def build_vault_kv_read_path(secret_path: str, kv_mount: str = "secret", kv_version: int = 2) -> str:
    """Build the Vault HTTP API read path for a secret given KV mount and version."""
    clean_mount = kv_mount.strip().strip("/")
    clean_path = secret_path.strip().strip("/")

    if kv_version == 2:
        return f"/v1/{clean_mount}/data/{clean_path}"
    return f"/v1/{clean_mount}/{clean_path}"


def resolve_vault_config(env: dict[str, str] | None = None) -> VaultConfig:
    """Resolve Vault configuration from environment variables."""
    source_env = env if isinstance(env, dict) else os.environ

    addr = source_env.get("VAULT_ADDR", "").strip()
    raw_method = str(
        source_env.get("OPENCLAW_VAULT_AUTH_METHOD")
        or source_env.get("JARVIS_VAULT_AUTH_METHOD")
        or "token"
    ).lower()

    auth_method: VaultAuthMethod = (
        raw_method if raw_method in ("token", "token_file", "jwt", "kubernetes") else "token"  # type: ignore[assignment]
    )

    kv_mount = (
        source_env.get("OPENCLAW_VAULT_KV_MOUNT")
        or source_env.get("JARVIS_VAULT_KV_MOUNT")
        or "secret"
    ).strip()

    raw_version = (
        source_env.get("OPENCLAW_VAULT_KV_VERSION")
        or source_env.get("JARVIS_VAULT_KV_VERSION")
        or "2"
    )
    kv_version = 2 if str(raw_version).strip() != "1" else 1

    return VaultConfig(
        addr=addr,
        auth_method=auth_method,
        token=source_env.get("VAULT_TOKEN"),
        token_file=source_env.get("VAULT_TOKEN_FILE"),
        jwt_file=source_env.get("OPENCLAW_VAULT_JWT_FILE") or source_env.get("JARVIS_VAULT_JWT_FILE"),
        auth_role=source_env.get("OPENCLAW_VAULT_AUTH_ROLE") or source_env.get("JARVIS_VAULT_AUTH_ROLE"),
        auth_mount=source_env.get("OPENCLAW_VAULT_AUTH_MOUNT") or source_env.get("JARVIS_VAULT_AUTH_MOUNT"),
        kv_mount=kv_mount,
        kv_version=kv_version,
        namespace=source_env.get("VAULT_NAMESPACE"),
    )


__all__ = [
    "VAULT_PLUGIN_ID",
    "VaultAuthMethod",
    "VaultConfig",
    "build_vault_kv_read_path",
    "parse_vault_secret_id",
    "resolve_vault_config",
]
