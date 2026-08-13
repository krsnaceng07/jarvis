"""Wave 1 tests — channels_core package: allowlist, bindings, reply, presence.

Tests the public surface of ``packages/channels_core/`` introduced in W1.
Does NOT test network calls (Telegram API) — those require UV_LIVE_TEST=1.
"""

from __future__ import annotations

import threading
import time


from jarvis_channels import (
    BindingRegistry,
    InboundMessage,
    derive_session_key,
    derive_webhook_path,
    format_reply,
    is_allowed,
    normalize_allowlist,
    sender_label,
    split_reply,
    strip_markdown,
)
from jarvis_channels.presence import PresenceEmitter, ReactionEmitter


# ── Allowlist ──────────────────────────────────────────────────────────


class TestAllowlist:
    def test_none_policy_allows_all(self) -> None:
        assert is_allowed("999", None, None)

    def test_star_string_allows_all(self) -> None:
        assert is_allowed("999", None, "*")

    def test_empty_list_allows_all(self) -> None:
        assert is_allowed("999", None, [])

    def test_exact_id_match(self) -> None:
        assert is_allowed("123", None, ["123", "456"])

    def test_unknown_id_blocked(self) -> None:
        assert not is_allowed("999", None, ["123", "456"])

    def test_username_match(self) -> None:
        assert is_allowed("999", "alice", ["@alice"])

    def test_username_case_insensitive(self) -> None:
        assert is_allowed("999", "ALICE", ["@alice"])

    def test_username_strip_at(self) -> None:
        assert is_allowed("999", "@alice", ["@alice"])

    def test_star_in_list_allows_all(self) -> None:
        assert is_allowed("999", None, ["123", "*"])

    def test_normalize_star_string(self) -> None:
        assert normalize_allowlist("*") is None

    def test_normalize_comma_string(self) -> None:
        result = normalize_allowlist("123, 456")
        assert result == ["123", "456"]

    def test_normalize_list(self) -> None:
        result = normalize_allowlist(["123", "456"])
        assert result == ["123", "456"]

    def test_normalize_list_with_star(self) -> None:
        assert normalize_allowlist(["*", "123"]) is None


# ── Bindings ───────────────────────────────────────────────────────────


class TestSessionKeyDerivation:
    def test_deterministic(self) -> None:
        k1 = derive_session_key("telegram", "12345")
        k2 = derive_session_key("telegram", "12345")
        assert k1 == k2

    def test_different_conversations(self) -> None:
        k1 = derive_session_key("telegram", "11111")
        k2 = derive_session_key("telegram", "22222")
        assert k1 != k2

    def test_different_channels(self) -> None:
        k1 = derive_session_key("telegram", "12345")
        k2 = derive_session_key("discord", "12345")
        assert k1 != k2

    def test_format(self) -> None:
        key = derive_session_key("telegram", "12345")
        assert key.startswith("telegram:")
        assert len(key) == len("telegram:") + 8

    def test_webhook_path(self) -> None:
        assert derive_webhook_path("telegram") == "/v1/channels/telegram/inbound"
        assert derive_webhook_path("discord") == "/v1/channels/discord/inbound"


class TestBindingRegistry:
    def _msg(self, conv_id: str = "chat1", sender: str = "user1") -> InboundMessage:
        return InboundMessage(
            channel_id="telegram",
            conversation_id=conv_id,
            sender_id=sender,
            text="hello",
        )

    def test_creates_session(self) -> None:
        reg = BindingRegistry()
        session = reg.get_or_create(self._msg())
        assert session.channel_id == "telegram"
        assert session.conversation_id == "chat1"

    def test_idempotent(self) -> None:
        reg = BindingRegistry()
        s1 = reg.get_or_create(self._msg())
        s2 = reg.get_or_create(self._msg())
        assert s1.session_key == s2.session_key

    def test_different_conversations(self) -> None:
        reg = BindingRegistry()
        s1 = reg.get_or_create(self._msg("conv1"))
        s2 = reg.get_or_create(self._msg("conv2"))
        assert s1.session_key != s2.session_key

    def test_session_count(self) -> None:
        reg = BindingRegistry()
        reg.get_or_create(self._msg("c1"))
        reg.get_or_create(self._msg("c2"))
        assert reg.session_count() == 2

    def test_remove(self) -> None:
        reg = BindingRegistry()
        s = reg.get_or_create(self._msg())
        reg.remove(s.session_key)
        assert reg.session_count() == 0

    def test_get_by_conversation(self) -> None:
        reg = BindingRegistry()
        reg.get_or_create(self._msg("myconv"))
        s = reg.get_by_conversation("telegram", "myconv")
        assert s is not None
        assert s.conversation_id == "myconv"

    def test_clear(self) -> None:
        reg = BindingRegistry()
        reg.get_or_create(self._msg("c1"))
        reg.get_or_create(self._msg("c2"))
        reg.clear()
        assert reg.session_count() == 0

    def test_thread_safe_parallel_creates(self) -> None:
        reg = BindingRegistry()
        sessions: list = []
        lock = threading.Lock()

        def _create() -> None:
            s = reg.get_or_create(self._msg("shared_conv"))
            with lock:
                sessions.append(s.session_key)

        threads = [threading.Thread(target=_create) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All threads should have gotten the same key (idempotent).
        assert len(set(sessions)) == 1


# ── Reply formatting ───────────────────────────────────────────────────


class TestFormatReply:
    def test_short_message_unchanged(self) -> None:
        assert format_reply("hello", channel_id="telegram") == "hello"

    def test_prefix_prepended(self) -> None:
        result = format_reply("world", prefix="🤖 ")
        assert result.startswith("🤖 world")

    def test_truncates_at_limit(self) -> None:
        long = "x" * 5000
        result = format_reply(long, channel_id="telegram")
        assert len(result) <= 4096

    def test_truncate_marker(self) -> None:
        long = "x" * 5000
        result = format_reply(long, channel_id="telegram")
        assert result.endswith("…")


class TestSplitReply:
    def test_short_single_chunk(self) -> None:
        chunks = split_reply("hello world", channel_id="telegram")
        assert chunks == ["hello world"]

    def test_splits_long_text(self) -> None:
        text = ("word " * 1000).strip()
        chunks = split_reply(text, channel_id="telegram")
        assert len(chunks) > 1
        for c in chunks:
            assert len(c) <= 4096

    def test_prefix_on_first_chunk_only(self) -> None:
        text = ("word " * 1000).strip()
        chunks = split_reply(text, channel_id="telegram", prefix="🤖 ")
        assert chunks[0].startswith("🤖 ")
        for c in chunks[1:]:
            assert not c.startswith("🤖 ")

    def test_all_content_preserved(self) -> None:
        text = " ".join(f"w{i}" for i in range(500))
        chunks = split_reply(text, channel_id="telegram")
        joined = " ".join(chunks)
        # All words are present (order preserved, whitespace may vary).
        for i in range(500):
            assert f"w{i}" in joined


class TestSenderLabel:
    def test_owner_label(self) -> None:
        label = sender_label("123", "Alice", is_owner=True)
        assert "Owner" in label

    def test_display_name_used(self) -> None:
        label = sender_label("123", "Bob")
        assert "Bob" in label

    def test_fallback_to_id(self) -> None:
        label = sender_label("123")
        assert "123" in label


class TestStripMarkdown:
    def test_strips_bold(self) -> None:
        assert strip_markdown("**bold**") == "bold"

    def test_strips_link(self) -> None:
        assert strip_markdown("[text](https://example.com)") == "text"

    def test_strips_heading(self) -> None:
        result = strip_markdown("# Title\nbody")
        assert "Title" in result
        assert "#" not in result

    def test_preserves_code_content(self) -> None:
        result = strip_markdown("```python\nprint('hi')\n```")
        assert "print" in result


# ── Presence emitter ───────────────────────────────────────────────────


class TestPresenceEmitter:
    def test_calls_send_fn(self) -> None:
        calls: list[str] = []
        emitter = PresenceEmitter(
            send_fn=lambda cid: calls.append(cid),
            conversation_id="chat1",
            interval_sec=0.05,
        )
        emitter.start()
        time.sleep(0.15)
        emitter.stop()
        assert len(calls) >= 1
        assert all(c == "chat1" for c in calls)

    def test_context_manager(self) -> None:
        calls: list[str] = []
        with PresenceEmitter(
            send_fn=lambda cid: calls.append(cid),
            conversation_id="chat1",
            interval_sec=0.05,
        ):
            time.sleep(0.12)
        assert len(calls) >= 1

    def test_stops_cleanly(self) -> None:
        calls: list[str] = []
        emitter = PresenceEmitter(
            send_fn=lambda cid: calls.append(cid),
            conversation_id="chat1",
            interval_sec=0.05,
        )
        emitter.start()
        emitter.stop()
        count_after_stop = len(calls)
        time.sleep(0.1)
        # No new calls after stop.
        assert len(calls) == count_after_stop


class TestReactionEmitter:
    def test_react_calls_send_fn(self) -> None:
        calls: list[tuple[str, str]] = []
        emitter = ReactionEmitter(send_fn=lambda mid, emoji: calls.append((mid, emoji)))
        emitter.react("msg1", "👍")
        assert calls == [("msg1", "👍")]

    def test_ack_sends_thumbsup(self) -> None:
        calls: list[tuple[str, str]] = []
        emitter = ReactionEmitter(send_fn=lambda mid, emoji: calls.append((mid, emoji)))
        emitter.ack("msg2")
        assert calls[0][1] == "👍"

    def test_error_ignores_exceptions(self) -> None:
        def _raise(mid: str, emoji: str) -> None:
            raise RuntimeError("channel down")

        emitter = ReactionEmitter(send_fn=_raise)
        emitter.error("msg3")  # must not raise
