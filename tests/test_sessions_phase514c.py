"""Tests for the Phase 5.14b session ports (batch 2).

Mirrors the test cases from OpenClaw's
``extensions/sessions/session-lifecycle-events`` and
``extensions/sessions/level-overrides`` test files.
"""
from __future__ import annotations

import pytest

from src.sessions.level_overrides import (
    ParsedTraceOverride,
    ParsedVerboseOverride,
    TraceLevel,
    VerboseLevel,
    apply_trace_override,
    apply_verbose_override,
    normalize_trace_level,
    normalize_verbose_level,
    parse_trace_override,
    parse_verbose_override,
)
from src.sessions.session_lifecycle_events import (
    SessionIdentityMutation,
    SessionIdentityMutationTarget,
    SessionLifecycleEvent,
    _reset_session_lifecycle_listeners_for_tests,
    emit_session_identity_mutation,
    emit_session_lifecycle_event,
    on_session_identity_mutation,
    on_session_lifecycle_event,
)


# ── Lifecycle events ───────────────────────────────────────────────


class TestSessionLifecycleEvents:
    def setup_method(self) -> None:
        _reset_session_lifecycle_listeners_for_tests()

    def test_register_and_emit(self) -> None:
        """A registered listener is called on emit."""
        received: list[SessionLifecycleEvent] = []
        on_session_lifecycle_event(received.append)
        emit_session_lifecycle_event(
            SessionLifecycleEvent(
                session_key="agent:1:main",
                reason="created",
            )
        )
        assert len(received) == 1
        assert received[0].session_key == "agent:1:main"
        assert received[0].reason == "created"

    def test_unregister(self) -> None:
        """The unregister callable removes the listener."""
        received: list[SessionLifecycleEvent] = []
        unregister = on_session_lifecycle_event(received.append)
        unregister()
        emit_session_lifecycle_event(
            SessionLifecycleEvent(session_key="x", reason="created")
        )
        assert received == []

    def test_multiple_listeners_called_in_order(self) -> None:
        """Listeners are called in registration order."""
        order: list[str] = []
        on_session_lifecycle_event(lambda _e: order.append("a"))
        on_session_lifecycle_event(lambda _e: order.append("b"))
        on_session_lifecycle_event(lambda _e: order.append("c"))
        emit_session_lifecycle_event(
            SessionLifecycleEvent(session_key="x", reason="created")
        )
        assert order == ["a", "b", "c"]

    def test_listener_exception_does_not_break_chain(self) -> None:
        """A throwing listener doesn't stop subsequent listeners."""
        order: list[str] = []
        on_session_lifecycle_event(lambda _e: (_ for _ in ()).throw(RuntimeError("boom")))
        on_session_lifecycle_event(lambda _e: order.append("ok"))
        emit_session_lifecycle_event(
            SessionLifecycleEvent(session_key="x", reason="created")
        )
        assert order == ["ok"]

    def test_lifecycle_event_fields(self) -> None:
        """Optional fields (parent_session_key, label, display_name) round-trip."""
        event = SessionLifecycleEvent(
            session_key="agent:1:child",
            reason="linked",
            parent_session_key="agent:1:parent",
            label="My Child",
            display_name="Child Display",
        )
        assert event.session_key == "agent:1:child"
        assert event.parent_session_key == "agent:1:parent"
        assert event.label == "My Child"
        assert event.display_name == "Child Display"


class TestSessionIdentityMutation:
    def setup_method(self) -> None:
        _reset_session_lifecycle_listeners_for_tests()

    def test_register_and_emit_create(self) -> None:
        """A create mutation is delivered to listeners."""
        received: list[SessionIdentityMutation] = []
        on_session_identity_mutation(received.append)
        emit_session_identity_mutation(
            SessionIdentityMutation(
                kind="create",
                previous=SessionIdentityMutationTarget(),
                current=SessionIdentityMutationTarget(
                    session_id="abc",
                    session_keys=("agent:1:main",),
                ),
            )
        )
        assert len(received) == 1
        assert received[0].kind == "create"
        assert received[0].current is not None
        assert received[0].current.session_id == "abc"

    def test_delete_mutation_has_no_current(self) -> None:
        """A delete mutation has no ``current`` field (mirrors the TS union)."""
        received: list[SessionIdentityMutation] = []
        on_session_identity_mutation(received.append)
        emit_session_identity_mutation(
            SessionIdentityMutation(
                kind="delete",
                previous=SessionIdentityMutationTarget(
                    session_id="abc",
                    session_keys=("agent:1:main",),
                ),
            )
        )
        assert received[0].kind == "delete"
        assert received[0].current is None

    def test_listener_exception_is_swallowed(self) -> None:
        """Listener exceptions don't break the chain."""
        order: list[str] = []
        on_session_identity_mutation(
            lambda _m: (_ for _ in ()).throw(RuntimeError("boom"))
        )
        on_session_identity_mutation(lambda _m: order.append("ok"))
        emit_session_identity_mutation(
            SessionIdentityMutation(
                kind="delete",
                previous=SessionIdentityMutationTarget(),
            )
        )
        assert order == ["ok"]


# ── Level overrides ────────────────────────────────────────────────


class TestNormalizeVerboseLevel:
    def test_canonical_values(self) -> None:
        for v in ["on", "off", "full"]:
            assert normalize_verbose_level(v) == v

    def test_case_insensitive(self) -> None:
        assert normalize_verbose_level("ON") == "on"
        assert normalize_verbose_level("Full") == "full"

    def test_strips_whitespace(self) -> None:
        assert normalize_verbose_level("  on  ") == "on"

    def test_unknown_value(self) -> None:
        assert normalize_verbose_level("verbose") is None

    def test_non_string(self) -> None:
        assert normalize_verbose_level(123) is None
        assert normalize_verbose_level(None) is None
        assert normalize_verbose_level([]) is None


class TestNormalizeTraceLevel:
    def test_canonical_values(self) -> None:
        for v in ["on", "off", "raw"]:
            assert normalize_trace_level(v) == v

    def test_case_insensitive(self) -> None:
        assert normalize_trace_level("RAW") == "raw"
        assert normalize_trace_level("Off") == "off"

    def test_unknown_value(self) -> None:
        assert normalize_trace_level("full") is None  # 'full' is verbose only

    def test_non_string(self) -> None:
        assert normalize_trace_level(None) is None
        assert normalize_trace_level(42) is None


class TestParseVerboseOverride:
    def test_none_means_clear(self) -> None:
        """Python ``None`` → tri-state clear (mirrors TS ``null``)."""
        result = parse_verbose_override(None)
        assert result == ParsedVerboseOverride(ok=True, value=None)

    def test_valid_level(self) -> None:
        result = parse_verbose_override("full")
        assert result == ParsedVerboseOverride(ok=True, value="full")

    def test_invalid_level(self) -> None:
        result = parse_verbose_override("verbose")
        assert result.ok is False
        assert "invalid verboseLevel" in (result.error or "")

    def test_non_string(self) -> None:
        result = parse_verbose_override(42)
        assert result.ok is False
        assert "invalid" in (result.error or "")


class TestApplyVerboseOverride:
    def test_set(self) -> None:
        entry: dict = {}
        apply_verbose_override(entry, "full")
        assert entry["verboseLevel"] == "full"

    def test_clear_via_empty_string(self) -> None:
        """Empty string clears (the Python "clear" sentinel)."""
        entry = {"verboseLevel": "full"}
        apply_verbose_override(entry, "")  # type: ignore[arg-type]
        assert "verboseLevel" not in entry

    def test_no_change_via_none(self) -> None:
        """``None`` = no change (tri-state sentinel)."""
        entry = {"verboseLevel": "full"}
        apply_verbose_override(entry, None)
        assert entry["verboseLevel"] == "full"  # unchanged


class TestParseTraceOverride:
    def test_none_means_clear(self) -> None:
        assert parse_trace_override(None) == ParsedTraceOverride(ok=True, value=None)

    def test_valid_level(self) -> None:
        assert parse_trace_override("raw") == ParsedTraceOverride(ok=True, value="raw")

    def test_invalid_level(self) -> None:
        result = parse_trace_override("full")  # 'full' is verbose, not trace
        assert result.ok is False
        assert "invalid traceLevel" in (result.error or "")

    def test_non_string(self) -> None:
        result = parse_trace_override([])
        assert result.ok is False


class TestApplyTraceOverride:
    def test_set(self) -> None:
        entry: dict = {}
        apply_trace_override(entry, "raw")
        assert entry["traceLevel"] == "raw"

    def test_clear(self) -> None:
        entry = {"traceLevel": "raw"}
        apply_trace_override(entry, "")  # type: ignore[arg-type]
        assert "traceLevel" not in entry

    def test_no_change(self) -> None:
        entry = {"traceLevel": "raw"}
        apply_trace_override(entry, None)
        assert entry["traceLevel"] == "raw"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
