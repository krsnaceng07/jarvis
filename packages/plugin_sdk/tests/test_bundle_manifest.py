"""Tests for bundle_manifest.py and bundle_mcp.py.

Covers:
- detect_bundle_format() detection precedence (verbatim OpenClaw logic).
- load_bundle_manifest() per-format normalisation.
- Bundle capability detection per format.
- is_bundle_capability_supported() routing.
- MCP placeholder expansion.
- sanitize_mcp_tool_name() provider-safe naming.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jarvis_sdk.bundle_manifest import (
    detect_bundle_format,
    is_bundle_capability_supported,
    load_bundle_manifest,
    merge_bundle_path_lists,
    normalize_bundle_path_list,
)
from jarvis_sdk.bundle_mcp import (
    sanitize_mcp_tool_name,
)


# ── helpers ───────────────────────────────────────────────────────────────────


def _write(root: Path, rel: str, content: str = "") -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _write_json(root: Path, rel: str, obj: object) -> None:
    _write(root, rel, json.dumps(obj, indent=2))


AGENT_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"


# ── detect_bundle_format ──────────────────────────────────────────────────────


class TestDetectBundleFormat:
    def test_codex_marker_wins(self, tmp_path: Path) -> None:
        _write_json(tmp_path, ".codex-plugin/plugin.json", {"name": "x"})
        assert detect_bundle_format(tmp_path) == "codex"

    def test_cursor_marker(self, tmp_path: Path) -> None:
        _write_json(tmp_path, ".cursor-plugin/plugin.json", {"name": "x"})
        assert detect_bundle_format(tmp_path) == "cursor"

    def test_claude_marker(self, tmp_path: Path) -> None:
        _write_json(tmp_path, ".claude-plugin/plugin.json", {"name": "x"})
        assert detect_bundle_format(tmp_path) == "claude"

    def test_codex_beats_cursor(self, tmp_path: Path) -> None:
        _write_json(tmp_path, ".codex-plugin/plugin.json", {"name": "x"})
        _write_json(tmp_path, ".cursor-plugin/plugin.json", {"name": "x"})
        assert detect_bundle_format(tmp_path) == "codex"

    def test_native_manifest_returns_none(self, tmp_path: Path) -> None:
        _write_json(tmp_path, "openclaw.plugin.json", {"id": "native"})
        assert detect_bundle_format(tmp_path) is None

    def test_native_beats_codex_marker(self, tmp_path: Path) -> None:
        """Native manifest takes priority once client-specific markers are absent."""
        _write_json(tmp_path, "openclaw.plugin.json", {"id": "native"})
        _write_json(tmp_path, ".codex-plugin/plugin.json", {"name": "x"})
        # codex marker is checked BEFORE native, so codex wins here
        assert detect_bundle_format(tmp_path) == "codex"

    def test_agent_schema_detected(self, tmp_path: Path) -> None:
        _write_json(
            tmp_path,
            "plugin.json",
            {
                "$schema": AGENT_SCHEMA,
                "name": "my-agent",
            },
        )
        assert detect_bundle_format(tmp_path) == "agent"

    def test_wrong_agent_schema_returns_none(self, tmp_path: Path) -> None:
        _write_json(
            tmp_path,
            "plugin.json",
            {
                "$schema": "https://example.com/other-schema.json",
                "name": "x",
            },
        )
        assert detect_bundle_format(tmp_path) is None

    def test_manifestless_claude_skills_dir(self, tmp_path: Path) -> None:
        (tmp_path / "skills").mkdir()
        assert detect_bundle_format(tmp_path) == "claude"

    def test_manifestless_claude_commands_dir(self, tmp_path: Path) -> None:
        (tmp_path / "commands").mkdir()
        assert detect_bundle_format(tmp_path) == "claude"

    def test_manifestless_claude_mcp_file(self, tmp_path: Path) -> None:
        _write_json(tmp_path, ".mcp.json", {})
        assert detect_bundle_format(tmp_path) == "claude"

    def test_manifestless_claude_settings(self, tmp_path: Path) -> None:
        _write_json(tmp_path, "settings.json", {})
        assert detect_bundle_format(tmp_path) == "claude"

    def test_empty_dir_returns_none(self, tmp_path: Path) -> None:
        assert detect_bundle_format(tmp_path) is None


# ── load_bundle_manifest (per-format) ────────────────────────────────────────


class TestLoadBundleManifestAgent:
    def test_valid_agent(self, tmp_path: Path) -> None:
        _write_json(
            tmp_path,
            "plugin.json",
            {
                "$schema": AGENT_SCHEMA,
                "name": "Hello World",
            },
        )
        (tmp_path / "skills").mkdir()
        bm = load_bundle_manifest(tmp_path, "agent")
        assert bm is not None
        assert bm.bundle_format == "agent"
        assert bm.id == "hello-world"
        assert bm.name == "Hello World"
        assert "skills" in bm.skills

    def test_agent_missing_name_returns_none(self, tmp_path: Path) -> None:
        _write_json(tmp_path, "plugin.json", {"$schema": AGENT_SCHEMA})
        assert load_bundle_manifest(tmp_path, "agent") is None

    def test_agent_wrong_schema_returns_none(self, tmp_path: Path) -> None:
        _write_json(
            tmp_path,
            "plugin.json",
            {
                "$schema": "https://example.com/bad.schema.json",
                "name": "x",
            },
        )
        assert load_bundle_manifest(tmp_path, "agent") is None

    def test_agent_mcp_capability(self, tmp_path: Path) -> None:
        _write_json(
            tmp_path,
            "plugin.json",
            {
                "$schema": AGENT_SCHEMA,
                "name": "Has MCP",
            },
        )
        _write_json(tmp_path, "mcp.json", {})
        bm = load_bundle_manifest(tmp_path, "agent")
        assert bm is not None
        assert "mcpServers" in bm.capabilities

    def test_agent_activation_from_extension_namespace(self, tmp_path: Path) -> None:
        _write_json(
            tmp_path,
            "plugin.json",
            {
                "$schema": AGENT_SCHEMA,
                "name": "Always On",
                "extensions": {"ai.openclaw": {"activation": {"always": True}}},
            },
        )
        bm = load_bundle_manifest(tmp_path, "agent")
        assert bm is not None
        assert bm.activation == "always"


class TestLoadBundleManifestCodex:
    def test_basic_codex(self, tmp_path: Path) -> None:
        _write_json(
            tmp_path,
            ".codex-plugin/plugin.json",
            {
                "name": "Codex Plugin",
                "version": "1.2.3",
            },
        )
        (tmp_path / "skills").mkdir()
        bm = load_bundle_manifest(tmp_path, "codex")
        assert bm is not None
        assert bm.bundle_format == "codex"
        assert bm.version == "1.2.3"
        assert "skills" in bm.skills

    def test_codex_skills_from_manifest(self, tmp_path: Path) -> None:
        _write_json(
            tmp_path,
            ".codex-plugin/plugin.json",
            {
                "name": "X",
                "skills": ["my-skills"],
            },
        )
        bm = load_bundle_manifest(tmp_path, "codex")
        assert bm is not None
        assert "my-skills" in bm.skills

    def test_codex_hooks(self, tmp_path: Path) -> None:
        _write_json(tmp_path, ".codex-plugin/plugin.json", {"name": "X"})
        (tmp_path / "hooks").mkdir()
        bm = load_bundle_manifest(tmp_path, "codex")
        assert bm is not None
        assert "hooks" in bm.hooks
        assert "hooks" in bm.capabilities


class TestLoadBundleManifestClaude:
    def test_manifestless_skills_dir(self, tmp_path: Path) -> None:
        (tmp_path / "skills").mkdir()
        bm = load_bundle_manifest(tmp_path, "claude")
        assert bm is not None
        assert bm.bundle_format == "claude"
        assert "skills" in bm.skills

    def test_claude_commands_merged_into_skills(self, tmp_path: Path) -> None:
        (tmp_path / "commands").mkdir()
        bm = load_bundle_manifest(tmp_path, "claude")
        assert bm is not None
        assert "commands" in bm.skills
        assert "commands" in bm.capabilities

    def test_claude_agents_merged_into_skills(self, tmp_path: Path) -> None:
        (tmp_path / "agents").mkdir()
        bm = load_bundle_manifest(tmp_path, "claude")
        assert bm is not None
        assert "agents" in bm.skills

    def test_claude_mcp_capability(self, tmp_path: Path) -> None:
        _write_json(tmp_path, ".mcp.json", {})
        bm = load_bundle_manifest(tmp_path, "claude")
        assert bm is not None
        assert "mcpServers" in bm.capabilities

    def test_claude_settings_file(self, tmp_path: Path) -> None:
        _write_json(tmp_path, "settings.json", {})
        bm = load_bundle_manifest(tmp_path, "claude")
        assert bm is not None
        assert "settings.json" in bm.settings_files
        assert "settings" in bm.capabilities

    def test_claude_manifest_based(self, tmp_path: Path) -> None:
        _write_json(
            tmp_path,
            ".claude-plugin/plugin.json",
            {
                "name": "Claude Plugin",
                "version": "0.1.0",
            },
        )
        (tmp_path / "skills").mkdir()
        bm = load_bundle_manifest(tmp_path, "claude")
        assert bm is not None
        assert bm.name == "Claude Plugin"
        assert bm.version == "0.1.0"


class TestLoadBundleManifestCursor:
    def test_basic_cursor(self, tmp_path: Path) -> None:
        _write_json(tmp_path, ".cursor-plugin/plugin.json", {"name": "Cursor Plugin"})
        (tmp_path / "skills").mkdir()
        bm = load_bundle_manifest(tmp_path, "cursor")
        assert bm is not None
        assert bm.bundle_format == "cursor"
        assert "skills" in bm.skills

    def test_cursor_commands_dir(self, tmp_path: Path) -> None:
        _write_json(tmp_path, ".cursor-plugin/plugin.json", {"name": "X"})
        (tmp_path / ".cursor" / "commands").mkdir(parents=True)
        bm = load_bundle_manifest(tmp_path, "cursor")
        assert bm is not None
        assert ".cursor/commands" in bm.skills
        assert "commands" in bm.capabilities

    def test_cursor_rules_capability(self, tmp_path: Path) -> None:
        _write_json(tmp_path, ".cursor-plugin/plugin.json", {"name": "X"})
        (tmp_path / ".cursor" / "rules").mkdir(parents=True)
        bm = load_bundle_manifest(tmp_path, "cursor")
        assert bm is not None
        assert "rules" in bm.capabilities

    def test_cursor_mcp_capability(self, tmp_path: Path) -> None:
        _write_json(tmp_path, ".cursor-plugin/plugin.json", {"name": "X"})
        _write_json(tmp_path, ".mcp.json", {})
        bm = load_bundle_manifest(tmp_path, "cursor")
        assert bm is not None
        assert "mcpServers" in bm.capabilities


# ── is_bundle_capability_supported ───────────────────────────────────────────


@pytest.mark.parametrize(
    "bundle_format,capability,expected",
    [
        # skills — always supported
        ("agent", "skills", True),
        ("codex", "skills", True),
        ("claude", "skills", True),
        ("cursor", "skills", True),
        # mcpServers — always supported
        ("agent", "mcpServers", True),
        ("codex", "mcpServers", True),
        ("claude", "mcpServers", True),
        ("cursor", "mcpServers", True),
        # settings — always supported (used by claude detect)
        ("claude", "settings", True),
        ("codex", "settings", True),
        # commands — claude + cursor only
        ("claude", "commands", True),
        ("cursor", "commands", True),
        ("agent", "commands", False),
        ("codex", "commands", False),
        # agents — claude only
        ("claude", "agents", True),
        ("cursor", "agents", False),
        ("codex", "agents", False),
        # hooks — codex + claude only
        ("codex", "hooks", True),
        ("claude", "hooks", True),
        ("cursor", "hooks", False),
        ("agent", "hooks", False),
        # rules — NOT wired (detect only)
        ("cursor", "rules", False),
        # apps — NOT wired
        ("codex", "apps", False),
    ],
)
def test_is_bundle_capability_supported(
    bundle_format: str, capability: str, expected: bool
) -> None:
    assert is_bundle_capability_supported(bundle_format, capability) is expected  # type: ignore[arg-type]


# ── normalize_bundle_path_list ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value,expected",
    [
        ("skills", ["skills"]),
        (["skills", "commands"], ["skills", "commands"]),
        (["skills", " skills ", "commands"], ["skills", "commands"]),  # dedup
        ([], []),
        (None, []),
        (42, []),
    ],
)
def test_normalize_bundle_path_list(value: object, expected: list[str]) -> None:
    assert normalize_bundle_path_list(value) == expected


# ── merge_bundle_path_lists ───────────────────────────────────────────────────


def test_merge_bundle_path_lists_dedup_preserves_order() -> None:
    result = merge_bundle_path_lists(["a", "b"], ["b", "c"])
    assert result == ["a", "b", "c"]


# ── sanitize_mcp_tool_name ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "server,tool,expected",
    [
        ("my-server", "list_files", "my-server__list_files"),
        ("My Server!", "read file", "My-Server-__read-file"),
        ("123numeric", "tool", "s-123numeric__tool"),
        ("", "tool", "mcp__tool"),
        # Long server names are capped at 30 chars
        ("a" * 40, "t", f"{'a' * 30}__t"),
    ],
)
def test_sanitize_mcp_tool_name(server: str, tool: str, expected: str) -> None:
    assert sanitize_mcp_tool_name(server, tool) == expected


# ── slugify (via load_bundle_manifest id field) ───────────────────────────────


@pytest.mark.parametrize(
    "name,expected_id",
    [
        ("Hello World", "hello-world"),
        ("My Plugin!", "my-plugin"),
        ("  UPPER  ", "upper"),
        ("foo--bar", "foo-bar"),
        ("123", "123"),
    ],
)
def test_bundle_id_slugification(tmp_path: Path, name: str, expected_id: str) -> None:
    _write_json(
        tmp_path,
        "plugin.json",
        {
            "$schema": AGENT_SCHEMA,
            "name": name,
        },
    )
    bm = load_bundle_manifest(tmp_path, "agent")
    assert bm is not None
    assert bm.id == expected_id
