"""Phase 7.6d-5 tests — 7 attempt-stream/tool-base files (stream-prepare, tool-base-prepare, stream, stream-settle, stream-runtime-prepare, stream-transport, stream-finalize)."""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.agents.embedded_agent_runner.run.attempt_stream_prepare import (
    prepare_embedded_attempt_stream,
    set_prepare_stream_hook,
)
from src.agents.embedded_agent_runner.run.attempt_tool_base_prepare import (
    prepare_embedded_attempt_tool_base,
    set_prepare_tool_base_hook,
)
from src.agents.embedded_agent_runner.run.attempt_stream import (
    install_embedded_attempt_stream_guards,
    set_install_stream_guards_hook,
)
from src.agents.embedded_agent_runner.run.attempt_stream_settle import (
    set_settle_embedded_attempt_stream_hook,
    settle_embedded_attempt_stream,
)
from src.agents.embedded_agent_runner.run.attempt_stream_runtime_prepare import (
    prepare_embedded_attempt_stream_runtime,
    set_prepare_stream_runtime_hook,
)
from src.agents.embedded_agent_runner.run.attempt_stream_transport import (
    prepare_embedded_attempt_transport,
    set_prepare_transport_hook,
)
from src.agents.embedded_agent_runner.run.attempt_stream_finalize import (
    finalize_embedded_attempt_stream_phase,
    set_finalize_attempt_stream_phase_hook,
)


# ============================================================================
# attempt-stream-prepare
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_stream_prepare_hooks() -> None:
    set_prepare_stream_hook(lambda _p: {})
    yield
    set_prepare_stream_hook(lambda _p: {})


class TestPrepareEmbeddedAttemptStream:
    def test_basic(self) -> None:
        result = prepare_embedded_attempt_stream({})
        assert result["stream"] == {}
        assert result["subscription"] is None
        assert result["queueHandle"] is None
        assert result["streamStrategy"] is None

    def test_with_hook(self) -> None:
        set_prepare_stream_hook(
            lambda _p: {
                "stream": {"queueHandle": "qh"},
                "subscription": "sub",
                "streamStrategy": "strat",
            }
        )
        result = prepare_embedded_attempt_stream({})
        assert result["stream"]["queueHandle"] == "qh"
        assert result["subscription"] == "sub"
        assert result["streamStrategy"] == "strat"


# ============================================================================
# attempt-tool-base-prepare
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_tool_base_hooks() -> None:
    set_prepare_tool_base_hook(lambda _p: {})
    yield
    set_prepare_tool_base_hook(lambda _p: {})


class TestPrepareEmbeddedAttemptToolBase:
    def test_basic(self) -> None:
        result = prepare_embedded_attempt_tool_base({})
        assert result["toolBase"] == {}
        assert result["toolSearchTargetTranscriptProjections"] is None

    def test_with_hook(self) -> None:
        set_prepare_tool_base_hook(
            lambda _p: {
                "toolSearchTargetTranscriptProjections": [
                    {"toolName": "read"}
                ]
            }
        )
        result = prepare_embedded_attempt_tool_base({})
        assert result["toolBase"]["toolSearchTargetTranscriptProjections"] == [
            {"toolName": "read"}
        ]


# ============================================================================
# attempt-stream
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_stream_hooks() -> None:
    set_install_stream_guards_hook(lambda _p: {})
    yield
    set_install_stream_guards_hook(lambda _p: {})


class TestInstallEmbeddedAttemptStreamGuards:
    def test_basic(self) -> None:
        result = install_embedded_attempt_stream_guards({})
        assert result["guards"] == {}
        assert result["abortable"] is None

    def test_with_abortable(self) -> None:
        set_install_stream_guards_hook(
            lambda _p: {"abortable": "abort-1"}
        )
        result = install_embedded_attempt_stream_guards({})
        assert result["abortable"] == "abort-1"


# ============================================================================
# attempt-stream-settle
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_stream_settle_hooks() -> None:
    set_settle_embedded_attempt_stream_hook(
        lambda _p: asyncio.sleep(0)
    )
    yield
    set_settle_embedded_attempt_stream_hook(
        lambda _p: asyncio.sleep(0)
    )


class TestSettleEmbeddedAttemptStream:
    def test_basic(self) -> None:
        result = asyncio.run(
            settle_embedded_attempt_stream({})
        )
        assert result["stream"] is None
        assert result["ready"] is True

    def test_with_hook(self) -> None:
        async def _settle(_p: Any) -> Any:
            return {"ready": False, "streamStrategy": "block"}

        set_settle_embedded_attempt_stream_hook(_settle)
        result = asyncio.run(
            settle_embedded_attempt_stream({})
        )
        assert result["ready"] is False
        assert result["streamStrategy"] == "block"


# ============================================================================
# attempt-stream-runtime-prepare
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_stream_runtime_hooks() -> None:
    set_prepare_stream_runtime_hook(lambda _p: asyncio.sleep(0))
    yield
    set_prepare_stream_runtime_hook(lambda _p: asyncio.sleep(0))


class TestPrepareEmbeddedAttemptStreamRuntime:
    def test_basic(self) -> None:
        result = asyncio.run(
            prepare_embedded_attempt_stream_runtime({})
        )
        assert result["stream"] == {}
        assert result["timeout"] == {}
        assert result["history"] == {}
        assert result["isProbeSession"] is False
        assert result["cache"] == {}

    def test_with_hook(self) -> None:
        async def _prepare(_p: Any) -> Any:
            return {
                "stream": {"queueHandle": "qh"},
                "timeout": {"budget": 5000},
                "history": {"messages": []},
                "isProbeSession": True,
                "abortable": "abort-1",
                "cache": {"enabled": True},
            }

        set_prepare_stream_runtime_hook(_prepare)
        result = asyncio.run(
            prepare_embedded_attempt_stream_runtime({})
        )
        assert result["stream"]["queueHandle"] == "qh"
        assert result["timeout"]["budget"] == 5000
        assert result["isProbeSession"] is True
        assert result["abortable"] == "abort-1"
        assert result["cache"]["enabled"] is True


# ============================================================================
# attempt-stream-transport
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_transport_hooks() -> None:
    set_prepare_transport_hook(lambda _p: asyncio.sleep(0))
    yield
    set_prepare_transport_hook(lambda _p: asyncio.sleep(0))


class TestPrepareEmbeddedAttemptTransport:
    def test_basic(self) -> None:
        result = asyncio.run(
            prepare_embedded_attempt_transport({})
        )
        assert result["effectiveAgentTransport"] is None
        assert result["effectiveExtraParams"] == {}
        assert result["streamStrategy"] is None

    def test_with_hook(self) -> None:
        async def _prepare(_p: Any) -> Any:
            return {
                "effectiveAgentTransport": "openai-responses",
                "effectiveExtraParams": {"temperature": 0.5},
                "streamStrategy": "openai-stream",
            }

        set_prepare_transport_hook(_prepare)
        result = asyncio.run(
            prepare_embedded_attempt_transport({})
        )
        assert result["effectiveAgentTransport"] == "openai-responses"
        assert result["effectiveExtraParams"]["temperature"] == 0.5
        assert result["streamStrategy"] == "openai-stream"


# ============================================================================
# attempt-stream-finalize
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_stream_finalize_hooks() -> None:
    set_finalize_attempt_stream_phase_hook(
        lambda _p: asyncio.sleep(0)
    )
    yield
    set_finalize_attempt_stream_phase_hook(
        lambda _p: asyncio.sleep(0)
    )


class TestFinalizeEmbeddedAttemptStreamPhase:
    def test_basic(self) -> None:
        result = asyncio.run(
            finalize_embedded_attempt_stream_phase({})
        )
        assert result["messagesSnapshot"] == []
        assert result["timedOutDuringCompaction"] is False

    def test_with_hook(self) -> None:
        async def _finalize(_p: Any) -> Any:
            return {
                "messagesSnapshot": [{"role": "user", "content": "hi"}],
                "lastAssistant": {"stopReason": "endTurn"},
                "currentAttemptAssistant": {"content": "x"},
                "currentAttemptCompletedAssistant": {"content": "y"},
                "attemptUsage": {"input": 100, "output": 50},
                "cacheBreak": {"code": "x"},
                "promptCache": {"retention": "high"},
                "timedOutDuringCompaction": True,
            }

        set_finalize_attempt_stream_phase_hook(_finalize)
        result = asyncio.run(
            finalize_embedded_attempt_stream_phase({})
        )
        assert len(result["messagesSnapshot"]) == 1
        assert result["lastAssistant"]["stopReason"] == "endTurn"
        assert result["timedOutDuringCompaction"] is True
        assert result["attemptUsage"]["output"] == 50
