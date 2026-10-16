"""Unit tests for SecretRef parsing, setup plan builder, CLI handlers, and doctor checks."""

import json
from pathlib import Path

import pytest
from extensions.onepassword.src.cli import (
    handle_audit_command,
    handle_secretref_setup_command,
    handle_secretref_status_command,
    handle_status_command,
)
from extensions.onepassword.src.config import OnepasswordConfig, OnepasswordItemConfig
from extensions.onepassword.src.doctor import run_doctor_checks
from extensions.onepassword.src.secretref import (
    ParsedSecretRef,
    build_secrets_setup_plan,
    decode_opaque_secret_ref,
    encode_opaque_secret_ref,
)
from extensions.onepassword.src.storage import OnepasswordStorage


def test_secretref_parsing() -> None:
    """Test parsing 3-part and 4-part 1Password URI references."""
    # 3-part: vault/item/field
    ref1 = ParsedSecretRef.parse("op://Automation/Anthropic/credential")
    assert ref1.vault == "Automation"
    assert ref1.item == "Anthropic"
    assert ref1.field == "credential"
    assert ref1.section is None

    # 4-part: vault/item/section/field
    ref2 = ParsedSecretRef.parse("op://Automation/Anthropic/Production/credential")
    assert ref2.vault == "Automation"
    assert ref2.item == "Anthropic"
    assert ref2.section == "Production"
    assert ref2.field == "credential"

    # Spaces in names
    ref3 = ParsedSecretRef.parse("op://Agent credentials/Model provider key/credential")
    assert ref3.vault == "Agent credentials"
    assert ref3.item == "Model provider key"
    assert ref3.field == "credential"

    # Invalid URIs
    with pytest.raises(ValueError, match="must start with 'op://'"):
        ParsedSecretRef.parse("invalid://vault/item/field")

    with pytest.raises(ValueError, match="contain at least vault, item, and field"):
        ParsedSecretRef.parse("op://vault/item")


def test_opaque_secretref_encoding() -> None:
    """Test encoding and decoding opaque SecretRef references."""
    raw = "op://My Vault/Special Item #1/Section.Alpha/my-field"
    opaque = encode_opaque_secret_ref(raw)
    assert opaque.startswith("op-opaque:")

    decoded = decode_opaque_secret_ref(opaque)
    assert decoded == raw

    # Parsing opaque directly
    parsed = ParsedSecretRef.parse(opaque)
    assert parsed.vault == "My Vault"
    assert parsed.item == "Special Item #1"
    assert parsed.field == "my-field"


def test_build_secrets_setup_plan(tmp_path: Path) -> None:
    """Test generating a secrets setup plan document."""
    plan = build_secrets_setup_plan(
        anthropic_id="op://Automation/Anthropic/credential",
        openrouter_id="op://Automation/OpenRouter/credential",
        provider_keys=["openai=op://Automation/OpenAI/credential"],
        targets=["channels.telegram.botToken=op://Automation/Telegram/token"],
    )

    data = plan.to_dict()
    assert data["schemaVersion"] == 1
    assert data["provider"]["id"] == "onepassword"
    targets = data["targets"]
    assert "models.providers.anthropic.apiKey" in targets
    assert "models.providers.openrouter.apiKey" in targets
    assert "models.providers.openai.apiKey" in targets
    assert "channels.telegram.botToken" in targets

    out_file = tmp_path / "plan.json"
    plan.save(out_file)
    assert out_file.exists()
    loaded = json.loads(out_file.read_text(encoding="utf-8"))
    assert loaded["targets"] == targets


def test_cli_handlers(
    mock_state_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test CLI commands: status, audit, secretref status, secretref setup."""
    db_path = mock_state_dir / "state" / "jarvis.sqlite"
    storage = OnepasswordStorage(db_path=db_path)
    storage.record_audit(
        slug="test-slug",
        action="get",
        outcome="allowed",
        reason="test reason",
    )

    config = OnepasswordConfig(
        vault="Automation",
        items={
            "test-slug": OnepasswordItemConfig(item="Test Item", policy="auto"),
        },
    )

    # 1. status
    handle_status_command(config=config, state_dir=mock_state_dir, storage=storage)
    captured = capsys.readouterr()
    assert "1Password Plugin Status:" in captured.out
    assert "Registered items:      1" in captured.out

    # 2. audit
    handle_audit_command(storage=storage, limit=10)
    captured_audit = capsys.readouterr()
    assert "test-slug" in captured_audit.out
    assert "allowed" in captured_audit.out

    # 3. secretref status text
    handle_secretref_status_command(config=config, state_dir=mock_state_dir, as_json=False)
    captured_sr = capsys.readouterr()
    assert "1Password SecretRef Status:" in captured_sr.out

    # 4. secretref status JSON
    handle_secretref_status_command(config=config, state_dir=mock_state_dir, as_json=True)
    captured_json = capsys.readouterr()
    sr_data = json.loads(captured_json.out)
    assert sr_data["provider"] == "onepassword"
    assert sr_data["tokenReady"] is True

    # 5. secretref setup CLI
    plan_out = tmp_path / "cli_plan.json"
    code = handle_secretref_setup_command(
        args=[
            "--anthropic-id",
            "op://Automation/Anthropic/credential",
            "--plan-out",
            str(plan_out),
        ],
        state_dir=mock_state_dir,
    )
    assert code == 0
    assert plan_out.exists()


def test_doctor_checks(mock_state_dir: Path) -> None:
    """Test doctor diagnostics."""
    findings = run_doctor_checks(
        raw_config={
            "vault": "Automation",
            "items": {"repo-token": {"item": "Repo Token"}},
        },
        state_dir=mock_state_dir,
    )

    checks = {f.check_id: f for f in findings}
    assert "onepassword/config-validity" in checks
    assert checks["onepassword/config-validity"].status == "ok"
    assert "onepassword/token-file" in checks
    assert checks["onepassword/token-file"].status == "ok"
