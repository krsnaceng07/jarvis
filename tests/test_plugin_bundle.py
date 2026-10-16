"""Tests for src/plugins/plugin_bundle.py.

Mirrors tests of bundle-manifest.ts and agent-bundle-mcp-names.ts in OpenClaw.
"""

from __future__ import annotations

from pathlib import Path

from src.plugins.plugin_bundle import (
    build_safe_tool_name,
    detect_plugin_bundle_format,
    sanitize_server_name,
)


def test_detect_native_plugin(tmp_path: Path):
    (tmp_path / "jarvis.plugin.json").write_text("{}", encoding="utf-8")
    res = detect_plugin_bundle_format(tmp_path)
    assert res.format_type == "native"


def test_detect_codex_bundle(tmp_path: Path):
    codex_dir = tmp_path / ".codex-plugin"
    codex_dir.mkdir()
    (codex_dir / "plugin.json").write_text("{}", encoding="utf-8")

    res = detect_plugin_bundle_format(tmp_path)
    assert res.format_type == "bundle"
    assert res.bundle_format == "codex"


def test_detect_claude_bundle(tmp_path: Path):
    claude_dir = tmp_path / ".claude-plugin"
    claude_dir.mkdir()
    (claude_dir / "plugin.json").write_text("{}", encoding="utf-8")

    res = detect_plugin_bundle_format(tmp_path)
    assert res.format_type == "bundle"
    assert res.bundle_format == "claude"


def test_detect_agent_plugin_bundle(tmp_path: Path):
    (tmp_path / "plugin.json").write_text("{}", encoding="utf-8")
    res = detect_plugin_bundle_format(tmp_path)
    assert res.format_type == "bundle"
    assert res.bundle_format == "agent"


def test_sanitize_server_name():
    used = set()
    s1 = sanitize_server_name("vigil-harbor", used)
    assert s1 == "vigil-harbor"

    # Numeric start gets 'mcp-' prefix
    s2 = sanitize_server_name("12306", used)
    assert s2.startswith("mcp-12306")

    # Collision disambiguation
    s3 = sanitize_server_name("vigil-harbor", used)
    assert s3 == "vigil-harbor-2"


def test_build_safe_tool_name():
    t_name = build_safe_tool_name("vigil-harbor", "memory_search")
    assert t_name == "vigil-harbor__memory_search"
    assert len(t_name) <= 64
