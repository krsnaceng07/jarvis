"""Tests for src/plugins/plugin_source.py.

Mirrors tests of plugins/install-source-info.ts in OpenClaw.
"""

from __future__ import annotations


from src.plugins.plugin_source import parse_plugin_source_spec


def test_parse_clawhub_spec():
    res = parse_plugin_source_spec("clawhub:calendar@1.2.3")
    assert res.kind == "clawhub"
    assert res.package_name == "calendar"
    assert res.version == "1.2.3"


def test_parse_npm_spec():
    res = parse_plugin_source_spec("npm:@openclaw/codex@2.0.0")
    assert res.kind == "npm"
    assert res.package_name == "@openclaw/codex"
    assert res.version == "2.0.0"


def test_parse_git_spec():
    res = parse_plugin_source_spec("git:github.com/acme/openclaw-plugin@v1.0.0")
    assert res.kind == "git"
    assert res.package_name == "github.com/acme/openclaw-plugin"
    assert res.git_ref == "v1.0.0"


def test_parse_local_path():
    res = parse_plugin_source_spec("./my-plugin")
    assert res.kind == "local"
    assert res.path == "./my-plugin"


def test_parse_bare_fallback():
    res = parse_plugin_source_spec("my-custom-plugin")
    assert res.kind == "npm"
    assert res.package_name == "my-custom-plugin"
