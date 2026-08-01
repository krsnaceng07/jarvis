"""Phase 6.12e — agent_session_execution + inspection tests.

Verifies the public surface of:

- :class:`AgentSessionExecution` —
  auto-retry + bash execution.
- :class:`AgentSessionInspection` —
  session management + stats + export
  + last-assistant text.

Also covers the small runtime helpers
(:func:`is_context_overflow`,
:func:`classify_rate_limit_window`,
:func:`is_retryable_assistant_error`,
:func:`sleep`).
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import pytest

from src.agents.sessions.agent_session_execution import AgentSessionExecution
from src.agents.sessions.agent_session_inspection import (
    AgentSessionInspection,
    CURRENT_SESSION_VERSION,
)
from src.agents.sessions.agent_session_types import (
    AgentSessionConfig,
    SessionStats,
)
from src.agents.sessions.runtime_helpers import (
    classify_rate_limit_window,
    is_context_overflow,
    is_retryable_assistant_error,
    sleep,
)


# ============================================================================
# Fakes
# ============================================================================


class _NS:
    def __init__(self, **kw: Any) -> None:
        self.__dict__.update(kw)


class FakeAgent:
    def __init__(self) -> None:
        self.state: Any = _NS(
            model=None,
            messages=[],
            thinkingLevel="medium",
            systemPrompt="",
            steeringMode="one-at-a-time",
            followUpMode="one-at-a-time",
        )


class FakeRegistry:
    def has_configured_auth(self, model: Any) -> bool:
        return True

    def get_available(self) -> list:
        return []


class FakeSettingsManager:
    def __init__(self) -> None:
        self.retry_enabled: bool = True
        self.retry_max: int = 3
        self.retry_base_delay_ms: int = 100

    def get_retry_enabled(self) -> bool:
        return self.retry_enabled

    def get_retry_max_attempts(self) -> int:
        return self.retry_max

    def get_retry_base_delay_ms(self) -> int:
        return self.retry_base_delay_ms

    def get_retry_settings(self) -> dict:
        return {
            "enabled": self.retry_enabled,
            "maxRetries": self.retry_max,
            "baseDelayMs": self.retry_base_delay_ms,
        }

    def set_retry_enabled(self, enabled: bool) -> None:
        self.retry_enabled = enabled

    def set_retry_settings(self, settings: dict) -> None:
        self.retry_enabled = settings.get("enabled", True)
        self.retry_max = settings.get("maxRetries", 3)
        self.retry_base_delay_ms = settings.get("baseDelayMs", 1000)

    def get_default_thinking_level(self) -> str:
        return "medium"

    def get_shell_path(self) -> str | None:
        return None

    def get_shell_command_prefix(self) -> str | None:
        return None


class FakeSessionManager:
    def __init__(self) -> None:
        self.appended: list = []
        self.session_id: str = "sess-1"
        self.session_name: str | None = None
        self.session_file: str | None = "/tmp/sess.jsonl"
        self.cwd: str = "/tmp/proj"
        self.branch: list = []

    def append_message(self, message: Any) -> None:
        self.appended.append(message)

    def append_session_info(self, name: str) -> None:
        self.session_name = name

    def get_session_id(self) -> str:
        return self.session_id

    def get_session_name(self) -> str | None:
        return self.session_name

    def get_session_file(self) -> str | None:
        return self.session_file

    def get_cwd(self) -> str:
        return self.cwd

    def get_branch(self) -> list:
        return list(self.branch)


class FakeExtensionRunner:
    def __init__(self) -> None:
        self.events: list = []

    async def emit(self, event: dict) -> None:
        self.events.append(event)


def _make_model(provider: str = "openai", model_id: str = "gpt-5") -> dict:
    return {"provider": provider, "id": model_id, "reasoning": True}


def _make_execution_session(
    tmp_path: Path | None = None,
    *,
    model: Any = None,
    settings: Any | None = None,
    session_manager: Any | None = None,
) -> AgentSessionExecution:
    import tempfile

    if tmp_path is None:
        tmp_path = Path(tempfile.mkdtemp())
    agent = FakeAgent()
    config = AgentSessionConfig(
        agent=agent,
        session_manager=session_manager or FakeSessionManager(),
        settings_manager=settings or FakeSettingsManager(),
        cwd=str(tmp_path),
        resource_loader=_NS(),  # type: ignore[arg-type]
        model_registry=FakeRegistry(),  # type: ignore[arg-type]
    )
    session = AgentSessionExecution(config)
    session.current_extension_runner = FakeExtensionRunner()
    session.model = model
    return session


def _make_inspection_session(
    tmp_path: Path | None = None,
    *,
    model: Any = None,
    session_manager: Any | None = None,
) -> AgentSessionInspection:
    import tempfile

    if tmp_path is None:
        tmp_path = Path(tempfile.mkdtemp())
    agent = FakeAgent()
    config = AgentSessionConfig(
        agent=agent,
        session_manager=session_manager or FakeSessionManager(),
        settings_manager=FakeSettingsManager(),
        cwd=str(tmp_path),
        resource_loader=_NS(),  # type: ignore[arg-type]
        model_registry=FakeRegistry(),  # type: ignore[arg-type]
    )
    session = AgentSessionInspection(config)
    session.current_extension_runner = FakeExtensionRunner()
    session.model = model
    return session


# ============================================================================
# Runtime helpers
# ============================================================================


class TestIsContextOverflow:
    def test_empty(self) -> None:
        assert is_context_overflow({}, 1000) is False

    def test_context_in_message(self) -> None:
        msg = {"errorMessage": "context length exceeded"}
        assert is_context_overflow(msg, 1000) is True

    def test_no_context_window(self) -> None:
        msg = {"errorMessage": "context length exceeded"}
        # context_window=0 → can't tell.
        assert is_context_overflow(msg, 0) is False

    def test_other_error(self) -> None:
        msg = {"errorMessage": "rate limit exceeded"}
        assert is_context_overflow(msg, 1000) is False


class TestClassifyRateLimitWindow:
    def test_none(self) -> None:
        assert classify_rate_limit_window("")["kind"] == "none"
        assert classify_rate_limit_window("some unrelated error")["kind"] == "none"

    def test_rpm(self) -> None:
        result = classify_rate_limit_window("rate limit: 60 requests per minute")
        assert result["kind"] == "short"
        assert result["retryAfterSeconds"] == 30.0

    def test_quota(self) -> None:
        result = classify_rate_limit_window("monthly quota exceeded")
        assert result["kind"] == "long"


class TestIsRetryableAssistantError:
    def test_not_error(self) -> None:
        assert is_retryable_assistant_error({}) is False

    def test_error_no_message(self) -> None:
        msg = {"stopReason": "error"}
        assert is_retryable_assistant_error(msg) is False

    def test_rate_limit(self) -> None:
        msg = {"stopReason": "error", "errorMessage": "rate limit exceeded"}
        assert is_retryable_assistant_error(msg) is True

    def test_overloaded(self) -> None:
        msg = {"stopReason": "error", "errorMessage": "server overloaded"}
        assert is_retryable_assistant_error(msg) is True


class TestSleep:
    @pytest.mark.asyncio
    async def test_sleep_short(self) -> None:
        # Just check it doesn't raise.
        await sleep(10)

    @pytest.mark.asyncio
    async def test_sleep_zero(self) -> None:
        await sleep(0)

    @pytest.mark.asyncio
    async def test_sleep_aborted(self) -> None:
        signal = _NS(aborted=True)
        with pytest.raises(asyncio.CancelledError):
            await sleep(100, signal)


# ============================================================================
# AgentSessionExecution: is_retryable_error
# ============================================================================


class TestIsRetryableError:
    def test_not_error(self) -> None:
        session = _make_execution_session(model=_make_model())
        assert session.is_retryable_error({"stopReason": "stop"}) is False

    def test_error_no_message(self) -> None:
        session = _make_execution_session(model=_make_model())
        msg = {"stopReason": "error"}
        assert session.is_retryable_error(msg) is False

    def test_error_with_rate_limit(self) -> None:
        session = _make_execution_session(model=_make_model())
        msg = {
            "stopReason": "error",
            "errorMessage": "rate limit exceeded",
        }
        assert session.is_retryable_error(msg) is True

    def test_context_overflow_not_retryable(self) -> None:
        model = _make_model()
        model["contextWindow"] = 1000
        session = _make_execution_session(model=model)
        msg = {
            "stopReason": "error",
            "errorMessage": "context length exceeded",
        }
        assert session.is_retryable_error(msg) is False


# ============================================================================
# AgentSessionExecution: prepare_retry + abort_retry + auto_retry_enabled
# ============================================================================


class TestPrepareRetry:
    @pytest.mark.asyncio
    async def test_disabled(self) -> None:
        settings = FakeSettingsManager()
        settings.retry_enabled = False
        session = _make_execution_session(settings=settings)
        result = await session.prepare_retry({"stopReason": "error"})
        assert result is False

    @pytest.mark.asyncio
    async def test_max_retries_reached(self) -> None:
        settings = FakeSettingsManager()
        settings.retry_max = 2
        session = _make_execution_session(settings=settings)
        session.retry_count = 5
        result = await session.prepare_retry({"stopReason": "error"})
        assert result is False

    @pytest.mark.asyncio
    async def test_scheduled(self) -> None:
        settings = FakeSettingsManager()
        settings.retry_base_delay_ms = 1  # Tiny delay.
        session = _make_execution_session(settings=settings)
        result = await session.prepare_retry(
            {
                "stopReason": "error",
                "errorMessage": "rate limit",
            }
        )
        assert result is True
        assert session.retry_count == 1


class TestAbortRetry:
    def test_abort_idle(self) -> None:
        session = _make_execution_session()
        session.abort_retry()  # no-op
        assert session.is_retrying is False

    def test_abort_in_progress(self) -> None:
        session = _make_execution_session()
        from src.agents.sessions.agent_session_execution import (
            _AbortControllerLike,
        )
        session.retry_abort_controller = _AbortControllerLike()
        session.abort_retry()
        assert session.retry_abort_controller.aborted is True


class TestAutoRetryEnabled:
    def test_enabled(self) -> None:
        session = _make_execution_session()
        assert session.auto_retry_enabled is True

    def test_disabled(self) -> None:
        settings = FakeSettingsManager()
        settings.retry_enabled = False
        session = _make_execution_session(settings=settings)
        assert session.auto_retry_enabled is False


class TestSetAutoRetryEnabled:
    def test_set(self) -> None:
        settings = FakeSettingsManager()
        session = _make_execution_session(settings=settings)
        session.set_auto_retry_enabled(False)
        assert settings.retry_enabled is False


# ============================================================================
# AgentSessionExecution: bash
# ============================================================================


class TestExecuteBash:
    @pytest.mark.asyncio
    async def test_basic(self) -> None:
        sm = FakeSessionManager()
        session = _make_execution_session(session_manager=sm)
        result = await session.execute_bash("echo hello")
        assert result["output"] == ""
        # Recorded in session.
        assert len(sm.appended) == 1
        assert sm.appended[0]["command"] == "echo hello"

    @pytest.mark.asyncio
    async def test_streaming_deferred(self) -> None:
        sm = FakeSessionManager()
        session = _make_execution_session(session_manager=sm)
        session.is_streaming = True
        await session.execute_bash("echo hello")
        # Not in session yet (deferred).
        assert sm.appended == []
        # Queued in pending.
        assert len(session.pending_bash_messages) == 1


class TestRecordBashResult:
    def test_basic(self) -> None:
        sm = FakeSessionManager()
        session = _make_execution_session(session_manager=sm)
        result = {
            "output": "hello",
            "exitCode": 0,
            "cancelled": False,
            "truncated": False,
        }
        session.record_bash_result("echo hi", result)
        assert len(sm.appended) == 1
        assert sm.appended[0]["output"] == "hello"

    def test_streaming_deferred(self) -> None:
        sm = FakeSessionManager()
        session = _make_execution_session(session_manager=sm)
        session.is_streaming = True
        session.record_bash_result(
            "echo hi",
            {
                "output": "x",
                "exitCode": 0,
                "cancelled": False,
                "truncated": False,
            },
        )
        assert sm.appended == []
        assert len(session.pending_bash_messages) == 1

    def test_exclude_from_context(self) -> None:
        sm = FakeSessionManager()
        session = _make_execution_session(session_manager=sm)
        session.record_bash_result(
            "echo hi",
            {
                "output": "x",
                "exitCode": 0,
                "cancelled": False,
                "truncated": False,
            },
            {"excludeFromContext": True},
        )
        assert sm.appended[0]["excludeFromContext"] is True


class TestAbortBash:
    def test_idle(self) -> None:
        session = _make_execution_session()
        session.abort_bash()
        assert session.is_bash_running is False

    def test_in_progress(self) -> None:
        session = _make_execution_session()
        from src.agents.sessions.agent_session_execution import (
            _AbortControllerLike,
        )
        session.bash_abort_controller = _AbortControllerLike()
        session.abort_bash()
        assert session.bash_abort_controller.aborted is True


class TestFlushPendingBashMessages:
    def test_empty(self) -> None:
        session = _make_execution_session()
        session.flush_pending_bash_messages()
        # No-op when empty.

    def test_flush(self) -> None:
        sm = FakeSessionManager()
        session = _make_execution_session(session_manager=sm)
        session.pending_bash_messages = [
            {
                "role": "bashExecution",
                "command": "echo 1",
                "output": "1",
                "exitCode": 0,
                "cancelled": False,
                "truncated": False,
                "timestamp": 0,
            }
        ]
        session.flush_pending_bash_messages()
        assert session.pending_bash_messages == []
        assert len(sm.appended) == 1


# ============================================================================
# AgentSessionInspection
# ============================================================================


class TestSetSessionName:
    def test_set(self) -> None:
        sm = FakeSessionManager()
        session = _make_inspection_session(session_manager=sm)
        events: list = []
        session.subscribe(events.append)
        session.set_session_name("My session")
        assert sm.session_name == "My session"
        info_events = [
            e for e in events
            if e.get("type") == "session_info_changed"
        ]
        assert len(info_events) == 1
        assert info_events[0]["name"] == "My session"


class TestGetSessionStats:
    def test_basic(self) -> None:
        session = _make_inspection_session()
        stats = session.get_session_stats()
        assert isinstance(stats, SessionStats)
        assert stats.user_messages == 0
        assert stats.assistant_messages == 0
        assert stats.tool_calls == 0
        assert stats.total_messages == 0

    def test_with_messages(self) -> None:
        session = _make_inspection_session()
        session.agent.state.messages = [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "hello"},
                    {"type": "toolCall", "name": "x"},
                ],
                "usage": {
                    "input": 100,
                    "output": 50,
                    "cacheRead": 10,
                    "cacheWrite": 5,
                    "cost": {"total": 0.01},
                },
            },
            {"role": "toolResult", "content": "ok"},
        ]
        stats = session.get_session_stats()
        assert stats.user_messages == 1
        assert stats.assistant_messages == 1
        assert stats.tool_calls == 1
        assert stats.tool_results == 1
        assert stats.total_messages == 3
        assert stats.tokens.input_tokens == 100
        assert stats.tokens.output_tokens == 50
        assert stats.tokens.total_tokens == 165
        assert abs(stats.cost - 0.01) < 1e-9


class TestGetContextUsage:
    def test_no_model(self) -> None:
        session = _make_inspection_session()
        assert session.get_context_usage() is None

    def test_model_no_context_window(self) -> None:
        session = _make_inspection_session(model={"provider": "x", "id": "y"})
        assert session.get_context_usage() is None

    def test_with_context_window(self) -> None:
        session = _make_inspection_session(
            model={"provider": "x", "id": "y", "contextWindow": 1000}
        )
        usage = session.get_context_usage()
        assert usage is not None
        assert usage["contextWindow"] == 1000
        # No messages → tokens=0 →
        # percent=0.0 (not None — the
        # context window is known).
        assert usage["percent"] is not None
        assert usage["percent"] == 0.0

    def test_with_messages(self) -> None:
        session = _make_inspection_session(
            model={"provider": "x", "id": "y", "contextWindow": 1000}
        )
        session.agent.state.messages = [
            {"role": "user", "content": "hello world this is a test"},
            {"role": "assistant", "content": "hi"},
        ]
        usage = session.get_context_usage()
        assert usage is not None
        assert usage["percent"] is not None
        assert usage["percent"] > 0


class TestExportToJsonl:
    def test_basic(self, tmp_path: Path) -> None:
        sm = FakeSessionManager()
        sm.branch = [
            {"id": "a", "type": "message", "message": {"role": "user"}},
            {"id": "b", "type": "message", "message": {"role": "assistant"}},
        ]
        session = _make_inspection_session(session_manager=sm)
        output = tmp_path / "out.jsonl"
        path = session.export_to_jsonl(str(output))
        assert path == str(output)
        content = output.read_text(encoding="utf-8")
        lines = content.strip().split("\n")
        # Header + 2 branch entries.
        assert len(lines) == 3
        header = json.loads(lines[0])
        assert header["type"] == "session"
        assert header["version"] == CURRENT_SESSION_VERSION
        # Linear chain (parentId links).
        e1 = json.loads(lines[1])
        e2 = json.loads(lines[2])
        assert e1["parentId"] is None
        assert e2["parentId"] == "a"

    def test_default_path(self) -> None:
        # The default path lives in
        # session.cwd; set the cwd to
        # a tmp dir + check the file is
        # created there.
        with tempfile.TemporaryDirectory() as td:
            sm = FakeSessionManager()
            session = _make_inspection_session(
                tmp_path=Path(td), session_manager=sm
            )
            session.cwd = td
            session.agent.state.messages = []
            path = session.export_to_jsonl()
            assert path.startswith(td)
            assert os.path.isfile(path)


class TestGetLastAssistantText:
    def test_no_assistant(self) -> None:
        session = _make_inspection_session()
        assert session.get_last_assistant_text() is None

    def test_text_content(self) -> None:
        session = _make_inspection_session()
        session.agent.state.messages = [
            {
                "role": "assistant",
                "stopReason": "stop",
                "content": [
                    {"type": "text", "text": "Hello there"},
                ],
            }
        ]
        assert session.get_last_assistant_text() == "Hello there"

    def test_skips_aborted(self) -> None:
        session = _make_inspection_session()
        session.agent.state.messages = [
            {
                "role": "assistant",
                "stopReason": "aborted",
                "content": [],
            },
            {
                "role": "assistant",
                "stopReason": "stop",
                "content": [
                    {"type": "text", "text": "World"},
                ],
            },
        ]
        assert session.get_last_assistant_text() == "World"

    def test_string_content(self) -> None:
        session = _make_inspection_session()
        session.agent.state.messages = [
            {
                "role": "assistant",
                "stopReason": "stop",
                "content": "Just a string",
            }
        ]
        assert session.get_last_assistant_text() == "Just a string"


# ============================================================================
# Constructor / inheritance
# ============================================================================


class TestConstructor:
    def test_inherits_models(self, tmp_path: Path) -> None:
        session = _make_execution_session(tmp_path)
        from src.agents.sessions.agent_session_models import AgentSessionModels
        assert isinstance(session, AgentSessionModels)

    def test_inspection_inherits_models(self, tmp_path: Path) -> None:
        session = _make_inspection_session(tmp_path)
        from src.agents.sessions.agent_session_models import AgentSessionModels
        assert isinstance(session, AgentSessionModels)
