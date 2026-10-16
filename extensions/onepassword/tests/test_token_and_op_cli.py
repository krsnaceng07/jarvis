"""Unit tests for token discovery, isolated environment, and OpCliRunner."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from extensions.onepassword.src.op_cli import (
    OpCliRunner,
    build_isolated_env,
    map_op_error,
    resolve_op_binary,
)
from extensions.onepassword.src.token import (
    get_token_file_path,
    read_service_account_token,
    verify_token_prerequisites,
)
from extensions.onepassword.src.types import (
    AUTH_FAILED,
    FIELD_NOT_FOUND,
    ITEM_NOT_FOUND,
    OP_ERROR,
    OP_NOT_FOUND,
    RATE_LIMITED,
    TIMEOUT,
    TOKEN_MISSING,
)


def test_token_discovery(mock_state_dir: Path) -> None:
    """Test token file location and reading."""
    token_path = get_token_file_path(mock_state_dir)
    assert token_path.exists()
    assert token_path.is_file()

    ready, err = verify_token_prerequisites(mock_state_dir)
    assert ready is True
    assert err is None

    token = read_service_account_token(mock_state_dir)
    assert token == "ops_test_token_1234567890"


def test_missing_and_empty_token(tmp_path: Path) -> None:
    """Test missing or empty token behavior."""
    empty_state = tmp_path / "empty_state"
    ready, err = verify_token_prerequisites(empty_state)
    assert ready is False
    assert "Token file not found" in str(err)
    assert read_service_account_token(empty_state) is None

    # Empty token file
    token_file = empty_state / "credentials" / "onepassword" / "service-account-token"
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text("   \n", encoding="utf-8")

    ready2, err2 = verify_token_prerequisites(empty_state)
    assert ready2 is False
    assert "empty" in str(err2)
    assert read_service_account_token(empty_state) is None


def test_build_isolated_env() -> None:
    """Test environment isolation variables."""
    env = build_isolated_env("test-token-xyz")
    assert env["OP_SERVICE_ACCOUNT_TOKEN"] == "test-token-xyz"
    assert env["OP_LOAD_DESKTOP_APP_SETTINGS"] == "false"
    assert env["OP_BIOMETRIC_UNLOCK_ENABLED"] == "false"
    assert "HOME" in env


def test_map_op_error() -> None:
    """Test error code mapping from stderr/stdout."""
    # Rate limit
    code, _ = map_op_error("Error: [429] Rate limit exceeded for service account", "", 1)
    assert code == RATE_LIMITED

    # Auth failed
    code, _ = map_op_error("Error: authentication failed: invalid token", "", 1)
    assert code == AUTH_FAILED

    # Item not found
    code, _ = map_op_error("Error: 'MySecret' isn't an item in the 'Automation' vault", "", 1)
    assert code == ITEM_NOT_FOUND

    # Field not found
    code, _ = map_op_error("Error: 'custom_field' isn't a field in the item", "", 1)
    assert code == FIELD_NOT_FOUND

    # Generic op error
    code, _ = map_op_error("Unknown internal error", "", 1)
    assert code == OP_ERROR


def test_resolve_op_binary(tmp_path: Path) -> None:
    """Test custom op binary resolution."""
    # Custom non-existent path
    path, err = resolve_op_binary(str(tmp_path / "nonexistent" / "op"))
    assert path is None
    assert "does not exist" in str(err)

    # Valid custom binary
    fake_op = tmp_path / "op.exe"
    fake_op.write_text("fake binary")
    path, err = resolve_op_binary(str(fake_op))
    assert path == str(fake_op.resolve())
    assert err is None


@pytest.mark.asyncio
async def test_op_runner_missing_token(tmp_path: Path) -> None:
    """Test OpCliRunner when service account token is missing."""
    empty_state = tmp_path / "no_token_state"
    runner = OpCliRunner(state_dir=empty_state)

    res, err_code, err_msg = await runner.get_item_field(
        slug="test-slug",
        item="Test Item",
        field="credential",
        vault="Automation",
    )
    assert res is None
    assert err_code == TOKEN_MISSING

    ref_res = await runner.read_secret_ref("op://Automation/Test Item/credential")
    assert ref_res.error_code == TOKEN_MISSING


@pytest.mark.asyncio
async def test_op_runner_missing_binary(mock_state_dir: Path, tmp_path: Path) -> None:
    """Test OpCliRunner when op binary is missing."""
    runner = OpCliRunner(
        op_bin=str(tmp_path / "missing_op_executable"),
        state_dir=mock_state_dir,
    )

    res, err_code, err_msg = await runner.get_item_field(
        slug="test-slug",
        item="Test Item",
        field="credential",
        vault="Automation",
    )
    assert res is None
    assert err_code == OP_NOT_FOUND


@pytest.mark.asyncio
async def test_op_runner_successful_execution(mock_state_dir: Path, tmp_path: Path) -> None:
    """Test OpCliRunner handling mocked subprocess success."""
    fake_op = tmp_path / "mock_op"
    fake_op.write_text("dummy")

    runner = OpCliRunner(
        op_bin=str(fake_op),
        state_dir=mock_state_dir,
    )

    # Mock asyncio.create_subprocess_exec
    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate.return_value = (
        b'{"value": "super-secret-password-123"}',
        b"",
    )

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        result, error_code, error_msg = await runner.get_item_field(
            slug="db-pass",
            item="Database Credentials",
            field="credential",
            vault="Automation",
        )

        assert error_code is None
        assert result is not None
        assert result.slug == "db-pass"
        assert result.value == "super-secret-password-123"


@pytest.mark.asyncio
async def test_op_runner_timeout(mock_state_dir: Path, tmp_path: Path) -> None:
    """Test OpCliRunner handling subprocess timeout."""
    fake_op = tmp_path / "mock_op"
    fake_op.write_text("dummy")

    runner = OpCliRunner(
        op_bin=str(fake_op),
        state_dir=mock_state_dir,
        default_timeout_ms=100,
    )

    mock_proc = AsyncMock()
    mock_proc.communicate.side_effect = asyncio.TimeoutError()

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        result, error_code, error_msg = await runner.get_item_field(
            slug="db-pass",
            item="Database Credentials",
            field="credential",
            vault="Automation",
        )

        assert result is None
        assert error_code == TIMEOUT
        assert "timed out" in str(error_msg)
