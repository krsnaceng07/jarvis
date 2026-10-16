"""Tests for src/channels/streaming_config.py.

Mirrors channels/streaming.ts config resolution in OpenClaw.
"""

from __future__ import annotations


from src.channels.streaming_config import (
    resolve_channel_progress_config,
    resolve_channel_streaming_config,
    resolve_channel_streaming_mode,
)


def test_resolve_default_streaming_modes():
    assert resolve_channel_streaming_mode("telegram") == "progress"
    assert resolve_channel_streaming_mode("slack") == "progress"
    assert resolve_channel_streaming_mode("discord") == "off"
    assert resolve_channel_streaming_mode("mattermost") == "partial"


def test_resolve_custom_streaming_mode():
    cfg = {"streaming": {"mode": "progress"}}
    assert resolve_channel_streaming_mode("discord", cfg) == "progress"

    cfg_off = {"streaming": {"mode": "off"}}
    assert resolve_channel_streaming_mode("telegram", cfg_off) == "off"


def test_resolve_progress_config():
    prog = resolve_channel_progress_config("discord")
    assert prog.label == "auto"
    assert prog.tool_progress is True
    assert prog.command_text == "status"
    assert prog.max_lines == 8
    assert prog.max_line_chars == 120

    custom_cfg = {
        "streaming": {
            "mode": "progress",
            "progress": {
                "label": "Investigating",
                "toolProgress": False,
                "commandText": "raw",
                "maxLines": 4,
                "maxLineChars": 160,
            },
        }
    }

    custom_prog = resolve_channel_progress_config("discord", custom_cfg)
    assert custom_prog.label == "Investigating"
    assert custom_prog.tool_progress is False
    assert custom_prog.command_text == "raw"
    assert custom_prog.max_lines == 4
    assert custom_prog.max_line_chars == 160


def test_resolve_full_streaming_config():
    full_cfg = resolve_channel_streaming_config("telegram")
    assert full_cfg.mode == "progress"
    assert full_cfg.progress.tool_progress is True
