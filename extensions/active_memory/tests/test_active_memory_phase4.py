"""Phase 4.2a active_memory parity tests.

Covers the foundation surface shipped in this commit:

  - Plugin manifest + entry shape
  - ``types`` — constants + default access
  - ``config`` — 25-key normalization, clamping, defaults,
    CLI-runtime timeout bump, deprecated-key detection
  - ``recall_state`` — TTL cache + circuit breaker +
    log helpers
  - ``session_policy`` — eligibility, harness skip,
    chat-type resolution, allow/deny lists, session toggle
    store, admin gating, config mutation, help text
"""

# pyright: reportArgumentType=false
# Tests pass partial dict literals to functions that take
# strict TypedDict unions. The source-level type contract
# is enforced at the plugin boundary, not at the test edge.

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
for _candidate in (
    ROOT / "packages" / "plugin_sdk" / "src",
    ROOT / "apps" / "desktop" / "src",
):
    _candidate_str = str(_candidate)
    if _candidate_str not in sys.path:
        sys.path.insert(0, _candidate_str)


# ── Plugin manifest + entry shape ───────────────────────────────


class TestActiveMemoryManifest:
    def test_manifest_exists(self) -> None:
        path = ROOT / "extensions" / "active_memory" / "openclaw.plugin.json"
        assert path.is_file()

    def test_manifest_id(self) -> None:
        path = ROOT / "extensions" / "active_memory" / "openclaw.plugin.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        assert manifest["id"] == "active_memory"
        assert manifest["kind"] == "memory"
        # JARVIS uses the string activation shape
        # (OpenClaw's dict shape is a Phase 4.4+ improvement).
        assert manifest["activation"] in {"always", "on_startup", "on_demand"}
        # Config schema includes all 25+ keys
        props = set(manifest["configSchema"]["properties"].keys())
        for required in (
            "enabled",
            "agents",
            "model",
            "modelFallback",
            "allowedChatTypes",
            "allowedChatIds",
            "deniedChatIds",
            "thinking",
            "fastMode",
            "timeoutMs",
            "setupGraceTimeoutMs",
            "queryMode",
            "promptStyle",
            "toolsAllow",
            "maxSummaryChars",
            "recentUserTurns",
            "recentAssistantTurns",
            "recentUserChars",
            "recentAssistantChars",
            "logging",
            "cacheTtlMs",
            "circuitBreakerMaxTimeouts",
            "circuitBreakerCooldownMs",
            "persistTranscripts",
            "transcriptDir",
            "qmd",
        ):
            assert required in props, f"missing config key: {required}"


class TestActiveMemoryEntry:
    def test_entry_shape(self) -> None:
        from extensions.active_memory import entry

        assert entry.id == "active_memory"
        assert entry.kind == "memory"
        assert entry.activation == "on_startup"
        assert entry.permissions
        assert entry.version == "0.1.0"


# ── types ─────────────────────────────────────────────────────────


class TestTypes:
    def test_defaults_match_openclaw(self) -> None:
        from extensions.active_memory.types import (
            CACHE_SWEEP_INTERVAL_MS,
            DEFAULT_AGENT_ID,
            DEFAULT_CACHE_TTL_MS,
            DEFAULT_CIRCUIT_BREAKER_COOLDOWN_MS,
            DEFAULT_CIRCUIT_BREAKER_MAX_TIMEOUTS,
            DEFAULT_CLI_RUNTIME_RECALL_TIMEOUT_MS,
            DEFAULT_MAX_CACHE_ENTRIES,
            DEFAULT_MAX_SUMMARY_CHARS,
            DEFAULT_MIN_TIMEOUT_MS,
            DEFAULT_PARTIAL_TRANSCRIPT_MAX_CHARS,
            DEFAULT_QMD_SEARCH_MODE,
            DEFAULT_QUERY_MODE,
            DEFAULT_RECENT_ASSISTANT_CHARS,
            DEFAULT_RECENT_ASSISTANT_TURNS,
            DEFAULT_RECENT_USER_CHARS,
            DEFAULT_RECENT_USER_TURNS,
            DEFAULT_SETUP_GRACE_TIMEOUT_MS,
            DEFAULT_TIMEOUT_MS,
            DEFAULT_TRANSCRIPT_DIR,
            DEFAULT_TRANSCRIPT_READ_MAX_BYTES,
            DEFAULT_TRANSCRIPT_READ_MAX_LINES,
            HOOK_TIMEOUT_RECOVERY_GRACE_MS,
            MAX_ACTIVE_MEMORY_SEARCH_QUERY_CHARS,
            MAX_LOG_VALUE_CHARS,
            MAX_SETUP_GRACE_TIMEOUT_MS,
            MAX_TIMEOUT_MS,
            TERMINAL_MEMORY_SEARCH_POLL_INTERVAL_MS,
            TIMEOUT_PARTIAL_DATA_GRACE_MS,
        )

        assert DEFAULT_TIMEOUT_MS == 15_000
        assert DEFAULT_CLI_RUNTIME_RECALL_TIMEOUT_MS == 45_000
        assert DEFAULT_AGENT_ID == "default"
        assert DEFAULT_MAX_SUMMARY_CHARS == 220
        assert DEFAULT_RECENT_USER_TURNS == 2
        assert DEFAULT_RECENT_ASSISTANT_TURNS == 1
        assert DEFAULT_RECENT_USER_CHARS == 220
        assert DEFAULT_RECENT_ASSISTANT_CHARS == 180
        assert DEFAULT_CACHE_TTL_MS == 15_000
        assert DEFAULT_MAX_CACHE_ENTRIES == 1000
        assert DEFAULT_MIN_TIMEOUT_MS == 250
        assert DEFAULT_SETUP_GRACE_TIMEOUT_MS == 0
        assert MAX_TIMEOUT_MS == 120_000
        assert MAX_SETUP_GRACE_TIMEOUT_MS == 30_000
        assert DEFAULT_QUERY_MODE == "recent"
        assert DEFAULT_QMD_SEARCH_MODE == "search"
        assert DEFAULT_TRANSCRIPT_DIR == "active-memory"
        assert DEFAULT_CIRCUIT_BREAKER_MAX_TIMEOUTS == 3
        assert DEFAULT_CIRCUIT_BREAKER_COOLDOWN_MS == 60_000
        assert DEFAULT_PARTIAL_TRANSCRIPT_MAX_CHARS == 32_000
        assert DEFAULT_TRANSCRIPT_READ_MAX_LINES == 2_000
        assert DEFAULT_TRANSCRIPT_READ_MAX_BYTES == 50 * 1024 * 1024
        assert TIMEOUT_PARTIAL_DATA_GRACE_MS == 500
        assert HOOK_TIMEOUT_RECOVERY_GRACE_MS == 1_500
        assert MAX_ACTIVE_MEMORY_SEARCH_QUERY_CHARS == 480
        assert TERMINAL_MEMORY_SEARCH_POLL_INTERVAL_MS == 25
        assert MAX_LOG_VALUE_CHARS == 300
        assert CACHE_SWEEP_INTERVAL_MS == 1000

    def test_active_memory_reserved_tools_allow(self) -> None:
        from extensions.active_memory.types import ACTIVE_MEMORY_RESERVED_TOOLS_ALLOW

        # Core agent tools are reserved (must not appear in
        # operator's toolsAllow list).
        for tool in (
            "edit",
            "read",
            "write",
            "exec",
            "browser",
            "cron",
            "subagents",
            "*",
        ):
            assert tool in ACTIVE_MEMORY_RESERVED_TOOLS_ALLOW

    def test_no_recall_values(self) -> None:
        from extensions.active_memory.types import NO_RECALL_VALUES

        for token in (
            "",
            "none",
            "no_reply",
            "timeout",
            "[]",
            "{}",
            "null",
        ):
            assert token in NO_RECALL_VALUES

    def test_active_memory_plugin_tag(self) -> None:
        from extensions.active_memory.types import (
            ACTIVE_MEMORY_CLOSE_TAG,
            ACTIVE_MEMORY_DEBUG_PREFIX,
            ACTIVE_MEMORY_OPEN_TAG,
            ACTIVE_MEMORY_PLUGIN_TAG,
            ACTIVE_MEMORY_STATUS_PREFIX,
            ACTIVE_MEMORY_UNTRUSTED_CONTEXT_HEADER,
        )

        assert ACTIVE_MEMORY_PLUGIN_TAG == "active_memory_plugin"
        assert ACTIVE_MEMORY_OPEN_TAG == "<active_memory_plugin>"
        assert ACTIVE_MEMORY_CLOSE_TAG == "</active_memory_plugin>"
        assert "Untrusted context" in ACTIVE_MEMORY_UNTRUSTED_CONTEXT_HEADER
        assert ACTIVE_MEMORY_STATUS_PREFIX.startswith("🧩")
        assert ACTIVE_MEMORY_DEBUG_PREFIX.startswith("🔎")


# ── config ────────────────────────────────────────────────────────


class TestConfig:
    def test_normalize_defaults(self) -> None:
        from extensions.active_memory.config import normalize_plugin_config

        cfg = normalize_plugin_config({})
        assert cfg["enabled"] is True
        assert cfg["agents"] == []
        assert cfg["model"] is None
        assert cfg["modelFallback"] is None
        assert cfg["modelFallbackPolicy"] == "default-remote"
        assert cfg["allowedChatTypes"] == ["direct"]
        assert cfg["allowedChatIds"] == []
        assert cfg["deniedChatIds"] == []
        assert cfg["thinking"] == "off"
        assert cfg["fastMode"] is None
        assert cfg["promptStyle"] == "balanced"
        assert cfg["toolsAllow"] == ["memory_search", "memory_get"]
        assert cfg["promptOverride"] is None
        assert cfg["promptAppend"] is None
        assert cfg["timeoutMs"] == 15_000
        assert cfg["timeoutMsIsDefault"] is True
        assert cfg["setupGraceTimeoutMs"] == 0
        assert cfg["queryMode"] == "recent"
        assert cfg["maxSummaryChars"] == 220
        assert cfg["recentUserTurns"] == 2
        assert cfg["recentAssistantTurns"] == 1
        assert cfg["recentUserChars"] == 220
        assert cfg["recentAssistantChars"] == 180
        assert cfg["logging"] is False
        assert cfg["cacheTtlMs"] == 15_000
        assert cfg["circuitBreakerMaxTimeouts"] == 3
        assert cfg["circuitBreakerCooldownMs"] == 60_000
        assert cfg["persistTranscripts"] is False
        assert cfg["transcriptDir"] == "active-memory"
        assert cfg["qmd"]["searchMode"] == "search"

    def test_lancedb_slot_uses_memory_recall(self) -> None:
        from extensions.active_memory.config import normalize_plugin_config

        cfg = {
            "plugins": {
                "slots": {"memory": "memory-lancedb"},
            }
        }
        normalized = normalize_plugin_config({}, cfg)
        assert normalized["toolsAllow"] == ["memory_recall"]

    def test_timeout_clamped_to_max(self) -> None:
        from extensions.active_memory.config import normalize_plugin_config

        cfg = normalize_plugin_config({"timeoutMs": 1_000_000})
        assert cfg["timeoutMs"] == 120_000

    def test_timeout_clamped_to_min(self) -> None:
        from extensions.active_memory.config import (
            normalize_plugin_config,
            reset_active_memory_config_for_tests,
            set_minimum_timeout_ms_for_tests,
        )

        set_minimum_timeout_ms_for_tests(1000)
        try:
            cfg = normalize_plugin_config({"timeoutMs": 100})
            assert cfg["timeoutMs"] == 1000
        finally:
            reset_active_memory_config_for_tests()

    def test_recent_user_turns_clamped(self) -> None:
        from extensions.active_memory.config import normalize_plugin_config

        cfg = normalize_plugin_config({"recentUserTurns": 100})
        assert cfg["recentUserTurns"] == 4

    def test_recent_assistant_turns_clamped(self) -> None:
        from extensions.active_memory.config import normalize_plugin_config

        cfg = normalize_plugin_config({"recentAssistantTurns": 100})
        assert cfg["recentAssistantTurns"] == 3

    def test_summary_chars_clamped(self) -> None:
        from extensions.active_memory.config import normalize_plugin_config

        cfg = normalize_plugin_config({"maxSummaryChars": 10})
        assert cfg["maxSummaryChars"] == 40
        cfg = normalize_plugin_config({"maxSummaryChars": 100_000})
        assert cfg["maxSummaryChars"] == 1000

    def test_circuit_breaker_clamped(self) -> None:
        from extensions.active_memory.config import normalize_plugin_config

        cfg = normalize_plugin_config(
            {"circuitBreakerMaxTimeouts": 0, "circuitBreakerCooldownMs": 1}
        )
        assert cfg["circuitBreakerMaxTimeouts"] == 1
        assert cfg["circuitBreakerCooldownMs"] == 5000

    def test_prompt_style_inference_from_query_mode(self) -> None:
        from extensions.active_memory.config import normalize_plugin_config

        for query_mode, expected in (
            ("message", "strict"),
            ("full", "contextual"),
            ("recent", "balanced"),
            ("unknown", "balanced"),
        ):
            cfg = normalize_plugin_config({"queryMode": query_mode})
            assert cfg["promptStyle"] == expected, query_mode

    def test_prompt_style_explicit_wins(self) -> None:
        from extensions.active_memory.config import normalize_plugin_config

        cfg = normalize_plugin_config({"queryMode": "message", "promptStyle": "preference-only"})
        assert cfg["promptStyle"] == "preference-only"

    def test_thinking_levels(self) -> None:
        from extensions.active_memory.config import normalize_plugin_config

        for level in (
            "off",
            "minimal",
            "low",
            "medium",
            "high",
            "xhigh",
            "adaptive",
            "max",
        ):
            cfg = normalize_plugin_config({"thinking": level})
            assert cfg["thinking"] == level, level
        cfg = normalize_plugin_config({"thinking": "nonsense"})
        assert cfg["thinking"] == "off"

    def test_fast_mode_normalization(self) -> None:
        from extensions.active_memory.config import normalize_plugin_config

        for value, expected in (
            (True, True),
            (False, False),
            ("auto", "auto"),
            (42, None),
            ("yes", None),
        ):
            cfg = normalize_plugin_config({"fastMode": value})
            assert cfg["fastMode"] == expected, value

    def test_tools_allow_filters_reserved(self) -> None:
        from extensions.active_memory.config import normalize_plugin_config

        cfg = normalize_plugin_config(
            {"toolsAllow": ["memory_search", "edit", "read", "memory_get"]}
        )
        # Reserved entries (edit, read) are filtered out.
        assert cfg["toolsAllow"] == ["memory_search", "memory_get"]

    def test_tools_allow_cap(self) -> None:
        from extensions.active_memory.config import (
            MAX_ACTIVE_MEMORY_TOOLS_ALLOW,
            normalize_plugin_config,
        )

        too_many = [f"tool_{i}" for i in range(MAX_ACTIVE_MEMORY_TOOLS_ALLOW + 50)]
        cfg = normalize_plugin_config({"toolsAllow": too_many})
        assert len(cfg["toolsAllow"]) == MAX_ACTIVE_MEMORY_TOOLS_ALLOW

    def test_chat_id_lists_normalized(self) -> None:
        from extensions.active_memory.config import normalize_plugin_config

        cfg = normalize_plugin_config(
            {
                "allowedChatIds": ["  OC-123  ", "oc-123", "", "OC-456"],
                "deniedChatIds": ["bad-1", "bad-2"],
            }
        )
        assert cfg["allowedChatIds"] == ["oc-123", "oc-456"]
        assert cfg["deniedChatIds"] == ["bad-1", "bad-2"]

    def test_chat_types_filtered(self) -> None:
        from extensions.active_memory.config import normalize_plugin_config

        cfg = normalize_plugin_config({"allowedChatTypes": ["direct", "nonsense", "group"]})
        assert cfg["allowedChatTypes"] == ["direct", "group"]

    def test_enabled_false_disables(self) -> None:
        from extensions.active_memory.config import normalize_plugin_config

        cfg = normalize_plugin_config({"enabled": False})
        assert cfg["enabled"] is False

    def test_apply_cli_runtime_timeout_default_bumps(self) -> None:
        from extensions.active_memory.config import (
            DEFAULT_CLI_RUNTIME_RECALL_TIMEOUT_MS,
            apply_cli_runtime_recall_timeout_default,
            normalize_plugin_config,
        )

        cfg = normalize_plugin_config({})
        bumped = apply_cli_runtime_recall_timeout_default(cfg, True)
        assert bumped["timeoutMs"] == DEFAULT_CLI_RUNTIME_RECALL_TIMEOUT_MS
        # Plain default = no bump when not eligible.
        plain = apply_cli_runtime_recall_timeout_default(cfg, False)
        assert plain["timeoutMs"] == 15_000

    def test_apply_cli_runtime_timeout_default_respects_explicit(self) -> None:
        from extensions.active_memory.config import (
            apply_cli_runtime_recall_timeout_default,
            normalize_plugin_config,
        )

        cfg = normalize_plugin_config({"timeoutMs": 60_000})
        # Operator-configured timeout — no bump even if eligible.
        assert apply_cli_runtime_recall_timeout_default(cfg, True)["timeoutMs"] == 60_000

    def test_has_deprecated_model_fallback_policy(self) -> None:
        from extensions.active_memory.config import (
            has_deprecated_model_fallback_policy,
        )

        assert has_deprecated_model_fallback_policy({}) is False
        assert has_deprecated_model_fallback_policy({"modelFallbackPolicy": "x"}) is True
        assert has_deprecated_model_fallback_policy(None) is False

    def test_resolve_safe_transcript_dir(self) -> None:
        import os
        import tempfile

        from extensions.active_memory.config import resolve_safe_transcript_dir

        with tempfile.TemporaryDirectory() as tmp:
            base = os.path.realpath(tmp)
            # Normal join.
            safe = resolve_safe_transcript_dir(base, "active-memory")
            assert safe == os.path.join(base, "active-memory")
            # Absolute path refused.
            assert resolve_safe_transcript_dir(base, "/etc/passwd") == os.path.join(
                base, "active-memory"
            )
            # Traversal refused.
            assert resolve_safe_transcript_dir(base, "../../etc") == os.path.join(
                base, "active-memory"
            )
            # Drive letter refused (Windows-style with colon).
            assert resolve_safe_transcript_dir(base, "C:\\Windows") == os.path.join(
                base, "active-memory"
            )

    def test_to_safe_transcript_agent_dir_name(self) -> None:
        from extensions.active_memory.config import to_safe_transcript_agent_dir_name

        assert to_safe_transcript_agent_dir_name("default") == "default"
        # Slashes get URL-encoded.
        assert "%2F" in to_safe_transcript_agent_dir_name("a/b")
        # Empty falls back to "unknown-agent".
        assert to_safe_transcript_agent_dir_name("   ") == "unknown-agent"

    def test_resolve_persistent_transcript_base_dir(self) -> None:
        import os
        import tempfile

        from extensions.active_memory.config import (
            resolve_persistent_transcript_base_dir,
        )

        with tempfile.TemporaryDirectory() as tmp:
            base = os.path.realpath(tmp)

            class _FakeApi:
                class _Runtime:
                    class _State:
                        def resolve_state_dir(self) -> str:
                            return base

                    state = _State()

                runtime = _Runtime()

            path = resolve_persistent_transcript_base_dir(_FakeApi(), "agent-1")
            assert path == os.path.join(
                base, "plugins", "active-memory", "transcripts", "agents", "agent-1"
            )

    def test_resolve_persistent_transcript_base_dir_fallback(self) -> None:
        import os

        from extensions.active_memory.config import (
            resolve_persistent_transcript_base_dir,
        )

        class _FakeApi:
            runtime = None  # type: ignore[assignment]

        path = resolve_persistent_transcript_base_dir(_FakeApi(), "agent-1")
        assert "plugins" in path
        assert "active-memory" in path
        assert path.endswith("agent-1")
        # Sanity: absolute path.
        assert os.path.isabs(path)

    def test_is_missing_registered_memory_tools_error(self) -> None:
        from extensions.active_memory.config import (
            is_missing_registered_memory_tools_error,
        )

        msg = (
            "No callable tools remain after resolving explicit tool allowlist ("
            "runtime toolsAllow: memory_search, memory_get); no registered "
            "tools matched. Fix the allowlist or enable the plugin that "
            "registers the requested tool."
        )
        assert is_missing_registered_memory_tools_error(RuntimeError(msg)) is True
        # Mismatched source list — not the same error.
        msg2 = msg.replace("memory_search, memory_get", "memory_recall")
        assert is_missing_registered_memory_tools_error(RuntimeError(msg2)) is False
        # Non-RuntimeError input → False.
        assert is_missing_registered_memory_tools_error("not an error") is False


# ── recall_state ─────────────────────────────────────────────────


class TestRecallState:
    def setup_method(self) -> None:
        from extensions.active_memory import recall_state

        recall_state.reset_active_recall_state_for_tests()

    def test_build_cache_key(self) -> None:
        from extensions.active_memory.recall_state import build_cache_key

        a = build_cache_key({"agentId": "a", "sessionKey": "s1", "query": "hello"})
        b = build_cache_key({"agentId": "a", "sessionKey": "s1", "query": "hello"})
        c = build_cache_key({"agentId": "a", "sessionKey": "s1", "query": "world"})
        d = build_cache_key({"agentId": "a", "sessionId": "id1", "query": "hello"})
        assert a == b
        assert a != c
        assert a != d  # sessionKey vs sessionId differ
        # Same key for the same shape.
        e = build_cache_key({"agentId": "a", "sessionKey": "s1", "query": "hello"})
        assert a == e

    def test_set_and_get_cached_result(self) -> None:
        from extensions.active_memory.recall_state import (
            get_cached_result,
            set_cached_result,
        )

        result: dict[str, object] = {
            "status": "ok",
            "elapsedMs": 100,
            "rawReply": "r",
            "summary": "s",
        }
        set_cached_result("key-a", result, ttl_ms=5_000)  # type: ignore[arg-type]
        cached = get_cached_result("key-a")
        assert cached == result

    def test_expired_cache_returns_none(self) -> None:
        from extensions.active_memory.recall_state import (
            get_cached_result,
            set_cached_result,
        )

        set_cached_result(  # type: ignore[arg-type]
            "key-b", {"status": "ok", "summary": "x"}, ttl_ms=1
        )
        # Sleep past expiry.
        time.sleep(0.05)
        assert get_cached_result("key-b") is None

    def test_should_cache_result(self) -> None:
        from extensions.active_memory.recall_state import should_cache_result

        # pyright: ignore[reportArgumentType] — tests pass partial
        # dict literals; the strict union discriminator is enforced
        # at the source level, not the test boundary.
        assert should_cache_result({"status": "ok", "summary": "x"}) is True  # type: ignore[arg-type]
        assert should_cache_result({"status": "ok", "summary": ""}) is False  # type: ignore[arg-type]
        assert should_cache_result({"status": "empty", "summary": None}) is False  # type: ignore[arg-type]
        assert should_cache_result({"status": "failed", "summary": "x"}) is False  # type: ignore[arg-type]

    def test_build_circuit_breaker_key(self) -> None:
        from extensions.active_memory.recall_state import build_circuit_breaker_key

        a = build_circuit_breaker_key("agent-1", "openai", "gpt-4")
        b = build_circuit_breaker_key("agent-1", "openai", "gpt-4")
        # Both null → "unknown/unknown".
        c = build_circuit_breaker_key("agent-1")
        # Only model null → "<provider>/unknown".
        d = build_circuit_breaker_key("agent-1", "openai", None)
        # Only provider null → "unknown/<model>".
        e = build_circuit_breaker_key("agent-1", None, "gpt-4")
        assert a == b
        assert a != c
        assert c == "agent-1:unknown/unknown"
        assert d == "agent-1:openai/unknown"
        assert e == "agent-1:unknown/gpt-4"

    def test_circuit_breaker_opens_after_max_timeouts(self) -> None:
        from extensions.active_memory.recall_state import (
            build_circuit_breaker_key,
            is_circuit_breaker_open,
            record_circuit_breaker_timeout,
            reset_active_recall_state_for_tests,
            reset_circuit_breaker,
        )

        reset_active_recall_state_for_tests()
        key = build_circuit_breaker_key("agent-1", "openai", "gpt-4")
        # 1st timeout — not yet open.
        record_circuit_breaker_timeout(key)
        assert is_circuit_breaker_open(key, max_timeouts=3, cooldown_ms=60_000) is False
        # 2nd timeout — still not open.
        record_circuit_breaker_timeout(key)
        assert is_circuit_breaker_open(key, max_timeouts=3, cooldown_ms=60_000) is False
        # 3rd timeout — open.
        record_circuit_breaker_timeout(key)
        assert is_circuit_breaker_open(key, max_timeouts=3, cooldown_ms=60_000) is True
        # Reset clears it.
        reset_circuit_breaker(key)
        assert is_circuit_breaker_open(key, max_timeouts=3, cooldown_ms=60_000) is False

    def test_circuit_breaker_cooldown_resets(self) -> None:
        from extensions.active_memory.recall_state import (
            build_circuit_breaker_key,
            is_circuit_breaker_open,
            record_circuit_breaker_timeout,
            reset_active_recall_state_for_tests,
        )

        reset_active_recall_state_for_tests()
        key = build_circuit_breaker_key("agent-1", "openai", "gpt-4")
        for _ in range(3):
            record_circuit_breaker_timeout(key)
        # Cooldown of 0 means "any time has elapsed → reset".
        assert is_circuit_breaker_open(key, max_timeouts=3, cooldown_ms=0) is False
        # Tiny sleep + small cooldown verifies the timed reset.
        time.sleep(0.01)
        assert is_circuit_breaker_open(key, max_timeouts=3, cooldown_ms=5) is False

    def test_to_single_line_log_value(self) -> None:
        from extensions.active_memory.recall_state import to_single_line_log_value

        assert to_single_line_log_value("hello\nworld\t!") == "hello world !"
        assert to_single_line_log_value(None) == ""
        assert to_single_line_log_value(42) == "42"
        assert to_single_line_log_value({"a": 1}) == '{"a": 1}'
        # Long input truncated.
        long = "a" * 500
        out = to_single_line_log_value(long)
        assert len(out) <= 300 + len("...")


# ── session_policy ────────────────────────────────────────────────


class TestSessionPolicy:
    def test_is_eligible_interactive_session_requires_user_trigger(self) -> None:
        from extensions.active_memory.session_policy import is_eligible_interactive_session

        # Needs either sessionKey or sessionId AND a channel id (or webchat).
        assert (
            is_eligible_interactive_session(
                {"trigger": "user", "sessionKey": "agent:main:direct:alice"}
            )
            is False
        )
        assert (
            is_eligible_interactive_session(
                {
                    "trigger": "user",
                    "sessionKey": "agent:main:direct:alice",
                    "channelId": "c1",
                }
            )
            is True
        )
        assert (
            is_eligible_interactive_session(
                {
                    "trigger": "scheduled",
                    "sessionKey": "agent:main:direct:alice",
                    "channelId": "c1",
                }
            )
            is False
        )
        assert (
            is_eligible_interactive_session(
                {
                    "trigger": "user",
                    "sessionKey": "agent:main",
                    "messageProvider": "webchat",
                }
            )
            is True
        )
        assert (
            is_eligible_interactive_session(
                {
                    "trigger": "user",
                    "sessionKey": "agent:main:direct:alice",
                    "messageProvider": "telegram",
                    "channelId": "",
                }
            )
            is False
        )
        # Needs either sessionKey or sessionId.
        assert is_eligible_interactive_session({"trigger": "user"}) is False

    def test_is_eligible_interactive_session_blocks_dreaming(self) -> None:
        from extensions.active_memory.session_policy import is_eligible_interactive_session

        for key in (
            "dreaming-narrative-light-abc",
            "dreaming-narrative-rem-xyz",
            "dreaming-narrative-deep-qwe",
            "agent:main:dreaming-narrative-light-abc",
            "agent:foo:dreaming-narrative-rem-xyz",
        ):
            assert (
                is_eligible_interactive_session(
                    {"trigger": "user", "sessionKey": key, "channelId": "c1"}
                )
                is False
            ), key

    def test_resolve_chat_type_direct(self) -> None:
        from extensions.active_memory.session_policy import resolve_chat_type

        # Bare "agent:<id>:direct:<peer>" shape.
        assert resolve_chat_type({"sessionKey": "agent:main:direct:alice"}) == "direct"
        # "<channel>:direct:<peer>" shape.
        assert resolve_chat_type({"sessionKey": "agent:main:telegram:direct:alice"}) == "direct"

    def test_resolve_chat_type_group(self) -> None:
        from extensions.active_memory.session_policy import resolve_chat_type

        assert resolve_chat_type({"sessionKey": "agent:main:slack:group:room1"}) == "group"

    def test_resolve_chat_type_channel(self) -> None:
        from extensions.active_memory.session_policy import resolve_chat_type

        assert resolve_chat_type({"sessionKey": "agent:main:discord:channel:abc"}) == "channel"

    def test_resolve_chat_type_explicit(self) -> None:
        from extensions.active_memory.session_policy import resolve_chat_type

        assert resolve_chat_type({"sessionKey": "agent:main:explicit"}) == "explicit"

    def test_resolve_chat_type_strips_thread_suffix(self) -> None:
        from extensions.active_memory.session_policy import resolve_chat_type

        assert resolve_chat_type({"sessionKey": "agent:main:direct:alice:thread:t1"}) == "direct"

    def test_resolve_chat_type_webchat(self) -> None:
        from extensions.active_memory.session_policy import resolve_chat_type

        assert (
            resolve_chat_type({"sessionKey": "agent:main", "messageProvider": "webchat"})
            == "direct"
        )

    def test_resolve_chat_type_unknown(self) -> None:
        from extensions.active_memory.session_policy import resolve_chat_type

        assert resolve_chat_type({"sessionKey": "agent:main:weird:shape"}) is None

    def test_is_allowed_chat_type(self) -> None:
        from extensions.active_memory.config import normalize_plugin_config
        from extensions.active_memory.session_policy import is_allowed_chat_type

        cfg = normalize_plugin_config({"allowedChatTypes": ["direct", "explicit"]})
        assert is_allowed_chat_type(cfg, {"sessionKey": "agent:main:direct:alice"}) is True
        assert is_allowed_chat_type(cfg, {"sessionKey": "agent:main:slack:group:room1"}) is False
        assert is_allowed_chat_type(cfg, {"sessionKey": "agent:main:weird:shape"}) is False

    def test_is_private_recall_destination(self) -> None:
        from extensions.active_memory.session_policy import is_private_recall_destination

        assert is_private_recall_destination({"sessionKey": "agent:main:direct:alice"}) is True
        assert is_private_recall_destination({"sessionKey": "agent:main:explicit"}) is True
        assert (
            is_private_recall_destination({"sessionKey": "agent:main:slack:group:room1"}) is False
        )

    def test_is_allowed_chat_id(self) -> None:
        from extensions.active_memory.config import normalize_plugin_config
        from extensions.active_memory.session_policy import is_allowed_chat_id

        # No allow/deny → True.
        cfg = normalize_plugin_config({})
        assert is_allowed_chat_id(cfg, {"sessionKey": "agent:main:direct:alice"}) is True
        # Allowlist only.
        cfg = normalize_plugin_config({"allowedChatIds": ["oc-123"]})
        assert is_allowed_chat_id(cfg, {"sessionKey": "agent:main:direct:oc-123"}) is True
        assert is_allowed_chat_id(cfg, {"sessionKey": "agent:main:direct:oc-456"}) is False
        # Denylist only.
        cfg = normalize_plugin_config({"deniedChatIds": ["oc-bad"]})
        assert is_allowed_chat_id(cfg, {"sessionKey": "agent:main:direct:oc-bad"}) is False
        assert is_allowed_chat_id(cfg, {"sessionKey": "agent:main:direct:oc-123"}) is True

    def test_harness_session_skip(self) -> None:
        from extensions.active_memory.session_policy import (
            should_skip_active_memory_for_harness_session,
        )

        class _FakeApi:
            class _Runtime:
                class _Agent:
                    class _Session:
                        def get_session_entry(self, params: dict) -> None:
                            return None

                    session = _Session()

                agent = _Agent()

            runtime = _Runtime()

        # No session key — return False.
        assert should_skip_active_memory_for_harness_session({"api": _FakeApi()}) is False
        # Harness key + missing session entry → True.
        assert (
            should_skip_active_memory_for_harness_session(
                {"api": _FakeApi(), "sessionKey": "agent:main:harness:test-1"}
            )
            is True
        )
        # Non-harness key + missing session entry → False.
        assert (
            should_skip_active_memory_for_harness_session(
                {"api": _FakeApi(), "sessionKey": "agent:main:direct:alice"}
            )
            is False
        )

    def test_harness_skip_when_get_entry_raises(self) -> None:
        from extensions.active_memory.session_policy import (
            should_skip_active_memory_for_harness_session,
        )

        class _FakeApi:
            class _Runtime:
                class _Agent:
                    class _Session:
                        def get_session_entry(self, params: dict) -> None:
                            raise RuntimeError("host down")

                    session = _Session()

                agent = _Agent()

            runtime = _Runtime()

        # Even non-harness key skipped when host can't read sessions.
        assert (
            should_skip_active_memory_for_harness_session(
                {"api": _FakeApi(), "sessionKey": "agent:main:direct:alice"}
            )
            is True
        )

    def test_harness_skip_model_locked(self) -> None:
        from extensions.active_memory.session_policy import (
            should_skip_active_memory_for_harness_session,
        )

        class _LockedEntry(dict):
            def get(self, key: str, default: object = None) -> object:
                if key == "modelSelectionLocked":
                    return True
                return super().get(key, default)

        class _FakeApi:
            class _Runtime:
                class _Agent:
                    class _Session:
                        def get_session_entry(self, params: dict) -> _LockedEntry:
                            return _LockedEntry()

                    session = _Session()

                agent = _Agent()

            runtime = _Runtime()

        assert (
            should_skip_active_memory_for_harness_session(
                {"api": _FakeApi(), "sessionKey": "agent:main:direct:alice"}
            )
            is True
        )

    def test_is_active_memory_globally_enabled(self) -> None:
        from extensions.active_memory.session_policy import (
            is_active_memory_globally_enabled,
        )

        assert is_active_memory_globally_enabled({}) is True
        assert (
            is_active_memory_globally_enabled(
                {"plugins": {"entries": {"active-memory": {"enabled": True}}}}
            )
            is True
        )
        assert (
            is_active_memory_globally_enabled(
                {"plugins": {"entries": {"active-memory": {"enabled": False}}}}
            )
            is False
        )
        assert (
            is_active_memory_globally_enabled(
                {
                    "plugins": {
                        "entries": {
                            "active-memory": {
                                "enabled": True,
                                "config": {"enabled": False},
                            }
                        }
                    }
                }
            )
            is False
        )

    def test_is_active_memory_plugin_enabled(self) -> None:
        from extensions.active_memory.session_policy import (
            is_active_memory_plugin_enabled,
        )

        # plugins.enabled = False → False.
        assert is_active_memory_plugin_enabled({"plugins": {"enabled": False}}) is False
        # Deny list → False.
        assert (
            is_active_memory_plugin_enabled(
                {
                    "plugins": {
                        "enabled": True,
                        "deny": ["active-memory"],
                    }
                }
            )
            is False
        )
        # Allow list excludes the plugin → False.
        assert (
            is_active_memory_plugin_enabled(
                {
                    "plugins": {
                        "enabled": True,
                        "allow": ["other-plugin"],
                    }
                }
            )
            is False
        )
        # Plugin-level enabled = False → False.
        assert (
            is_active_memory_plugin_enabled(
                {
                    "plugins": {
                        "enabled": True,
                        "entries": {"active-memory": {"enabled": False}},
                    }
                }
            )
            is False
        )
        # Allow list includes the plugin → True.
        assert (
            is_active_memory_plugin_enabled(
                {
                    "plugins": {
                        "enabled": True,
                        "allow": ["active-memory"],
                    }
                }
            )
            is True
        )

    def test_is_enabled_for_agent(self) -> None:
        from extensions.active_memory.config import normalize_plugin_config
        from extensions.active_memory.session_policy import is_enabled_for_agent

        # Empty agents list → all enabled.
        cfg = normalize_plugin_config({})
        assert is_enabled_for_agent(cfg, "main") is True
        assert is_enabled_for_agent(cfg, "anything") is True
        # Pinned agents list.
        cfg = normalize_plugin_config({"agents": ["main", "alt"]})
        assert is_enabled_for_agent(cfg, "main") is True
        assert is_enabled_for_agent(cfg, "alt") is True
        assert is_enabled_for_agent(cfg, "other") is False
        # Missing agentId.
        assert is_enabled_for_agent(cfg, None) is False
        # Disabled.
        cfg = normalize_plugin_config({"enabled": False})
        assert is_enabled_for_agent(cfg, "main") is False

    def test_session_toggle_store_round_trip(self) -> None:
        from extensions.active_memory.session_policy import (
            _in_process_is_disabled,
            _in_process_set_disabled,
            is_session_active_memory_disabled,
            set_session_active_memory_disabled,
        )

        # Direct in-process check.
        _in_process_set_disabled("s1", True)
        assert _in_process_is_disabled("s1") is True
        _in_process_set_disabled("s1", False)
        assert _in_process_is_disabled("s1") is False

        # Async API: in-process fallback (no real api).
        asyncio.run(
            set_session_active_memory_disabled({"api": None, "sessionKey": "s2", "disabled": True})
        )
        assert (
            asyncio.run(is_session_active_memory_disabled({"api": None, "sessionKey": "s2"}))
            is True
        )
        asyncio.run(
            set_session_active_memory_disabled({"api": None, "sessionKey": "s2", "disabled": False})
        )
        assert (
            asyncio.run(is_session_active_memory_disabled({"api": None, "sessionKey": "s2"}))
            is False
        )

    def test_lacks_admin_to_mutate_active_memory_global(self) -> None:
        from extensions.active_memory.session_policy import (
            lacks_admin_to_mutate_active_memory_global,
        )

        # Gateway scope wins.
        assert (
            lacks_admin_to_mutate_active_memory_global({"gatewayClientScopes": ["operator.admin"]})
            is False
        )
        assert (
            lacks_admin_to_mutate_active_memory_global({"gatewayClientScopes": ["operator.read"]})
            is True
        )
        # No scopes → senderIsOwner required.
        assert lacks_admin_to_mutate_active_memory_global({}) is True
        assert lacks_admin_to_mutate_active_memory_global({"senderIsOwner": True}) is False

    def test_update_active_memory_global_enabled_in_config(self) -> None:
        from extensions.active_memory.session_policy import (
            update_active_memory_global_enabled_in_config,
        )

        # Empty config.
        out = update_active_memory_global_enabled_in_config({}, True)
        assert out["plugins"]["entries"]["active-memory"]["enabled"] is True
        assert out["plugins"]["entries"]["active-memory"]["config"]["enabled"] is True
        # Preserve existing entries.
        cfg = {"plugins": {"entries": {"other": {"x": 1}}}}
        out = update_active_memory_global_enabled_in_config(cfg, False)
        assert out["plugins"]["entries"]["other"] == {"x": 1}
        assert out["plugins"]["entries"]["active-memory"]["config"]["enabled"] is False

    def test_format_active_memory_command_help(self) -> None:
        from extensions.active_memory.session_policy import (
            format_active_memory_command_help,
        )

        help_text = format_active_memory_command_help()
        assert "/active-memory status" in help_text
        assert "/active-memory on" in help_text
        assert "/active-memory off" in help_text
        assert "/active-memory on --global" in help_text

    def test_admin_required_text_constant(self) -> None:
        from extensions.active_memory.session_policy import (
            ACTIVE_MEMORY_GLOBAL_MUTATION_ADMIN_REQUIRED_TEXT,
        )

        assert "operator.admin" in ACTIVE_MEMORY_GLOBAL_MUTATION_ADMIN_REQUIRED_TEXT


# ── Plugin entry shape (re-asserted with current config) ──────────


class TestActiveMemoryRegistration:
    def test_register_logs_and_does_not_throw(self) -> None:
        from extensions.active_memory import _register
        from jarvis_sdk import PluginApi, PluginContext

        ctx = PluginContext(
            plugin_id="active_memory",
            plugin_kind="memory",
            data_dir=Path("/tmp/jarvis"),
            workspace=ROOT,
        )
        api = PluginApi(ctx)
        # Should not raise.
        _register(api)
