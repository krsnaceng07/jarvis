"""Unit tests for Vault configuration resolution and authentication strategies."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from extensions.vault.src.auth import VaultAuthenticator
from extensions.vault.src.config import (
    DEFAULT_KV_MOUNT,
    DEFAULT_KV_VERSION,
    DEFAULT_TIMEOUT_MS,
    VaultConfig,
    resolve_vault_config,
)
from extensions.vault.src.types import AUTH_FAILED


def test_default_config() -> None:
    """Test default values of VaultConfig."""
    cfg = resolve_vault_config({}, env={})
    assert cfg.vault_addr == ""
    assert cfg.auth_method == "token"
    assert cfg.token is None
    assert cfg.token_file is None
    assert cfg.kv_mount == DEFAULT_KV_MOUNT
    assert cfg.kv_version == DEFAULT_KV_VERSION
    assert cfg.timeout_ms == DEFAULT_TIMEOUT_MS


def test_config_from_env() -> None:
    """Test resolving VaultConfig from environment variables."""
    env = {
        "VAULT_ADDR": "https://vault.example.com/",
        "OPENCLAW_VAULT_AUTH_METHOD": "jwt",
        "OPENCLAW_VAULT_AUTH_MOUNT": "custom-jwt",
        "OPENCLAW_VAULT_AUTH_ROLE": "openclaw-role",
        "OPENCLAW_VAULT_JWT_FILE": "/var/run/secrets/token",
        "VAULT_NAMESPACE": "corp-namespace",
        "OPENCLAW_VAULT_KV_MOUNT": "kv-prod",
        "OPENCLAW_VAULT_KV_VERSION": "1",
    }

    cfg = resolve_vault_config({}, env=env)
    assert cfg.vault_addr == "https://vault.example.com"
    assert cfg.auth_method == "jwt"
    assert cfg.get_effective_auth_mount() == "custom-jwt"
    assert cfg.auth_role == "openclaw-role"
    assert cfg.jwt_file == "/var/run/secrets/token"
    assert cfg.namespace == "corp-namespace"
    assert cfg.kv_mount == "kv-prod"
    assert cfg.kv_version == 1


@pytest.mark.asyncio
async def test_auth_token_strategy() -> None:
    """Test direct client token authentication."""
    # 1. Token present
    cfg = VaultConfig(token="s.validToken123")
    auth = VaultAuthenticator(config=cfg)
    token, err_code, err_msg = await auth.get_client_token()
    assert token == "s.validToken123"
    assert err_code is None

    # 2. Token missing
    cfg_empty = VaultConfig(token=None)
    auth_empty = VaultAuthenticator(config=cfg_empty)
    token, err_code, err_msg = await auth_empty.get_client_token()
    assert token is None
    assert err_code == AUTH_FAILED
    assert "VAULT_TOKEN is missing" in str(err_msg)


@pytest.mark.asyncio
async def test_auth_token_file_strategy(sample_token_file: Path, tmp_path: Path) -> None:
    """Test token-file authentication."""
    # 1. Valid token file
    cfg = VaultConfig(auth_method="token_file", token_file=str(sample_token_file))
    auth = VaultAuthenticator(config=cfg)
    token, err_code, err_msg = await auth.get_client_token()
    assert token == "s.mockToken1234567890"
    assert err_code is None

    # 2. Missing token file
    missing_path = tmp_path / "nonexistent-token"
    cfg_missing = VaultConfig(auth_method="token_file", token_file=str(missing_path))
    auth_missing = VaultAuthenticator(config=cfg_missing)
    token, err_code, err_msg = await auth_missing.get_client_token()
    assert token is None
    assert err_code == AUTH_FAILED
    assert "not found" in str(err_msg)


@pytest.mark.asyncio
async def test_auth_jwt_strategy(sample_jwt_file: Path) -> None:
    """Test JWT login strategy."""
    cfg = VaultConfig(
        vault_addr="https://vault.example.com",
        auth_method="jwt",
        auth_role="openclaw-agent",
        jwt_file=str(sample_jwt_file),
    )
    auth = VaultAuthenticator(config=cfg)

    mock_resp_data = {
        "auth": {
            "client_token": "s.jwtLoggedInToken999",
            "lease_duration": 3600,
            "renewable": True,
        }
    }

    mock_urlopen = MagicMock()
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_resp_data).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    mock_urlopen.return_value = mock_resp

    with patch("urllib.request.urlopen", mock_urlopen):
        token, err_code, err_msg = await auth.get_client_token()
        assert token == "s.jwtLoggedInToken999"
        assert err_code is None

        # Verify request payload
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "https://vault.example.com/v1/auth/jwt/login"
        req_data = json.loads(req.data.decode("utf-8"))
        assert req_data["role"] == "openclaw-agent"
        assert req_data["jwt"].startswith("eyJhbGciOi")
