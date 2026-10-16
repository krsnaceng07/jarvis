"""Tests for src/plugins/codex_supervision.py.

Mirrors tests of codex-supervision-tools-serve in OpenClaw.
"""

from __future__ import annotations


from src.plugins.codex_supervision import (
    LEGACY_SUPERVISOR_TOOL_NAMES,
    resolve_codex_session_catalog_config,
    resolve_codex_supervision_config,
)


def test_legacy_supervisor_tool_names():
    assert "codex_sessions_list" in LEGACY_SUPERVISOR_TOOL_NAMES
    assert "codex_session_read" in LEGACY_SUPERVISOR_TOOL_NAMES
    assert "codex_session_send" in LEGACY_SUPERVISOR_TOOL_NAMES
    assert len(LEGACY_SUPERVISOR_TOOL_NAMES) == 5


def test_resolve_codex_supervision_config():
    cfg = resolve_codex_supervision_config(None)
    assert cfg.enabled is False
    assert cfg.allow_raw_transcripts is False
    assert cfg.allow_write_controls is False

    custom_plugin_cfg = {
        "supervision": {
            "enabled": True,
            "allowRawTranscripts": True,
            "allowWriteControls": True,
        }
    }
    custom_cfg = resolve_codex_supervision_config(custom_plugin_cfg)
    assert custom_cfg.enabled is True
    assert custom_cfg.allow_raw_transcripts is True
    assert custom_cfg.allow_write_controls is True


def test_resolve_codex_session_catalog_config():
    cat = resolve_codex_session_catalog_config(None)
    assert cat.enabled is True

    custom = resolve_codex_session_catalog_config({"sessionCatalog": {"enabled": False}})
    assert custom.enabled is False
