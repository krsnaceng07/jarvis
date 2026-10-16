"""Tests for Wave 16 — Channels Core Body."""

from __future__ import annotations


from src.channels import (
    SessionEnvelope,
    ThreadContext,
    resolve_channel_model,
    resolve_send_target,
    resolve_thread_id,
    thread_reply_target,
)


def test_session_envelope():
    env = SessionEnvelope(
        channel_id="telegram",
        sender_id="12345",
        content="Hello JARVIS",
        thread_id="99",
    )
    assert env.session_key == "telegram:12345:99"
    assert env.allowed


def test_resolve_thread_id_and_target():
    raw_msg = {"message_thread_id": 42}
    thread_id = resolve_thread_id(raw_msg)
    assert thread_id == "42"

    ctx = ThreadContext(channel_id="telegram", thread_id="42", parent_msg_id="101")
    target = thread_reply_target(ctx)
    assert target == {"channel_id": "telegram", "thread_id": "42", "reply_to_message_id": "101"}


def test_resolve_send_target():
    target = resolve_send_target("TELEGRAM", " 12345 ", thread_id=" 10 ")
    assert target.channel_id == "telegram"
    assert target.target_id == "12345"
    assert target.thread_id == "10"


def test_resolve_channel_model():
    cfg = {
        "channels": {
            "telegram": {"model": "models/gemini-3.1-flash"},
            "discord": {"model_override": "models/claude-3-5-sonnet"},
        }
    }
    assert resolve_channel_model("telegram", cfg) == "models/gemini-3.1-flash"
    assert resolve_channel_model("discord", cfg) == "models/claude-3-5-sonnet"
    assert resolve_channel_model("slack", cfg) is None
