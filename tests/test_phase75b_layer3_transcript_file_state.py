"""Phase 7.5b tests — transcript-file-state."""
from __future__ import annotations

from typing import Any, List

import pytest

from src.agents.embedded_agent_runner.transcript_file_state import (
    TranscriptFileState,
    create_transcript_file_state_from_persisted_entries,
    persist_transcript_state_mutation,
    read_transcript_file_state,
    set_read_transcript_file_state_hook,
    set_write_transcript_file_atomic_hook,
    write_transcript_file_atomic,
)


# ============================================================================
# Constructor + getters
# ============================================================================


class TestTranscriptFileStateBasics:
    def test_empty(self) -> None:
        state = TranscriptFileState()
        assert state.get_header() is None
        assert state.get_entries() == []
        assert state.get_leaf_id() is None
        assert state.get_append_parent_id() is None
        assert state.get_append_mode() is None
        assert state.get_cwd() == ""

    def test_header_only(self) -> None:
        state = TranscriptFileState(
            header={"type": "session", "id": "s1", "cwd": "/tmp/ws"}
        )
        assert state.get_cwd() == "/tmp/ws"
        assert state.get_header() == {
            "type": "session",
            "id": "s1",
            "cwd": "/tmp/ws",
        }

    def test_migrated_flag(self) -> None:
        state = TranscriptFileState(migrated=True)
        assert state.migrated is True


# ============================================================================
# Append helpers
# ============================================================================


class TestAppendHelpers:
    def test_append_message(self) -> None:
        state = TranscriptFileState()
        entry = state.append_message({"role": "user", "content": "hi"})
        assert entry["type"] == "message"
        assert entry["message"] == {"role": "user", "content": "hi"}
        # After append, the leaf is the new entry's id.
        assert state.get_leaf_id() == entry["id"]

    def test_append_message_with_parent_id(self) -> None:
        state = TranscriptFileState()
        first = state.append_message({"role": "user", "content": "1"})
        second = state.append_message({"role": "user", "content": "2"}, parent_id=first["id"])
        assert second["parentId"] == first["id"]

    def test_append_compaction(self) -> None:
        state = TranscriptFileState()
        entry = state.append_compaction("summary", "first-kept", 1000)
        assert entry["type"] == "compaction"
        assert entry["summary"] == "summary"
        assert entry["firstKeptEntryId"] == "first-kept"
        assert entry["tokensBefore"] == 1000

    def test_append_thinking_level_change(self) -> None:
        state = TranscriptFileState()
        entry = state.append_thinking_level_change("high")
        assert entry["type"] == "thinking_level_change"
        assert entry["thinkingLevel"] == "high"

    def test_append_model_change(self) -> None:
        state = TranscriptFileState()
        entry = state.append_model_change("openai", "gpt-5.4")
        assert entry["type"] == "model_change"
        assert entry["provider"] == "openai"
        assert entry["modelId"] == "gpt-5.4"

    def test_append_custom_entry(self) -> None:
        state = TranscriptFileState()
        entry = state.append_custom_entry("foo", {"x": 1})
        assert entry["type"] == "custom"
        assert entry["customType"] == "foo"
        assert entry["data"] == {"x": 1}

    def test_append_custom_message_entry(self) -> None:
        state = TranscriptFileState()
        entry = state.append_custom_message_entry("foo", "body", display=False)
        assert entry["type"] == "custom_message"
        assert entry["display"] is False

    def test_append_session_info(self) -> None:
        state = TranscriptFileState()
        entry = state.append_session_info("my session")
        assert entry["type"] == "session_info"
        assert entry["name"] == "my session"

    def test_branch_with_summary(self) -> None:
        state = TranscriptFileState()
        entry = state.branch_with_summary("parent-id", "summary", {"x": 1})
        assert entry["type"] == "branch_summary"
        assert entry["parentId"] == "parent-id"

    def test_append_label_change(self) -> None:
        state = TranscriptFileState()
        entry = state.append_label_change("target-1", "my-label")
        assert entry["type"] == "label"
        assert entry["targetId"] == "target-1"
        assert entry["label"] == "my-label"

    def test_append_leaf_control(self) -> None:
        state = TranscriptFileState()
        state.append_message({"role": "user", "content": "1"})
        entry = state.append_leaf_control(
            target_id="some-id",
            append_parent_id="parent-id",
            append_mode="side",
        )
        assert entry["type"] == "leaf_control"
        assert entry["targetId"] == "some-id"
        assert entry["appendParentId"] == "parent-id"
        assert entry["appendMode"] == "side"


# ============================================================================
# Branch + reset_leaf
# ============================================================================


class TestBranchNavigation:
    def test_get_branch_default(self) -> None:
        state = TranscriptFileState()
        first = state.append_message({"role": "user", "content": "1"})
        second = state.append_message({"role": "assistant", "content": "2"})
        branch = state.get_branch()
        assert len(branch) == 2
        assert branch[0]["id"] == first["id"]
        assert branch[1]["id"] == second["id"]

    def test_get_branch_from_leaf_id(self) -> None:
        state = TranscriptFileState()
        state.append_message({"role": "user", "content": "1"})
        second = state.append_message({"role": "assistant", "content": "2"})
        # Branch ending at the second message.
        branch = state.get_branch(second["id"])
        assert len(branch) == 2
        assert branch[-1]["id"] == second["id"]

    def test_get_branch_from_unknown_leaf_id(self) -> None:
        state = TranscriptFileState()
        state.append_message({"role": "user", "content": "1"})
        branch = state.get_branch("missing")
        assert branch == []

    def test_branch_sets_leaf(self) -> None:
        state = TranscriptFileState()
        state.append_message({"role": "user", "content": "1"})
        second = state.append_message({"role": "assistant", "content": "2"})
        state.branch(second["id"])
        # After branch, the new message appends as a sibling of
        # second (its parentId is second["id"]).
        third = state.append_message({"role": "user", "content": "3"})
        assert third["parentId"] == second["id"]

    def test_branch_to_none(self) -> None:
        state = TranscriptFileState()
        state.append_message({"role": "user", "content": "1"})
        state.branch(None)
        # After branching to None, the leaf is None and the next
        # message has parentId=None.
        entry = state.append_message({"role": "user", "content": "2"})
        assert entry["parentId"] is None

    def test_reset_leaf(self) -> None:
        state = TranscriptFileState()
        state.append_message({"role": "user", "content": "1"})
        state.reset_leaf()
        assert state.get_leaf_id() is None
        assert state.get_append_parent_id() is None


# ============================================================================
# build_session_context
# ============================================================================


class TestBuildSessionContext:
    def test_basic(self) -> None:
        state = TranscriptFileState(
            header={"type": "session", "id": "s1", "cwd": "/tmp/ws"}
        )
        state.append_message({"role": "user", "content": "hi"})
        state.append_label_change("user-msg-id", "my-label")
        ctx = state.build_session_context()
        assert ctx["header"] == state.get_header()
        assert len(ctx["entries"]) == 2
        assert ctx["labelsById"] == {"user-msg-id": "my-label"}


# ============================================================================
# create_transcript_file_state_from_persisted_entries
# ============================================================================


class TestCreateFromPersistedEntries:
    def test_empty(self) -> None:
        state = create_transcript_file_state_from_persisted_entries([])
        assert state.get_header() is None
        assert state.get_entries() == []

    def test_header_and_message(self) -> None:
        entries = [
            {"type": "session", "id": "s1", "cwd": "/tmp"},
            {
                "type": "message",
                "id": "m1",
                "parentId": None,
                "message": {"role": "user", "content": "hi"},
            },
        ]
        state = create_transcript_file_state_from_persisted_entries(entries)
        assert state.get_header() == {
            "type": "session",
            "id": "s1",
            "cwd": "/tmp",
        }
        assert state.get_leaf_id() == "m1"

    def test_skip_non_dict(self) -> None:
        entries: List[Any] = [
            None,
            "string",
            {"type": "message", "id": "m1", "parentId": None, "message": {}},
        ]
        state = create_transcript_file_state_from_persisted_entries(entries)
        assert state.get_leaf_id() == "m1"


# ============================================================================
# File I/O
# ============================================================================


class TestFileIO:
    def setup_method(self) -> None:
        set_read_transcript_file_state_hook(lambda _p: _default_read())
        set_write_transcript_file_atomic_hook(lambda _p, _e: _default_write())

    def teardown_method(self) -> None:
        set_read_transcript_file_state_hook(lambda _p: _default_read())
        set_write_transcript_file_atomic_hook(lambda _p, _e: _default_write())

    @pytest.mark.asyncio
    async def test_read_default(self) -> None:
        state = await read_transcript_file_state("/tmp/s.jsonl")
        assert isinstance(state, TranscriptFileState)
        assert state.get_header() is None

    @pytest.mark.asyncio
    async def test_read_custom_hook(self) -> None:
        async def read(path: str) -> TranscriptFileState:
            assert path == "/tmp/s.jsonl"
            return TranscriptFileState(
                header={"type": "session", "id": "s1", "cwd": "/tmp"}
            )

        set_read_transcript_file_state_hook(read)
        state = await read_transcript_file_state("/tmp/s.jsonl")
        assert state.get_header() == {
            "type": "session",
            "id": "s1",
            "cwd": "/tmp",
        }

    @pytest.mark.asyncio
    async def test_write_atomic_default(self) -> None:
        # Should not raise.
        await write_transcript_file_atomic("/tmp/s.jsonl", [])

    @pytest.mark.asyncio
    async def test_write_atomic_custom_hook(self) -> None:
        called: List[Any] = []

        async def write(path: str, entries: List[Any]) -> None:
            called.append((path, entries))

        set_write_transcript_file_atomic_hook(write)
        await write_transcript_file_atomic("/tmp/s.jsonl", [{"x": 1}])
        assert called == [("/tmp/s.jsonl", [{"x": 1}])]

    @pytest.mark.asyncio
    async def test_persist_state_mutation(self) -> None:
        called: List[Any] = []

        async def write(path: str, entries: List[Any]) -> None:
            called.append((path, entries))

        set_write_transcript_file_atomic_hook(write)
        state = TranscriptFileState(
            header={"type": "session", "id": "s1", "cwd": "/tmp"}
        )
        state.append_message({"role": "user", "content": "hi"})
        appended = list(state.get_entries())
        await persist_transcript_state_mutation(
            session_file="/tmp/s.jsonl",
            state=state,
            appended_entries=appended,
        )
        # First entry is the header; rest are the appended entries.
        assert called[0][0] == "/tmp/s.jsonl"
        assert called[0][1][0]["type"] == "session"
        assert len(called[0][1]) == 1 + len(appended)

    @pytest.mark.asyncio
    async def test_persist_state_mutation_no_header(self) -> None:
        called: List[Any] = []

        async def write(path: str, entries: List[Any]) -> None:
            called.append((path, entries))

        set_write_transcript_file_atomic_hook(write)
        state = TranscriptFileState()
        state.append_message({"role": "user", "content": "hi"})
        appended = list(state.get_entries())
        await persist_transcript_state_mutation(
            session_file="/tmp/s.jsonl",
            state=state,
            appended_entries=appended,
        )
        # No header -> only the appended entries.
        assert called[0][1] == appended


async def _default_read() -> TranscriptFileState:
    return TranscriptFileState()


async def _default_write() -> None:
    return None
