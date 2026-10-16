"""Vault infra plugin definition and SecretRef resolver.

OpenClaw parity: mirrors @openclaw/vault infra extension:
- Managed exec SecretRef provider for HashiCorp Vault
- KV v1 and KV v2 engine support
- HTTP REST client with token, token_file, JWT, and Kubernetes auth
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin

from .src.client import VaultClient
from .src.config import resolve_vault_config
from .src.doctor import run_vault_doctor_checks
from .src.secretref import VaultSecretRefResolver
from .src.types import VaultSecretRefResolution


@dataclass(frozen=True, slots=True)
class VaultPlugin(Plugin):
    """Vault infra plugin descriptor."""

    id: str = "vault"
    name: str = "Vault"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "HashiCorp Vault SecretRefs provider."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any = None) -> None:
        """Initialize plugin runtime and SecretRef resolver."""
        raw_config = getattr(ctx, "config", {}) if ctx else {}
        if isinstance(raw_config, dict) and "plugins" in raw_config:
            raw_config = (
                raw_config.get("plugins", {}).get("entries", {}).get("vault", {}).get("config", {})
            )
        elif isinstance(raw_config, dict) and "vault" in raw_config:
            raw_config = raw_config["vault"]

        config = resolve_vault_config(raw_config)
        client = VaultClient(config=config)
        resolver = VaultSecretRefResolver(config=config, client=client)

        self.metadata["config"] = config
        self.metadata["client"] = client
        self.metadata["resolver"] = resolver

        # Register doctor contract
        if hasattr(ctx, "register_doctor_contract"):
            ctx.register_doctor_contract(
                "vault",
                lambda raw_cfg, fix=False: run_vault_doctor_checks(
                    raw_config=raw_cfg,
                ),
            )

        # Register secretref provider
        if hasattr(ctx, "register_secretref_provider"):
            ctx.register_secretref_provider(
                "vault",
                resolver.resolve,
            )

    async def resolve_secret_ref(self, ref_id: str) -> VaultSecretRefResolution:
        """Resolve a Vault secret reference ID."""
        resolver: VaultSecretRefResolver = self.metadata.get("resolver") or VaultSecretRefResolver()
        return await resolver.resolve(ref_id)


vault_plugin = VaultPlugin()
entry = vault_plugin
