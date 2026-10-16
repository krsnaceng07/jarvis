"""Configuration schemas and validation for 1Password plugin.

OpenClaw parity: mirrors @openclaw/onepassword configuration options,
slug rules, item registry limits (max 32 slugs, 200 char descriptions),
and policy tiers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .types import PolicyTier

SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
MAX_REGISTRY_ITEMS = 32
MAX_DESCRIPTION_LENGTH = 200
MAX_REASON_LENGTH = 300
DEFAULT_VAULT = "Automation"
DEFAULT_FIELD = "credential"
DEFAULT_POLICY: PolicyTier = "approve"
DEFAULT_CACHE_TTL_SECONDS = 300
DEFAULT_GRANT_TTL_HOURS = 720
DEFAULT_OP_TIMEOUT_MS = 15000
MAX_APPROVAL_WAIT_SECONDS = 600
MAX_STANDING_GRANTS = 1024


@dataclass(frozen=True, slots=True)
class OnepasswordItemConfig:
    """Configured secret item in the curated registry."""

    item: str
    field: str = DEFAULT_FIELD
    policy: PolicyTier | None = None
    vault: str | None = None
    description: str = ""

    def validate(self, slug: str) -> None:
        """Validate item configuration constraints."""
        if not self.item or not self.item.strip():
            raise ValueError(f"Item title/ID for slug '{slug}' cannot be empty")
        if self.item.startswith("-"):
            raise ValueError(f"Item title for slug '{slug}' must not start with a hyphen ('-')")
        if "," in self.field:
            raise ValueError(f"Field '{self.field}' for slug '{slug}' must not contain commas")
        if len(self.description) > MAX_DESCRIPTION_LENGTH:
            raise ValueError(
                f"Description for slug '{slug}' exceeds maximum {MAX_DESCRIPTION_LENGTH} characters "
                f"({len(self.description)} chars)"
            )
        if self.policy is not None and self.policy not in ("auto", "approve", "deny"):
            raise ValueError(
                f"Invalid policy '{self.policy}' for slug '{slug}'. Must be auto, approve, or deny"
            )


@dataclass(frozen=True, slots=True)
class OnepasswordConfig:
    """Root 1Password plugin configuration."""

    vault: str = DEFAULT_VAULT
    default_policy: PolicyTier = DEFAULT_POLICY
    cache_ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS
    grant_ttl_hours: int = DEFAULT_GRANT_TTL_HOURS
    op_timeout_ms: int = DEFAULT_OP_TIMEOUT_MS
    op_bin: str | None = None
    items: dict[str, OnepasswordItemConfig] = field(default_factory=dict)

    def validate(self) -> None:
        """Validate root configuration and all items."""
        if self.default_policy not in ("auto", "approve", "deny"):
            raise ValueError(
                f"Invalid defaultPolicy '{self.default_policy}'. Must be auto, approve, or deny"
            )
        if self.cache_ttl_seconds < 0:
            raise ValueError("cacheTtlSeconds must be non-negative")
        if self.grant_ttl_hours <= 0:
            raise ValueError("grantTtlHours must be positive")
        if self.op_timeout_ms <= 0:
            raise ValueError("opTimeoutMs must be positive")

        if len(self.items) > MAX_REGISTRY_ITEMS:
            raise ValueError(
                f"Item registry exceeds maximum {MAX_REGISTRY_ITEMS} slugs ({len(self.items)} configured)"
            )

        for slug, item_cfg in self.items.items():
            if not SLUG_PATTERN.match(slug):
                raise ValueError(
                    f"Invalid slug '{slug}'. Slugs must start with a lowercase letter or number, "
                    "contain only lowercase letters, numbers, and hyphens, and be at most 64 characters long."
                )
            item_cfg.validate(slug)

    def get_effective_vault(self, slug: str) -> str:
        """Return item-specific vault or fallback to default vault."""
        item = self.items.get(slug)
        if item and item.vault:
            return item.vault
        return self.vault

    def get_effective_policy(self, slug: str) -> PolicyTier:
        """Return item-specific policy or fallback to default policy."""
        item = self.items.get(slug)
        if item and item.policy is not None:
            return item.policy
        return self.default_policy


def parse_onepassword_config(raw: dict[str, Any] | None) -> OnepasswordConfig:
    """Parse raw dictionary into validated OnepasswordConfig."""
    if not raw or not isinstance(raw, dict):
        cfg = OnepasswordConfig()
        cfg.validate()
        return cfg

    vault = str(raw.get("vault") or DEFAULT_VAULT)
    raw_default_policy = (
        raw.get("defaultPolicy")
        if "defaultPolicy" in raw
        else raw.get("default_policy", DEFAULT_POLICY)
    )
    default_policy: Any = raw_default_policy if raw_default_policy is not None else DEFAULT_POLICY

    cache_ttl = (
        raw.get("cacheTtlSeconds")
        if "cacheTtlSeconds" in raw
        else raw.get("cache_ttl_seconds", DEFAULT_CACHE_TTL_SECONDS)
    )
    grant_ttl = (
        raw.get("grantTtlHours")
        if "grantTtlHours" in raw
        else raw.get("grant_ttl_hours", DEFAULT_GRANT_TTL_HOURS)
    )
    op_timeout = (
        raw.get("opTimeoutMs")
        if "opTimeoutMs" in raw
        else raw.get("op_timeout_ms", DEFAULT_OP_TIMEOUT_MS)
    )
    op_bin = raw.get("opBin") or raw.get("op_bin")

    items_raw = raw.get("items") or {}
    items: dict[str, OnepasswordItemConfig] = {}

    if isinstance(items_raw, dict):
        for slug, item_dict in items_raw.items():
            if isinstance(item_dict, dict):
                item_title = str(item_dict.get("item") or "")
                field_name = str(item_dict.get("field") or DEFAULT_FIELD)
                policy_raw = item_dict.get("policy")
                policy: Any = str(policy_raw) if policy_raw is not None else None
                item_vault = (
                    str(item_dict["vault"]) if "vault" in item_dict and item_dict["vault"] else None
                )
                description = str(item_dict.get("description") or "")
                items[slug] = OnepasswordItemConfig(
                    item=item_title,
                    field=field_name,
                    policy=policy,
                    vault=item_vault,
                    description=description,
                )

    config = OnepasswordConfig(
        vault=vault,
        default_policy=default_policy,
        cache_ttl_seconds=int(cache_ttl),
        grant_ttl_hours=int(grant_ttl),
        op_timeout_ms=int(op_timeout),
        op_bin=str(op_bin) if op_bin else None,
        items=items,
    )
    config.validate()
    return config
