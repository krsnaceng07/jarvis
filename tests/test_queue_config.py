"""Tests for src/config/queue_config.py.

Mirrors tests of queue-helpers.ts and queue precedence in OpenClaw.
"""

from __future__ import annotations


from src.config.queue_config import (
    parse_queue_command,
    parse_time_duration_ms,
    resolve_queue_config,
    resolve_queue_mode,
)


def test_parse_time_duration_ms():
    assert parse_time_duration_ms("500ms") == 500
    assert parse_time_duration_ms("0.5s") == 500
    assert parse_time_duration_ms("2s") == 2000
    assert parse_time_duration_ms("1m") == 60_000
    assert parse_time_duration_ms(1500) == 1500


def test_parse_queue_command():
    parsed_steer = parse_queue_command("/queue steer")
    assert parsed_steer == {"mode": "steer"}

    parsed_opts = parse_queue_command("/queue collect debounce:0.5s cap:25 drop:summarize")
    assert parsed_opts["mode"] == "collect"
    assert parsed_opts["debounce_ms"] == 500
    assert parsed_opts["cap"] == 25
    assert parsed_opts["drop"] == "summarize"

    parsed_reset = parse_queue_command("/queue reset")
    assert parsed_reset == {"reset": True}


def test_resolve_queue_mode_precedence():
    cfg = {
        "messages": {
            "queue": {
                "mode": "followup",
                "byChannel": {
                    "discord": "collect",
                },
            }
        }
    }

    # 1. Session override wins
    assert resolve_queue_mode(cfg, channel="discord", session_override_mode="interrupt") == "interrupt"

    # 2. Channel override wins over global
    assert resolve_queue_mode(cfg, channel="discord") == "collect"

    # 3. Global mode used when channel has no override
    assert resolve_queue_mode(cfg, channel="telegram") == "followup"

    # 4. Default fallback when no config
    assert resolve_queue_mode(None) == "steer"


def test_resolve_queue_config():
    cfg = {
        "messages": {
            "queue": {
                "mode": "followup",
                "cap": 15,
                "drop": "summarize",
            }
        }
    }

    resolved = resolve_queue_config(cfg)
    assert resolved.mode == "followup"
    assert resolved.cap == 15
    assert resolved.drop == "summarize"
    assert resolved.debounce_ms == 500
