"""Tests for src/plugins/onepassword.py.

Mirrors tests of extensions/onepassword/src/config.ts in OpenClaw.
"""

from __future__ import annotations

import pytest

from src.plugins.onepassword import (
    MAX_REGISTERED_ITEMS,
    ONEPASSWORD_ERROR_CODES,
    ONEPASSWORD_PLUGIN_ID,
    ONEPASSWORD_TOOL_NAME,
    is_valid_onepassword_slug,
    parse_op_secret_uri,
    resolve_onepassword_config,
)


def test_onepassword_constants():
    assert ONEPASSWORD_PLUGIN_ID == "onepassword"
    assert ONEPASSWORD_TOOL_NAME == "onepassword"
    assert "TOKEN_MISSING" in ONEPASSWORD_ERROR_CODES
    assert "RATE_LIMITED" in ONEPASSWORD_ERROR_CODES
    assert len(ONEPASSWORD_ERROR_CODES) == 17
    assert MAX_REGISTERED_ITEMS == 32


def test_is_valid_onepassword_slug():
    assert is_valid_onepassword_slug("repository-token") is True
    assert is_valid_onepassword_slug("model-key-1") is True
    assert is_valid_onepassword_slug("-invalid-start") is False
    assert is_valid_onepassword_slug("Invalid_Caps") is False


def test_parse_op_secret_uri_3_parts():
    res = parse_op_secret_uri("op://Automation/OpenRouter/credential")
    assert res["vault"] == "Automation"
    assert res["item"] == "OpenRouter"
    assert res["field"] == "credential"


def test_parse_op_secret_uri_4_parts():
    res = parse_op_secret_uri("op://Automation/OpenRouter/Section/credential")
    assert res["vault"] == "Automation"
    assert res["item"] == "OpenRouter"
    assert res["section"] == "Section"
    assert res["field"] == "credential"


def test_parse_op_secret_uri_invalid():
    with pytest.raises(ValueError, match="Must start with 'op://'"):
        parse_op_secret_uri("https://example.com")

    with pytest.raises(ValueError, match="Expected 'op://<vault>/<item>/<field>'"):
        parse_op_secret_uri("op://Automation/OpenRouter")


def test_resolve_onepassword_config():
    cfg_raw = {
        "vault": "Automation",
        "defaultPolicy": "approve",
        "items": {
            "repository-token": {
                "item": "Repository token",
                "field": "credential",
                "policy": "approve",
                "description": "Token for repo",
            }
        },
    }
    cfg = resolve_onepassword_config(cfg_raw)
    assert cfg.vault == "Automation"
    assert cfg.defaultPolicy == "approve"
    assert "repository-token" in cfg.items
    item = cfg.items["repository-token"]
    assert item.item == "Repository token"
    assert item.vault == "Automation"
    assert item.field == "credential"
    assert item.policy == "approve"
    assert item.description == "Token for repo"
