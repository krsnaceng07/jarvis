"""SecretRef parser, resolver, and setup plan generator for HashiCorp Vault.

OpenClaw parity: mirrors @openclaw/vault SecretRef mechanics:
- ID format: <vault-secret-path>/<field>
- Setup plan builder for model providers and arbitrary target paths.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .client import VaultClient
from .config import VaultConfig, resolve_vault_config
from .types import INVALID_REF_ID, VaultSecretRefResolution

logger = logging.getLogger("jarvis.vault.secretref")


def parse_vault_secret_ref(ref_id: str) -> tuple[str, str]:
    """Parse `<vault-secret-path>/<field>` into (path, field).

    Splits on the last `/`.
    """
    trimmed = ref_id.strip().strip("/")
    if not trimmed or "/" not in trimmed:
        raise ValueError(
            f"Invalid Vault SecretRef ID '{ref_id}'. Format must be '<vault-secret-path>/<field>'"
        )

    parts = trimmed.rsplit("/", 1)
    path = parts[0]
    field = parts[1]

    if not path or not field:
        raise ValueError(f"Invalid Vault SecretRef ID '{ref_id}'. Path and field cannot be empty")

    return path, field


@dataclass(frozen=True, slots=True)
class VaultSetupPlan:
    """Plan document for applying Vault SecretRefs to OpenClaw config."""

    targets: dict[str, dict[str, Any]]
    schema_version: int = 1
    generated_by: str = "vault setup"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "generatedBy": self.generated_by,
            "provider": {
                "id": "vault",
                "source": "exec",
                "pluginIntegration": {
                    "pluginId": "vault",
                    "integrationId": "vault",
                },
            },
            "targets": self.targets,
        }

    def save(self, out_path: Path | str) -> None:
        path = Path(out_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")


class VaultSecretRefResolver:
    """Resolves SecretRefs against HashiCorp Vault."""

    def __init__(
        self,
        config: VaultConfig | None = None,
        client: VaultClient | None = None,
    ) -> None:
        self.config = config or resolve_vault_config()
        self.client = client or VaultClient(config=self.config)

    async def resolve(self, ref_id: str) -> VaultSecretRefResolution:
        """Resolve a single SecretRef id."""
        try:
            path, field_name = parse_vault_secret_ref(ref_id)
        except ValueError as err:
            return VaultSecretRefResolution(
                ref_id=ref_id,
                error=str(err),
                error_code=INVALID_REF_ID,
            )

        return await self.client.read_secret(path, field_name)


def build_vault_setup_plan(
    openai_id: str | None = None,
    anthropic_id: str | None = None,
    openrouter_id: str | None = None,
    provider_keys: list[str] | None = None,
    targets: list[str] | None = None,
) -> VaultSetupPlan:
    """Build a secrets apply plan from CLI arguments."""
    plan_targets: dict[str, dict[str, Any]] = {}

    if openai_id:
        plan_targets["models.providers.openai.apiKey"] = {
            "source": "exec",
            "provider": "vault",
            "id": openai_id.strip(),
        }

    if anthropic_id:
        plan_targets["models.providers.anthropic.apiKey"] = {
            "source": "exec",
            "provider": "vault",
            "id": anthropic_id.strip(),
        }

    if openrouter_id:
        plan_targets["models.providers.openrouter.apiKey"] = {
            "source": "exec",
            "provider": "vault",
            "id": openrouter_id.strip(),
        }

    if provider_keys:
        for item in provider_keys:
            if "=" in item:
                provider_name, ref_id = item.split("=", 1)
                provider_name = provider_name.strip()
                ref_id = ref_id.strip()
                if provider_name and ref_id:
                    plan_targets[f"models.providers.{provider_name}.apiKey"] = {
                        "source": "exec",
                        "provider": "vault",
                        "id": ref_id,
                    }

    if targets:
        for item in targets:
            if "=" in item:
                target_path, ref_id = item.split("=", 1)
                target_path = target_path.strip()
                ref_id = ref_id.strip()
                if target_path and ref_id:
                    plan_targets[target_path] = {
                        "source": "exec",
                        "provider": "vault",
                        "id": ref_id,
                    }

    if not plan_targets:
        raise ValueError("At least one target reference is required to build a setup plan")

    return VaultSetupPlan(targets=plan_targets)
