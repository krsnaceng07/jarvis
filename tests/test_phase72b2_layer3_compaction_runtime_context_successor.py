"""Phase 7.2b-2 tests — compaction_runtime_context + compaction_successor_transcript."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from src.agents.embedded_agent_runner.compaction_runtime_context import (
    build_embedded_compaction_runtime_context,
    resolve_compaction_harness_runtime,
    resolve_embedded_compaction_target,
    resolve_embedded_compaction_thinking_level,
    set_active_process_sessions,
    set_default_provider,
    set_inferred_provider,
    set_model_alias_index,
)
from src.agents.embedded_agent_runner.compaction_successor_transcript import (
    CURRENT_SESSION_VERSION,
    rotate_transcript_after_compaction,
    set_read_transcript_file_state,
    set_write_transcript_atomic,
    should_rotate_compaction_transcript,
)


# ============================================================================
# resolve_embedded_compaction_thinking_level
# ============================================================================


class TestResolveEmbeddedCompactionThinkingLevel:
    def test_uses_compaction_override(self) -> None:
        result = resolve_embedded_compaction_thinking_level(
            config={"agents": {"defaults": {"compaction": {"thinkingLevel": "low"}}}},
            provider="openai",
            model_id="gpt-5.4",
            inherited_level="high",
        )
        assert result == "low"

    def test_ultra_clamped_to_high(self) -> None:
        result = resolve_embedded_compaction_thinking_level(
            config={"agents": {"defaults": {"compaction": {"thinkingLevel": "ultra"}}}},
            provider="openai",
            model_id="gpt-5.4",
        )
        assert result == "high"

    def test_inherits_level(self) -> None:
        assert (
            resolve_embedded_compaction_thinking_level(
                provider="openai", model_id="gpt-5.4", inherited_level="medium"
            )
            == "medium"
        )

    def test_defaults_to_off(self) -> None:
        assert (
            resolve_embedded_compaction_thinking_level(
                provider="openai", model_id="gpt-5.4"
            )
            == "off"
        )


# ============================================================================
# resolve_embedded_compaction_target
# ============================================================================


class TestResolveEmbeddedCompactionTarget:
    def test_no_override(self) -> None:
        result = resolve_embedded_compaction_target(
            provider="openai",
            model_id="gpt-5.4",
            auth_profile_id="openai:p1",
            default_provider="openai",
            default_model="gpt-5.4",
        )
        assert result["provider"] == "openai"
        assert result["model"] == "gpt-5.4"
        assert result["authProfileId"] == "openai:p1"

    def test_model_locked_ignores_override(self) -> None:
        result = resolve_embedded_compaction_target(
            config={"agents": {"defaults": {"compaction": {"model": "anthropic/claude-opus"}}}},
            provider="openai",
            model_id="gpt-5.4",
            auth_profile_id="openai:p1",
            model_selection_locked=True,
        )
        assert result["provider"] == "openai"
        assert result["model"] == "gpt-5.4"
        assert result["authProfileId"] == "openai:p1"

    def test_provider_model_override(self) -> None:
        result = resolve_embedded_compaction_target(
            config={"agents": {"defaults": {"compaction": {"model": "anthropic/claude-opus"}}}},
            provider="ollama",
            model_id="m2.7",
            auth_profile_id="ollama:default",
        )
        assert result["provider"] == "anthropic"
        assert result["model"] == "claude-opus"
        # Auth profile dropped on provider change.
        assert result["authProfileId"] is None

    def test_model_only_override_same_provider(self) -> None:
        result = resolve_embedded_compaction_target(
            config={"agents": {"defaults": {"compaction": {"model": "gpt-4o"}}}},
            provider="openai",
            model_id="gpt-3.5-turbo",
            auth_profile_id="openai:p1",
        )
        assert result["provider"] == "openai"
        assert result["model"] == "gpt-4o"
        assert result["authProfileId"] == "openai:p1"

    def test_bare_configured_model_lookup(self) -> None:
        result = resolve_embedded_compaction_target(
            config={
                "agents": {
                    "defaults": {
                        "models": {"openai/gpt-4o": {}},
                        "compaction": {"model": "gpt-4o"},
                    },
                },
            },
            provider="openai",
            model_id="gpt-3.5-turbo",
            auth_profile_id="openai:p1",
        )
        assert result["model"] == "gpt-4o"

    def test_inferred_provider_override(self) -> None:
        set_inferred_provider("custom-model", "customprov")
        try:
            result = resolve_embedded_compaction_target(
                provider="openai",
                model_id="gpt-5.4",
                auth_profile_id="openai:p1",
                default_provider="openai",
                default_model="gpt-5.4",
            )
            # No override configured so this branch shouldn't fire.
            assert result["provider"] == "openai"
        finally:
            # Reset
            from src.agents.embedded_agent_runner import compaction_runtime_context
            compaction_runtime_context._INFERRED_PROVIDER_REGISTRY.clear()

    def test_alias_resolution(self) -> None:
        set_model_alias_index({"gpt54mini": {"provider": "openai", "model": "gpt-5.4-mini"}})
        try:
            result = resolve_embedded_compaction_target(
                config={
                    "agents": {
                        "defaults": {
                            "compaction": {"model": "gpt54mini"},
                        },
                    },
                },
                provider="openai",
                model_id="gpt-5.5",
                auth_profile_id="openai:default",
                default_provider="openai",
                default_model="gpt-5.5",
            )
            assert result["provider"] == "openai"
            assert result["model"] == "gpt-5.4-mini"
        finally:
            set_model_alias_index({})

    def test_falls_back_to_literal_when_alias_missing(self) -> None:
        result = resolve_embedded_compaction_target(
            config={
                "agents": {
                    "defaults": {
                        "compaction": {"model": "nonexistent-alias"},
                    },
                },
            },
            provider="openai",
            model_id="gpt-5.5",
            auth_profile_id="openai:default",
        )
        assert result["model"] == "nonexistent-alias"


# ============================================================================
# resolve_compaction_harness_runtime
# ============================================================================


class TestResolveCompactionHarnessRuntime:
    def test_bound_takes_precedence(self) -> None:
        result = resolve_compaction_harness_runtime(
            bound_harness_runtime="copilot",
            prepared_runtime_plan=None,
            configured_harness_runtime="custom",
            provider="openai",
            model_id="gpt-5.4",
        )
        assert result == "copilot"

    def test_falls_back_to_prepared_when_matching(self) -> None:
        plan = {
            "resolvedRef": {"harnessId": "codex"},
            "auth": {"providerForAuth": "openai", "modelId": "gpt-5.4"},
        }
        result = resolve_compaction_harness_runtime(
            bound_harness_runtime=None,
            prepared_runtime_plan=plan,
            configured_harness_runtime="custom",
            provider="openai",
            model_id="gpt-5.4",
        )
        assert result == "codex"

    def test_prepared_skipped_when_target_mismatch(self) -> None:
        plan = {
            "resolvedRef": {"harnessId": "codex"},
            "auth": {"providerForAuth": "openai", "modelId": "gpt-5.4"},
        }
        result = resolve_compaction_harness_runtime(
            bound_harness_runtime=None,
            prepared_runtime_plan=plan,
            configured_harness_runtime="custom",
            provider="openai",
            model_id="gpt-5.5",
        )
        assert result == "custom"

    def test_falls_back_to_configured(self) -> None:
        result = resolve_compaction_harness_runtime(
            bound_harness_runtime=None,
            prepared_runtime_plan=None,
            configured_harness_runtime="custom",
            provider="openai",
            model_id="gpt-5.4",
        )
        assert result == "custom"

    def test_returns_none_when_all_unset(self) -> None:
        result = resolve_compaction_harness_runtime(
            bound_harness_runtime=None,
            prepared_runtime_plan=None,
            configured_harness_runtime=None,
            provider="openai",
            model_id="gpt-5.4",
        )
        assert result is None

    def test_normalizes_blank_string(self) -> None:
        result = resolve_compaction_harness_runtime(
            bound_harness_runtime="   ",
            prepared_runtime_plan=None,
            configured_harness_runtime="custom",
            provider="openai",
            model_id="gpt-5.4",
        )
        assert result == "custom"


# ============================================================================
# build_embedded_compaction_runtime_context
# ============================================================================


class TestBuildEmbeddedCompactionRuntimeContext:
    def test_preserves_routing_fields(self) -> None:
        result = build_embedded_compaction_runtime_context(
            session_key="agent:main:thread:1",
            message_channel="slack",
            message_provider="slack",
            chat_type="channel",
            agent_account_id="acct-1",
            current_channel_id="C123",
            current_thread_ts="thread-9",
            current_message_id="msg-42",
            auth_profile_id="openai:p1",
            workspace_dir="/tmp/ws",
            cwd="/tmp/repo",
            agent_dir="/tmp/agent",
            config={},
            sender_is_owner=True,
            sender_id="user-123",
            provider="openai",
            model_id="gpt-5.4",
        )
        assert result["sessionKey"] == "agent:main:thread:1"
        assert result["messageChannel"] == "slack"
        assert result["chatType"] == "channel"
        assert result["workspaceDir"] == "/tmp/ws"
        assert result["senderId"] == "user-123"
        assert result["provider"] == "openai"
        assert result["model"] == "gpt-5.4"

    def test_normalizes_nullables_to_none(self) -> None:
        result = build_embedded_compaction_runtime_context(
            session_key=None,
            message_channel=None,
            workspace_dir="/tmp/ws",
            agent_dir="/tmp/agent",
        )
        assert result["sessionKey"] is None
        assert result["messageChannel"] is None
        assert result["provider"] is None
        assert result["model"] is None

    def test_override_with_provider_model(self) -> None:
        result = build_embedded_compaction_runtime_context(
            workspace_dir="/tmp/ws",
            agent_dir="/tmp/agent",
            config={"agents": {"defaults": {"compaction": {"model": "anthropic/claude-opus"}}}},
            provider="ollama",
            model_id="m2.7",
            auth_profile_id="ollama:default",
        )
        assert result["provider"] == "anthropic"
        assert result["model"] == "claude-opus"
        assert result["authProfileId"] is None

    def test_active_process_sessions_omitted_when_empty(self) -> None:
        result = build_embedded_compaction_runtime_context(
            workspace_dir="/tmp/ws",
            agent_dir="/tmp/agent",
        )
        assert "activeProcessSessions" not in result

    def test_active_process_sessions_passed_through(self) -> None:
        sessions = [{"id": "s1", "command": "sleep"}]
        result = build_embedded_compaction_runtime_context(
            workspace_dir="/tmp/ws",
            agent_dir="/tmp/agent",
            session_key="k",
            active_process_sessions=sessions,
        )
        assert result["activeProcessSessions"] == sessions

    def test_active_process_sessions_via_scope(self) -> None:
        set_active_process_sessions({"k1": [{"id": "s1", "command": "x"}]})
        try:
            result = build_embedded_compaction_runtime_context(
                workspace_dir="/tmp/ws",
                agent_dir="/tmp/agent",
                session_key="k1",
            )
            assert result["activeProcessSessions"] == [{"id": "s1", "command": "x"}]
        finally:
            set_active_process_sessions({})

    def test_active_process_sessions_unscoped_returns_empty(self) -> None:
        set_active_process_sessions({"k1": [{"id": "s1"}]})
        try:
            result = build_embedded_compaction_runtime_context(
                workspace_dir="/tmp/ws",
                agent_dir="/tmp/agent",
            )
            assert "activeProcessSessions" not in result
        finally:
            set_active_process_sessions({})

    def test_runtime_auth_plan_dropped_on_mismatch(self) -> None:
        result = build_embedded_compaction_runtime_context(
            workspace_dir="/tmp/ws",
            agent_dir="/tmp/agent",
            provider="openai",
            model_id="gpt-5.4",
            runtime_auth_plan={
                "providerForAuth": "openai",
                "modelId": "gpt-5.5",  # mismatch
            },
        )
        assert result["runtimeAuthPlan"] is None


# ============================================================================
# should_rotate_compaction_transcript
# ============================================================================


class TestShouldRotateCompactionTranscript:
    def test_false_when_unset(self) -> None:
        assert should_rotate_compaction_transcript({}) is False

    def test_false_when_false(self) -> None:
        assert (
            should_rotate_compaction_transcript(
                {"agents": {"defaults": {"compaction": {"truncateAfterCompaction": False}}}}
            )
            is False
        )

    def test_true_when_set(self) -> None:
        assert (
            should_rotate_compaction_transcript(
                {"agents": {"defaults": {"compaction": {"truncateAfterCompaction": True}}}}
            )
            is True
        )


# ============================================================================
# rotate_transcript_after_compaction
# ============================================================================


class _FakeSessionManager:
    """Minimal session-manager stub for successor transcript tests."""

    def __init__(
        self,
        branch: List[Dict[str, Any]],
        all_entries: List[Dict[str, Any]],
        cwd: str = "/tmp/cwd",
        header: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._branch = branch
        self._entries = all_entries
        self._cwd = cwd
        self._header = header

    def getBranch(self) -> List[Dict[str, Any]]:
        return self._branch

    def get_branch(self) -> List[Dict[str, Any]]:
        return self._branch

    def getEntries(self) -> List[Dict[str, Any]]:
        return self._entries

    def get_entries(self) -> List[Dict[str, Any]]:
        return self._entries

    def getCwd(self) -> str:
        return self._cwd

    def getHeader(self) -> Optional[Dict[str, Any]]:
        return self._header

    def get_header(self) -> Optional[Dict[str, Any]]:
        return self._header


class TestRotateTranscriptAfterCompaction:
    @pytest.mark.asyncio
    async def test_empty_session_file(self) -> None:
        result = await rotate_transcript_after_compaction(
            session_manager=_FakeSessionManager([], []),
            session_file="",
        )
        assert result["rotated"] is False
        assert result["reason"] == "missing session file"

    @pytest.mark.asyncio
    async def test_no_compaction_entry(self) -> None:
        result = await rotate_transcript_after_compaction(
            session_manager=_FakeSessionManager(
                branch=[{"type": "message", "id": "1"}],
                all_entries=[{"type": "message", "id": "1"}],
            ),
            session_file="/tmp/s.jsonl",
        )
        assert result["rotated"] is False
        assert result["reason"] == "no compaction entry"

    @pytest.mark.asyncio
    async def test_writes_successor_file(self) -> None:
        captured: List[Any] = []

        async def write(path: str, contents: List[Dict[str, Any]]) -> None:
            captured.append((path, contents))

        set_write_transcript_atomic(write)
        try:
            sm = _FakeSessionManager(
                branch=[
                    {"type": "message", "id": "u1", "message": {"role": "user"}},
                    {
                        "type": "compaction",
                        "id": "c1",
                        "firstKeptEntryId": "u1",
                    },
                    {"type": "message", "id": "u2", "message": {"role": "user"}},
                ],
                all_entries=[
                    {"type": "message", "id": "u1", "message": {"role": "user"}},
                    {"type": "compaction", "id": "c1", "firstKeptEntryId": "u1"},
                    {"type": "message", "id": "u2", "message": {"role": "user"}},
                ],
                cwd="/tmp/cwd",
            )
            result = await rotate_transcript_after_compaction(
                session_manager=sm,
                session_file="/tmp/2026-01-01_sess.jsonl",
            )
            assert result["rotated"] is True
            assert result["sessionFile"].endswith(".jsonl")
            assert result["compactionEntryId"] == "c1"
            assert len(captured) == 1
            path, contents = captured[0]
            assert path == result["sessionFile"]
            assert contents[0]["type"] == "session"
            assert contents[0]["version"] == CURRENT_SESSION_VERSION
            assert contents[0]["cwd"] == "/tmp/cwd"
            assert contents[0]["parentSession"] == "/tmp/2026-01-01_sess.jsonl"
        finally:
            set_write_transcript_atomic(None)

    @pytest.mark.asyncio
    async def test_empty_successor(self) -> None:
        """When all pre-compaction entries are summarized away, the compaction
        entry itself still survives as the kept entry (so ``rotated=True`` and
        the new file contains the compaction entry)."""
        captured: List[Any] = []

        async def write(path: str, contents: List[Dict[str, Any]]) -> None:
            captured.append((path, contents))

        set_write_transcript_atomic(write)
        try:
            sm = _FakeSessionManager(
                branch=[
                    {"type": "compaction", "id": "c1", "firstKeptEntryId": "c1"},
                ],
                all_entries=[
                    {"type": "compaction", "id": "c1", "firstKeptEntryId": "c1"},
                ],
            )
            result = await rotate_transcript_after_compaction(
                session_manager=sm,
                session_file="/tmp/s.jsonl",
            )
            assert result["rotated"] is True
            assert result["entriesWritten"] >= 1
            # The compaction entry itself is in the kept set.
            kept = captured[0][1]
            assert any(e.get("id") == "c1" for e in kept)
        finally:
            set_write_transcript_atomic(None)
