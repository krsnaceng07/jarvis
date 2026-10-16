"""SecretRef resolver and setup plan builder for 1Password plugin.

OpenClaw parity: mirrors @openclaw/onepassword SecretRef management:
- References: `op://<vault>/<item>/<field>` or `op://<vault>/<item>/<section>/<field>`
- Names may contain spaces and special characters.
- Setup command creates a secrets apply plan for model provider keys and arbitrary targets.
- Status reports prerequisites readiness and provider wiring.
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from .op_cli import OpCliRunner
from .types import SecretRefResolution

logger = logging.getLogger("jarvis.onepassword.secretref")

OPAQUE_PREFIX = "op-opaque:"


@dataclass(frozen=True, slots=True)
class ParsedSecretRef:
    """Parsed representation of a 1Password URI reference."""

    raw_uri: str
    vault: str
    item: str
    field: str
    section: str | None = None

    @classmethod
    def parse(cls, uri: str) -> ParsedSecretRef:
        """Parse `op://<vault>/<item>/<field>` or `op://<vault>/<item>/<section>/<field>`."""
        trimmed = uri.strip()

        # Check if opaque encoded
        if trimmed.startswith(OPAQUE_PREFIX):
            decoded_uri = decode_opaque_secret_ref(trimmed)
            return cls.parse(decoded_uri)

        if not trimmed.startswith("op://"):
            raise ValueError(f"1Password SecretRef URI must start with 'op://' (got '{uri}')")

        path = trimmed[len("op://") :]
        parts = [unquote(p) for p in path.split("/") if p]

        if len(parts) < 3:
            raise ValueError(
                f"1Password SecretRef URI must contain at least vault, item, and field (got '{uri}')"
            )

        vault = parts[0]
        item = parts[1]

        if len(parts) == 3:
            return cls(
                raw_uri=trimmed,
                vault=vault,
                item=item,
                field=parts[2],
                section=None,
            )
        else:
            # 4 or more parts: vault / item / section / field
            section = parts[2]
            field_name = "/".join(parts[3:])
            return cls(
                raw_uri=trimmed,
                vault=vault,
                item=item,
                section=section,
                field=field_name,
            )


def encode_opaque_secret_ref(uri: str) -> str:
    """Encode a complex 1Password reference to an opaque string if needed."""
    encoded = base64.urlsafe_b64encode(uri.encode("utf-8")).decode("ascii").rstrip("=")
    return f"{OPAQUE_PREFIX}{encoded}"


def decode_opaque_secret_ref(opaque_str: str) -> str:
    """Decode an opaque 1Password reference back to its URI string."""
    if not opaque_str.startswith(OPAQUE_PREFIX):
        return opaque_str
    raw_b64 = opaque_str[len(OPAQUE_PREFIX) :]
    # Add padding
    rem = len(raw_b64) % 4
    if rem:
        raw_b64 += "=" * (4 - rem)
    return base64.urlsafe_b64decode(raw_b64.encode("ascii")).decode("utf-8")


@dataclass(frozen=True, slots=True)
class SecretRefSetupPlan:
    """Plan document for applying 1Password secret references."""

    targets: dict[str, dict[str, Any]]
    schema_version: int = 1
    generated_by: str = "onepassword secretref setup"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "generatedBy": self.generated_by,
            "provider": {
                "id": "onepassword",
                "source": "exec",
                "pluginIntegration": {
                    "pluginId": "onepassword",
                    "integrationId": "onepassword",
                },
            },
            "targets": self.targets,
        }

    def save(self, out_path: Path | str) -> None:
        path = Path(out_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")


class SecretRefResolver:
    """Resolves 1Password SecretRefs through the op CLI."""

    def __init__(self, op_runner: OpCliRunner | None = None) -> None:
        self.op_runner = op_runner or OpCliRunner()

    async def resolve(self, ref_id: str) -> SecretRefResolution:
        """Resolve a single SecretRef ID."""
        try:
            parsed = ParsedSecretRef.parse(ref_id)
            uri_to_fetch = parsed.raw_uri
        except ValueError as err:
            return SecretRefResolution(
                ref_id=ref_id,
                error=str(err),
                error_code="INVALID_REF_URI",
            )

        return await self.op_runner.read_secret_ref(uri_to_fetch)


def build_secrets_setup_plan(
    anthropic_id: str | None = None,
    openrouter_id: str | None = None,
    provider_keys: list[str] | None = None,
    targets: list[str] | None = None,
) -> SecretRefSetupPlan:
    """Build a secrets apply plan from CLI arguments."""
    plan_targets: dict[str, dict[str, Any]] = {}

    if anthropic_id:
        plan_targets["models.providers.anthropic.apiKey"] = {
            "source": "exec",
            "provider": "onepassword",
            "id": anthropic_id,
        }

    if openrouter_id:
        plan_targets["models.providers.openrouter.apiKey"] = {
            "source": "exec",
            "provider": "onepassword",
            "id": openrouter_id,
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
                        "provider": "onepassword",
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
                        "provider": "onepassword",
                        "id": ref_id,
                    }

    if not plan_targets:
        raise ValueError("At least one target reference is required to build a setup plan")

    return SecretRefSetupPlan(targets=plan_targets)
