"""Unit tests for 1Password plugin configuration and schema validation."""

import pytest
from extensions.onepassword.src.config import (
    DEFAULT_CACHE_TTL_SECONDS,
    DEFAULT_FIELD,
    DEFAULT_GRANT_TTL_HOURS,
    DEFAULT_OP_TIMEOUT_MS,
    DEFAULT_POLICY,
    DEFAULT_VAULT,
    MAX_DESCRIPTION_LENGTH,
    MAX_REGISTRY_ITEMS,
    parse_onepassword_config,
)


def test_default_config() -> None:
    """Test default values of OnepasswordConfig."""
    cfg = parse_onepassword_config(None)
    assert cfg.vault == DEFAULT_VAULT
    assert cfg.default_policy == DEFAULT_POLICY
    assert cfg.cache_ttl_seconds == DEFAULT_CACHE_TTL_SECONDS
    assert cfg.grant_ttl_hours == DEFAULT_GRANT_TTL_HOURS
    assert cfg.op_timeout_ms == DEFAULT_OP_TIMEOUT_MS
    assert cfg.op_bin is None
    assert len(cfg.items) == 0


def test_custom_valid_config() -> None:
    """Test parsing a valid custom configuration."""
    raw = {
        "vault": "Production",
        "defaultPolicy": "auto",
        "cacheTtlSeconds": 600,
        "grantTtlHours": 24,
        "opTimeoutMs": 30000,
        "opBin": "/usr/local/bin/op",
        "items": {
            "api-key": {
                "item": "Backend API Key",
                "field": "token",
                "policy": "approve",
                "vault": "Secrets",
                "description": "API token for backend services",
            },
            "db-pass": {
                "item": "Database Credentials",
            },
        },
    }

    cfg = parse_onepassword_config(raw)
    assert cfg.vault == "Production"
    assert cfg.default_policy == "auto"
    assert cfg.cache_ttl_seconds == 600
    assert cfg.grant_ttl_hours == 24
    assert cfg.op_timeout_ms == 30000
    assert cfg.op_bin == "/usr/local/bin/op"
    assert len(cfg.items) == 2

    item1 = cfg.items["api-key"]
    assert item1.item == "Backend API Key"
    assert item1.field == "token"
    assert item1.policy == "approve"
    assert item1.vault == "Secrets"
    assert item1.description == "API token for backend services"
    assert cfg.get_effective_vault("api-key") == "Secrets"
    assert cfg.get_effective_policy("api-key") == "approve"

    item2 = cfg.items["db-pass"]
    assert item2.item == "Database Credentials"
    assert item2.field == DEFAULT_FIELD
    assert item2.policy is None
    assert item2.vault is None
    assert cfg.get_effective_vault("db-pass") == "Production"
    assert cfg.get_effective_policy("db-pass") == "auto"  # inherited default


def test_slug_validation() -> None:
    """Test slug format rules."""
    # Valid slugs
    valid_slugs = ["a", "0", "api-key", "database-token-123", "github-pat", "model-key-v2"]
    for s in valid_slugs:
        raw = {"items": {s: {"item": "Test Item"}}}
        cfg = parse_onepassword_config(raw)
        assert s in cfg.items

    # Invalid slugs
    invalid_slugs = [
        "-leading-hyphen",
        "UPPERCASE",
        "with_underscore",
        "with space",
        "with.dot",
        "a" * 65,  # > 64 chars
    ]
    for s in invalid_slugs:
        raw = {"items": {s: {"item": "Test Item"}}}
        with pytest.raises(ValueError, match="Invalid slug"):
            parse_onepassword_config(raw)


def test_max_items_limit() -> None:
    """Test enforcement of max 32 items in registry."""
    items = {f"item-{i}": {"item": f"Title {i}"} for i in range(MAX_REGISTRY_ITEMS)}
    raw = {"items": items}
    cfg = parse_onepassword_config(raw)
    assert len(cfg.items) == MAX_REGISTRY_ITEMS

    # Add 33rd item
    items["item-33"] = {"item": "Title 33"}
    with pytest.raises(ValueError, match="Item registry exceeds maximum 32 slugs"):
        parse_onepassword_config(raw)


def test_description_length_limit() -> None:
    """Test enforcement of max 200 chars in description."""
    long_desc = "x" * (MAX_DESCRIPTION_LENGTH + 1)
    raw = {
        "items": {
            "my-secret": {
                "item": "Secret",
                "description": long_desc,
            }
        }
    }
    with pytest.raises(
        ValueError, match="Description for slug 'my-secret' exceeds maximum 200 characters"
    ):
        parse_onepassword_config(raw)


def test_item_constraints() -> None:
    """Test item title cannot start with hyphen and field cannot contain comma."""
    # Hyphen in item title
    with pytest.raises(ValueError, match="must not start with a hyphen"):
        parse_onepassword_config({"items": {"secret-1": {"item": "-dash-item"}}})

    # Empty item title
    with pytest.raises(ValueError, match="cannot be empty"):
        parse_onepassword_config({"items": {"secret-1": {"item": ""}}})

    # Comma in field
    with pytest.raises(ValueError, match="must not contain commas"):
        parse_onepassword_config(
            {"items": {"secret-1": {"item": "Valid Item", "field": "field1,field2"}}}
        )


def test_invalid_policy_values() -> None:
    """Test rejection of invalid policy strings."""
    with pytest.raises(ValueError, match="Invalid defaultPolicy"):
        parse_onepassword_config({"defaultPolicy": "invalid"})

    with pytest.raises(ValueError, match="Invalid policy 'unknown'"):
        parse_onepassword_config(
            {"items": {"secret-1": {"item": "Valid Item", "policy": "unknown"}}}
        )
