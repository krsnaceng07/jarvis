"""Tests for sender identity resolution.

OpenClaw parity: mirrors functions in
``openclaw-main/src/auto-reply/sender-identity.ts``.
"""

from jarvis.auto_reply.sender_identity import is_conversation_like_identity, should_use_from_as_sender_fallback


def test_is_conversation_like_identity() -> None:
    assert is_conversation_like_identity("chat_id:123") is True
    assert is_conversation_like_identity("channel:C123") is True
    assert is_conversation_like_identity("group:G123") is True
    assert is_conversation_like_identity("thread:T123") is True
    assert is_conversation_like_identity("topic:T123") is True
    assert is_conversation_like_identity("room:R123") is True
    assert is_conversation_like_identity("space:S123") is True
    assert is_conversation_like_identity("spaces:S123") is True
    assert is_conversation_like_identity("discord:channel:123") is True
    
    assert is_conversation_like_identity("user:U123") is False
    assert is_conversation_like_identity("whatsapp:+15551234567") is False
    assert is_conversation_like_identity("telegram:123456") is False
    assert is_conversation_like_identity(None) is False
    assert is_conversation_like_identity("") is False


def test_should_use_from_as_sender_fallback() -> None:
    assert should_use_from_as_sender_fallback("whatsapp:+15551234567", "direct") is True
    assert should_use_from_as_sender_fallback("whatsapp:+15551234567", None) is True
    
    assert should_use_from_as_sender_fallback("whatsapp:+15551234567", "group") is False
    assert should_use_from_as_sender_fallback("group:12345", "direct") is False
    assert should_use_from_as_sender_fallback(None, "direct") is False
    assert should_use_from_as_sender_fallback("", "direct") is False
