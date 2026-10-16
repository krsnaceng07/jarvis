"""HTTP Vault client for reading KV v1 and KV v2 secrets.

OpenClaw parity: mirrors @openclaw/vault HTTP REST client:
- KV v2 reads: GET /v1/<kvMount>/data/<path> -> data.data.<field>
- KV v1 reads: GET /v1/<kvMount>/<path> -> data.<field>
- Support for namespaces via X-Vault-Namespace
- Error handling with closed error codes: VAULT_ADDR_MISSING, AUTH_FAILED,
  SECRET_NOT_FOUND, FIELD_NOT_FOUND, TIMEOUT, VAULT_ERROR
"""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
import urllib.error
import urllib.request

from .auth import VaultAuthenticator
from .config import VaultConfig
from .types import (
    AUTH_FAILED,
    FIELD_NOT_FOUND,
    SECRET_NOT_FOUND,
    TIMEOUT,
    VAULT_ADDR_MISSING,
    VAULT_ERROR,
    VaultSecretRefResolution,
)

logger = logging.getLogger("jarvis.vault.client")

VAULT_SEMAPHORE = asyncio.Semaphore(10)


class VaultClient:
    """HTTP client for HashiCorp Vault secrets engine."""

    def __init__(
        self,
        config: VaultConfig,
        authenticator: VaultAuthenticator | None = None,
    ) -> None:
        self.config = config
        self.auth = authenticator or VaultAuthenticator(config=config)
        self._cache: dict[str, str] = {}

    def invalidate_cache(self) -> None:
        """Clear cached secret values and auth tokens."""
        self._cache.clear()
        self.auth.invalidate()

    async def read_secret(
        self,
        path: str,
        field_name: str,
        use_cache: bool = True,
    ) -> VaultSecretRefResolution:
        """Read a single field from a Vault KV secret path.

        Returns VaultSecretRefResolution.
        """
        ref_id = f"{path}/{field_name}"

        # 1. Check in-memory cache
        if use_cache and ref_id in self._cache:
            return VaultSecretRefResolution(
                ref_id=ref_id,
                value=self._cache[ref_id],
                cached=True,
            )

        # 2. Check Vault Address
        if not self.config.vault_addr:
            return VaultSecretRefResolution(
                ref_id=ref_id,
                error="VAULT_ADDR is missing or empty. Set VAULT_ADDR environment variable.",
                error_code=VAULT_ADDR_MISSING,
            )

        # 3. Obtain client token
        token, auth_err_code, auth_err_msg = await self.auth.get_client_token()
        if auth_err_code or not token:
            return VaultSecretRefResolution(
                ref_id=ref_id,
                error=auth_err_msg or "Failed to authenticate with Vault",
                error_code=auth_err_code or AUTH_FAILED,
            )

        # 4. Construct URL based on KV version
        clean_path = path.strip("/")
        mount = self.config.kv_mount

        if self.config.kv_version == 2:
            url = f"{self.config.vault_addr}/v1/{mount}/data/{clean_path}"
        else:
            url = f"{self.config.vault_addr}/v1/{mount}/{clean_path}"

        headers = {
            "X-Vault-Token": token,
            "User-Agent": "OpenClaw-Vault/1.0",
        }
        if self.config.namespace:
            headers["X-Vault-Namespace"] = self.config.namespace

        timeout_sec = self.config.timeout_ms / 1000.0
        ssl_ctx = None
        if self.config.ca_cert:
            ssl_ctx = ssl.create_default_context(cafile=self.config.ca_cert)

        async with VAULT_SEMAPHORE:
            try:
                loop = asyncio.get_running_loop()
                resp_bytes = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: self._execute_http_get(url, headers, timeout_sec, ssl_ctx),
                    ),
                    timeout=timeout_sec + 1.0,
                )

                resp_data = json.loads(resp_bytes.decode("utf-8"))

                # Extract secret data based on KV version
                if self.config.kv_version == 2:
                    data_wrapper = resp_data.get("data")
                    if isinstance(data_wrapper, dict):
                        secret_data = data_wrapper.get("data")
                    else:
                        secret_data = None
                else:
                    secret_data = resp_data.get("data")

                if not isinstance(secret_data, dict):
                    return VaultSecretRefResolution(
                        ref_id=ref_id,
                        error=f"Unexpected response structure from Vault at {url}",
                        error_code=VAULT_ERROR,
                    )

                if field_name not in secret_data:
                    avail = list(secret_data.keys())
                    return VaultSecretRefResolution(
                        ref_id=ref_id,
                        error=f"Field '{field_name}' not found at Vault path '{path}'. Available fields: {avail}",
                        error_code=FIELD_NOT_FOUND,
                    )

                raw_val = secret_data[field_name]
                str_val = str(raw_val) if raw_val is not None else ""

                # Cache and return
                self._cache[ref_id] = str_val
                return VaultSecretRefResolution(
                    ref_id=ref_id,
                    value=str_val,
                    cached=False,
                )

            except asyncio.TimeoutError:
                return VaultSecretRefResolution(
                    ref_id=ref_id,
                    error=f"Vault read request to {url} timed out after {timeout_sec:.1f}s",
                    error_code=TIMEOUT,
                )
            except urllib.error.HTTPError as http_err:
                err_body = ""
                try:
                    err_body = http_err.read().decode("utf-8", errors="replace")
                except Exception:
                    pass

                if http_err.code == 404:
                    return VaultSecretRefResolution(
                        ref_id=ref_id,
                        error=f"Secret not found at Vault path '{path}' (HTTP 404)",
                        error_code=SECRET_NOT_FOUND,
                    )
                if http_err.code in (401, 403):
                    # Invalidate cached token on auth failure
                    self.auth.invalidate()
                    return VaultSecretRefResolution(
                        ref_id=ref_id,
                        error=f"Access denied to Vault path '{path}' (HTTP {http_err.code}): {err_body or http_err.reason}",
                        error_code=AUTH_FAILED,
                    )

                return VaultSecretRefResolution(
                    ref_id=ref_id,
                    error=f"Vault API error HTTP {http_err.code} for {url}: {err_body or http_err.reason}",
                    error_code=VAULT_ERROR,
                )
            except Exception as exc:
                return VaultSecretRefResolution(
                    ref_id=ref_id,
                    error=f"Failed to query Vault ({url}): {exc}",
                    error_code=VAULT_ERROR,
                )

    def _execute_http_get(
        self,
        url: str,
        headers: dict[str, str],
        timeout_sec: float,
        ssl_ctx: ssl.SSLContext | None,
    ) -> bytes:
        """Synchronous HTTP GET executed in thread executor."""
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=timeout_sec, context=ssl_ctx) as resp:
            return resp.read()
