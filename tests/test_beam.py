"""Tests for src/plugins/beam.py.

Mirrors tests of beam plugin contract in OpenClaw.
"""

from __future__ import annotations


from src.plugins.beam import (
    BEAM_ITEM_TYPES,
    BEAM_MAX_BODY_BYTES,
    BEAM_MAX_ITEMS,
    BEAM_MAX_ITEM_TEXT_CHARS,
    BEAM_ROUTE_PATH,
    build_beam_session_url,
    resolve_beam_mirror_config,
)


def test_beam_constants():
    assert BEAM_ROUTE_PATH == "/api/v1/beam/sessions"
    assert BEAM_MAX_BODY_BYTES == 56 * 1024
    assert BEAM_MAX_ITEMS == 200
    assert BEAM_MAX_ITEM_TEXT_CHARS == 6000
    assert "userMessage" in BEAM_ITEM_TYPES
    assert "agentMessage" in BEAM_ITEM_TYPES
    assert "other" in BEAM_ITEM_TYPES


def test_build_beam_session_url():
    url = build_beam_session_url("0123456789abcdef")
    assert url == "/chat/main?catalog=beam&host=gateway&thread=0123456789abcdef"


def test_resolve_beam_mirror_config_none():
    assert resolve_beam_mirror_config(None) is None
    assert resolve_beam_mirror_config({"mirror": {}}) is None


def test_resolve_beam_mirror_config_valid():
    cfg_raw = {
        "mirror": {
            "endpoint": "https://team.example.com/api/v1/beam/sessions",
            "token": "secret_token",
            "catalogs": ["claude", "codex"],
            "pollSeconds": 5,  # clamped to min 10
            "activeWindowMinutes": 120,
        }
    }
    mirror = resolve_beam_mirror_config(cfg_raw)
    assert mirror is not None
    assert mirror.endpoint == "https://team.example.com/api/v1/beam/sessions"
    assert mirror.catalogs == ["claude", "codex"]
    assert mirror.token == "secret_token"
    assert mirror.pollSeconds == 10
    assert mirror.activeWindowMinutes == 120
