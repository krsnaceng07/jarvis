"""Phase 7.6e tests — 13 small attempt.* files (user-message-boundary, execution-types, prompt-error, trajectory, prompt-skip, trajectory-flush-cleanup, session-settle, user-transcript-context-registry, abort-settle-timeout, hook-messages, tool-call-block-type, http-runtime, prompt-execution-prepare)."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import pytest

from src.agents.embedded_agent_runner.run.attempt_user_message_boundary import (
    find_active_user_message_index,
    project_persisted_sender_context,
    read_first_user_text,
    resolve_user_transcript_messages,
    set_project_persisted_sender_context_hook,
    set_resolve_user_transcript_messages_hook,
    split_leading_timestamp_envelope,
)
from src.agents.embedded_agent_runner.run.attempt_execution_types import (
    EmbeddedAttemptExecutionPhaseInput,
    EmbeddedAttemptExecutionState,
)
from src.agents.embedded_agent_runner.run.attempt_prompt_error import (
    handle_embedded_attempt_prompt_error,
    set_handle_embedded_attempt_prompt_error_hook,
)
from src.agents.embedded_agent_runner.run.attempt_trajectory import (
    prepare_embedded_attempt_trajectory,
    set_prepare_trajectory_hook,
)
from src.agents.embedded_agent_runner.run.attempt_prompt_skip import (
    resolve_prompt_submission_skip_reason,
    set_resolve_prompt_submission_skip_reason_hook,
)
from src.agents.embedded_agent_runner.run.attempt_trajectory_flush_cleanup import (
    flush_embedded_attempt_trajectory_recorder,
    set_flush_embedded_attempt_trajectory_recorder_hook,
)
from src.agents.embedded_agent_runner.run.attempt_session_settle import (
    create_embedded_attempt_session_settle_tracker,
    set_create_embedded_attempt_session_settle_tracker_hook,
)
from src.agents.embedded_agent_runner.run.attempt_user_transcript_context_registry import (
    create_user_transcript_context_registry,
)
from src.agents.embedded_agent_runner.run.attempt_abort_settle_timeout import (
    DEFAULT_EMBEDDED_ABORT_SETTLE_TIMEOUT_MS,
    resolve_embedded_abort_settle_timeout_ms,
    set_resolve_embedded_abort_settle_timeout_ms_hook,
)
from src.agents.embedded_agent_runner.run.attempt_hook_messages import (
    clone_hook_messages,
)
from src.agents.embedded_agent_runner.run.attempt_tool_call_block_type import (
    is_runner_tool_call_block_type,
)
from src.agents.embedded_agent_runner.run.attempt_http_runtime import (
    DEFAULT_EMBEDDED_ATTEMPT_HTTP_TIMEOUT_MS,
    configure_embedded_attempt_http_runtime,
    set_configure_embedded_attempt_http_runtime_hook,
)
from src.agents.embedded_agent_runner.run.attempt_prompt_execution_prepare import (
    prepare_embedded_attempt_prompt_execution,
    set_prepare_prompt_execution_hook,
)


# ============================================================================
# attempt.user-message-boundary
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_user_message_boundary_hooks() -> None:
    set_project_persisted_sender_context_hook(lambda _p: None)
    set_resolve_user_transcript_messages_hook(lambda _p: [])
    yield
    set_project_persisted_sender_context_hook(lambda _p: None)
    set_resolve_user_transcript_messages_hook(lambda _p: [])


class TestSplitLeadingTimestampEnvelope:
    def test_with_timestamp(self) -> None:
        result = split_leading_timestamp_envelope("[2024-01-01] hello")
        assert result["timestamp"] == "2024-01-01"
        assert result["body"] == "hello"

    def test_without_timestamp(self) -> None:
        result = split_leading_timestamp_envelope("hello")
        assert result["timestamp"] is None
        assert result["body"] == "hello"

    def test_empty(self) -> None:
        result = split_leading_timestamp_envelope("")
        assert result["timestamp"] is None
        assert result["body"] == ""

    def test_non_string(self) -> None:
        result = split_leading_timestamp_envelope(None)  # type: ignore[arg-type]
        assert result["timestamp"] is None
        assert result["body"] == ""


class TestReadFirstUserText:
    def test_string_content(self) -> None:
        assert read_first_user_text("hello") == "hello"

    def test_empty_string(self) -> None:
        assert read_first_user_text("") is None

    def test_list_with_text(self) -> None:
        assert read_first_user_text(
            [{"type": "text", "text": "hello"}]
        ) == "hello"

    def test_list_without_text(self) -> None:
        assert read_first_user_text([{"type": "image"}]) is None

    def test_non_list_non_string(self) -> None:
        assert read_first_user_text(123) is None  # type: ignore[arg-type]

    def test_empty_list(self) -> None:
        assert read_first_user_text([]) is None


class TestResolveUserTranscriptMessages:
    def test_basic(self) -> None:
        assert resolve_user_transcript_messages({}) == []

    def test_with_hook(self) -> None:
        set_resolve_user_transcript_messages_hook(
            lambda _p: [{"role": "user", "content": "hi"}]
        )
        assert resolve_user_transcript_messages({}) == [
            {"role": "user", "content": "hi"}
        ]


class TestProjectPersistedSenderContext:
    def test_basic(self) -> None:
        assert project_persisted_sender_context({}) is None

    def test_with_hook(self) -> None:
        set_project_persisted_sender_context_hook(
            lambda _p: {"senderId": "s1"}
        )
        assert project_persisted_sender_context({}) == {"senderId": "s1"}


class TestFindActiveUserMessageIndex:
    def test_found(self) -> None:
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        assert find_active_user_message_index(messages) == 1

    def test_not_found(self) -> None:
        assert find_active_user_message_index([]) == -1
        assert (
            find_active_user_message_index(
                [{"role": "system"}, {"role": "assistant"}]
            )
            == -1
        )

    def test_first(self) -> None:
        assert (
            find_active_user_message_index([{"role": "user"}]) == 0
        )

    def test_non_list(self) -> None:
        assert find_active_user_message_index("not a list") == -1  # type: ignore[arg-type]


# ============================================================================
# attempt-execution-types
# ============================================================================


class TestAttemptExecutionTypes:
    def test_types(self) -> None:
        state: EmbeddedAttemptExecutionState = {"aborted": True}
        assert state["aborted"] is True
        input_obj: EmbeddedAttemptExecutionPhaseInput = {
            "attempt": {},
            "state": {},
        }
        assert input_obj["state"] == {}


# ============================================================================
# attempt-prompt-error
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_prompt_error_hooks() -> None:
    set_handle_embedded_attempt_prompt_error_hook(
        lambda _p: asyncio.sleep(0)
    )
    yield
    set_handle_embedded_attempt_prompt_error_hook(
        lambda _p: asyncio.sleep(0)
    )


class TestHandleEmbeddedAttemptPromptError:
    def test_basic(self) -> None:
        result = asyncio.run(
            handle_embedded_attempt_prompt_error({})
        )
        assert result["outcome"] == "complete"
        assert result["result"] is None

    def test_with_hook(self) -> None:
        async def _handle(_p: Any) -> Any:
            return {"outcome": "retry", "result": {"x": 1}}

        set_handle_embedded_attempt_prompt_error_hook(_handle)
        result = asyncio.run(
            handle_embedded_attempt_prompt_error({})
        )
        assert result["outcome"] == "retry"
        assert result["result"] == {"x": 1}


# ============================================================================
# attempt-trajectory
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_trajectory_hooks() -> None:
    set_prepare_trajectory_hook(lambda _p: asyncio.sleep(0))
    yield
    set_prepare_trajectory_hook(lambda _p: asyncio.sleep(0))


class TestPrepareEmbeddedAttemptTrajectory:
    def test_basic(self) -> None:
        result = asyncio.run(
            prepare_embedded_attempt_trajectory({})
        )
        assert result["recorder"] is None
        assert result["trajectory"] == {}

    def test_with_hook(self) -> None:
        async def _prepare(_p: Any) -> Any:
            return {
                "recorder": "tr-1",
                "trajectory": {"runs": [{"id": "r1"}]},
            }

        set_prepare_trajectory_hook(_prepare)
        result = asyncio.run(
            prepare_embedded_attempt_trajectory({})
        )
        assert result["recorder"] == "tr-1"
        assert len(result["trajectory"]["runs"]) == 1


# ============================================================================
# attempt-prompt-skip
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_prompt_skip_hooks() -> None:
    set_resolve_prompt_submission_skip_reason_hook(lambda _p: None)
    yield
    set_resolve_prompt_submission_skip_reason_hook(lambda _p: None)


class TestResolvePromptSubmissionSkipReason:
    def test_basic(self) -> None:
        assert resolve_prompt_submission_skip_reason({}) is None

    def test_with_hook(self) -> None:
        set_resolve_prompt_submission_skip_reason_hook(
            lambda _p: {"reason": "duplicate"}
        )
        assert resolve_prompt_submission_skip_reason({}) == {
            "reason": "duplicate"
        }


# ============================================================================
# attempt-trajectory-flush-cleanup
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_trajectory_flush_cleanup_hooks() -> None:
    set_flush_embedded_attempt_trajectory_recorder_hook(
        lambda _p: asyncio.sleep(0)
    )
    yield
    set_flush_embedded_attempt_trajectory_recorder_hook(
        lambda _p: asyncio.sleep(0)
    )


class TestFlushEmbeddedAttemptTrajectoryRecorder:
    def test_basic(self) -> None:
        result = asyncio.run(
            flush_embedded_attempt_trajectory_recorder({})
        )
        assert result["flushed"] is True
        assert result["discarded"] is False

    def test_with_hook(self) -> None:
        async def _flush(_p: Any) -> Any:
            return {"flushed": True, "discarded": True}

        set_flush_embedded_attempt_trajectory_recorder_hook(_flush)
        result = asyncio.run(
            flush_embedded_attempt_trajectory_recorder({})
        )
        assert result["discarded"] is True


# ============================================================================
# attempt-session-settle
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_session_settle_hooks() -> None:
    set_create_embedded_attempt_session_settle_tracker_hook(lambda _p: {})
    yield
    set_create_embedded_attempt_session_settle_tracker_hook(lambda _p: {})


class TestCreateEmbeddedAttemptSessionSettleTracker:
    def test_basic(self) -> None:
        result = create_embedded_attempt_session_settle_tracker({})
        assert result == {}

    def test_with_hook(self) -> None:
        set_create_embedded_attempt_session_settle_tracker_hook(
            lambda _p: {"sessionId": "s1", "settled": False}
        )
        result = create_embedded_attempt_session_settle_tracker({})
        assert result["sessionId"] == "s1"
        assert result["settled"] is False


# ============================================================================
# attempt.user-transcript-context-registry
# ============================================================================


class TestCreateUserTranscriptContextRegistry:
    def test_basic(self) -> None:
        result = create_user_transcript_context_registry()
        assert "by_session" in result
        assert "active_session" in result
        assert result["by_session"] == {}
        assert result["active_session"] is None


# ============================================================================
# attempt.abort-settle-timeout
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_abort_settle_timeout_hooks() -> None:
    set_resolve_embedded_abort_settle_timeout_ms_hook(
        lambda _p: DEFAULT_EMBEDDED_ABORT_SETTLE_TIMEOUT_MS
    )
    yield
    set_resolve_embedded_abort_settle_timeout_ms_hook(
        lambda _p: DEFAULT_EMBEDDED_ABORT_SETTLE_TIMEOUT_MS
    )


class TestResolveEmbeddedAbortSettleTimeoutMs:
    def test_default(self) -> None:
        assert DEFAULT_EMBEDDED_ABORT_SETTLE_TIMEOUT_MS == 5_000
        assert resolve_embedded_abort_settle_timeout_ms() == 5_000

    def test_with_hook(self) -> None:
        set_resolve_embedded_abort_settle_timeout_ms_hook(
            lambda _p: 10_000
        )
        assert resolve_embedded_abort_settle_timeout_ms() == 10_000


# ============================================================================
# attempt-hook-messages
# ============================================================================


class TestCloneHookMessages:
    def test_basic(self) -> None:
        messages = [{"id": 1, "content": "hi"}]
        result = clone_hook_messages(messages)
        assert result == messages
        # Deep clone — mutating original should not affect the clone.
        messages[0]["id"] = 2
        assert result[0]["id"] == 1

    def test_empty(self) -> None:
        assert clone_hook_messages([]) == []

    def test_non_list(self) -> None:
        assert clone_hook_messages("not a list") == []  # type: ignore[arg-type]

    def test_nested_deep_copy(self) -> None:
        messages = [{"content": [{"text": "hello"}]}]
        result = clone_hook_messages(messages)
        messages[0]["content"][0]["text"] = "modified"
        assert result[0]["content"][0]["text"] == "hello"


# ============================================================================
# attempt.tool-call-block-type
# ============================================================================


class TestIsRunnerToolCallBlockType:
    def test_match(self) -> None:
        assert is_runner_tool_call_block_type("toolCall") is True
        assert is_runner_tool_call_block_type("toolUse") is True
        assert is_runner_tool_call_block_type("tool_use") is True
        assert (
            is_runner_tool_call_block_type("assistant_tool_call") is True
        )

    def test_no_match(self) -> None:
        assert is_runner_tool_call_block_type("text") is False
        assert is_runner_tool_call_block_type("image") is False
        assert is_runner_tool_call_block_type("") is False
        assert is_runner_tool_call_block_type(None) is False  # type: ignore[arg-type]
        assert is_runner_tool_call_block_type(123) is False  # type: ignore[arg-type]


# ============================================================================
# attempt-http-runtime
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_http_runtime_hooks() -> None:
    set_configure_embedded_attempt_http_runtime_hook(lambda _p: None)
    yield
    set_configure_embedded_attempt_http_runtime_hook(lambda _p: None)


class TestConfigureEmbeddedAttemptHttpRuntime:
    def test_default(self) -> None:
        captured: List[Dict[str, Any]] = []

        def _hook(p: Dict[str, Any]) -> None:
            captured.append(p)

        set_configure_embedded_attempt_http_runtime_hook(_hook)
        configure_embedded_attempt_http_runtime({})
        assert captured[0]["timeoutMs"] == DEFAULT_EMBEDDED_ATTEMPT_HTTP_TIMEOUT_MS

    def test_custom_timeout(self) -> None:
        captured: List[Dict[str, Any]] = []

        def _hook(p: Dict[str, Any]) -> None:
            captured.append(p)

        set_configure_embedded_attempt_http_runtime_hook(_hook)
        configure_embedded_attempt_http_runtime({"timeoutMs": 30_000})
        assert captured[0]["timeoutMs"] == 30_000

    def test_constant(self) -> None:
        assert DEFAULT_EMBEDDED_ATTEMPT_HTTP_TIMEOUT_MS == 60_000


# ============================================================================
# attempt-prompt-execution-prepare
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_prompt_execution_prepare_hooks() -> None:
    set_prepare_prompt_execution_hook(lambda _p: asyncio.sleep(0))
    yield
    set_prepare_prompt_execution_hook(lambda _p: asyncio.sleep(0))


class TestPrepareEmbeddedAttemptPromptExecution:
    def test_basic(self) -> None:
        result = asyncio.run(
            prepare_embedded_attempt_prompt_execution({})
        )
        assert result["ready"] is True
        assert result["execution"] == {}

    def test_with_hook(self) -> None:
        async def _prepare(_p: Any) -> Any:
            return {"ready": False, "execution": {"phase": "tool"}}

        set_prepare_prompt_execution_hook(_prepare)
        result = asyncio.run(
            prepare_embedded_attempt_prompt_execution({})
        )
        assert result["ready"] is False
        assert result["execution"]["phase"] == "tool"
