"""Authentication strategies for HashiCorp Vault.

OpenClaw parity: mirrors @openclaw/vault authentication methods:
- `token`: client token directly from env or config
- `token_file`: token read from sink file
- `jwt`: workload JWT file login via /v1/auth/<mount>/login
- `kubernetes`: service account token login via /v1/auth/kubernetes/login
"""

from __future__ import annotations

import json
import logging
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path

from .config import VaultConfig
from .types import AUTH_FAILED, VaultAuthToken

logger = logging.getLogger("jarvis.vault.auth")


class VaultAuthenticator:
    """Manages client token acquisition and caching for Vault operations."""

    def __init__(self, config: VaultConfig) -> None:
        self.config = config
        self._cached_token: VaultAuthToken | None = None

    def invalidate(self) -> None:
        """Clear cached client token."""
        self._cached_token = None

    async def get_client_token(self) -> tuple[str | None, str | None, str | None]:
        """Acquire a valid Vault client token.

        Returns (token, error_code, error_message).
        """
        now = time.time()
        if self._cached_token and self._cached_token.token:
            if self._cached_token.expires_at is None or now < (
                self._cached_token.expires_at - 10.0
            ):
                return self._cached_token.token, None, None

        method = self.config.auth_method

        # ── 1. Token Auth ─────────────────────────────────────────────────────
        if method == "token":
            token = self.config.token
            if not token:
                return (
                    None,
                    AUTH_FAILED,
                    "VAULT_TOKEN is missing or empty for auth method 'token'",
                )
            self._cached_token = VaultAuthToken(token=token)
            return token, None, None

        # ── 2. Token File Auth ────────────────────────────────────────────────
        if method == "token_file":
            token_path_str = self.config.token_file
            if not token_path_str:
                return (
                    None,
                    AUTH_FAILED,
                    "VAULT_TOKEN_FILE path is not configured for auth method 'token_file'",
                )
            token_path = Path(token_path_str).expanduser()
            if not token_path.exists() or not token_path.is_file():
                return (
                    None,
                    AUTH_FAILED,
                    f"Vault token file not found at {token_path}",
                )
            try:
                token = token_path.read_text(encoding="utf-8").strip()
                if not token:
                    return None, AUTH_FAILED, f"Vault token file at {token_path} is empty"
                self._cached_token = VaultAuthToken(token=token)
                return token, None, None
            except Exception as exc:
                return None, AUTH_FAILED, f"Failed to read Vault token file: {exc}"

        # ── 3. JWT & Kubernetes Auth ──────────────────────────────────────────
        if method in ("jwt", "kubernetes"):
            role = self.config.auth_role
            if not role:
                return (
                    None,
                    AUTH_FAILED,
                    f"OPENCLAW_VAULT_AUTH_ROLE is required for auth method '{method}'",
                )

            jwt_path_str = self.config.get_effective_jwt_file()
            if not jwt_path_str:
                return (
                    None,
                    AUTH_FAILED,
                    f"JWT/workload token file path is not configured for auth method '{method}'",
                )

            jwt_path = Path(jwt_path_str).expanduser()
            if not jwt_path.exists() or not jwt_path.is_file():
                return (
                    None,
                    AUTH_FAILED,
                    f"JWT token file not found at {jwt_path}",
                )

            try:
                jwt_token = jwt_path.read_text(encoding="utf-8").strip()
                if not jwt_token:
                    return None, AUTH_FAILED, f"JWT token file at {jwt_path} is empty"
            except Exception as exc:
                return None, AUTH_FAILED, f"Failed to read JWT token file: {exc}"

            mount = self.config.get_effective_auth_mount()
            login_url = f"{self.config.vault_addr}/v1/auth/{mount}/login"

            payload = {"role": role, "jwt": jwt_token}
            login_data = json.dumps(payload).encode("utf-8")

            headers = {
                "Content-Type": "application/json",
                "User-Agent": "OpenClaw-Vault/1.0",
            }
            if self.config.namespace:
                headers["X-Vault-Namespace"] = self.config.namespace

            timeout_sec = self.config.timeout_ms / 1000.0
            ssl_ctx = None
            if self.config.ca_cert:
                ssl_ctx = ssl.create_default_context(cafile=self.config.ca_cert)

            try:
                req = urllib.request.Request(
                    login_url,
                    data=login_data,
                    headers=headers,
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=timeout_sec, context=ssl_ctx) as resp:
                    resp_bytes = resp.read()
                    resp_data = json.loads(resp_bytes.decode("utf-8"))

                auth_data = resp_data.get("auth") or {}
                client_token = auth_data.get("client_token")
                if not client_token:
                    return (
                        None,
                        AUTH_FAILED,
                        "Vault login response did not contain 'auth.client_token'",
                    )

                lease_duration = float(auth_data.get("lease_duration") or 0.0)
                expires_at = (now + lease_duration) if lease_duration > 0 else None
                renewable = bool(auth_data.get("renewable", False))

                self._cached_token = VaultAuthToken(
                    token=client_token,
                    expires_at=expires_at,
                    renewable=renewable,
                )
                return client_token, None, None

            except urllib.error.HTTPError as http_err:
                err_body = ""
                try:
                    err_body = http_err.read().decode("utf-8", errors="replace")
                except Exception:
                    pass
                return (
                    None,
                    AUTH_FAILED,
                    f"Vault login HTTP {http_err.code} to {login_url}: {err_body or http_err.reason}",
                )
            except Exception as exc:
                return (
                    None,
                    AUTH_FAILED,
                    f"Vault login error ({login_url}): {exc}",
                )

        return None, AUTH_FAILED, f"Unsupported auth method '{method}'"
