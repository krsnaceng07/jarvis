"""Phase 7.6h-7 tests — 3 final run/ files."""
from __future__ import annotations

import asyncio
import os
import sys
from typing import Any, Dict, List, Optional

import pytest

# Ensure src/ is on sys.path
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from src.agents.embedded_agent_runner.run.terminal_outcome import (  # noqa: E402
    AGENT_RUN_RESTART_ABORT_REASONS,
    AGENT_RUN_RESTART_ABORT_STOP_REASON,
    is_agent_run_restart_abort_reason,
    is_embedded_run_terminal_abort,
    is_embedded_run_terminal_interrupted,
    is_embedded_run_terminal_timeout,
    resolve_agent_run_abort_lifecycle_fields,
    resolve_embedded_run_attempt_terminal_outcome,
    set_is_embedded_run_terminal_abort_hook,
    set_is_embedded_run_terminal_timeout_hook,
    set_resolve_agent_run_abort_lifecycle_fields_hook,
    set_resolve_embedded_run_attempt_terminal_outcome_hook,
)
from src.agents.embedded_agent_runner.run.session_prompt_state import (  # noqa: E402
    MID_TURN_PRECHECK_CONTINUATION_PROMPT,
    create_embedded_run_session_prompt_state,
    set_build_context_engine_compaction_session_target_hook,
    set_create_embedded_run_session_prompt_state_hook,
    set_register_agent_run_context_hook,
    set_resolve_agent_run_session_target_hook,
)
from src.agents.embedded_agent_runner.run.payloads_test_helpers import (  # noqa: E402
    build_payloads,
    expect_single_payload_text,
    expect_single_tool_error_payload,
    set_build_embedded_run_payloads_fn,
    set_build_payloads_hook,
)


# ============================================================================
# terminal_outcome
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_terminal_outcome_hooks() -> None:
    set_resolve_embedded_run_attempt_terminal_outcome_hook(None)
    set_is_embedded_run_terminal_timeout_hook(None)
    set_is_embedded_run_terminal_abort_hook(None)
    set_resolve_agent_run_abort_lifecycle_fields_hook(None)
    yield
    set_resolve_embedded_run_attempt_terminal_outcome_hook(None)
    set_is_embedded_run_terminal_timeout_hook(None)
    set_is_embedded_run_terminal_abort_hook(None)
    set_resolve_agent_run_abort_lifecycle_fields_hook(None)


class TestTerminalOutcome:
    def test_constants(self) -> None:
        assert AGENT_RUN_RESTART_ABORT_STOP_REASON == "restart_abort"
        assert "restart_requested" in AGENT_RUN_RESTART_ABORT_REASONS
        assert "restart_abort" in AGENT_RUN_RESTART_ABORT_REASONS
        assert "steering_restart" in AGENT_RUN_RESTART_ABORT_REASONS
        assert "lane_restart" in AGENT_RUN_RESTART_ABORT_REASONS

    def test_is_restart_reason(self) -> None:
        assert is_agent_run_restart_abort_reason("restart_abort")
        assert is_agent_run_restart_abort_reason("restart_requested")
        assert not is_agent_run_restart_abort_reason("aborted")
        assert not is_agent_run_restart_abort_reason(None)

    def test_is_restart_reason_object(self) -> None:
        class _E(Exception):
            reason = "restart_abort"
        assert is_agent_run_restart_abort_reason(_E())

    def test_resolve_abort_lifecycle_no_signal(self) -> None:
        out = resolve_agent_run_abort_lifecycle_fields(None)
        assert out["aborted"] is False
        assert out["stopReason"] is None

    def test_resolve_abort_lifecycle_aborted(self) -> None:
        class _S:
            aborted = True
        out = resolve_agent_run_abort_lifecycle_fields(_S())
        assert out["aborted"] is True
        assert out["stopReason"] == "aborted"

    def test_resolve_abort_lifecycle_with_reason(self) -> None:
        class _S:
            aborted = True
            reason = "timeout"
        out = resolve_agent_run_abort_lifecycle_fields(_S())
        assert out["aborted"] is True
        assert out["stopReason"] == "timeout"

    def test_resolve_abort_lifecycle_with_hook(self) -> None:
        set_resolve_agent_run_abort_lifecycle_fields_hook(lambda _s: {"hooked": True})
        out = resolve_agent_run_abort_lifecycle_fields(None)
        assert out == {"hooked": True}

    def test_resolve_attempt_no_attempt(self) -> None:
        out = resolve_embedded_run_attempt_terminal_outcome({})
        assert out["status"] == "ok"

    def test_resolve_attempt_ok(self) -> None:
        out = resolve_embedded_run_attempt_terminal_outcome(
            {"attempt": {}, "assistant": {"stopReason": "end_turn"}}
        )
        assert out["status"] == "ok"
        assert out["stopReason"] == "end_turn"

    def test_resolve_attempt_timed_out(self) -> None:
        out = resolve_embedded_run_attempt_terminal_outcome(
            {"attempt": {"timedOut": True}}
        )
        assert out["status"] == "timeout"
        assert out["reason"] in ("hard_timeout", "timed_out")

    def test_resolve_attempt_idle_timed_out(self) -> None:
        out = resolve_embedded_run_attempt_terminal_outcome(
            {"attempt": {"idleTimedOut": True}}
        )
        assert out["status"] == "timeout"

    def test_resolve_attempt_aborted(self) -> None:
        out = resolve_embedded_run_attempt_terminal_outcome(
            {"attempt": {"aborted": True}}
        )
        assert out["status"] == "error"
        assert out["stopReason"] == "aborted"

    def test_resolve_attempt_with_prompt_error(self) -> None:
        err = RuntimeError("boom")
        out = resolve_embedded_run_attempt_terminal_outcome(
            {"attempt": {"promptError": err}}
        )
        assert out["status"] == "error"

    def test_resolve_attempt_with_assistant_error(self) -> None:
        out = resolve_embedded_run_attempt_terminal_outcome(
            {"attempt": {}, "assistant": {"stopReason": "error"}}
        )
        assert out["status"] == "error"

    def test_resolve_attempt_with_prompt_timeout_outcome(self) -> None:
        out = resolve_embedded_run_attempt_terminal_outcome(
            {
                "attempt": {
                    "timedOut": True,
                    "promptTimeoutOutcome": {
                        "timeoutPhase": "context",
                        "providerStarted": True,
                    },
                }
            }
        )
        assert out["timeoutPhase"] == "context"
        assert out["providerStarted"] is True

    def test_resolve_attempt_unattributed_timeout(self) -> None:
        out = resolve_embedded_run_attempt_terminal_outcome(
            {"attempt": {"timedOut": True, "idleTimedOut": True}}
        )
        # No timeoutPhase and no providerStarted → unattributed, stopReason
        # is undefined to avoid mis-attribution
        assert out["status"] == "timeout"
        assert out.get("stopReason") is None

    def test_resolve_attempt_with_restart_abort(self) -> None:
        # Nested restart reason
        class _Inner(Exception):
            reason = "restart_requested"
        class _Outer(Exception):
            def __init__(self):
                self.cause = _Inner()
        out = resolve_embedded_run_attempt_terminal_outcome(
            {"attempt": {"promptError": _Outer()}}
        )
        assert out["stopReason"] == AGENT_RUN_RESTART_ABORT_STOP_REASON

    def test_resolve_with_hook(self) -> None:
        set_resolve_embedded_run_attempt_terminal_outcome_hook(
            lambda _p: {"hooked": True}
        )
        out = resolve_embedded_run_attempt_terminal_outcome({})
        assert out == {"hooked": True}

    def test_is_terminal_timeout(self) -> None:
        assert is_embedded_run_terminal_timeout({"reason": "hard_timeout"})
        assert is_embedded_run_terminal_timeout({"reason": "timed_out"})
        assert not is_embedded_run_terminal_timeout({"reason": "aborted"})

    def test_is_terminal_timeout_with_hook(self) -> None:
        set_is_embedded_run_terminal_timeout_hook(lambda _o: True)
        assert is_embedded_run_terminal_timeout({}) is True

    def test_is_terminal_abort(self) -> None:
        assert is_embedded_run_terminal_abort({"reason": "aborted"})
        assert is_embedded_run_terminal_abort({"reason": "cancelled"})
        assert not is_embedded_run_terminal_abort({"reason": "timed_out"})

    def test_is_terminal_abort_with_hook(self) -> None:
        set_is_embedded_run_terminal_abort_hook(lambda _o: True)
        assert is_embedded_run_terminal_abort({}) is True

    def test_is_terminal_interrupted(self) -> None:
        assert is_embedded_run_terminal_interrupted({"reason": "aborted"})
        assert is_embedded_run_terminal_interrupted({"reason": "hard_timeout"})
        assert is_embedded_run_terminal_interrupted({"reason": "timed_out"})
        assert is_embedded_run_terminal_interrupted({"reason": "cancelled"})
        assert not is_embedded_run_terminal_interrupted({"reason": "ok"})

    def test_is_terminal_non_dict(self) -> None:
        assert not is_embedded_run_terminal_timeout(None)
        assert not is_embedded_run_terminal_abort(None)


# ============================================================================
# session_prompt_state
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_session_prompt_state_hooks() -> None:
    set_create_embedded_run_session_prompt_state_hook(None)
    set_build_context_engine_compaction_session_target_hook(None)
    set_register_agent_run_context_hook(None)
    set_resolve_agent_run_session_target_hook(None)
    yield
    set_create_embedded_run_session_prompt_state_hook(None)
    set_build_context_engine_compaction_session_target_hook(None)
    set_register_agent_run_context_hook(None)
    set_resolve_agent_run_session_target_hook(None)


class TestSessionPromptState:
    def test_constants(self) -> None:
        assert "Continue from the current transcript" in MID_TURN_PRECHECK_CONTINUATION_PROMPT

    def test_basic(self) -> None:
        state = create_embedded_run_session_prompt_state(
            {
                "runParams": {"sessionId": "s1", "sessionFile": "/x.jsonl", "runId": "r1"},
                "sessionAgentId": "main",
                "resolvedSessionKey": "key-1",
                "lifecycleGeneration": 1,
            }
        )
        assert state is not None
        assert "sessionId" in state
        assert "adoptSessionId" in state
        assert "activateInternalPrompt" in state
        assert "continueFromCurrentTranscript" in state
        assert "onUserMessagePersisted" in state

    def test_session_id_initial(self) -> None:
        state = create_embedded_run_session_prompt_state(
            {
                "runParams": {"sessionId": "s1", "sessionFile": "/x.jsonl"},
                "sessionAgentId": "main",
                "resolvedSessionKey": "k",
                "lifecycleGeneration": 1,
            }
        )
        assert state["sessionId"] == "s1"

    def test_adopt_session_id(self) -> None:
        called = {"update": None, "onChanged": None, "registered": None}
        state = create_embedded_run_session_prompt_state(
            {
                "runParams": {
                    "sessionId": "s1",
                    "sessionFile": "/x.jsonl",
                    "runId": "r1",
                    "replyOperation": {"updateSessionId": lambda v: called.__setitem__("update", v)},
                    "onSessionIdChanged": lambda v: called.__setitem__("onChanged", v),
                },
                "sessionAgentId": "main",
                "resolvedSessionKey": "k",
                "lifecycleGeneration": 1,
            }
        )
        state["adoptSessionId"]("s2")
        assert called["update"] == "s2"
        assert called["onChanged"] == "s2"

    def test_adopt_session_id_no_change(self) -> None:
        called = {"update": None}
        state = create_embedded_run_session_prompt_state(
            {
                "runParams": {
                    "sessionId": "s1",
                    "sessionFile": "/x.jsonl",
                    "runId": "r1",
                    "replyOperation": {"updateSessionId": lambda v: called.__setitem__("update", v)},
                },
                "sessionAgentId": "main",
                "resolvedSessionKey": "k",
                "lifecycleGeneration": 1,
            }
        )
        # Same session ID → no-op
        state["adoptSessionId"]("s1")
        assert called["update"] is None

    def test_adopt_session_id_none(self) -> None:
        state = create_embedded_run_session_prompt_state(
            {
                "runParams": {"sessionId": "s1", "sessionFile": "/x.jsonl"},
                "sessionAgentId": "main",
                "resolvedSessionKey": "k",
                "lifecycleGeneration": 1,
            }
        )
        # None → no-op
        state["adoptSessionId"](None)

    def test_adopt_session_id_with_register_hook(self) -> None:
        called = {}
        set_register_agent_run_context_hook(
            lambda run_id, payload: called.__setitem__("reg", (run_id, payload))
        )
        state = create_embedded_run_session_prompt_state(
            {
                "runParams": {"sessionId": "s1", "sessionFile": "/x.jsonl", "runId": "r1"},
                "sessionAgentId": "main",
                "resolvedSessionKey": "k",
                "lifecycleGeneration": 1,
            }
        )
        state["adoptSessionId"]("s2")
        assert called["reg"][0] == "r1"
        assert called["reg"][1]["sessionId"] == "s2"

    def test_adopt_session_target_no_target(self) -> None:
        state = create_embedded_run_session_prompt_state(
            {
                "runParams": {"sessionId": "s1", "sessionFile": "/x.jsonl"},
                "sessionAgentId": "main",
                "resolvedSessionKey": "k",
                "lifecycleGeneration": 1,
            }
        )
        asyncio.run(state["adoptSessionTarget"](None))

    def test_adopt_session_target_basic(self) -> None:
        state = create_embedded_run_session_prompt_state(
            {
                "runParams": {"sessionId": "s1", "sessionFile": "/x.jsonl", "runId": "r1"},
                "sessionAgentId": "main",
                "resolvedSessionKey": "k",
                "lifecycleGeneration": 1,
            }
        )
        asyncio.run(
            state["adoptSessionTarget"](
                {
                    "agentId": "main",
                    "sessionId": "s2",
                    "sessionKey": "k2",
                    "sessionFile": "/y.jsonl",
                }
            )
        )
        assert state["sessionId"] == "s2"

    def test_adopt_session_target_with_resolve_hook(self) -> None:
        async def _hook(_p):
            return {"sessionId": "resolved", "sessionFile": "/r.jsonl"}
        set_resolve_agent_run_session_target_hook(_hook)
        state = create_embedded_run_session_prompt_state(
            {
                "runParams": {"sessionId": "s1", "sessionFile": "/x.jsonl", "runId": "r1"},
                "sessionAgentId": "main",
                "resolvedSessionKey": "k",
                "lifecycleGeneration": 1,
            }
        )
        asyncio.run(
            state["adoptSessionTarget"](
                {
                    "agentId": "main",
                    "sessionId": "s2",
                    "sessionKey": "k2",
                    "sessionFile": "/y.jsonl",
                }
            )
        )
        assert state["sessionId"] == "resolved"

    def test_activate_internal_prompt(self) -> None:
        state = create_embedded_run_session_prompt_state(
            {
                "runParams": {"sessionId": "s1", "sessionFile": "/x.jsonl"},
                "sessionAgentId": "main",
                "resolvedSessionKey": "k",
                "lifecycleGeneration": 1,
            }
        )
        state["activateInternalPrompt"]("hello", True)
        prompt = state["activePrompt"]
        assert prompt.get("override") == "hello"
        assert prompt.get("persisted") is True
        assert prompt.get("internal") is True

    def test_continue_from_current_transcript(self) -> None:
        state = create_embedded_run_session_prompt_state(
            {
                "runParams": {"sessionId": "s1", "sessionFile": "/x.jsonl"},
                "sessionAgentId": "main",
                "resolvedSessionKey": "k",
                "lifecycleGeneration": 1,
            }
        )
        state["continueFromCurrentTranscript"]()
        prompt = state["activePrompt"]
        assert prompt.get("internal") is True
        assert prompt.get("override") == MID_TURN_PRECHECK_CONTINUATION_PROMPT

    def test_on_user_message_persisted_no_recorder(self) -> None:
        state = create_embedded_run_session_prompt_state(
            {
                "runParams": {
                    "sessionId": "s1",
                    "sessionFile": "/x.jsonl",
                    "onUserMessagePersisted": lambda _m: None,
                },
                "sessionAgentId": "main",
                "resolvedSessionKey": "k",
                "lifecycleGeneration": 1,
            }
        )
        # Without a recorder, onUserMessagePersisted marks active prompt persisted
        state["onUserMessagePersisted"]({"role": "user", "content": "hi"})
        assert state["activePrompt"].get("persisted") is True

    def test_on_user_message_persisted_blocked(self) -> None:
        captured = {}
        recorder = {
            "persistBlocked": lambda msg: captured.__setitem__("msg", msg) or PromiseLike(),
            "persistApproved": lambda: PromiseLike(),
            "hasPersisted": lambda: False,
            "hasRuntimePersistencePending": lambda: False,
            "waitForRuntimePersistence": lambda: asyncio.sleep(0),
            "markRuntimePersistencePending": lambda _p: None,
        }
        state = create_embedded_run_session_prompt_state(
            {
                "runParams": {
                    "sessionId": "s1",
                    "sessionFile": "/x.jsonl",
                    "userTurnTranscriptRecorder": recorder,
                },
                "sessionAgentId": "main",
                "resolvedSessionKey": "k",
                "lifecycleGeneration": 1,
            }
        )
        state["onUserMessagePersisted"](
            {"role": "user", "__openclaw": {"beforeAgentRunBlocked": True}, "content": "hi"}
        )
        assert "msg" in captured

    def test_with_hook(self) -> None:
        set_create_embedded_run_session_prompt_state_hook(lambda _p: {"hooked": True})
        out = create_embedded_run_session_prompt_state({})
        assert out == {"hooked": True}

    def test_build_context_engine_session_target_hook(self) -> None:
        set_build_context_engine_compaction_session_target_hook(
            lambda _p: {"hooked": True}
        )
        # Trigger through create_embedded_run_session_prompt_state
        state = create_embedded_run_session_prompt_state(
            {
                "runParams": {"sessionId": "s1", "sessionFile": "/x.jsonl"},
                "sessionAgentId": "main",
                "resolvedSessionKey": "k",
                "lifecycleGeneration": 1,
            }
        )
        assert state is not None


class _PromiseLike:
    def __init__(self) -> None:
        self._callbacks = []

    def then(self, on_fulfilled, on_rejected=None):
        if on_fulfilled:
            try:
                on_fulfilled({"message": True})
            except Exception:
                pass
        return self

    def catch(self, on_rejected):
        return self


# ============================================================================
# payloads_test_helpers
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_payloads_test_helpers_hooks() -> None:
    set_build_payloads_hook(None)
    set_build_embedded_run_payloads_fn(None)
    yield
    set_build_payloads_hook(None)
    set_build_embedded_run_payloads_fn(None)


class TestPayloadsTestHelpers:
    def test_build_payloads_no_fn(self) -> None:
        out = build_payloads()
        assert out == []

    def test_build_payloads_with_fn(self) -> None:
        def _build(p):
            return [{"text": p.get("sessionKey", "")}]
        set_build_embedded_run_payloads_fn(_build)
        out = build_payloads()
        assert out == [{"text": "session:telegram"}]

    def test_build_payloads_overrides(self) -> None:
        captured = {}
        def _build(p):
            captured.update(p)
            return []
        set_build_embedded_run_payloads_fn(_build)
        build_payloads({"sessionKey": "session:discord", "verboseLevel": "on"})
        assert captured["sessionKey"] == "session:discord"
        assert captured["verboseLevel"] == "on"
        assert captured["isCronTrigger"] is False

    def test_build_payloads_with_hook(self) -> None:
        set_build_payloads_hook(lambda _o: [{"hooked": True}])
        assert build_payloads() == [{"hooked": True}]

    def test_expect_single_payload_text(self) -> None:
        expect_single_payload_text([{"text": "hello"}], "hello")

    def test_expect_single_payload_text_with_error(self) -> None:
        expect_single_payload_text(
            [{"text": "error happened", "isError": True}],
            "error happened",
            expected_error=True,
        )

    def test_expect_single_payload_text_wrong_count(self) -> None:
        with pytest.raises(AssertionError):
            expect_single_payload_text([], "hello")

    def test_expect_single_payload_text_wrong_text(self) -> None:
        with pytest.raises(AssertionError):
            expect_single_payload_text([{"text": "goodbye"}], "hello")

    def test_expect_single_tool_error(self) -> None:
        expect_single_tool_error_payload(
            [{"text": "Tool X failed: connection refused", "isError": True}],
            {"title": "Tool X failed", "detail": "connection refused"},
        )

    def test_expect_single_tool_error_with_absent_detail(self) -> None:
        expect_single_tool_error_payload(
            [{"text": "Tool X failed", "isError": True}],
            {"title": "Tool X failed", "absentDetail": "should not be present"},
        )

    def test_expect_single_tool_error_wrong_count(self) -> None:
        with pytest.raises(AssertionError):
            expect_single_tool_error_payload([], {"title": "X"})

    def test_expect_single_tool_error_wrong_is_error(self) -> None:
        with pytest.raises(AssertionError):
            expect_single_tool_error_payload(
                [{"text": "Tool X failed", "isError": False}],
                {"title": "X"},
            )

    def test_expect_single_tool_error_title_missing(self) -> None:
        with pytest.raises(AssertionError):
            expect_single_tool_error_payload(
                [{"text": "different text", "isError": True}],
                {"title": "expected title"},
            )
