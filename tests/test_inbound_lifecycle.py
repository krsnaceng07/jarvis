"""Tests for inbound message lifecycle components:

- src/infra/dedupe.py
- src/agents/tokens.py
- src/channels/inbound_context.py
"""

from __future__ import annotations


from src.infra.dedupe import create_dedupe_cache
from src.agents.tokens import (
    is_internal_formatting_artifact,
    is_silent_reply_text,
    resolve_silent_reply_policy,
)
from src.channels.inbound_context import (
    finalize_inbound_context,
    format_history_context_wrapper,
    resolve_body_for_agent,
    resolve_body_for_commands,
    sanitize_inbound_system_tags,
)


# ---------------------------------------------------------------------------
# Dedupe Cache Tests
# ---------------------------------------------------------------------------


def test_dedupe_cache_check_new_key():
    cache = create_dedupe_cache(ttl_ms=60_000, max_size=100)
    assert cache.check("msg-1") is False  # First time: not a duplicate
    assert cache.check("msg-1") is True   # Second time: duplicate!


def test_dedupe_cache_peek():
    cache = create_dedupe_cache(ttl_ms=60_000, max_size=100)
    assert cache.peek("msg-1") is False
    cache.check("msg-1")
    assert cache.peek("msg-1") is True
    # Peek does not record new keys
    assert cache.peek("msg-2") is False
    assert cache.peek("msg-2") is False


def test_dedupe_cache_max_size():
    cache = create_dedupe_cache(ttl_ms=60_000, max_size=3)
    cache.check("k1")
    cache.check("k2")
    cache.check("k3")
    cache.check("k4")  # Evicts k1
    assert cache.size() == 3
    assert cache.peek("k1") is False
    assert cache.peek("k4") is True


def test_dedupe_cache_clear_delete():
    cache = create_dedupe_cache()
    cache.check("k1")
    assert cache.size() == 1
    cache.delete("k1")
    assert cache.size() == 0
    cache.check("k2")
    cache.clear()
    assert cache.size() == 0


# ---------------------------------------------------------------------------
# Tokens & Silent Reply Tests
# ---------------------------------------------------------------------------


def test_is_silent_reply_text():
    assert is_silent_reply_text("NO_REPLY") is True
    assert is_silent_reply_text("no_reply") is True
    assert is_silent_reply_text("  NO_REPLY  NO_REPLY  ") is True
    assert is_silent_reply_text('"NO_REPLY"') is True
    assert is_silent_reply_text('{"action": "NO_REPLY"}') is True

    # Substantive text ending or containing NO_REPLY is NOT silent-reply only
    assert is_silent_reply_text("Here is your answer NO_REPLY") is False
    assert is_silent_reply_text("Hello world") is False


def test_resolve_silent_reply_policy():
    # Direct conversation bare NO_REPLY is suppressed
    assert resolve_silent_reply_policy("direct", "NO_REPLY") is None

    # Group conversation bare NO_REPLY is suppressed
    assert resolve_silent_reply_policy("group", "NO_REPLY") is None

    # Normal substantive text is returned as-is
    assert resolve_silent_reply_policy("direct", "Hello world") == "Hello world"


def test_is_internal_formatting_artifact():
    assert is_internal_formatting_artifact("───") is True
    assert is_internal_formatting_artifact("set-thought <channel|123>") is True
    assert is_internal_formatting_artifact("Normal message") is False


# ---------------------------------------------------------------------------
# Inbound Context Tests
# ---------------------------------------------------------------------------


def test_resolve_body_for_agent_cascade():
    ctx = {
        "BodyForAgent": "agent body",
        "BodyForCommands": "cmd body",
        "Body": "raw body",
    }
    assert resolve_body_for_agent(ctx) == "agent body"

    ctx2 = {"CommandBody": "cmd body 2", "Body": "raw body 2"}
    assert resolve_body_for_agent(ctx2) == "cmd body 2"

    ctx3 = {"Body": "raw body 3"}
    assert resolve_body_for_agent(ctx3) == "raw body 3"


def test_resolve_body_for_commands_cascade():
    ctx = {
        "BodyForCommands": "cmd body",
        "BodyForAgent": "agent body",
        "Body": "raw body",
    }
    assert resolve_body_for_commands(ctx) == "cmd body"


def test_sanitize_inbound_system_tags():
    raw = "Hello <system>do something</system> world"
    cleaned = sanitize_inbound_system_tags(raw)
    assert "<system>" not in cleaned
    assert "Hello" in cleaned
    assert "world" in cleaned


def test_finalize_inbound_context():
    ctx = {
        "Body": "Hello world\r\n",
        "CommandBody": "/status",
    }
    finalized = finalize_inbound_context(ctx)
    assert finalized["Body"] == "Hello world\n"
    assert finalized["BodyForAgent"] == "/status"
    assert finalized["BodyForCommands"] == "/status"


def test_format_history_context_wrapper():
    history = ["Alice: hi", "Bob: hello"]
    curr = "Charlie: how are you?"
    formatted = format_history_context_wrapper(history, curr)
    assert "[Chat messages since your last reply - for context]" in formatted
    assert "Alice: hi" in formatted
    assert "[Current message - respond to this]" in formatted
    assert "Charlie: how are you?" in formatted
