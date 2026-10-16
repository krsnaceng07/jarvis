"""jarvis.plugins.onepassword — 1Password plugin & SecretRef resolver integration.

OpenClaw parity: mirrors
``openclaw-main/extensions/onepassword/src/config.ts`` and
``openclaw-main/extensions/onepassword/src/errors.ts``.

Features:
- `ONEPASSWORD_PLUGIN_ID`: `"onepassword"`
- `ONEPASSWORD_TOOL_NAME`: `"onepassword"`
- `OnePasswordPolicy`: `"auto"` | `"approve"` | `"deny"`
- `ONEPASSWORD_ERROR_CODES`: List of 15 closed 1Password & policy error codes.
- `SLUG_REGEX`: Regex pattern `^[a-z0-9][a-z0-9-]{0,63}$`.
- `MAX_REGISTERED_ITEMS`: `32`
- `MAX_DESCRIPTION_LENGTH`: `200`
- `MAX_REASON_LENGTH`: `300`
- `is_valid_onepassword_slug()`: Validates slug format.
- `parse_op_secret_uri()`: Parses `op://<vault>/<item>/<field>` or `op://<vault>/<item>/<section>/<field>`.
- `OnePasswordItemConfig`: Item configuration dataclass.
- `OnePasswordConfig`: Plugin configuration dataclass.
- `resolve_onepassword_config()`: Resolves and validates 1Password plugin config.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

ONEPASSWORD_PLUGIN_ID: str = "onepassword"
ONEPASSWORD_TOOL_NAME: str = "onepassword"

OnePasswordPolicy = Literal["auto", "approve", "deny"]

ONEPASSWORD_ERROR_CODES: list[str] = [
    # 1Password access errors
    "TOKEN_MISSING",
    "OP_NOT_FOUND",
    "ITEM_NOT_FOUND",
    "FIELD_NOT_FOUND",
    "RATE_LIMITED",
    "AUTH_FAILED",
    "TIMEOUT",
    "OP_ERROR",
    # Policy and validation errors
    "INVALID_ACTION",
    "INVALID_REASON",
    "INVALID_SLUG",
    "UNKNOWN_SLUG",
    "TOOL_CALL_ID_MISSING",
    "POLICY_NOT_EVALUATED",
    "POLICY_CHANGED",
    "GRANT_EXPIRED",
    "APPROVAL_CANCELLED",
]

SLUG_REGEX = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
MAX_REGISTERED_ITEMS: int = 32
MAX_DESCRIPTION_LENGTH: int = 200
MAX_REASON_LENGTH: int = 300


def is_valid_onepassword_slug(slug: str) -> bool:
    """Validate if a string matches the 1Password slug pattern."""
    if not slug or not isinstance(slug, str):
        return False
    return bool(SLUG_REGEX.match(slug.strip()))


def parse_op_secret_uri(uri: str) -> dict[str, str]:
    """Parse an op:// secret reference URI.

    Formats:
    - op://<vault>/<item>/<field>
    - op://<vault>/<item>/<section>/<field>
    """
    if not uri or not isinstance(uri, str) or not uri.startswith("op://"):
        raise ValueError(f"Invalid 1Password SecretRef URI '{uri}'. Must start with 'op://'.")

    stripped = uri[5:].strip()
    parts = [p.strip() for p in stripped.split("/") if p.strip()]

    if len(parts) < 3:
        raise ValueError(
            f"Invalid 1Password SecretRef URI '{uri}'. Expected 'op://<vault>/<item>/<field>' or 'op://<vault>/<item>/<section>/<field>'."
        )

    vault = parts[0]
    item = parts[1]

    if len(parts) == 3:
        return {"vault": vault, "item": item, "field": parts[2]}
    else:
        return {
            "vault": vault,
            "item": item,
            "section": parts[2],
            "field": "/".join(parts[3:]),
        }


@dataclass
class OnePasswordItemConfig:
    item: str
    vault: str
    field: str = "credential"
    policy: OnePasswordPolicy = "approve"
    description: str | None = None


@dataclass
class OnePasswordConfig:
    vault: str = "Automation"
    opBin: str | None = None
    defaultPolicy: OnePasswordPolicy = "approve"
    cacheTtlSeconds: int = 300
    grantTtlHours: int = 720
    opTimeoutMs: int = 15000
    items: dict[str, OnePasswordItemConfig] = field(default_factory=dict)


def resolve_onepassword_config(plugin_cfg: dict[str, Any] | None) -> OnePasswordConfig:
    """Resolve and validate 1Password plugin configuration."""
    val = plugin_cfg if isinstance(plugin_cfg, dict) else {}

    default_vault = str(val.get("vault") or "Automation").strip()
    op_bin = str(val.get("opBin")).strip() if val.get("opBin") else None

    raw_policy = str(val.get("defaultPolicy") or "approve").lower()
    default_policy: OnePasswordPolicy = (
        raw_policy if raw_policy in ("auto", "approve", "deny") else "approve"  # type: ignore[assignment]
    )

    items_raw = val.get("items")
    parsed_items: dict[str, OnePasswordItemConfig] = {}

    if isinstance(items_raw, dict):
        for slug, item_raw in items_raw.items():
            if len(parsed_items) >= MAX_REGISTERED_ITEMS:
                break
            if not is_valid_onepassword_slug(slug) or not isinstance(item_raw, dict):
                continue

            item_title = str(item_raw.get("item") or "").strip()
            if not item_title or item_title.startswith("-"):
                continue

            item_vault = str(item_raw.get("vault") or default_vault).strip()
            item_field = str(item_raw.get("field") or "credential").strip()

            raw_item_pol = str(item_raw.get("policy") or default_policy).lower()
            item_policy: OnePasswordPolicy = (
                raw_item_pol if raw_item_pol in ("auto", "approve", "deny") else default_policy  # type: ignore[assignment]
            )

            desc = str(item_raw.get("description")).strip() if item_raw.get("description") else None
            if desc and len(desc) > MAX_DESCRIPTION_LENGTH:
                desc = desc[:MAX_DESCRIPTION_LENGTH]

            parsed_items[slug] = OnePasswordItemConfig(
                item=item_title,
                vault=item_vault,
                field=item_field,
                policy=item_policy,
                description=desc,
            )

    return OnePasswordConfig(
        vault=default_vault,
        opBin=op_bin,
        defaultPolicy=default_policy,
        cacheTtlSeconds=int(val.get("cacheTtlSeconds", 300)),
        grantTtlHours=int(val.get("grantTtlHours", 720)),
        opTimeoutMs=int(val.get("opTimeoutMs", 15000)),
        items=parsed_items,
    )


__all__ = [
    "MAX_DESCRIPTION_LENGTH",
    "MAX_REASON_LENGTH",
    "MAX_REGISTERED_ITEMS",
    "ONEPASSWORD_ERROR_CODES",
    "ONEPASSWORD_PLUGIN_ID",
    "ONEPASSWORD_TOOL_NAME",
    "OnePasswordConfig",
    "OnePasswordItemConfig",
    "OnePasswordPolicy",
    "SLUG_REGEX",
    "is_valid_onepassword_slug",
    "parse_op_secret_uri",
    "resolve_onepassword_config",
]
