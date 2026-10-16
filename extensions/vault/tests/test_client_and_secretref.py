"""Unit tests for VaultClient HTTP reads and SecretRef resolution."""

import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest
from extensions.vault.src.client import VaultClient
from extensions.vault.src.config import VaultConfig
from extensions.vault.src.secretref import (
    VaultSecretRefResolver,
    parse_vault_secret_ref,
)
from extensions.vault.src.types import (
    AUTH_FAILED,
    FIELD_NOT_FOUND,
    INVALID_REF_ID,
    SECRET_NOT_FOUND,
    VAULT_ADDR_MISSING,
)


def test_parse_vault_secret_ref() -> None:
    """Test parsing Vault SecretRef ID into path and field."""
    path, field = parse_vault_secret_ref("providers/openrouter/apiKey")
    assert path == "providers/openrouter"
    assert field == "apiKey"

    path2, field2 = parse_vault_secret_ref("teams/agent-prod/openrouter")
    assert path2 == "teams/agent-prod"
    assert field2 == "openrouter"

    path3, field3 = parse_vault_secret_ref("deep/nested/secret/path/my-token")
    assert path3 == "deep/nested/secret/path"
    assert field3 == "my-token"

    # Invalid refs
    with pytest.raises(ValueError, match="Invalid Vault SecretRef ID"):
        parse_vault_secret_ref("noslash")

    with pytest.raises(ValueError, match="Invalid Vault SecretRef ID"):
        parse_vault_secret_ref("")


@pytest.mark.asyncio
async def test_vault_client_kv2_read_success() -> None:
    """Test reading secret from KV v2 engine."""
    cfg = VaultConfig(
        vault_addr="https://vault.example.com",
        token="s.testClientToken",
        kv_mount="secret",
        kv_version=2,
    )
    client = VaultClient(config=cfg)

    mock_resp_data = {
        "data": {
            "data": {
                "apiKey": "sk-or-v1-super-secret-key-123",
                "org": "openclaw-team",
            },
            "metadata": {"version": 1},
        }
    }

    mock_urlopen = MagicMock()
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_resp_data).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    mock_urlopen.return_value = mock_resp

    with patch("urllib.request.urlopen", mock_urlopen):
        res = await client.read_secret(
            path="providers/openrouter",
            field_name="apiKey",
        )

        assert res.value == "sk-or-v1-super-secret-key-123"
        assert res.cached is False
        assert res.error is None

        # Verify URL constructed for KV v2: /v1/<kvMount>/data/<path>
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "https://vault.example.com/v1/secret/data/providers/openrouter"
        assert req.headers["X-vault-token"] == "s.testClientToken"

        # Subsequent read hits in-memory cache without urlopen
        res_cached = await client.read_secret(
            path="providers/openrouter",
            field_name="apiKey",
        )
        assert res_cached.value == "sk-or-v1-super-secret-key-123"
        assert res_cached.cached is True
        assert mock_urlopen.call_count == 1


@pytest.mark.asyncio
async def test_vault_client_kv1_read_success() -> None:
    """Test reading secret from KV v1 engine."""
    cfg = VaultConfig(
        vault_addr="https://vault.example.com",
        token="s.testClientToken",
        kv_mount="secret",
        kv_version=1,
    )
    client = VaultClient(config=cfg)

    mock_resp_data = {
        "data": {
            "apiKey": "sk-openai-key-999",
        }
    }

    mock_urlopen = MagicMock()
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_resp_data).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    mock_urlopen.return_value = mock_resp

    with patch("urllib.request.urlopen", mock_urlopen):
        res = await client.read_secret(
            path="providers/openai",
            field_name="apiKey",
        )

        assert res.value == "sk-openai-key-999"
        # Verify URL for KV v1: /v1/<kvMount>/<path>
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "https://vault.example.com/v1/secret/providers/openai"


@pytest.mark.asyncio
async def test_vault_client_errors() -> None:
    """Test VaultClient error codes for missing field, 404, 403, missing addr."""
    # 1. Missing VAULT_ADDR
    cfg_no_addr = VaultConfig(vault_addr="", token="s.token")
    client_no_addr = VaultClient(config=cfg_no_addr)
    res_no_addr = await client_no_addr.read_secret("path", "field")
    assert res_no_addr.error_code == VAULT_ADDR_MISSING

    # 2. Field not found in response
    cfg = VaultConfig(vault_addr="https://vault.example.com", token="s.token")
    client = VaultClient(config=cfg)

    mock_resp_data = {"data": {"data": {"otherField": "val"}}}
    mock_urlopen = MagicMock()
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_resp_data).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    mock_urlopen.return_value = mock_resp

    with patch("urllib.request.urlopen", mock_urlopen):
        res_field = await client.read_secret("path", "targetField")
        assert res_field.error_code == FIELD_NOT_FOUND

    # 3. HTTP 404 Not Found
    mock_404 = MagicMock()
    mock_404.side_effect = urllib.error.HTTPError(
        url="https://vault.example.com",
        code=404,
        msg="Not Found",
        hdrs=None,  # type: ignore
        fp=MagicMock(),
    )
    with patch("urllib.request.urlopen", mock_404):
        res_404 = await client.read_secret("missing/path", "key", use_cache=False)
        assert res_404.error_code == SECRET_NOT_FOUND

    # 4. HTTP 403 Forbidden
    mock_403 = MagicMock()
    mock_403.side_effect = urllib.error.HTTPError(
        url="https://vault.example.com",
        code=403,
        msg="Permission Denied",
        hdrs=None,  # type: ignore
        fp=MagicMock(),
    )
    with patch("urllib.request.urlopen", mock_403):
        res_403 = await client.read_secret("secret/path", "key", use_cache=False)
        assert res_403.error_code == AUTH_FAILED


@pytest.mark.asyncio
async def test_secretref_resolver() -> None:
    """Test SecretRef resolver end-to-end."""
    cfg = VaultConfig(
        vault_addr="https://vault.example.com",
        token="s.token",
    )
    resolver = VaultSecretRefResolver(config=cfg)

    # 1. Invalid ref format
    res_inv = await resolver.resolve("invalid-ref-without-slash")
    assert res_inv.error_code == INVALID_REF_ID

    # 2. Valid ref resolution
    mock_resp_data = {"data": {"data": {"apiKey": "resolved-secret-token"}}}
    mock_urlopen = MagicMock()
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_resp_data).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    mock_urlopen.return_value = mock_resp

    with patch("urllib.request.urlopen", mock_urlopen):
        res = await resolver.resolve("providers/anthropic/apiKey")
        assert res.value == "resolved-secret-token"
        assert res.error is None
