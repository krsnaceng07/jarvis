"""Phase 7.6h-5 tests — 3 top-level big files."""
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

from src.agents.embedded_agent_runner.context_engine_maintenance import (  # noqa: E402
    TURN_MAINTENANCE_LANE_PREFIX,
    TURN_MAINTENANCE_LONG_WAIT_MS,
    TURN_MAINTENANCE_TASK_KIND,
    TURN_MAINTENANCE_TASK_LABEL,
    _active_deferred_runs,
    reset_deferred_turn_maintenance_state_for_test,
    run_context_engine_maintenance,
    schedule_deferred_turn_maintenance,
    set_run_context_engine_maintenance_hook,
    set_schedule_deferred_turn_maintenance_hook,
    set_wait_for_deferred_turn_maintenance_for_session_hook,
    wait_for_deferred_turn_maintenance_for_session,
)
from src.agents.embedded_agent_runner.google_prompt_cache import (  # noqa: E402
    GOOGLE_PROMPT_CACHE_CUSTOM_TYPE,
    GOOGLE_PROMPT_CACHE_LONG_REFRESH_WINDOW_MS,
    GOOGLE_PROMPT_CACHE_RETRY_BACKOFF_MS,
    GOOGLE_PROMPT_CACHE_SHORT_REFRESH_WINDOW_MS,
    build_google_prompt_cache_match_key,
    prepare_google_prompt_cache_stream_fn,
    read_latest_google_prompt_cache_entry,
    resolve_google_prompt_cache_refresh_window_ms,
    resolve_google_prompt_cache_ttl,
    set_build_google_prompt_cache_match_key_hook,
    set_prepare_google_prompt_cache_stream_fn_hook,
    set_read_latest_google_prompt_cache_entry_hook,
)
from src.agents.embedded_agent_runner.thinking import (  # noqa: E402
    OMITTED_ASSISTANT_REASONING_TEXT,
    THINKING_BLOCK_ERROR_PATTERN,
    build_assistant_message_with_sanitized_thinking,
    recover_anthropic_thinking,
    sanitize_thinking_for_replay,
    strip_invalid_thinking_signatures,
    strip_stale_thinking_signatures_for_compaction_replay,
    strip_thinking_signatures_from_message,
    set_build_assistant_message_with_sanitized_thinking_hook,
    set_recover_anthropic_thinking_hook,
    set_sanitize_thinking_for_replay_hook,
    set_strip_invalid_thinking_signatures_hook,
    set_strip_stale_thinking_signatures_for_compaction_replay_hook,
    set_strip_thinking_signatures_from_message_hook,
)


# ============================================================================
# context_engine_maintenance
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_ctx_engine_maint_hooks() -> None:
    reset_deferred_turn_maintenance_state_for_test()
    set_run_context_engine_maintenance_hook(None)
    set_schedule_deferred_turn_maintenance_hook(None)
    set_wait_for_deferred_turn_maintenance_for_session_hook(None)
    yield
    reset_deferred_turn_maintenance_state_for_test()
    set_run_context_engine_maintenance_hook(None)
    set_schedule_deferred_turn_maintenance_hook(None)
    set_wait_for_deferred_turn_maintenance_for_session_hook(None)


class TestContextEngineMaintenance:
    def test_constants(self) -> None:
        assert TURN_MAINTENANCE_TASK_KIND == "context_engine_turn_maintenance"
        assert TURN_MAINTENANCE_LANE_PREFIX == "context-engine-turn-maintenance:"
        assert TURN_MAINTENANCE_LONG_WAIT_MS == 10_000
        assert TURN_MAINTENANCE_TASK_LABEL

    def test_run_no_engine(self) -> None:
        out = asyncio.run(run_context_engine_maintenance({"sessionId": "s1"}))
        assert out is None

    def test_run_engine_no_maintain(self) -> None:
        out = asyncio.run(
            run_context_engine_maintenance(
                {"sessionId": "s1", "contextEngine": {"info": {}}}
            )
        )
        assert out is None

    def test_run_engine_with_maintain(self) -> None:
        called = {}

        async def _maintain(_req):
            called["yes"] = True
            return {"changed": True, "rewrittenEntries": 1, "bytesFreed": 100}

        ctx = {"maintain": _maintain, "info": {}}
        out = asyncio.run(
            run_context_engine_maintenance(
                {"sessionId": "s1", "contextEngine": ctx, "reason": "bootstrap"}
            )
        )
        assert out is not None
        assert out["changed"] is True
        assert called.get("yes") is True

    def test_run_with_defer(self) -> None:
        # turn reason + turnMaintenanceMode=background → defers via schedule_deferred_turn_maintenance
        ctx = {"maintain": lambda _r: None, "info": {"turnMaintenanceMode": "background"}}
        out = asyncio.run(
            run_context_engine_maintenance(
                {
                    "sessionId": "s1",
                    "sessionKey": "s1",
                    "contextEngine": ctx,
                    "reason": "turn",
                }
            )
        )
        assert out is None
        # The deferred entry was registered
        assert "s1" in _active_deferred_runs

    def test_run_with_hook(self) -> None:
        async def _hook(_p):
            return {"hooked": True}
        set_run_context_engine_maintenance_hook(_hook)
        out = asyncio.run(run_context_engine_maintenance({}))
        assert out == {"hooked": True}

    def test_run_sync_hook(self) -> None:
        set_run_context_engine_maintenance_hook(lambda _p: {"sync": True})
        out = asyncio.run(run_context_engine_maintenance({}))
        assert out == {"sync": True}

    def test_run_maintain_exception(self) -> None:
        async def _maintain(_r):
            raise RuntimeError("boom")
        ctx = {"maintain": _maintain, "info": {}}
        out = asyncio.run(
            run_context_engine_maintenance(
                {"sessionId": "s1", "contextEngine": ctx, "reason": "bootstrap"}
            )
        )
        assert out is None

    def test_schedule_no_session_key(self) -> None:
        assert schedule_deferred_turn_maintenance({"sessionKey": None}) is None
        assert schedule_deferred_turn_maintenance({}) is None
        assert schedule_deferred_turn_maintenance({"sessionKey": "  "}) is None

    def test_schedule_basic(self) -> None:
        promise = schedule_deferred_turn_maintenance(
            {"sessionKey": "s1", "sessionId": "s1"}
        )
        assert promise is not None
        assert "s1" in _active_deferred_runs

    def test_schedule_idempotent(self) -> None:
        p1 = schedule_deferred_turn_maintenance(
            {"sessionKey": "s1", "sessionId": "s1"}
        )
        p2 = schedule_deferred_turn_maintenance(
            {"sessionKey": "s1", "sessionId": "s1"}
        )
        # Both return futures; second one chains into the first
        assert p1 is not None
        assert p2 is not None

    def test_schedule_with_hook(self) -> None:
        sentinel = object()
        set_schedule_deferred_turn_maintenance_hook(lambda _p: sentinel)
        out = schedule_deferred_turn_maintenance({})
        assert out is sentinel

    def test_wait_no_session(self) -> None:
        asyncio.run(wait_for_deferred_turn_maintenance_for_session(None))
        asyncio.run(wait_for_deferred_turn_maintenance_for_session(""))

    def test_wait_with_hook(self) -> None:
        called = {}
        async def _hook(_p):
            called["yes"] = True
        set_wait_for_deferred_turn_maintenance_for_session_hook(_hook)
        asyncio.run(wait_for_deferred_turn_maintenance_for_session("any"))

    def test_reset_state(self) -> None:
        schedule_deferred_turn_maintenance({"sessionKey": "x", "sessionId": "x"})
        assert "x" in _active_deferred_runs
        reset_deferred_turn_maintenance_state_for_test()
        assert "x" not in _active_deferred_runs


# ============================================================================
# google_prompt_cache
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_google_prompt_cache_hooks() -> None:
    set_prepare_google_prompt_cache_stream_fn_hook(None)
    set_read_latest_google_prompt_cache_entry_hook(None)
    set_build_google_prompt_cache_match_key_hook(None)
    yield
    set_prepare_google_prompt_cache_stream_fn_hook(None)
    set_read_latest_google_prompt_cache_entry_hook(None)
    set_build_google_prompt_cache_match_key_hook(None)


class TestGooglePromptCache:
    def test_constants(self) -> None:
        assert GOOGLE_PROMPT_CACHE_CUSTOM_TYPE == "openclaw.google-prompt-cache"
        assert GOOGLE_PROMPT_CACHE_RETRY_BACKOFF_MS == 10 * 60_000
        assert GOOGLE_PROMPT_CACHE_SHORT_REFRESH_WINDOW_MS == 30_000
        assert GOOGLE_PROMPT_CACHE_LONG_REFRESH_WINDOW_MS == 5 * 60_000

    def test_resolve_ttl(self) -> None:
        assert resolve_google_prompt_cache_ttl("short") == "300s"
        assert resolve_google_prompt_cache_ttl("long") == "3600s"

    def test_resolve_refresh_window(self) -> None:
        assert resolve_google_prompt_cache_refresh_window_ms("short") == 30_000
        assert resolve_google_prompt_cache_refresh_window_ms("long") == 5 * 60_000

    def test_build_match_key(self) -> None:
        k1 = build_google_prompt_cache_match_key(
            {
                "provider": "google",
                "modelId": "gemini-2.5-pro",
                "baseUrl": "https://generativelanguage.googleapis.com",
                "systemPromptDigest": "abc",
            }
        )
        k2 = build_google_prompt_cache_match_key(
            {
                "provider": "google",
                "modelId": "gemini-2.5-pro",
                "baseUrl": "https://generativelanguage.googleapis.com",
                "systemPromptDigest": "abc",
            }
        )
        assert k1 == k2
        # Different digest → different key
        k3 = build_google_prompt_cache_match_key(
            {
                "provider": "google",
                "modelId": "gemini-2.5-pro",
                "baseUrl": "https://generativelanguage.googleapis.com",
                "systemPromptDigest": "def",
            }
        )
        assert k1 != k3

    def test_build_match_key_with_hook(self) -> None:
        set_build_google_prompt_cache_match_key_hook(lambda _p: "custom")
        assert build_google_prompt_cache_match_key({}) == "custom"

    def test_read_latest_no_entries(self) -> None:
        assert read_latest_google_prompt_cache_entry({}, "k") is None

    def test_read_latest_no_get_entries(self) -> None:
        assert read_latest_google_prompt_cache_entry({"foo": 1}, "k") is None

    def test_read_latest_with_entries(self) -> None:
        sm = {
            "getEntries": lambda: [
                {
                    "type": "custom",
                    "customType": GOOGLE_PROMPT_CACHE_CUSTOM_TYPE,
                    "data": {
                        "provider": "google",
                        "modelId": "gemini-2.5-pro",
                        "baseUrl": "https://x",
                        "systemPromptDigest": "abc",
                        "status": "ready",
                        "cachedContent": "cc1",
                    },
                }
            ]
        }
        key = build_google_prompt_cache_match_key(
            {
                "provider": "google",
                "modelId": "gemini-2.5-pro",
                "baseUrl": "https://x",
                "systemPromptDigest": "abc",
            }
        )
        out = read_latest_google_prompt_cache_entry(sm, key)
        assert out is not None
        assert out["cachedContent"] == "cc1"

    def test_read_latest_with_hook(self) -> None:
        set_read_latest_google_prompt_cache_entry_hook(lambda _sm, _k: {"hooked": True})
        out = read_latest_google_prompt_cache_entry({}, "k")
        assert out == {"hooked": True}

    def test_read_latest_exception(self) -> None:
        sm = {"getEntries": lambda: (_ for _ in ()).throw(RuntimeError("boom"))}
        assert read_latest_google_prompt_cache_entry(sm, "k") is None

    def test_prepare_default(self) -> None:
        out = prepare_google_prompt_cache_stream_fn({"streamFn": "stub"})
        assert out == "stub"

    def test_prepare_with_hook(self) -> None:
        set_prepare_google_prompt_cache_stream_fn_hook(lambda _p: "wrapped")
        assert prepare_google_prompt_cache_stream_fn({}) == "wrapped"


# ============================================================================
# thinking
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_thinking_hooks() -> None:
    set_strip_thinking_signatures_from_message_hook(None)
    set_strip_stale_thinking_signatures_for_compaction_replay_hook(None)
    set_strip_invalid_thinking_signatures_hook(None)
    set_sanitize_thinking_for_replay_hook(None)
    set_recover_anthropic_thinking_hook(None)
    set_build_assistant_message_with_sanitized_thinking_hook(None)
    yield
    set_strip_thinking_signatures_from_message_hook(None)
    set_strip_stale_thinking_signatures_for_compaction_replay_hook(None)
    set_strip_invalid_thinking_signatures_hook(None)
    set_sanitize_thinking_for_replay_hook(None)
    set_recover_anthropic_thinking_hook(None)
    set_build_assistant_message_with_sanitized_thinking_hook(None)


class TestThinking:
    def test_constants(self) -> None:
        assert OMITTED_ASSISTANT_REASONING_TEXT == "[assistant reasoning omitted]"
        assert THINKING_BLOCK_ERROR_PATTERN.pattern

    def test_thinking_pattern_matches(self) -> None:
        assert THINKING_BLOCK_ERROR_PATTERN.search("thinking block signature invalid")
        assert THINKING_BLOCK_ERROR_PATTERN.search("missing thinking signature")
        assert not THINKING_BLOCK_ERROR_PATTERN.search("all good here")

    def test_strip_signatures_non_assistant(self) -> None:
        msg = {"role": "user", "content": [{"type": "text", "text": "hi"}]}
        out = strip_thinking_signatures_from_message(msg)
        assert out is msg

    def test_strip_signatures_basic(self) -> None:
        msg = {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "thought", "thinkingSignature": "sig1"},
                {"type": "text", "text": "hi"},
            ],
        }
        out = strip_thinking_signatures_from_message(msg)
        assert out is not msg
        assert "thinkingSignature" not in out["content"][0]

    def test_strip_signatures_redacted(self) -> None:
        msg = {
            "role": "assistant",
            "content": [
                {"type": "redacted_thinking", "data": "secret", "thinkingSignature": "sig"},
            ],
        }
        out = strip_thinking_signatures_from_message(msg)
        assert "data" not in out["content"][0]
        assert "thinkingSignature" not in out["content"][0]

    def test_strip_signatures_no_change(self) -> None:
        msg = {
            "role": "assistant",
            "content": [{"type": "text", "text": "hello"}],
        }
        out = strip_thinking_signatures_from_message(msg)
        assert out is msg

    def test_strip_with_hook(self) -> None:
        set_strip_thinking_signatures_from_message_hook(lambda _m: "hooked")
        assert strip_thinking_signatures_from_message({}) == "hooked"

    def test_strip_stale_no_compaction(self) -> None:
        msgs = [
            {"role": "assistant", "content": [{"type": "text", "text": "hi"}]}
        ]
        out = strip_stale_thinking_signatures_for_compaction_replay(msgs)
        assert out is msgs

    def test_strip_stale_basic(self) -> None:
        msgs = [
            {
                "role": "assistant",
                "timestamp": 1000,
                "content": [
                    {"type": "thinking", "thinkingSignature": "sig1", "thinking": "x"},
                ],
            },
            {
                "role": "compactionSummary",
                "timestamp": 5000,
                "content": [{"type": "text", "text": "summary"}],
            },
            {
                "role": "assistant",
                "timestamp": 6000,
                "content": [
                    {"type": "thinking", "thinkingSignature": "sig2", "thinking": "y"},
                ],
            },
        ]
        out = strip_stale_thinking_signatures_for_compaction_replay(msgs)
        # First message (ts=1000) is before compaction → strip
        assert "thinkingSignature" not in out[0]["content"][0]
        # Third message (ts=6000) is after compaction → keep
        assert out[2]["content"][0].get("thinkingSignature") == "sig2"

    def test_strip_stale_with_hook(self) -> None:
        set_strip_stale_thinking_signatures_for_compaction_replay_hook(
            lambda _m: "hooked"
        )
        assert strip_stale_thinking_signatures_for_compaction_replay([]) == "hooked"

    def test_strip_invalid_with_error_text(self) -> None:
        msgs = [
            {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinkingSignature": "sig", "thinking": "x"},
                ],
            }
        ]
        out = strip_invalid_thinking_signatures(msgs, "thinking signature invalid")
        # Error text matches → no stripping
        assert out is msgs

    def test_strip_invalid_no_error_text(self) -> None:
        msgs = [
            {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinkingSignature": "sig", "thinking": "x"},
                ],
            }
        ]
        out = strip_invalid_thinking_signatures(msgs, None)
        assert out is not msgs
        assert "thinkingSignature" not in out[0]["content"][0]

    def test_strip_invalid_with_hook(self) -> None:
        set_strip_invalid_thinking_signatures_hook(
            lambda _p: "hooked"
        )
        assert strip_invalid_thinking_signatures([]) == "hooked"

    def test_sanitize_basic(self) -> None:
        msgs = [
            {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinkingSignature": "sig", "thinking": "x"},
                    {"type": "text", "text": "hi"},
                ],
            }
        ]
        out = sanitize_thinking_for_replay(msgs)
        assert out is not msgs
        assert "thinkingSignature" not in out[0]["content"][0]

    def test_sanitize_no_thinking(self) -> None:
        msgs = [{"role": "assistant", "content": [{"type": "text", "text": "hi"}]}]
        out = sanitize_thinking_for_replay(msgs)
        assert out is msgs

    def test_sanitize_with_hook(self) -> None:
        set_sanitize_thinking_for_replay_hook(lambda _m: "hooked")
        assert sanitize_thinking_for_replay([]) == "hooked"

    def test_recover_basic(self) -> None:
        msgs = [
            {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinkingSignature": "sig", "thinking": "x"},
                ],
            }
        ]
        out = recover_anthropic_thinking({"messages": msgs})
        assert "originalMessages" in out
        assert "cleanedMessages" in out

    def test_recover_with_callback(self) -> None:
        called = {}
        def _on_recovered(rec):
            called["rec"] = rec
        msgs = [{"role": "assistant", "content": [{"type": "text", "text": "x"}]}]
        recover_anthropic_thinking({"messages": msgs, "onRecoveredAnthropicThinking": _on_recovered})
        assert "rec" in called

    def test_recover_with_hook(self) -> None:
        set_recover_anthropic_thinking_hook(lambda _p: {"hooked": True})
        assert recover_anthropic_thinking({}) == {"hooked": True}

    def test_build_assistant_basic(self) -> None:
        msg = {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "x"},
                {"type": "text", "text": "hi"},
            ],
        }
        out = build_assistant_message_with_sanitized_thinking({"message": msg})
        # The thinking block with no signature is dropped; the text remains
        assert len(out["content"]) == 1
        assert out["content"][0]["type"] == "text"

    def test_build_assistant_omitted_text(self) -> None:
        # When only thinking exists, prepend omitted-reasoning text so
        # provider converters don't drop the message
        msg = {
            "role": "assistant",
            "content": [{"type": "thinking", "thinking": "x"}],
        }
        out = build_assistant_message_with_sanitized_thinking({"message": msg})
        # The dropped thinking adds an omitted-reasoning block
        assert out["content"][0]["text"] == OMITTED_ASSISTANT_REASONING_TEXT

    def test_build_assistant_with_hook(self) -> None:
        set_build_assistant_message_with_sanitized_thinking_hook(
            lambda _p: {"hooked": True}
        )
        assert build_assistant_message_with_sanitized_thinking({}) == {"hooked": True}
