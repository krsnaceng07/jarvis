"""Tests for src/plugins/logbook.py.

Mirrors tests of extensions/logbook/src/config.ts in OpenClaw.
"""

from __future__ import annotations


from src.plugins.logbook import (
    LOGBOOK_RPC_METHODS,
    parse_model_ref,
    resolve_logbook_config,
)


def test_logbook_rpc_methods():
    assert "logbook.status" in LOGBOOK_RPC_METHODS
    assert "logbook.timeline" in LOGBOOK_RPC_METHODS
    assert len(LOGBOOK_RPC_METHODS) == 9


def test_resolve_logbook_config_defaults():
    cfg = resolve_logbook_config(None)
    assert cfg.captureEnabled is True
    assert cfg.captureIntervalSeconds == 30
    assert cfg.analysisIntervalMinutes == 15
    assert cfg.nodeId is None
    assert cfg.screenIndex == 0
    assert cfg.maxWidth == 1440
    assert cfg.visionModel is None
    assert cfg.retentionDays == 14


def test_resolve_logbook_config_clamping():
    raw = {
        "captureEnabled": False,
        "captureIntervalSeconds": 2,  # min is 5
        "analysisIntervalMinutes": 200,  # max is 120
        "nodeId": "  my-mac-node  ",
        "screenIndex": 20,  # max is 16
        "maxWidth": 200,  # min is 480
        "visionModel": "codex/gpt-5.6-sol",
        "retentionDays": 0,  # min is 1
    }
    cfg = resolve_logbook_config(raw)
    assert cfg.captureEnabled is False
    assert cfg.captureIntervalSeconds == 5
    assert cfg.analysisIntervalMinutes == 120
    assert cfg.nodeId == "my-mac-node"
    assert cfg.screenIndex == 16
    assert cfg.maxWidth == 480
    assert cfg.visionModel == "codex/gpt-5.6-sol"
    assert cfg.retentionDays == 1


def test_parse_model_ref():
    assert parse_model_ref("codex/gpt-5.6-sol") == ("codex", "gpt-5.6-sol")
    assert parse_model_ref("invalid-ref") is None
    assert parse_model_ref("/model") is None
    assert parse_model_ref("provider/") is None
