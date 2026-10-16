"""Tests for src/plugins/plugin_manifest.py.

Mirrors tests of plugins/manifest.ts in OpenClaw.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.plugins.plugin_manifest import (
    load_plugin_manifest,
)


def test_load_plugin_manifest_success(tmp_path: Path):
    manifest_data = {
        "id": "voice-call",
        "name": "Voice Call Plugin",
        "version": "1.0.0",
        "description": "Provides voice call provider",
        "format": "jarvis",
        "kind": "voice",
        "contracts": {
            "tools": ["make_call"],
            "providers": ["twilio"],
        },
        "config_schema": {
            "type": "object",
            "properties": {
                "account_sid": {"type": "string"},
            },
        },
    }

    (tmp_path / "jarvis.plugin.json").write_text(json.dumps(manifest_data), encoding="utf-8")

    manifest = load_plugin_manifest(tmp_path)
    assert manifest is not None
    assert manifest.id == "voice-call"
    assert manifest.name == "Voice Call Plugin"
    assert manifest.version == "1.0.0"
    assert manifest.contracts.tools == ["make_call"]
    assert manifest.contracts.providers == ["twilio"]
    assert "account_sid" in manifest.config_schema.get("properties", {})


def test_load_plugin_manifest_fallback_filename(tmp_path: Path):
    manifest_data = {"id": "legacy-plugin", "version": "0.1.0"}
    (tmp_path / "openclaw.plugin.json").write_text(json.dumps(manifest_data), encoding="utf-8")

    manifest = load_plugin_manifest(tmp_path)
    assert manifest is not None
    assert manifest.id == "legacy-plugin"


def test_load_plugin_manifest_non_existent():
    assert load_plugin_manifest("/non/existent/path") is None
