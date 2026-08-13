"""Wave 2 tests — terminal_outcome, ToolDispatcher, ChannelSessionRunner.

Tests the three new W2 components:
  1. terminal_outcome.py  — outcome normalization (precedence + factories)
  2. src/tools/dispatch.py — ToolDispatcher routing and error capture
  3. src/sessions/channel_session_runner.py — full turn loop with tools
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from jarvis_agent.terminal_outcome import (
    cancelled,
    error,
    normalize_outcome,
    success,
    timeout,
)
from jarvis_channels import InboundMessage
from src.channels.session_store import PersistedChannelRegistry
from src.sessions.channel_session_runner import ChannelSessionRunner
from src.tools.dispatch import ToolDispatcher

# ── terminal_outcome ────────────────────────────────────────────────────


class TestTerminalOutcome:
    def test_success_factory(self) -> None:
        o = success(duration_ms=42, session_key="k1")
        assert o.is_success
        assert not o.is_error
        assert not o.is_timeout
        assert not o.is_cancelled
        assert o.duration_ms == 42
        assert o.session_key == "k1"

    def test_error_factory(self) -> None:
        exc = ValueError("boom")
        o = error(exc, message="custom msg", duration_ms=10)
        assert o.is_error
        assert o.error is exc
        assert o.error_message == "custom msg"

    def test_error_factory_fallback_message(self) -> None:
        exc = ValueError("boom")
        o = error(exc)
        assert o.error_message == "boom"

    def test_timeout_factory(self) -> None:
        o = timeout(duration_ms=60000)
        assert o.is_timeout
        assert o.error_message == "Agent run timed out"

    def test_cancelled_factory(self) -> None:
        o = cancelled()
        assert o.is_cancelled
        assert o.error_message == "Agent run was cancelled"

    def test_display_message_from_error_message(self) -> None:
        o = error(ValueError("x"), message="explicit")
        assert o.display_message == "explicit"

    def test_display_message_from_error(self) -> None:
        o = error(ValueError("inner"))
        # When message is derived from exc, str(exc) is used.
        assert o.error_message == "inner"
        assert "inner" in o.display_message

    def test_display_message_for_success(self) -> None:
        o = success()
        assert o.display_message == "success"

    # normalize_outcome precedence: timeout > cancel > error > success

    def test_normalize_timeout_wins_over_cancel(self) -> None:
        o = normalize_outcome(timed_out=True, was_cancelled=True)
        assert o.is_timeout

    def test_normalize_cancel_wins_over_error(self) -> None:
        o = normalize_outcome(exc=ValueError(), was_cancelled=True)
        assert o.is_cancelled

    def test_normalize_error_wins_over_success(self) -> None:
        o = normalize_outcome(exc=RuntimeError("x"))
        assert o.is_error

    def test_normalize_no_flags_is_success(self) -> None:
        o = normalize_outcome()
        assert o.is_success

    def test_normalize_carries_duration_and_key(self) -> None:
        o = normalize_outcome(duration_ms=99, session_key="sk")
        assert o.duration_ms == 99
        assert o.session_key == "sk"

    def test_str(self) -> None:
        o = success()
        assert "success" in str(o)


# ── ToolDispatcher ──────────────────────────────────────────────────────


def _make_dispatcher(extra: dict | None = None) -> ToolDispatcher:
    fns = {
        "echo": lambda name, args: args.get("text", ""),
        "add": lambda name, args: args.get("a", 0) + args.get("b", 0),
        "fail": lambda name, args: 1 / 0,
        "none_return": lambda name, args: None,
        "dict_return": lambda name, args: {"x": 1},
    }
    if extra:
        fns.update(extra)
    return ToolDispatcher(fns)


class TestToolDispatcher:
    def test_has_registered_tool(self) -> None:
        d = _make_dispatcher()
        assert d.has("echo")
        assert not d.has("unknown")

    def test_registered_names(self) -> None:
        d = _make_dispatcher()
        assert "echo" in d.registered_names()

    def test_execute_returns_string_result(self) -> None:
        d = _make_dispatcher()
        res = d.execute("echo", {"text": "hello"}, call_id="c1")
        assert res.tool_name == "echo"
        assert res.call_id == "c1"
        assert res.content == "hello"
        assert not res.is_error

    def test_execute_numeric_result_stringified(self) -> None:
        d = _make_dispatcher()
        res = d.execute("add", {"a": 3, "b": 4})
        assert res.content == "7"
        assert not res.is_error

    def test_execute_none_returns_ok(self) -> None:
        d = _make_dispatcher()
        res = d.execute("none_return", {})
        assert res.content == "ok"

    def test_execute_dict_result_json_stringified(self) -> None:
        d = _make_dispatcher()
        res = d.execute("dict_return", {})
        assert '"x"' in res.content
        assert not res.is_error

    def test_execute_exception_captured_as_error(self) -> None:
        d = _make_dispatcher()
        res = d.execute("fail", {})
        assert res.is_error
        assert "ZeroDivisionError" in res.content

    def test_execute_unknown_tool_returns_error(self) -> None:
        d = _make_dispatcher()
        res = d.execute("no_such", {})
        assert res.is_error
        assert "unknown tool" in res.content

    def test_execute_duration_ms_set(self) -> None:
        d = _make_dispatcher()
        res = d.execute("echo", {"text": "x"})
        assert res.duration_ms >= 0

    def test_execute_batch(self) -> None:
        d = _make_dispatcher()
        results = d.execute_batch([
            {"name": "echo", "args": {"text": "a"}, "id": "1"},
            {"name": "echo", "args": {"text": "b"}, "id": "2"},
        ])
        assert len(results) == 2
        assert results[0].content == "a"
        assert results[1].content == "b"

    def test_execute_batch_preserves_order(self) -> None:
        d = _make_dispatcher()
        results = d.execute_batch([
            {"name": "echo", "args": {"text": str(i)}} for i in range(10)
        ])
        assert [r.content for r in results] == [str(i) for i in range(10)]

    def test_empty_dispatch_table(self) -> None:
        d = ToolDispatcher({})
        res = d.execute("echo", {})
        assert res.is_error


# ── ChannelSessionRunner ────────────────────────────────────────────────


def _make_runner(
    llm_replies: list[tuple[str | None, list]] | None = None,
    *,
    tools: dict | None = None,
    max_rounds: int = 5,
    timeout_sec: float = 5.0,
) -> tuple[ChannelSessionRunner, list]:
    """Build a runner with a canned LLM function."""
    calls: list[tuple] = []
    reply_iter = iter(llm_replies or [("hello", [])])

    def _llm(messages, tool_schemas, system):
        reply = next(reply_iter, (None, []))
        calls.append(("llm", len(messages)))
        return reply

    dispatcher = ToolDispatcher(tools or {
        "ping": lambda n, a: "pong",
    })
    runner = ChannelSessionRunner(
        dispatcher,
        _llm,
        system_prompt="test",
        tool_schemas=[],
        max_tool_rounds=max_rounds,
        timeout_sec=timeout_sec,
    )
    return runner, calls


class TestChannelSessionRunner:
    def test_simple_reply(self) -> None:
        runner, _ = _make_runner([("hello back", [])])
        result = runner.run("sk1", "hi")
        assert result == "hello back"

    def test_none_reply_when_no_text(self) -> None:
        runner, _ = _make_runner([(None, [])])
        result = runner.run("sk1", "hi")
        assert result is None

    def test_tool_call_round_trip(self) -> None:
        runner, calls = _make_runner([
            (None, [{"name": "ping", "args": {}, "id": "1"}]),  # first: tool call
            ("after tool", []),                                  # second: final reply
        ])
        result = runner.run("sk1", "ping?")
        assert result == "after tool"
        assert len(calls) == 2  # two LLM calls

    def test_session_history_grows(self) -> None:
        runner, calls = _make_runner([("r1", []), ("r2", [])])
        runner.run("sk1", "msg1")
        runner.run("sk1", "msg2")
        # Second turn history includes msg1 + r1.
        assert calls[1][1] > calls[0][1]

    def test_different_sessions_are_isolated(self) -> None:
        runner, _ = _make_runner([("a", []), ("b", [])])
        r1 = runner.run("skA", "hello")
        r2 = runner.run("skB", "hello")
        assert r1 == "a"
        assert r2 == "b"

    def test_max_tool_rounds_exceeded_returns_none(self) -> None:
        # Always returns a tool call — never a text reply.
        def _infinite_llm(messages, schemas, system):
            return (None, [{"name": "ping", "args": {}, "id": "x"}])

        dispatcher = ToolDispatcher({"ping": lambda n, a: "pong"})
        runner = ChannelSessionRunner(
            dispatcher,
            _infinite_llm,
            max_tool_rounds=3,
            timeout_sec=5.0,
        )
        result = runner.run("sk1", "loop forever")
        assert result is None

    def test_llm_error_returns_none(self) -> None:
        def _bad_llm(messages, schemas, system):
            raise RuntimeError("LLM down")

        dispatcher = ToolDispatcher({})
        runner = ChannelSessionRunner(dispatcher, _bad_llm, timeout_sec=5.0)
        result = runner.run("sk1", "hello")
        assert result is None

    def test_clear_history(self) -> None:
        runner, _ = _make_runner([("hi", []), ("hi2", [])])
        runner.run("sk1", "msg")
        assert runner.session_count() == 1
        runner.clear_history("sk1")
        assert runner.session_count() == 0

    def test_timeout_returns_none(self) -> None:
        """Timeout fires between tool rounds — use a tool-call loop to trigger it."""
        call_count = 0

        def _always_tool(messages, schemas, system):
            nonlocal call_count
            call_count += 1
            # Tiny sleep to let the deadline pass across rounds.
            time.sleep(0.05)
            return (None, [{"name": "ping", "args": {}, "id": "x"}])

        dispatcher = ToolDispatcher({"ping": lambda n, a: "pong"})
        # Very short deadline: 0.08 s. With 0.05 s sleep per round,
        # the second round will exceed the deadline.
        runner = ChannelSessionRunner(
            dispatcher, _always_tool, timeout_sec=0.08, max_tool_rounds=20
        )
        result = runner.run("sk1", "go")
        assert result is None
        # At most 2 LLM calls before timeout kills the loop.
        assert call_count <= 3

    def test_partial_reply_before_tool_call(self) -> None:
        """Text + tool_call in same turn: text is included in final reply."""
        runner, _ = _make_runner([
            ("partial ", [{"name": "ping", "args": {}, "id": "x"}]),
            ("done", []),
        ])
        result = runner.run("sk1", "go")
        assert result is not None
        assert "partial" in result
        assert "done" in result


# ── PersistedChannelRegistry ────────────────────────────────────────────


def _msg(conv: str = "c1", channel: str = "tg") -> InboundMessage:
    return InboundMessage(
        channel_id=channel,
        conversation_id=conv,
        sender_id="42",
        text="hi",
    )


class TestPersistedChannelRegistry:
    @pytest.fixture
    def reg(self, tmp_path: Path) -> PersistedChannelRegistry:
        return PersistedChannelRegistry(tmp_path / "test.sqlite")

    def test_creates_table_on_init(self, reg: PersistedChannelRegistry) -> None:
        assert reg._ready is True

    def test_get_or_create_returns_session(self, reg) -> None:
        sess = reg.get_or_create(_msg("c1"))
        assert sess.channel_id == "tg"
        assert sess.conversation_id == "c1"

    def test_get_or_create_idempotent(self, reg) -> None:
        s1 = reg.get_or_create(_msg("c1"))
        s2 = reg.get_or_create(_msg("c1"))
        assert s1.session_key == s2.session_key

    def test_get_returns_existing(self, reg) -> None:
        sess = reg.get_or_create(_msg("c2"))
        found = reg.get(sess.session_key)
        assert found is not None
        assert found.session_key == sess.session_key

    def test_get_returns_none_for_unknown(self, reg) -> None:
        assert reg.get("no-such-key") is None

    def test_remove_deletes_session(self, reg) -> None:
        sess = reg.get_or_create(_msg("c3"))
        reg.remove(sess.session_key)
        assert reg.get(sess.session_key) is None

    def test_all_sessions(self, reg) -> None:
        reg.get_or_create(_msg("c1"))
        reg.get_or_create(_msg("c2"))
        sessions = reg.all_sessions()
        assert len(sessions) == 2

    def test_session_count(self, reg) -> None:
        reg.get_or_create(_msg("c1"))
        assert reg.session_count() == 1

    def test_clear(self, reg) -> None:
        reg.get_or_create(_msg("c1"))
        reg.clear()
        assert reg.session_count() == 0

    def test_sessions_persist_across_instances(self, tmp_path: Path) -> None:
        db = tmp_path / "shared.sqlite"
        reg1 = PersistedChannelRegistry(db)
        sess = reg1.get_or_create(_msg("c1"))

        reg2 = PersistedChannelRegistry(db)
        found = reg2.get(sess.session_key)
        assert found is not None
        assert found.session_key == sess.session_key

    def test_fallback_on_bad_db_path(self, tmp_path: Path) -> None:
        """A path pointing to a file (not DB) causes OperationalError → fallback."""
        # Create a regular file where the DB is expected; sqlite3 will fail on it.
        bad_path = tmp_path / "notadb.txt"
        bad_path.write_text("not a sqlite db")
        reg = PersistedChannelRegistry(bad_path)
        # May succeed on some SQLite versions that can open any file, but
        # at minimum the registry must not crash and must return a valid session.
        sess = reg.get_or_create(_msg("c1"))
        assert sess is not None
