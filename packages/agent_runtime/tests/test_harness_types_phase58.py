"""Tests for ``jarvis_agent.harness_types``.

OpenClaw source: ``packages/agent-core/src/harness/types.ts`` (131 lines).
Upstream has no dedicated test file — the module is types plus two Error
classes — so cases are derived from the source: the Result discriminant
shape, error ``code``/``name``/``cause`` behaviour, entry ``type`` literals,
and the ten-variant union kept in declaration order.
"""

from __future__ import annotations

import dataclasses
import typing

import pytest

from jarvis_agent.harness_types import (
    SESSION_TREE_ENTRY_TYPES,
    BranchSummaryEntry,
    BranchSummaryError,
    BranchSummaryResult,
    CompactionEntry,
    CompactionError,
    CustomEntry,
    CustomMessageEntry,
    Err,
    FileOperations,
    LabelEntry,
    LeafEntry,
    MessageEntry,
    ModelChangeEntry,
    Ok,
    SessionContext,
    SessionInfoEntry,
    SessionModelRef,
    SessionTreeEntry,
    ThinkingLevelChangeEntry,
    err,
    ok,
)


class TestResult:
    def test_ok_discriminant(self) -> None:
        result = ok(42)
        assert result.ok is True
        assert result.value == 42
        assert isinstance(result, Ok)

    def test_err_discriminant(self) -> None:
        error = CompactionError("aborted", "stopped")
        result = err(error)
        assert result.ok is False
        assert result.error is error
        assert isinstance(result, Err)

    def test_err_carries_exception_objects_not_strings(self) -> None:
        # The whole reason this Result exists apart from the plugin-SDK one:
        # the harness returns err(CompactionError(...)) with a live object.
        result = err(BranchSummaryError("invalid_session", "bad"))
        assert isinstance(result.error, BranchSummaryError)

    def test_frozen(self) -> None:
        result = ok(1)
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.value = 2  # type: ignore[misc]


class TestHarnessErrors:
    def test_compaction_error_fields(self) -> None:
        error = CompactionError("summarization_failed", "llm went away")
        assert error.code == "summarization_failed"
        assert error.name == "CompactionError"
        assert str(error) == "llm went away"
        assert error.cause is None
        assert error.__cause__ is None

    def test_compaction_error_cause_chained(self) -> None:
        # TS: super(message, { cause }) — cause both stored and chained.
        inner = ValueError("boom")
        error = CompactionError("unknown", "wrapped", cause=inner)
        assert error.cause is inner
        assert error.__cause__ is inner

    def test_branch_summary_error_fields(self) -> None:
        error = BranchSummaryError("aborted", "user hit stop")
        assert error.code == "aborted"
        assert error.name == "BranchSummaryError"
        assert str(error) == "user hit stop"

    def test_code_sets_differ(self) -> None:
        # CompactionErrorCode has "unknown"; BranchSummaryErrorCode does not.
        from jarvis_agent.harness_types import (
            BranchSummaryErrorCode,
            CompactionErrorCode,
        )

        compaction_codes = set(typing.get_args(CompactionErrorCode))
        branch_codes = set(typing.get_args(BranchSummaryErrorCode))
        assert compaction_codes == {
            "aborted",
            "summarization_failed",
            "invalid_session",
            "unknown",
        }
        assert branch_codes == compaction_codes - {"unknown"}

    def test_errors_are_values_not_control_flow(self) -> None:
        # They must still be raisable (they subclass Exception) even though
        # the harness normally carries them inside Err.
        with pytest.raises(CompactionError):
            raise CompactionError("aborted", "x")


class TestEntryTypeLiterals:
    @pytest.mark.parametrize(
        ("cls", "expected"),
        [
            (MessageEntry, "message"),
            (ThinkingLevelChangeEntry, "thinking_level_change"),
            (ModelChangeEntry, "model_change"),
            (CompactionEntry, "compaction"),
            (BranchSummaryEntry, "branch_summary"),
            (CustomEntry, "custom"),
            (CustomMessageEntry, "custom_message"),
            (LabelEntry, "label"),
            (SessionInfoEntry, "session_info"),
            (LeafEntry, "leaf"),
        ],
    )
    def test_type_discriminant(self, cls: type, expected: str) -> None:
        assert cls().type == expected  # type: ignore[call-arg]

    def test_union_matches_declaration_order(self) -> None:
        # TS SessionTreeEntry union order == SESSION_TREE_ENTRY_TYPES order.
        union_types = [member().type for member in typing.get_args(SessionTreeEntry)]
        assert tuple(union_types) == SESSION_TREE_ENTRY_TYPES

    def test_ten_variants(self) -> None:
        assert len(SESSION_TREE_ENTRY_TYPES) == 10
        assert len(set(SESSION_TREE_ENTRY_TYPES)) == 10


class TestEntryFields:
    def test_base_fields_present_on_every_variant(self) -> None:
        for member in typing.get_args(SessionTreeEntry):
            names = {f.name for f in dataclasses.fields(member)}
            assert {"id", "parent_id", "timestamp", "append_mode"} <= names, member

    def test_compaction_entry_load_bearing_fields(self) -> None:
        entry = CompactionEntry(
            id="c1",
            parent_id="m3",
            timestamp="2026-07-17T00:00:00.000Z",
            summary="sum",
            first_kept_entry_id="m2",
            tokens_before=1234,
        )
        assert entry.first_kept_entry_id == "m2"
        assert entry.tokens_before == 1234
        assert entry.from_hook is None
        assert entry.details is None

    def test_label_none_means_remove_not_absent(self) -> None:
        # TS: label: string | undefined — undefined removes the label.
        entry = LabelEntry(target_id="m1", label=None)
        assert entry.label is None

    def test_leaf_entry_reset_and_override(self) -> None:
        entry = LeafEntry(target_id=None, append_parent_id="m9")
        assert entry.target_id is None
        assert entry.append_parent_id == "m9"

    def test_custom_vs_custom_message_payload_naming(self) -> None:
        # CustomEntry carries `data` (never model-visible); CustomMessageEntry
        # carries `content` (model-visible). The naming *is* the contract.
        data_fields = {f.name for f in dataclasses.fields(CustomEntry)}
        content_fields = {f.name for f in dataclasses.fields(CustomMessageEntry)}
        assert "data" in data_fields
        assert "content" not in data_fields
        assert "content" in content_fields
        assert "data" not in content_fields

    def test_custom_message_display_defaults_true(self) -> None:
        assert CustomMessageEntry().display is True

    def test_entries_frozen(self) -> None:
        entry = MessageEntry(id="m1")
        with pytest.raises(dataclasses.FrozenInstanceError):
            entry.id = "m2"  # type: ignore[misc]


class TestDerivedViews:
    def test_session_context_defaults(self) -> None:
        context = SessionContext()
        assert context.messages == []
        assert context.thinking_level == ""
        assert context.model is None

    def test_session_context_message_lists_are_independent(self) -> None:
        # default_factory, not a shared mutable default.
        assert SessionContext().messages is not SessionContext().messages

    def test_session_model_ref(self) -> None:
        ref = SessionModelRef(provider="anthropic", model_id="claude-opus-4")
        assert ref.provider == "anthropic"
        assert ref.model_id == "claude-opus-4"

    def test_file_operations_are_sets(self) -> None:
        ops = FileOperations()
        assert ops.read == set()
        assert ops.written == set()
        assert ops.edited == set()
        assert isinstance(ops.read, set)
        assert FileOperations().read is not FileOperations().read

    def test_branch_summary_result_are_lists(self) -> None:
        # Persisted and rendered — order matters, so lists not sets.
        result = BranchSummaryResult()
        assert result.summary == ""
        assert result.read_files == []
        assert result.modified_files == []
        assert isinstance(result.read_files, list)
