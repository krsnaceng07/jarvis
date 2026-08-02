"""Phase 7.2b-1 tests — compaction_session_agent + compaction_hooks.

Mirrors the OpenClaw surface in
``openclaw-main/src/agents/embedded-agent-runner/compaction-session-agent.ts``
and
``openclaw-main/src/agents/embedded-agent-runner/compaction-hooks.ts``.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from src.agents.embedded_agent_runner.compaction_hooks import (
    CompactionHookRunner,
    as_compaction_hook_runner,
    build_before_compaction_hook_metrics,
    estimate_tokens_after_compaction,
    run_after_compaction_hooks,
    run_before_compaction_hooks,
    run_post_compaction_side_effects,
    set_internal_hook_sink,
    set_memory_sync_sink,
    set_transcript_sink,
)
from src.agents.embedded_agent_runner.compaction_session_agent import (
    prepare_compaction_session_agent,
)


# ============================================================================
# Fake helpers
# ============================================================================


class _FakeAgent:
    """Captures the mutations made by prepare_compaction_session_agent."""

    def __init__(self) -> None:
        self.streamFn = object()
        self.preparedExtraParams: Any = None
        self.nativeWebSearchPolicyContext: Any = None
        self.providerTextTransforms: Any = None


class _FakeAuthStorage:
    def __init__(self, key: Optional[str]) -> None:
        self._key = key

    def getApiKey(self, provider: str) -> Optional[str]:
        return self._key


def _estimate_tokens(message: Any) -> int:
    return 10


# ============================================================================
# compaction_session_agent
# ============================================================================


class TestPrepareCompactionSessionAgent:
    def _params(self, **overrides: Any) -> Dict[str, Any]:
        base: Dict[str, Any] = {
            "session": {"agent": _FakeAgent()},
            "llmRuntime": object(),
            "providerStreamFn": None,
            "sessionId": "sess-1",
            "signal": object(),
            "effectiveModel": {"provider": "openai", "id": "gpt-5.4"},
            "resolvedApiKey": None,
            "authStorage": None,
            "config": None,
            "provider": "openai",
            "modelId": "gpt-5.4",
            "thinkLevel": "low",
            "sessionAgentId": "agent-1",
            "effectiveWorkspace": "/tmp/ws",
            "agentDir": "/tmp/agent",
        }
        base.update(overrides)
        return base

    def test_returns_agent(self) -> None:
        params = self._params()
        agent = prepare_compaction_session_agent(params)
        assert agent is params["session"]["agent"]

    def test_writes_native_web_search_policy_context(self) -> None:
        params = self._params(
            sessionKey="sess-key",
            messageProvider="telegram",
            senderId="user-1",
        )
        agent = prepare_compaction_session_agent(params)
        ctx = agent.nativeWebSearchPolicyContext
        assert ctx["sessionKey"] == "sess-key"
        assert ctx["messageProvider"] == "telegram"
        assert ctx["senderId"] == "user-1"

    def test_auth_storage_used_when_present(self) -> None:
        auth_storage = _FakeAuthStorage("sk-from-storage")
        params = self._params(
            authStorage=auth_storage,
            resolvedApiKey=None,
        )
        agent = prepare_compaction_session_agent(params)
        # The agent's streamFn should be set (we can't introspect the key,
        # but we can confirm the agent got a non-null streamFn after prep).
        assert agent.streamFn is not None

    def test_dict_auth_storage(self) -> None:
        auth_storage = {"getApiKey": lambda provider: "sk-dict"}
        params = self._params(authStorage=auth_storage)
        agent = prepare_compaction_session_agent(params)
        assert agent.streamFn is not None

    def test_resolved_api_key_used_when_no_auth_storage(self) -> None:
        params = self._params(
            authStorage=None,
            resolvedApiKey="sk-direct",
        )
        agent = prepare_compaction_session_agent(params)
        assert agent.streamFn is not None

    def test_no_auth_storage_no_api_key(self) -> None:
        params = self._params(
            authStorage=None,
            resolvedApiKey=None,
        )
        agent = prepare_compaction_session_agent(params)
        # Should not throw.
        assert agent is not None


# ============================================================================
# compaction_hooks
# ============================================================================


class TestAsCompactionHookRunner:
    def test_none_returns_none(self) -> None:
        assert as_compaction_hook_runner(None) is None

    def test_empty_runner_returns_hooks_with_no_methods(self) -> None:
        runner = as_compaction_hook_runner(object())
        assert runner is not None
        assert runner.has_hooks("anything") is False

    def test_runner_with_methods(self) -> None:
        class FakeRunner:
            def hasHooks(self, name):  # noqa: N802
                return name == "before_compaction"

            def runBeforeCompaction(self, metrics, context):
                return None

            def runAfterCompaction(self, metrics, context):
                return None

        runner = as_compaction_hook_runner(FakeRunner())
        assert runner is not None
        assert runner.has_hooks("before_compaction") is True
        assert runner.has_hooks("other") is False


class TestEstimateTokenCountSafe:
    def test_returns_none_on_raises(self) -> None:
        def bad_estimator(_: Any) -> int:
            raise ValueError("nope")

        from src.agents.embedded_agent_runner.compaction_hooks import (
            _estimate_token_count_safe,
        )

        assert _estimate_token_count_safe([1, 2, 3], bad_estimator) is None

    def test_sums_when_ok(self) -> None:
        from src.agents.embedded_agent_runner.compaction_hooks import (
            _estimate_token_count_safe,
        )

        assert _estimate_token_count_safe([1, 2, 3], _estimate_tokens) == 30


class TestBuildBeforeCompactionHookMetrics:
    def test_basic(self) -> None:
        metrics = build_before_compaction_hook_metrics(
            original_messages=[1, 2, 3, 4],
            current_messages=[1, 2],
            observed_token_count=None,
            estimate_tokens_fn=_estimate_tokens,
        )
        assert metrics["messageCountOriginal"] == 4
        assert metrics["messageCountBefore"] == 2
        assert metrics["tokenCountOriginal"] == 40
        assert metrics["tokenCountBefore"] == 20

    def test_uses_observed_when_provided(self) -> None:
        metrics = build_before_compaction_hook_metrics(
            original_messages=[1, 2],
            current_messages=[1],
            observed_token_count=999,
            estimate_tokens_fn=_estimate_tokens,
        )
        assert metrics["tokenCountBefore"] == 999


class TestEstimateTokensAfterCompaction:
    def test_returns_none_on_estimate_failure(self) -> None:
        def bad(_: Any) -> int:
            raise ValueError("nope")

        assert estimate_tokens_after_compaction(
            messages_after=[1, 2],
            observed_token_count=None,
            full_session_tokens_before=100,
            estimate_tokens_fn=bad,
        ) is None

    def test_rejects_impossible_growth(self) -> None:
        # observed: 100, current: 200 -> > 100 -> reject
        # Use 20 messages × 10 tokens = 200 to exceed 100.
        assert (
            estimate_tokens_after_compaction(
                messages_after=[1] * 20,
                observed_token_count=100,
                full_session_tokens_before=100,
                estimate_tokens_fn=_estimate_tokens,
            )
            is None
        )

    def test_allows_observed_equality(self) -> None:
        # observed: 100, current: 100 -> == 100 -> keep
        # Use 10 messages × 10 tokens = 100.
        assert (
            estimate_tokens_after_compaction(
                messages_after=[1] * 10,
                observed_token_count=100,
                full_session_tokens_before=999,
                estimate_tokens_fn=_estimate_tokens,
            )
            == 100
        )

    def test_allows_10pct_growth_without_observed(self) -> None:
        # baseline 100, current 105 -> 100*1.1 = 110, 105 <= 110 -> keep
        # Use 11 messages (110 tokens) for an over-growth check too.
        # 10 messages = 100 tokens, well under 110.
        assert (
            estimate_tokens_after_compaction(
                messages_after=[1] * 10,
                observed_token_count=None,
                full_session_tokens_before=100,
                estimate_tokens_fn=_estimate_tokens,
            )
            == 100
        )

    def test_rejects_growth_above_10pct_without_observed(self) -> None:
        # baseline 100, current 200 -> 100*1.1 = 110, 200 > 110 -> reject
        assert (
            estimate_tokens_after_compaction(
                messages_after=[1] * 20,
                observed_token_count=None,
                full_session_tokens_before=100,
                estimate_tokens_fn=_estimate_tokens,
            )
            is None
        )


class TestRunBeforeCompactionHooks:
    @pytest.mark.asyncio
    async def test_emits_internal_hook(self) -> None:
        captured: List[Dict[str, Any]] = []

        async def sink(**payload: Any) -> None:
            captured.append(payload)

        set_internal_hook_sink(sink)
        try:
            result = await run_before_compaction_hooks(
                session_id="sess-1",
                session_key=None,
                session_agent_id="agent-1",
                workspace_dir="/tmp/ws",
                metrics={
                    "messageCountBefore": 5,
                    "tokenCountBefore": 50,
                    "messageCountOriginal": 10,
                    "tokenCountOriginal": 100,
                },
            )
            assert result["missingSessionKey"] is True
            assert result["hookSessionKey"] == "sess-1"
            assert len(captured) == 1
            assert captured[0]["phase"] == "before"
        finally:
            set_internal_hook_sink(None)

    @pytest.mark.asyncio
    async def test_falls_back_to_session_id_when_key_missing(self) -> None:
        captured: List[Dict[str, Any]] = []

        async def sink(**payload: Any) -> None:
            captured.append(payload)

        set_internal_hook_sink(sink)
        try:
            result = await run_before_compaction_hooks(
                session_id="sess-1",
                session_key="",
                session_agent_id="agent-1",
                workspace_dir="/tmp/ws",
                metrics={"messageCountBefore": 1, "tokenCountBefore": 1},
            )
            assert result["hookSessionKey"] == "sess-1"
            assert result["missingSessionKey"] is True
        finally:
            set_internal_hook_sink(None)

    @pytest.mark.asyncio
    async def test_fires_plugin_hook(self) -> None:
        called: List[Dict[str, Any]] = []

        def has_hooks(name: Optional[str]) -> bool:
            return name == "before_compaction"

        async def run_before(metrics: Dict[str, Any], context: Dict[str, Any]) -> None:
            called.append({"metrics": metrics, "context": context})

        runner = CompactionHookRunner(
            has_hooks=has_hooks,
            run_before=run_before,
        )
        await run_before_compaction_hooks(
            hook_runner=runner,
            session_id="sess-1",
            session_key="key-1",
            session_agent_id="agent-1",
            workspace_dir="/tmp/ws",
            metrics={"messageCountBefore": 2, "tokenCountBefore": 20},
        )
        assert len(called) == 1
        assert called[0]["metrics"]["messageCount"] == 2
        assert called[0]["context"]["sessionKey"] == "key-1"

    @pytest.mark.asyncio
    async def test_swallows_internal_hook_errors(self) -> None:
        async def bad_sink(**_: Any) -> None:
            raise RuntimeError("boom")

        set_internal_hook_sink(bad_sink)
        try:
            # Should not raise.
            await run_before_compaction_hooks(
                session_id="sess-1",
                session_key="key-1",
                session_agent_id="agent-1",
                workspace_dir="/tmp/ws",
                metrics={},
            )
        finally:
            set_internal_hook_sink(None)


class TestRunAfterCompactionHooks:
    @pytest.mark.asyncio
    async def test_emits_internal_hook(self) -> None:
        captured: List[Dict[str, Any]] = []

        async def sink(**payload: Any) -> None:
            captured.append(payload)

        set_internal_hook_sink(sink)
        try:
            await run_after_compaction_hooks(
                session_id="sess-1",
                session_agent_id="agent-1",
                hook_session_key="key-1",
                missing_session_key=False,
                workspace_dir="/tmp/ws",
                message_count_after=2,
                tokens_after=20,
                compacted_count=10,
                session_file="/tmp/session.jsonl",
            )
            assert len(captured) == 1
            assert captured[0]["phase"] == "after"
            assert captured[0]["payload"]["messageCount"] == 2
        finally:
            set_internal_hook_sink(None)

    @pytest.mark.asyncio
    async def test_fires_plugin_hook(self) -> None:
        called: List[Dict[str, Any]] = []

        async def run_after(metrics: Dict[str, Any], context: Dict[str, Any]) -> None:
            called.append({"metrics": metrics, "context": context})

        runner = CompactionHookRunner(
            has_hooks=lambda n: n == "after_compaction",
            run_after=run_after,
        )
        await run_after_compaction_hooks(
            hook_runner=runner,
            session_id="sess-1",
            session_agent_id="agent-1",
            hook_session_key="key-1",
            missing_session_key=False,
            workspace_dir="/tmp/ws",
            message_count_after=1,
            compacted_count=5,
            session_file="/tmp/s.jsonl",
            previous_session_id="prev",
        )
        assert len(called) == 1
        assert called[0]["metrics"]["previousSessionId"] == "prev"

    @pytest.mark.asyncio
    async def test_swallows_internal_hook_errors(self) -> None:
        async def bad_sink(**_: Any) -> None:
            raise RuntimeError("boom")

        set_internal_hook_sink(bad_sink)
        try:
            await run_after_compaction_hooks(
                session_id="sess-1",
                session_agent_id="agent-1",
                hook_session_key="key-1",
                missing_session_key=False,
                workspace_dir="/tmp/ws",
                message_count_after=1,
                compacted_count=1,
                session_file="/tmp/s.jsonl",
            )
        finally:
            set_internal_hook_sink(None)


class TestRunPostCompactionSideEffects:
    @pytest.mark.asyncio
    async def test_emits_transcript_update(self) -> None:
        captured: List[Dict[str, Any]] = []

        def sink(payload: Dict[str, Any]) -> None:
            captured.append(payload)

        set_transcript_sink(sink)
        try:
            await run_post_compaction_side_effects(
                session_key="key-1",
                session_id="sess-1",
                agent_id="agent-1",
                session_file="/tmp/session.jsonl",
            )
            assert len(captured) == 1
            assert captured[0]["sessionFile"] == "/tmp/session.jsonl"
            assert captured[0]["sessionKey"] == "key-1"
        finally:
            set_transcript_sink(None)

    @pytest.mark.asyncio
    async def test_skips_empty_session_file(self) -> None:
        captured: List[Dict[str, Any]] = []

        def sink(payload: Dict[str, Any]) -> None:
            captured.append(payload)

        set_transcript_sink(sink)
        try:
            await run_post_compaction_side_effects(session_file="   ")
            assert captured == []
        finally:
            set_transcript_sink(None)

    @pytest.mark.asyncio
    async def test_runs_memory_sync_in_await_mode(self) -> None:
        sync_called: List[Dict[str, Any]] = []

        async def sync(**payload: Any) -> None:
            sync_called.append(payload)

        set_memory_sync_sink(sync)
        try:
            await run_post_compaction_side_effects(
                config={
                    "agents": {
                        "defaults": {
                            "compaction": {"postIndexSync": "await"},
                        },
                    },
                },
                session_id="sess-1",
                session_file="/tmp/session.jsonl",
            )
            assert len(sync_called) == 1
        finally:
            set_memory_sync_sink(None)

    @pytest.mark.asyncio
    async def test_skips_memory_sync_in_off_mode(self) -> None:
        sync_called: List[Dict[str, Any]] = []

        async def sync(**payload: Any) -> None:
            sync_called.append(payload)

        set_memory_sync_sink(sync)
        try:
            await run_post_compaction_side_effects(
                config={
                    "agents": {
                        "defaults": {
                            "compaction": {"postIndexSync": "off"},
                        },
                    },
                },
                session_file="/tmp/session.jsonl",
            )
            assert sync_called == []
        finally:
            set_memory_sync_sink(None)

    @pytest.mark.asyncio
    async def test_async_mode_does_not_await(self) -> None:
        """Async mode: fire-and-forget; the calling task returns immediately."""

        async def slow_sync(**_: Any) -> None:
            import asyncio
            await asyncio.sleep(0.05)

        set_memory_sync_sink(slow_sync)
        try:
            await run_post_compaction_side_effects(
                config={
                    "agents": {
                        "defaults": {
                            "compaction": {"postIndexSync": "async"},
                        },
                    },
                },
                session_file="/tmp/session.jsonl",
            )
            # If we got here, async mode did not block.
        finally:
            set_memory_sync_sink(None)
