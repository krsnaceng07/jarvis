"""Wave 11 tests — LifecycleHooks wired into ChannelSessionRunner."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.sessions.channel_session_runner import ChannelSessionRunner
from src.tools.dispatch import ToolDispatcher
from src.hooks import HookBus
from src.hooks.lifecycle import LifecycleHooks


# ── test doubles ─────────────────────────────────────────────────────────────


@dataclass
class _MockReg:
    name: str
    handler: Any
    priority: int = 0
    timeout_ms: int | None = None


def _noop_llm(messages, tools, system):
    """LLM stub: returns a text reply with no tool calls."""
    return "hello back", []


def _make_runner(fired: list) -> ChannelSessionRunner:
    """Build a ChannelSessionRunner with a spy hook bus."""
    bus = HookBus()
    for hook_name in ("message_received", "message_sent", "agent_end"):
        n = hook_name
        bus.register(_MockReg(
            name=n,
            handler=lambda p, n=n: fired.append((n, p)),
        ))
    lifecycle = LifecycleHooks(bus)
    dispatcher = ToolDispatcher(plugin_dispatch={})
    return ChannelSessionRunner(
        dispatcher=dispatcher,
        llm_fn=_noop_llm,
        lifecycle=lifecycle,
    )


# ── tests ─────────────────────────────────────────────────────────────────────


class TestChannelSessionRunnerLifecycle:
    def test_message_received_fired_on_run(self) -> None:
        fired: list = []
        runner = _make_runner(fired)
        runner.run("sess-1", "hi")
        names = [f[0] for f in fired]
        assert "message_received" in names

    def test_message_sent_fired_on_successful_reply(self) -> None:
        fired: list = []
        runner = _make_runner(fired)
        runner.run("sess-1", "hi")
        names = [f[0] for f in fired]
        assert "message_sent" in names

    def test_agent_end_always_fired(self) -> None:
        fired: list = []
        runner = _make_runner(fired)
        runner.run("sess-1", "hi")
        names = [f[0] for f in fired]
        assert "agent_end" in names

    def test_message_received_payload_contains_text(self) -> None:
        fired: list = []
        runner = _make_runner(fired)
        runner.run("sess-42", "test input")
        payloads = [p for n, p in fired if n == "message_received"]
        assert any(isinstance(p, dict) and p.get("text") == "test input" for p in payloads)

    def test_message_sent_payload_contains_reply(self) -> None:
        fired: list = []
        runner = _make_runner(fired)
        runner.run("sess-1", "anything")
        payloads = [p for n, p in fired if n == "message_sent"]
        # reply should be "hello back" from _noop_llm
        assert any(
            isinstance(p, dict) and "hello back" in str(p.get("reply", ""))
            for p in payloads
        )

    def test_session_key_in_received_payload(self) -> None:
        fired: list = []
        runner = _make_runner(fired)
        runner.run("my-session", "ping")
        payloads = [p for n, p in fired if n == "message_received"]
        assert any(isinstance(p, dict) and p.get("session_key") == "my-session" for p in payloads)

    def test_no_lifecycle_no_error(self) -> None:
        """Runner works correctly when lifecycle=None (default)."""
        dispatcher = ToolDispatcher(plugin_dispatch={})
        runner = ChannelSessionRunner(dispatcher=dispatcher, llm_fn=_noop_llm)
        reply = runner.run("sess", "hello")
        assert reply == "hello back"

    def test_error_llm_still_fires_agent_end(self) -> None:
        """Even on LLM error, agent_end hook is fired."""
        fired: list = []
        bus = HookBus()
        bus.register(_MockReg(
            name="agent_end",
            handler=lambda p: fired.append(("agent_end", p)),
        ))
        lifecycle = LifecycleHooks(bus)
        dispatcher = ToolDispatcher(plugin_dispatch={})

        def _failing_llm(messages, tools, system):
            raise RuntimeError("LLM unavailable")

        runner = ChannelSessionRunner(
            dispatcher=dispatcher,
            llm_fn=_failing_llm,
            lifecycle=lifecycle,
        )
        runner.run("err-session", "oops")
        assert any(n == "agent_end" for n, _ in fired)

    def test_hook_exception_does_not_break_runner(self) -> None:
        """A crashing hook handler must not propagate to the caller."""
        bus = HookBus()
        bus.register(_MockReg(
            name="message_received",
            handler=lambda p: 1 / 0,  # always raises
        ))
        lifecycle = LifecycleHooks(bus)
        dispatcher = ToolDispatcher(plugin_dispatch={})
        runner = ChannelSessionRunner(
            dispatcher=dispatcher,
            llm_fn=_noop_llm,
            lifecycle=lifecycle,
        )
        # Should not raise; HookBus swallows handler exceptions
        reply = runner.run("sess", "hello")
        assert reply is not None
