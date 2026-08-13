"""Wave 5 tests — ConversationHistoryStore + ChannelSessionRunner with SQLite history."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.sessions.history_store import ConversationHistoryStore
from src.sessions.channel_session_runner import ChannelSessionRunner
from src.tools.dispatch import ToolDispatcher


# ── ConversationHistoryStore ────────────────────────────────────────────────


class TestConversationHistoryStore:
    @pytest.fixture
    def store(self, tmp_path: Path) -> ConversationHistoryStore:
        return ConversationHistoryStore(tmp_path / "test.sqlite", max_turns=50)

    def test_ready_on_good_path(self, store: ConversationHistoryStore) -> None:
        assert store._ready is True

    def test_append_user_and_retrieve(self, store: ConversationHistoryStore) -> None:
        store.append_user("sk1", "hello")
        turns = store.get_turns("sk1")
        assert len(turns) == 1
        assert turns[0]["role"] == "user"
        assert turns[0]["content"] == "hello"

    def test_append_assistant(self, store: ConversationHistoryStore) -> None:
        store.append_assistant("sk1", "hi back")
        turns = store.get_turns("sk1")
        assert turns[0]["role"] == "assistant"

    def test_append_tool_result(self, store: ConversationHistoryStore) -> None:
        store.append_tool_result("sk1", "ping", "c1", "pong")
        turns = store.get_turns("sk1")
        assert turns[0]["role"] == "tool"
        assert turns[0]["tool_name"] == "ping"
        assert turns[0]["call_id"] == "c1"
        assert turns[0]["content"] == "pong"

    def test_order_preserved(self, store: ConversationHistoryStore) -> None:
        store.append_user("sk1", "msg1")
        store.append_assistant("sk1", "reply1")
        store.append_user("sk1", "msg2")
        turns = store.get_turns("sk1")
        assert [t["content"] for t in turns] == ["msg1", "reply1", "msg2"]

    def test_sessions_are_isolated(self, store: ConversationHistoryStore) -> None:
        store.append_user("skA", "a")
        store.append_user("skB", "b")
        assert [t["content"] for t in store.get_turns("skA")] == ["a"]
        assert [t["content"] for t in store.get_turns("skB")] == ["b"]

    def test_turn_count(self, store: ConversationHistoryStore) -> None:
        store.append_user("sk1", "a")
        store.append_user("sk1", "b")
        assert store.turn_count("sk1") == 2

    def test_clear_session(self, store: ConversationHistoryStore) -> None:
        store.append_user("sk1", "a")
        store.clear_session("sk1")
        assert store.get_turns("sk1") == []
        assert store.turn_count("sk1") == 0

    def test_clear_all(self, store: ConversationHistoryStore) -> None:
        store.append_user("skA", "a")
        store.append_user("skB", "b")
        store.clear_all()
        assert store.get_turns("skA") == []
        assert store.get_turns("skB") == []

    def test_persists_across_instances(self, tmp_path: Path) -> None:
        db = tmp_path / "shared.sqlite"
        s1 = ConversationHistoryStore(db)
        s1.append_user("sk1", "persistent")

        s2 = ConversationHistoryStore(db)
        turns = s2.get_turns("sk1")
        assert len(turns) == 1
        assert turns[0]["content"] == "persistent"

    def test_max_turns_trimming(self, tmp_path: Path) -> None:
        store = ConversationHistoryStore(tmp_path / "trim.sqlite", max_turns=5)
        for i in range(8):
            store.append_user("sk1", f"msg{i}")
        assert store.turn_count("sk1") <= 5

    def test_fallback_on_bad_path(self, tmp_path: Path) -> None:
        """A corrupt file triggers fallback to in-memory mode."""
        bad = tmp_path / "corrupt.sqlite"
        bad.write_text("not a database")
        # Might succeed (SQLite is lenient) or fail to init — either way
        # must not raise and must return a store that works.
        store = ConversationHistoryStore(bad)
        store.append_user("sk1", "hi")
        turns = store.get_turns("sk1")
        assert any(t["content"] == "hi" for t in turns)

    def test_empty_session_returns_empty(self, store: ConversationHistoryStore) -> None:
        assert store.get_turns("nonexistent") == []
        assert store.turn_count("nonexistent") == 0


# ── ChannelSessionRunner with history_store ─────────────────────────────────


def _make_runner_with_store(
    tmp_path: Path,
    llm_replies: list[tuple[str | None, list]] | None = None,
    tools: dict | None = None,
) -> tuple[ChannelSessionRunner, ConversationHistoryStore]:
    reply_iter = iter(llm_replies or [("hello", [])])

    def _llm(messages: list, schemas: list, system: str) -> tuple:
        return next(reply_iter, (None, []))

    store = ConversationHistoryStore(tmp_path / "history.sqlite")
    dispatcher = ToolDispatcher(tools or {"ping": lambda n, a: "pong"})
    runner = ChannelSessionRunner(
        dispatcher,
        _llm,
        system_prompt="test",
        tool_schemas=[],
        history_store=store,
    )
    return runner, store


class TestRunnerWithHistoryStore:
    def test_simple_turn_persisted(self, tmp_path: Path) -> None:
        runner, store = _make_runner_with_store(tmp_path, [("hi", [])])
        runner.run("sk1", "hello")
        turns = store.get_turns("sk1")
        # user + assistant turns stored
        assert any(t["role"] == "user" for t in turns)
        assert any(t["role"] == "assistant" for t in turns)

    def test_history_persists_across_runner_instances(self, tmp_path: Path) -> None:
        db = tmp_path / "h.sqlite"
        reply_iter1 = iter([("reply1", [])])
        store1 = ConversationHistoryStore(db)

        def _llm1(messages: list, s: list, sys: str) -> tuple:
            return next(reply_iter1, (None, []))

        r1 = ChannelSessionRunner(
            ToolDispatcher({}), _llm1, history_store=store1
        )
        r1.run("sk1", "first")

        # New runner on same DB — picks up history from store2.
        store2 = ConversationHistoryStore(db)
        history = store2.get_turns("sk1")
        assert len(history) >= 2  # user + assistant

    def test_clear_history_clears_store(self, tmp_path: Path) -> None:
        runner, store = _make_runner_with_store(tmp_path, [("hi", [])])
        runner.run("sk1", "hello")
        assert store.turn_count("sk1") > 0
        runner.clear_history("sk1")
        assert store.turn_count("sk1") == 0

    def test_tool_results_persisted(self, tmp_path: Path) -> None:
        runner, store = _make_runner_with_store(
            tmp_path,
            [
                (None, [{"name": "ping", "args": {}, "id": "x"}]),
                ("done", []),
            ],
        )
        runner.run("sk1", "go")
        turns = store.get_turns("sk1")
        tool_turns = [t for t in turns if t["role"] == "tool"]
        assert len(tool_turns) == 1
        assert tool_turns[0]["tool_name"] == "ping"

    def test_different_sessions_isolated_in_store(self, tmp_path: Path) -> None:
        reply_iter = iter([("a", []), ("b", [])])
        store = ConversationHistoryStore(tmp_path / "h.sqlite")

        def _llm(messages: list, s: list, sys: str) -> tuple:
            return next(reply_iter, (None, []))

        runner = ChannelSessionRunner(
            ToolDispatcher({}), _llm, history_store=store
        )
        runner.run("skA", "hello")
        runner.run("skB", "world")

        a_turns = [t for t in store.get_turns("skA") if t["role"] == "user"]
        b_turns = [t for t in store.get_turns("skB") if t["role"] == "user"]
        assert a_turns[0]["content"] == "hello"
        assert b_turns[0]["content"] == "world"

    def test_in_memory_mode_still_works(self) -> None:
        """history_store=None falls back to in-memory (W2 compat)."""
        reply_iter = iter([("ok", [])])

        def _llm(messages: list, s: list, sys: str) -> tuple:
            return next(reply_iter, (None, []))

        runner = ChannelSessionRunner(
            ToolDispatcher({}), _llm  # no history_store
        )
        result = runner.run("sk1", "hi")
        assert result == "ok"
        assert runner.session_count() == 1
