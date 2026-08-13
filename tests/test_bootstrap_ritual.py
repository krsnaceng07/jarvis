"""Test bootstrap ritual and config persistence."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from jarvis_config_core import AgentIdentity, JarvisConfig, load_config, save_config
from src.bootstrap import bootstrap_with_ritual


def test_bootstrap_ritual_result_structure(tmp_path: Path) -> None:
    """Verify ritual returns correct structure with agent name and soul."""
    config = JarvisConfig()

    # Mock user input for the three beats
    with patch("builtins.input") as mock_input:
        mock_input.side_effect = [
            "Arthur",      # Beat 1: agent name
            "Witty butler",  # Beat 2: soul
            "1",           # Beat 3: minimal plugins
        ]
        result, updated_config = bootstrap_with_ritual(tmp_path, config, skip_bootstrap=True)

    assert updated_config.agent.name == "Arthur"
    assert updated_config.agent.soul == "Witty butler"
    assert updated_config.agent.workspace_configured is True


def test_bootstrap_ritual_persists_to_identity_files(tmp_path: Path) -> None:
    """Verify ritual persists choices to IDENTITY.md and SOUL.md."""
    (tmp_path / "AGENTS.md").touch()  # Mark workspace as seeded

    config = JarvisConfig()

    with patch("builtins.input") as mock_input:
        mock_input.side_effect = [
            "Maxwell",
            "Formal and concise",
            "2",
        ]
        bootstrap_with_ritual(tmp_path, config, skip_bootstrap=True)

    identity_path = tmp_path / "IDENTITY.md"
    soul_path = tmp_path / "SOUL.md"

    assert identity_path.exists()
    assert soul_path.exists()

    identity_text = identity_path.read_text(encoding="utf-8")
    soul_text = soul_path.read_text(encoding="utf-8")

    assert "Maxwell" in identity_text
    assert "Formal and concise" in soul_text


def test_bootstrap_ritual_persists_to_config(tmp_path: Path) -> None:
    """Verify ritual persists agent identity to config.json."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_path = config_dir / "jarvis.json"

    config = JarvisConfig()
    save_config(config, config_path=config_path)

    # Mark workspace as seeded
    (tmp_path / "AGENTS.md").touch()

    with patch("builtins.input") as mock_input:
        mock_input.side_effect = [
            "Lexington",
            "Cool and collected",
            "1",
        ]
        _, updated_config = bootstrap_with_ritual(tmp_path, config, skip_bootstrap=True)

    # Manually save to verify file was updated
    save_config(updated_config, config_path=config_path)

    # Reload from disk
    reloaded = load_config(config_path=config_path)

    assert reloaded.agent.name == "Lexington"
    assert reloaded.agent.soul == "Cool and collected"
    assert reloaded.agent.workspace_configured is True


def test_bootstrap_ritual_skips_on_configured_workspace(tmp_path: Path) -> None:
    """Verify ritual does not run if workspace is already configured."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    # Mark workspace as configured
    identity_path = tmp_path / "IDENTITY.md"
    identity_path.write_text("# Identity\nAlready configured\n", encoding="utf-8")

    config = JarvisConfig()

    # No input mock needed — ritual should be skipped
    result, updated_config = bootstrap_with_ritual(tmp_path, config, skip_bootstrap=True)

    # Ritual should not have changed the config
    assert updated_config.agent.name == "JARVIS"  # default


def test_bootstrap_ritual_default_name(tmp_path: Path) -> None:
    """Verify default agent name is JARVIS if user presses enter."""
    config = JarvisConfig()

    with patch("builtins.input") as mock_input:
        mock_input.side_effect = [
            "",  # Empty input for name → defaults to JARVIS
            "Silent and swift",
            "2",
        ]
        _, updated_config = bootstrap_with_ritual(tmp_path, config, skip_bootstrap=True)

    assert updated_config.agent.name == "JARVIS"


def test_bootstrap_ritual_rejects_long_names(tmp_path: Path) -> None:
    """Verify ritual rejects agent names longer than 32 chars."""
    config = JarvisConfig()

    long_name = "A" * 40
    valid_name = "ValidName"

    with patch("builtins.input") as mock_input:
        # First call too long, second call valid, then soul and plugins
        mock_input.side_effect = [
            long_name,    # Rejected
            valid_name,   # Accepted
            "Some soul",
            "1",
        ]
        _, updated_config = bootstrap_with_ritual(tmp_path, config, skip_bootstrap=True)

    assert updated_config.agent.name == valid_name


def test_agent_identity_in_config_schema() -> None:
    """Verify AgentIdentity is part of JarvisConfig schema."""
    config = JarvisConfig()
    assert isinstance(config.agent, AgentIdentity)
    assert config.agent.name == "JARVIS"
    assert config.agent.workspace_configured is False


def test_agent_identity_serialization(tmp_path: Path) -> None:
    """Verify agent identity round-trips through JSON."""
    config_path = tmp_path / "config.json"

    original = JarvisConfig(
        agent=AgentIdentity(
            name="TestAgent",
            soul="Test soul line",
            workspace_configured=True,
        )
    )
    save_config(original, config_path=config_path)

    loaded = load_config(config_path=config_path)

    assert loaded.agent.name == "TestAgent"
    assert loaded.agent.soul == "Test soul line"
    assert loaded.agent.workspace_configured is True
