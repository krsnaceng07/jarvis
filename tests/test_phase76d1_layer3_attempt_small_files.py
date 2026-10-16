"""Phase 7.6d-1 tests — small attempt.* files (tool-allowlist + tool-run-context + transcript-policy + bootstrap-context + context-summary)."""
from __future__ import annotations


import pytest

from src.agents.embedded_agent_runner.run.attempt_tool_allowlist import (
    collect_attempt_explicit_tool_allowlist_sources,
    set_collect_explicit_tool_allowlist_sources_hook,
)
from src.agents.embedded_agent_runner.run.attempt_tool_run_context import (
    build_embedded_attempt_tool_run_context,
    set_build_embedded_attempt_tool_run_context_hook,
)
from src.agents.embedded_agent_runner.run.attempt_transcript_policy import (
    resolve_attempt_transcript_policy,
    set_as_provider_runtime_model_hook,
)
from src.agents.embedded_agent_runner.run.attempt_bootstrap_context import (
    remap_injected_context_files_to_workspace,
    set_is_relative_path_inside_or_equal_hook,
)
from src.agents.embedded_agent_runner.run.attempt_context_summary import (
    MAX_BTW_SNAPSHOT_MESSAGES,
    snapshot_recent_messages,
    summarize_session_context,
)


# ============================================================================
# attempt-tool-allowlist
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_tool_allowlist_hook() -> None:
    set_collect_explicit_tool_allowlist_sources_hook(
        lambda _s: {"sources": ["collected"]}
    )
    yield
    set_collect_explicit_tool_allowlist_sources_hook(
        lambda _s: {"sources": []}
    )


class TestCollectAttemptExplicitToolAllowlistSources:
    def test_with_agent_id(self) -> None:
        result = collect_attempt_explicit_tool_allowlist_sources(
            {
                "capabilityProfile": {
                    "agentId": "a1",
                    "policy": {
                        "globalPolicy": {"allow": ["read"]},
                        "agentPolicy": {"allow": ["write"]},
                    },
                },
                "toolsAllow": ["bash"],
            }
        )
        # Just check the result shape is passed through.
        assert "sources" in result
        assert result["sources"] == ["collected"]

    def test_without_agent_id(self) -> None:
        result = collect_attempt_explicit_tool_allowlist_sources(
            {
                "capabilityProfile": {
                    "policy": {
                        "globalPolicy": {"allow": ["read"]},
                    },
                },
            }
        )
        assert "sources" in result

    def test_empty_policy(self) -> None:
        result = collect_attempt_explicit_tool_allowlist_sources(
            {"capabilityProfile": {"policy": {}}}
        )
        assert "sources" in result


# ============================================================================
# attempt-tool-run-context
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_tool_run_context_hook() -> None:
    set_build_embedded_attempt_tool_run_context_hook(lambda _p: None)
    yield
    set_build_embedded_attempt_tool_run_context_hook(lambda _p: None)


class TestBuildEmbeddedAttemptToolRunContext:
    def test_basic(self) -> None:
        result = build_embedded_attempt_tool_run_context(
            {
                "attempt": {"runId": "r1"},
                "agentSession": {"sessionId": "s1"},
                "tools": [{"name": "read"}],
            }
        )
        assert result["attempt"]["runId"] == "r1"
        assert result["tools"] == [{"name": "read"}]
        assert result["toolContext"] is None

    def test_hook_override(self) -> None:
        set_build_embedded_attempt_tool_run_context_hook(
            lambda _p: {"wrapped": True}
        )
        result = build_embedded_attempt_tool_run_context({"tools": []})
        assert result["toolContext"] == {"wrapped": True}


# ============================================================================
# attempt-transcript-policy
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_transcript_policy_hook() -> None:
    set_as_provider_runtime_model_hook(lambda _m: _m)
    yield
    set_as_provider_runtime_model_hook(lambda _m: _m)


class TestResolveAttemptTranscriptPolicy:
    def test_basic(self) -> None:
        result = resolve_attempt_transcript_policy(
            {
                "runtimeModel": {"id": "m1"},
                "transcriptRetention": "keep",
                "extraParams": {"a": 1},
            }
        )
        assert result["runtimeModel"] == {"id": "m1"}
        assert result["transcriptRetention"] == "keep"
        assert result["extraParams"] == {"a": 1}

    def test_no_runtime_model(self) -> None:
        result = resolve_attempt_transcript_policy({})
        assert result["runtimeModel"] is None
        assert result["extraParams"] == {}

    def test_hook_override(self) -> None:
        set_as_provider_runtime_model_hook(
            lambda _m: {"wrapped": True}
        )
        result = resolve_attempt_transcript_policy(
            {"runtimeModel": {"id": "m1"}}
        )
        assert result["runtimeModel"] == {"wrapped": True}


# ============================================================================
# attempt-bootstrap-context
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_bootstrap_context_hook() -> None:
    set_is_relative_path_inside_or_equal_hook(_default_is_relative)
    yield
    set_is_relative_path_inside_or_equal_hook(_default_is_relative)


def _default_is_relative(p: str) -> bool:
    import os
    if not isinstance(p, str) or not p:
        return False
    if p.startswith("/") or p.startswith("\\"):
        return False
    if os.path.splitdrive(p)[0]:
        return False
    return True


class TestRemapInjectedContextFilesToWorkspace:
    def test_relative_path(self) -> None:
        result = remap_injected_context_files_to_workspace(
            {
                "workspaceDir": "/tmp/ws",
                "files": [
                    {"path": "foo/bar.txt", "contents": "x"},
                ],
            }
        )
        assert result[0]["path"].endswith("foo/bar.txt") or result[0]["path"] == "/tmp/ws/foo/bar.txt"

    def test_absolute_path_basename(self) -> None:
        result = remap_injected_context_files_to_workspace(
            {
                "workspaceDir": "/tmp/ws",
                "files": [
                    {"path": "/etc/passwd", "contents": "x"},
                ],
            }
        )
        assert result[0]["path"] == "/tmp/ws/passwd"

    def test_empty_files(self) -> None:
        result = remap_injected_context_files_to_workspace(
            {"workspaceDir": "/tmp/ws", "files": []}
        )
        assert result == []

    def test_non_list_files(self) -> None:
        result = remap_injected_context_files_to_workspace(
            {"workspaceDir": "/tmp/ws", "files": "not-a-list"}
        )
        assert result == []

    def test_custom_hook(self) -> None:
        # Custom hook: only relative paths with `safe/` are "inside"
        set_is_relative_path_inside_or_equal_hook(
            lambda p: p.startswith("safe/")
        )
        result = remap_injected_context_files_to_workspace(
            {
                "workspaceDir": "/tmp/ws",
                "files": [
                    {"path": "safe/file.txt"},
                    {"path": "other/file.txt"},
                ],
            }
        )
        # safe/file.txt is kept as relative, other/file.txt basename-mapped
        assert len(result) == 2


# ============================================================================
# attempt-context-summary
# ============================================================================


class TestAttemptContextSummaryConstants:
    def test_max(self) -> None:
        assert MAX_BTW_SNAPSHOT_MESSAGES == 100


class TestSummarizeSessionContext:
    def test_empty(self) -> None:
        result = summarize_session_context([])
        assert result["roleCounts"] == "none"
        assert result["totalTextChars"] == 0
        assert result["totalImageBlocks"] == 0

    def test_string_content(self) -> None:
        result = summarize_session_context(
            [{"role": "user", "content": "hello world"}]
        )
        assert result["totalTextChars"] == 11
        assert result["roleCounts"] == "user:1"

    def test_list_content(self) -> None:
        result = summarize_session_context(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "hello"},
                        {"type": "image", "src": "x"},
                    ],
                }
            ]
        )
        assert result["totalTextChars"] == 5
        assert result["totalImageBlocks"] == 1

    def test_mixed_roles(self) -> None:
        result = summarize_session_context(
            [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hello"},
                {"role": "user", "content": "how are you?"},
            ]
        )
        assert "user:2" in result["roleCounts"]
        assert "assistant:1" in result["roleCounts"]

    def test_max_message_text_chars(self) -> None:
        result = summarize_session_context(
            [
                {"role": "user", "content": "short"},
                {"role": "assistant", "content": "this is a longer message"},
            ]
        )
        # "this is a longer message" is 24 chars
        assert result["maxMessageTextChars"] == 24

    def test_non_list_input(self) -> None:
        result = summarize_session_context("not a list")  # type: ignore[arg-type]
        assert result["roleCounts"] == "none"


class TestSnapshotRecentMessages:
    def test_under_cap(self) -> None:
        msgs = [{"id": str(i)} for i in range(10)]
        result = snapshot_recent_messages(msgs)
        assert len(result) == 10
        assert result[0]["id"] == "0"

    def test_at_cap(self) -> None:
        msgs = [{"id": str(i)} for i in range(MAX_BTW_SNAPSHOT_MESSAGES)]
        result = snapshot_recent_messages(msgs)
        assert len(result) == MAX_BTW_SNAPSHOT_MESSAGES

    def test_over_cap(self) -> None:
        msgs = [{"id": str(i)} for i in range(MAX_BTW_SNAPSHOT_MESSAGES + 10)]
        result = snapshot_recent_messages(msgs)
        assert len(result) == MAX_BTW_SNAPSHOT_MESSAGES
        # Last message is the most recent.
        assert result[-1]["id"] == str(MAX_BTW_SNAPSHOT_MESSAGES + 9)

    def test_empty(self) -> None:
        assert snapshot_recent_messages([]) == []

    def test_non_list(self) -> None:
        assert snapshot_recent_messages("not a list") == []  # type: ignore[arg-type]


# ============================================================================
# Hook setters
# ============================================================================


class TestHookSetters:
    def test_set_tool_allowlist_hook(self) -> None:
        set_collect_explicit_tool_allowlist_sources_hook(
            lambda _s: {"sources": []}
        )

    def test_set_tool_run_context_hook(self) -> None:
        set_build_embedded_attempt_tool_run_context_hook(lambda _p: None)

    def test_set_transcript_policy_hook(self) -> None:
        set_as_provider_runtime_model_hook(lambda _m: _m)

    def test_set_bootstrap_context_hook(self) -> None:
        set_is_relative_path_inside_or_equal_hook(_default_is_relative)
