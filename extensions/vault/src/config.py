"""Configuration resolution for HashiCorp Vault plugin.

OpenClaw parity: mirrors @openclaw/vault environment variable discovery,
defaults (KV v2, mount 'secret'), auth method defaults, and config schemas.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from .types import AuthMethod

DEFAULT_KV_MOUNT = "secret"
DEFAULT_KV_VERSION = 2
DEFAULT_TIMEOUT_MS = 15000
DEFAULT_KUBERNETES_JWT_FILE = "/var/run/secrets/kubernetes.io/serviceaccount/token"


@dataclass(frozen=True, slots=True)
class VaultConfig:
    """HashiCorp Vault connection and authentication configuration."""

    vault_addr: str = ""
    auth_method: AuthMethod = "token"
    token: str | None = None
    token_file: str | None = None
    auth_mount: str | None = None
    auth_role: str | None = None
    jwt_file: str | None = None
    namespace: str | None = None
    kv_mount: str = DEFAULT_KV_MOUNT
    kv_version: int = DEFAULT_KV_VERSION
    timeout_ms: int = DEFAULT_TIMEOUT_MS
    ca_cert: str | None = None

    def get_effective_auth_mount(self) -> str:
        """Return the effective auth endpoint mount."""
        if self.auth_mount:
            return self.auth_mount.strip("/")
        if self.auth_method == "jwt":
            return "jwt"
        if self.auth_method == "kubernetes":
            return "kubernetes"
        return "jwt"

    def get_effective_jwt_file(self) -> str | None:
        """Return the effective JWT/workload token file path."""
        if self.jwt_file:
            return self.jwt_file
        if self.auth_method == "kubernetes":
            return DEFAULT_KUBERNETES_JWT_FILE
        return None


def resolve_vault_config(
    raw: dict[str, Any] | None = None,
    env: dict[str, str] | None = None,
) -> VaultConfig:
    """Resolve VaultConfig merging dictionary settings with environment variables."""
    e = os.environ if env is None else env
    cfg_dict = raw or {}

    # 1. Vault Address
    vault_addr = (
        (cfg_dict.get("vaultAddr") or cfg_dict.get("vault_addr") or e.get("VAULT_ADDR") or "")
        .strip()
        .rstrip("/")
    )

    # 2. Auth Method
    raw_auth = (
        (
            cfg_dict.get("authMethod")
            or cfg_dict.get("auth_method")
            or e.get("OPENCLAW_VAULT_AUTH_METHOD")
            or e.get("JARVIS_VAULT_AUTH_METHOD")
            or "token"
        )
        .strip()
        .lower()
    )

    auth_method: AuthMethod = (
        raw_auth if raw_auth in ("token", "token_file", "jwt", "kubernetes") else "token"
    )

    # 3. Direct Token
    token = cfg_dict.get("token") or e.get("VAULT_TOKEN") or None
    if token:
        token = token.strip()

    # 4. Token File
    token_file = (
        cfg_dict.get("tokenFile")
        or cfg_dict.get("token_file")
        or e.get("VAULT_TOKEN_FILE")
        or e.get("OPENCLAW_VAULT_TOKEN_FILE")
        or None
    )
    if token_file:
        token_file = token_file.strip()

    # 5. Auth Mount & Role
    auth_mount = (
        cfg_dict.get("authMount")
        or cfg_dict.get("auth_mount")
        or e.get("OPENCLAW_VAULT_AUTH_MOUNT")
        or None
    )
    if auth_mount:
        auth_mount = auth_mount.strip()

    auth_role = (
        cfg_dict.get("authRole")
        or cfg_dict.get("auth_role")
        or e.get("OPENCLAW_VAULT_AUTH_ROLE")
        or None
    )
    if auth_role:
        auth_role = auth_role.strip()

    # 6. JWT File
    jwt_file = (
        cfg_dict.get("jwtFile")
        or cfg_dict.get("jwt_file")
        or e.get("OPENCLAW_VAULT_JWT_FILE")
        or e.get("VAULT_JWT_FILE")
        or None
    )
    if jwt_file:
        jwt_file = jwt_file.strip()

    # 7. Namespace
    namespace = (
        cfg_dict.get("namespace")
        or e.get("VAULT_NAMESPACE")
        or e.get("OPENCLAW_VAULT_NAMESPACE")
        or None
    )
    if namespace:
        namespace = namespace.strip()

    # 8. KV Mount & Version
    kv_mount = (
        (
            cfg_dict.get("kvMount")
            or cfg_dict.get("kv_mount")
            or e.get("OPENCLAW_VAULT_KV_MOUNT")
            or e.get("JARVIS_VAULT_KV_MOUNT")
            or DEFAULT_KV_MOUNT
        )
        .strip()
        .strip("/")
    )

    raw_kv_ver = (
        cfg_dict.get("kvVersion")
        if "kvVersion" in cfg_dict
        else cfg_dict.get(
            "kv_version",
            e.get(
                "OPENCLAW_VAULT_KV_VERSION", e.get("JARVIS_VAULT_KV_VERSION", DEFAULT_KV_VERSION)
            ),
        )
    )
    try:
        kv_version = int(raw_kv_ver)
        if kv_version not in (1, 2):
            kv_version = DEFAULT_KV_VERSION
    except (ValueError, TypeError):
        kv_version = DEFAULT_KV_VERSION

    # 9. Timeout
    timeout_ms = int(cfg_dict.get("timeoutMs") or cfg_dict.get("timeout_ms") or DEFAULT_TIMEOUT_MS)

    # 10. CA Cert
    ca_cert = (
        cfg_dict.get("caCert")
        or cfg_dict.get("ca_cert")
        or e.get("NODE_EXTRA_CA_CERTS")
        or e.get("VAULT_CACERT")
        or e.get("SSL_CERT_FILE")
        or None
    )
    if ca_cert:
        ca_cert = ca_cert.strip()

    return VaultConfig(
        vault_addr=vault_addr,
        auth_method=auth_method,
        token=token,
        token_file=token_file,
        auth_mount=auth_mount,
        auth_role=auth_role,
        jwt_file=jwt_file,
        namespace=namespace,
        kv_mount=kv_mount,
        kv_version=kv_version,
        timeout_ms=timeout_ms,
        ca_cert=ca_cert,
    )
