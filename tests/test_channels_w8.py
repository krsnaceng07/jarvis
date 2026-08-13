"""Wave 8 tests — HookName enum, LifecycleHooks, Result type, TerminalOutcome."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from jarvis_hooks import (
    HookBus,
    HookName,
    BEFORE_AGENT_START,
    AGENT_END,
    MESSAGE_RECEIVED,
    MESSAGE_SENT,
    TOOL_CALLED,
    TOOL_COMPLETED,
    SESSION_START,
    SESSION_END,
)
from src.hooks.lifecycle import LifecycleHooks
from jarvis_normalization_core.result import Ok, Err, Result
from jarvis_agent.terminal_outcome import OutcomeKind, normalize_outcome


# ── Minimal HookRegistration stand-in (mirrors W3 test pattern) ─────────────


@dataclass
class _MockReg:
    """Minimal stand-in for HookRegistration; duck-typed by HookBus."""
    name: str
    handler: Any
    priority: int = 0
    timeout_ms: int | None = None


# ── HookName enum ────────────────────────────────────────────────────────────


class TestHookName:
    def test_all_values_defined(self) -> None:
        names = {h.value for h in HookName}
        expected = {
            "before_agent_start", "agent_end",
            "message_received", "message_sent",
            "tool_called", "tool_completed",
            "session_start", "session_end",
        }
        assert names == expected

    def test_is_str_subclass(self) -> None:
        assert isinstance(HookName.TOOL_CALLED, str)

    def test_compares_equal_to_string(self) -> None:
        # Critical: str equality so legacy bus.fire("tool_called", ...) works.
        assert HookName.TOOL_CALLED == "tool_called"
        assert HookName.SESSION_START == "session_start"

    def test_legacy_constants_equal_enum_values(self) -> None:
        assert BEFORE_AGENT_START == HookName.BEFORE_AGENT_START.value
        assert AGENT_END == HookName.AGENT_END.value
        assert MESSAGE_RECEIVED == HookName.MESSAGE_RECEIVED.value
        assert MESSAGE_SENT == HookName.MESSAGE_SENT.value
        assert TOOL_CALLED == HookName.TOOL_CALLED.value
        assert TOOL_COMPLETED == HookName.TOOL_COMPLETED.value
        assert SESSION_START == HookName.SESSION_START.value
        assert SESSION_END == HookName.SESSION_END.value

    def test_from_value(self) -> None:
        h = HookName("tool_called")
        assert h is HookName.TOOL_CALLED

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            HookName("not_a_hook")

    def test_enum_in_set_lookup(self) -> None:
        known = {"tool_called", "session_start"}
        assert HookName.TOOL_CALLED in known

    def test_string_in_enum_set(self) -> None:
        values = {h.value for h in HookName}
        assert "session_end" in values


# ── LifecycleHooks uses HookName ─────────────────────────────────────────────


class TestLifecycleHooksWithHookName:
    def _make_bus_and_hooks(self) -> tuple[HookBus, LifecycleHooks, list]:
        bus = HookBus()
        fired: list[tuple[str, Any]] = []

        for hook in HookName:
            name = hook.value
            bus.register(_MockReg(name=name, handler=lambda p, n=name: fired.append((n, p))))

        return bus, LifecycleHooks(bus), fired

    def test_session_start_fires_correct_hook(self) -> None:
        bus, lc, fired = self._make_bus_and_hooks()
        lc.on_session_start({"id": "s1"})
        names = [f[0] for f in fired]
        assert "session_start" in names

    def test_session_end_fires(self) -> None:
        bus, lc, fired = self._make_bus_and_hooks()
        lc.on_session_end({"id": "s1"})
        assert any("session_end" in f[0] for f in fired)

    def test_message_received_fires(self) -> None:
        bus, lc, fired = self._make_bus_and_hooks()
        lc.on_message_received("hello")
        assert any("message_received" in f[0] for f in fired)

    def test_message_sent_fires(self) -> None:
        bus, lc, fired = self._make_bus_and_hooks()
        lc.on_message_sent("reply")
        assert any("message_sent" in f[0] for f in fired)

    def test_before_agent_start_fires(self) -> None:
        bus, lc, fired = self._make_bus_and_hooks()
        lc.on_before_agent_start()
        assert any("before_agent_start" in f[0] for f in fired)

    def test_agent_end_fires(self) -> None:
        bus, lc, fired = self._make_bus_and_hooks()
        lc.on_agent_end("done")
        assert any("agent_end" in f[0] for f in fired)

    def test_none_bus_is_noop(self) -> None:
        lc = LifecycleHooks(None)
        # Must not raise
        lc.on_session_start()
        lc.on_agent_end()

    def test_payload_passed_through(self) -> None:
        bus = HookBus()
        payloads: list = []
        bus.register(_MockReg(
            name=HookName.MESSAGE_RECEIVED.value,
            handler=lambda p: payloads.append(p),
        ))
        LifecycleHooks(bus).on_message_received({"text": "hi"})
        assert payloads == [{"text": "hi"}]


# ── Result type ──────────────────────────────────────────────────────────────


class TestResult:
    def test_ok_is_ok(self) -> None:
        r = Ok(42)
        assert r.is_ok
        assert not r.is_err

    def test_err_is_err(self) -> None:
        r = Err("oops")
        assert r.is_err
        assert not r.is_ok

    def test_ok_value(self) -> None:
        assert Ok("hello").value == "hello"

    def test_err_message(self) -> None:
        assert Err("fail", code="E1").error == "fail"
        assert Err("fail", code="E1").code == "E1"

    def test_ok_match(self) -> None:
        result = Ok(10).match(ok=lambda v: v * 2, err=lambda e, c: 0)
        assert result == 20

    def test_err_match(self) -> None:
        result = Err("bad", "E_BAD").match(ok=lambda v: v, err=lambda e, c: f"{c}:{e}")
        assert result == "E_BAD:bad"

    def test_default_err_code(self) -> None:
        assert Err("x").code == "ERR"

    def test_result_type_alias(self) -> None:
        def f(x: int) -> Result:
            return Ok(x) if x > 0 else Err("negative")
        assert f(1).is_ok
        assert f(-1).is_err

    def test_ok_frozen(self) -> None:
        with pytest.raises((AttributeError, TypeError)):
            Ok(1).value = 99  # type: ignore[misc]


# ── TerminalOutcome ───────────────────────────────────────────────────────────


class TestTerminalOutcome:
    def test_success_outcome(self) -> None:
        o = normalize_outcome()
        assert o.kind == OutcomeKind.SUCCESS

    def test_error_outcome(self) -> None:
        exc = RuntimeError("boom")
        o = normalize_outcome(exc=exc)
        assert o.kind == OutcomeKind.ERROR
        assert o.error is exc

    def test_timeout_takes_precedence_over_error(self) -> None:
        o = normalize_outcome(exc=RuntimeError("e"), timed_out=True)
        assert o.kind == OutcomeKind.TIMEOUT

    def test_cancel_over_error(self) -> None:
        o = normalize_outcome(exc=RuntimeError("e"), was_cancelled=True)
        assert o.kind == OutcomeKind.CANCELLED

    def test_timeout_over_cancel(self) -> None:
        o = normalize_outcome(timed_out=True, was_cancelled=True)
        assert o.kind == OutcomeKind.TIMEOUT

    def test_duration_preserved(self) -> None:
        o = normalize_outcome(duration_ms=1234)
        assert o.duration_ms == 1234

    def test_outcome_kind_is_str(self) -> None:
        assert isinstance(OutcomeKind.SUCCESS, str)

    def test_frozen(self) -> None:
        o = normalize_outcome()
        with pytest.raises((AttributeError, TypeError)):
            o.kind = OutcomeKind.ERROR  # type: ignore[misc]
