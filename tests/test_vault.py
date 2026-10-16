"""Tests for src/plugins/vault.py.

Mirrors tests of extensions/vault/src/cli.ts in OpenClaw.
"""

from __future__ import annotations

import pytest

from src.plugins.vault import (
    VAULT_PLUGIN_ID,
    build_vault_kv_read_path,
    parse_vault_secret_id,
    resolve_vault_config,
)


def test_vault_plugin_id():
    assert VAULT_PLUGIN_ID == "vault"


def test_parse_vault_secret_id():
    path, field = parse_vault_secret_id("providers/openrouter/apiKey")
    assert path == "providers/openrouter"
    assert field == "apiKey"

    with pytest.raises(ValueError, match="Invalid Vault SecretRef id"):
        parse_vault_secret_id("invalid_id_without_slash")


def test_build_vault_kv_read_path():
    assert build_vault_kv_read_path("providers/openrouter", "secret", 2) == "/v1/secret/data/providers/openrouter"
    assert build_vault_kv_read_path("providers/openrouter", "secret", 1) == "/v1/secret/providers/openrouter"


def test_resolve_vault_config():
    env = {
        "VAULT_ADDR": "https://vault.example.com",
        "VAULT_TOKEN": "root_token",
        "OPENCLAW_VAULT_KV_MOUNT": "custom_secret",
        "OPENCLAW_VAULT_KV_VERSION": "1",
    }
    cfg = resolve_vault_config(env)
    assert cfg.addr == "https://vault.example.com"
    assert cfg.auth_method == "token"
    assert cfg.token == "root_token"
    assert cfg.kv_mount == "custom_secret"
    assert cfg.kv_version == 1
