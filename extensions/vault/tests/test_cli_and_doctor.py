"""Unit tests for Vault CLI subcommands and doctor diagnostics."""

import json
from pathlib import Path

import pytest
from extensions.vault.src.cli import (
    handle_vault_setup_command,
    handle_vault_status_command,
)
from extensions.vault.src.config import VaultConfig
from extensions.vault.src.doctor import run_vault_doctor_checks
from extensions.vault.src.secretref import build_vault_setup_plan


def test_build_vault_setup_plan(tmp_path: Path) -> None:
    """Test building and saving a Vault setup plan."""
    plan = build_vault_setup_plan(
        openai_id="providers/openai/apiKey",
        anthropic_id="providers/anthropic/apiKey",
        openrouter_id="providers/openrouter/apiKey",
        provider_keys=["groq=providers/groq/apiKey"],
        targets=[
            "channels.telegram.botToken=channels/telegram/botToken",
            "auth-profiles:main:profiles.openai.key=providers/openai/apiKey",
        ],
    )

    data = plan.to_dict()
    assert data["schemaVersion"] == 1
    assert data["provider"]["id"] == "vault"
    targets = data["targets"]

    assert targets["models.providers.openai.apiKey"]["id"] == "providers/openai/apiKey"
    assert targets["models.providers.anthropic.apiKey"]["id"] == "providers/anthropic/apiKey"
    assert targets["models.providers.openrouter.apiKey"]["id"] == "providers/openrouter/apiKey"
    assert targets["models.providers.groq.apiKey"]["id"] == "providers/groq/apiKey"
    assert targets["channels.telegram.botToken"]["id"] == "channels/telegram/botToken"
    assert targets["auth-profiles:main:profiles.openai.key"]["id"] == "providers/openai/apiKey"

    plan_path = tmp_path / "plan.json"
    plan.save(plan_path)
    assert plan_path.exists()
    loaded = json.loads(plan_path.read_text(encoding="utf-8"))
    assert loaded["targets"] == targets


def test_vault_status_command(capsys: pytest.CaptureFixture[str]) -> None:
    """Test `vault status` text and JSON output."""
    cfg = VaultConfig(
        vault_addr="https://vault.example.com",
        token="s.superSecretToken12345",
        namespace="corp-team",
    )

    # 1. Text status
    code = handle_vault_status_command(config=cfg, as_json=False)
    assert code == 0
    captured = capsys.readouterr()
    assert "HashiCorp Vault Plugin Status:" in captured.out
    assert "VAULT_ADDR:            https://vault.example.com" in captured.out
    assert "Token configured:      yes" in captured.out
    assert "Namespace:             corp-team" in captured.out
    # Verify token is NEVER printed
    assert "s.superSecretToken12345" not in captured.out

    # 2. JSON status
    code_json = handle_vault_status_command(config=cfg, as_json=True)
    assert code_json == 0
    captured_json = capsys.readouterr()
    json_data = json.loads(captured_json.out)
    assert json_data["provider"] == "vault"
    assert json_data["vaultAddr"] == "https://vault.example.com"
    assert json_data["tokenSet"] is True
    assert "token" not in json_data


def test_vault_setup_command(tmp_path: Path) -> None:
    """Test `vault setup` CLI execution."""
    out_file = tmp_path / "vault_cli_plan.json"
    code = handle_vault_setup_command(
        args=[
            "--openrouter-id",
            "providers/openrouter/apiKey",
            "--plan-out",
            str(out_file),
        ]
    )
    assert code == 0
    assert out_file.exists()


def test_vault_doctor_checks(sample_token_file: Path, tmp_path: Path) -> None:
    """Test doctor diagnostics for Vault."""
    # 1. Valid config
    findings = run_vault_doctor_checks(
        {
            "vaultAddr": "https://vault.example.com",
            "token": "s.token",
        }
    )
    status_map = {f.check_id: f.status for f in findings}
    assert status_map["vault/address-configured"] == "ok"
    assert status_map["vault/auth-credentials"] == "ok"
    assert status_map["vault/kv-config"] == "ok"

    # 2. Missing address
    findings_no_addr = run_vault_doctor_checks(
        {
            "vaultAddr": "",
            "token": "s.token",
        }
    )
    status_map_no_addr = {f.check_id: f.status for f in findings_no_addr}
    assert status_map_no_addr["vault/address-configured"] == "error"

    # 3. Missing token
    findings_no_token = run_vault_doctor_checks(
        {
            "vaultAddr": "https://vault.example.com",
            "token": "",
        }
    )
    status_map_no_token = {f.check_id: f.status for f in findings_no_token}
    assert status_map_no_token["vault/auth-credentials"] == "error"
