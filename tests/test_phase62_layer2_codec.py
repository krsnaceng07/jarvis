"""Phase 6.2 — Layer 2 session codec.

These tests prove the Phase-6.2 session-codec
modules in ``src/agents/sessions/`` match the
OpenClaw source contract for:

- ``session_manager_id`` — ``create_session_id``
  (UUID v7), ``generate_session_entry_id``
  (8-char collision-free prefix + UUID fallback)
- ``session_manager_types`` — every entry dataclass
  + the discriminated union
- ``session_manager_codec`` —
  - ``migrateToCurrentVersion`` (v1 → v2 → v3)
  - ``parseSessionEntries`` / ``parseJsonlEntries``
    (skips malformed lines with a warning)
  - ``normalizeLoadedFileEntry`` (string content
    → array, toolResult object → array)
  - ``getLatestCompactionEntry`` (most recent
    compaction, ``None`` when absent)
  - ``buildSessionContext`` (walk the parent chain
    to root, fallback to last entry, empty result
    when no entries)
  - ``hasReadableSessionHeader``,
    ``isJsonRecord``, ``isSessionEntryType``,
    ``isIndexedSessionEntry``
  - ``parseParentLinkedOpaqueEntry``,
    ``parseOpaqueLeafEntry`` (opaque-entry type
    guards)
  - ``partitionSessionFileEntries`` (split
    file-entries from the legacy opaque extras)
"""
from __future__ import annotations

import json
import os
import re
import sys

import pytest

# Project root on sys.path so ``src.agents.sessions``
# imports work without an editable install.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.agents.sessions import (  # noqa: E402
    CURRENT_SESSION_VERSION,
    AppendPersistenceOptions,
    BranchSummaryEntry,
    CompactionEntry,
    CustomEntry,
    CustomMessageEntry,
    FileEntry,
    LabelEntry,
    ModelChangeEntry,
    NewSessionOptions,
    PreservedOpaqueFileEntry,
    PromptReleasedSessionMergeResult,
    SessionContext,
    SessionEntry,
    SessionHeader,
    SessionInfo,
    SessionInfoEntry,
    SessionLeafControl,
    SessionListProgress,
    SessionMessageEntry,
    SessionTreeNode,
    ThinkingLevelChangeEntry,
    build_session_context,
    create_session_id,
    generate_session_entry_id,
    get_latest_compaction_entry,
    has_readable_session_header,
    is_indexed_session_entry,
    is_json_record,
    is_session_entry_type,
    migrate_session_entries,
    migrate_to_current_version,
    normalize_loaded_file_entry,
    parse_jsonl_entries,
    parse_opaque_leaf_entry,
    parse_parent_linked_opaque_entry,
    parse_session_entries,
    partition_session_file_entries,
)


# ── session_manager_id ───────────────────────────────


class TestSessionManagerId:
    def test_create_session_id_is_uuid_v7(self) -> None:
        """Mirrors ``createSessionId``
        (``session-manager-id.ts:4-6``)."""
        sid = create_session_id()
        # UUID v7 string is 36 chars: 8-4-4-4-12.
        assert re.match(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-"
            r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
            sid,
        )

    def test_create_session_id_is_unique(self) -> None:
        # Generate 100 ids; all must be distinct.
        ids = {create_session_id() for _ in range(100)}
        assert len(ids) == 100

    def test_generate_entry_id_avoids_collisions(self) -> None:
        """Mirrors ``generateSessionEntryId``
        (``session-manager-id.ts:9-16``)."""
        existing: set[str] = set()
        ids = [generate_session_entry_id(existing) for _ in range(50)]
        # All generated ids must be unique.
        assert len(set(ids)) == 50
        # All ids must be 8-char lowercase hex.
        for i in ids:
            assert re.match(r"^[0-9a-f]{8}$", i)

    def test_generate_entry_id_returns_full_uuid_on_collision(
        self,
    ) -> None:
        """When 100 attempts collide, the function
        falls back to a full UUID
        (``session-manager-id.ts:15-16``)."""
        from src.agents.sessions import session_manager_id as smid
        original_uuid4 = smid.uuid.uuid4

        class _FakeUUID:
            def __init__(self) -> None:
                self.hex = "deadbeef" * 4

            def __str__(self) -> str:
                # ``str(uuid.uuid4())`` returns the
                # canonical 36-char UUID string. The
                # mock mirrors that shape.
                return (
                    "deadbeef-dead-beef-dead-beefdeadbeef"
                )

        def fake_uuid4() -> _FakeUUID:
            return _FakeUUID()

        smid.uuid.uuid4 = fake_uuid4
        try:
            # The fake prefix is always ``deadbeef``
            # so the ``existing`` set containing
            # ``deadbeef`` guarantees a collision on
            # every attempt.
            existing = {"deadbeef"}
            result = generate_session_entry_id(existing)
            # After 100 collisions, the function
            # returns ``str(uuid.uuid4())`` — a
            # full 36-char UUID string.
            assert len(result) == 36
        finally:
            smid.uuid.uuid4 = original_uuid4


# ── session_manager_types — every entry dataclass
# ────────────────────────────────────────


class TestSessionTypes:
    def test_session_header_default_type(self) -> None:
        h = SessionHeader(id="abc", timestamp="2026-01-01T00:00:00Z", cwd="/tmp")
        assert h.type == "session"
        assert h.parent_session is None
        assert h.version is None

    def test_session_header_with_version(self) -> None:
        h = SessionHeader(
            id="abc", timestamp="t", cwd="/tmp", version=3
        )
        assert h.version == 3

    def test_new_session_options_defaults(self) -> None:
        o = NewSessionOptions()
        assert o.id is None
        assert o.parent_session is None

    def test_session_message_entry_fields(self) -> None:
        # Build with dict-style message; the codec
        # works on dicts at runtime.
        e = SessionMessageEntry(
            id="m1",
            parent_id=None,
            timestamp="t",
            message={"role": "user", "content": "hi"},
        )
        assert e.type == "message"
        assert e.message == {"role": "user", "content": "hi"}

    def test_thinking_level_change_entry(self) -> None:
        e = ThinkingLevelChangeEntry(
            id="t1", parent_id="p", timestamp="t", thinking_level="high"
        )
        assert e.type == "thinking_level_change"
        assert e.thinking_level == "high"

    def test_model_change_entry(self) -> None:
        e = ModelChangeEntry(
            id="mc", parent_id="p", timestamp="t",
            provider="openai", model_id="gpt-5",
        )
        assert e.type == "model_change"
        assert e.provider == "openai"
        assert e.model_id == "gpt-5"

    def test_compaction_entry(self) -> None:
        e = CompactionEntry(
            id="c1", parent_id="p", timestamp="t",
            summary="summary text",
            first_kept_entry_id="m1",
            tokens_before=1000,
        )
        assert e.type == "compaction"
        assert e.summary == "summary text"
        assert e.tokens_before == 1000

    def test_branch_summary_entry(self) -> None:
        e = BranchSummaryEntry(
            id="b1", parent_id="p", timestamp="t",
            from_id="m1", summary="branch summary",
        )
        assert e.type == "branch_summary"
        assert e.from_id == "m1"

    def test_custom_entry(self) -> None:
        e = CustomEntry(
            id="c", parent_id="p", timestamp="t",
            custom_type="my-state", data={"x": 1},
        )
        assert e.type == "custom"
        assert e.custom_type == "my-state"
        assert e.data == {"x": 1}

    def test_label_entry(self) -> None:
        e = LabelEntry(
            id="l1", parent_id="p", timestamp="t",
            target_id="m1", label="important",
        )
        assert e.type == "label"
        assert e.label == "important"

    def test_session_info_entry(self) -> None:
        e = SessionInfoEntry(
            id="si", parent_id="p", timestamp="t", name="My Session"
        )
        assert e.type == "session_info"
        assert e.name == "My Session"

    def test_custom_message_entry(self) -> None:
        e = CustomMessageEntry(
            id="cm", parent_id="p", timestamp="t",
            custom_type="note",
            content="hello",
            display=True,
            details={"key": "value"},
        )
        assert e.type == "custom_message"
        assert e.display is True
        assert e.content == "hello"

    def test_session_leaf_control(self) -> None:
        e = SessionLeafControl(
            id="lf", parent_id="p", timestamp="t", target_id="m1"
        )
        assert e.type == "leaf"
        assert e.target_id == "m1"
        assert e.append_mode is None

    def test_preserved_opaque_file_entry(self) -> None:
        e = PreservedOpaqueFileEntry(index=3, record={"x": 1})
        assert e.index == 3
        assert e.record == {"x": 1}

    def test_prompt_released_session_merge_result(self) -> None:
        r = PromptReleasedSessionMergeResult(requires_reload=True)
        assert r.requires_reload is True

    def test_append_persistence_options(self) -> None:
        o = AppendPersistenceOptions(
            config=None,
            idempotency_lookup="scan",
            invalidate_serialized_prefix_cache=True,
        )
        assert o.idempotency_lookup == "scan"
        assert o.invalidate_serialized_prefix_cache is True

    def test_session_tree_node(self) -> None:
        n = SessionTreeNode(
            entry={"id": "e", "type": "message"},
            children=[],
        )
        assert n.entry == {"id": "e", "type": "message"}
        assert n.children == []

    def test_session_context(self) -> None:
        c = SessionContext(
            messages=[{"role": "user", "content": "hi"}],
            thinking_level="medium",
            model={"provider": "openai", "modelId": "gpt-5"},
        )
        assert c.thinking_level == "medium"
        assert c.model == {"provider": "openai", "modelId": "gpt-5"}

    def test_session_info(self) -> None:
        from datetime import datetime
        i = SessionInfo(
            path="/x.jsonl", id="sid", cwd="/tmp",
            created=datetime(2026, 1, 1),
            modified=datetime(2026, 1, 2),
        )
        assert i.id == "sid"

    def test_session_list_progress_callable(self) -> None:
        calls: list = []
        progress: SessionListProgress = lambda loaded, total: calls.append((loaded, total))
        progress(10, 100)
        assert calls == [(10, 100)]


# ── session_manager_codec — schema migrations
# ────────────────────────────────────


class TestMigrations:
    def test_current_session_version_is_3(self) -> None:
        """Mirrors the OpenClaw ``CURRENT_SESSION_VERSION``
        constant."""
        assert CURRENT_SESSION_VERSION == 3

    def test_migrate_v1_assigns_id_and_parent_id(self) -> None:
        """Mirrors ``migrateV1ToV2``
        (``session-manager-codec.ts:17-48``)."""
        entries: list[FileEntry] = [
            {"type": "session", "id": "s1", "timestamp": "t", "cwd": "/"},
            {"type": "message", "message": {"role": "user"}},
            {"type": "message", "message": {"role": "assistant"}},
        ]
        migrate_to_current_version(entries)
        # Header was bumped to v2.
        assert entries[0].get("version") == 3  # v2 then v3 ran
        # Entries got id + parentId.
        assert isinstance(entries[1].get("id"), str)
        assert len(entries[1]["id"]) == 8
        assert entries[1].get("parentId") is None  # first entry, no parent
        assert entries[2].get("parentId") == entries[1]["id"]
        assert entries[2].get("id") != entries[1]["id"]

    def test_migrate_v1_to_v2_translates_first_kept_index(self) -> None:
        """Mirrors the
        ``compaction.firstKeptEntryIndex →
        firstKeptEntryId`` translation
        (``session-manager-codec.ts:35-46``)."""
        entries: list[FileEntry] = [
            {"type": "session", "id": "s1", "timestamp": "t", "cwd": "/"},
            {"type": "message", "message": {"role": "user"}},
            {"type": "compaction", "summary": "s", "firstKeptEntryIndex": 1},
        ]
        # Pre-migration sanity.
        assert "firstKeptEntryIndex" in entries[2]
        migrate_to_current_version(entries)
        # After migration, ``firstKeptEntryId`` is set
        # to the id of the entry at original index 1.
        # But by this time the v1 → v2 step has
        # rewritten the index to a real id.
        assert "firstKeptEntryIndex" not in entries[2]
        assert "firstKeptEntryId" in entries[2]
        assert entries[2]["firstKeptEntryId"] == entries[1]["id"]

    def test_migrate_v2_to_v3_renames_hook_message(self) -> None:
        """Mirrors ``migrateV2ToV3``
        (``session-manager-codec.ts:50-63``)."""
        entries: list[FileEntry] = [
            {"type": "session", "version": 2, "id": "s1", "timestamp": "t", "cwd": "/"},
            {
                "type": "message",
                "id": "m1",
                "parentId": None,
                "timestamp": "t",
                "message": {"role": "hookMessage", "content": "hi"},
            },
        ]
        migrate_to_current_version(entries)
        assert entries[0].get("version") == 3
        # ``hookMessage`` → ``custom``.
        assert entries[1]["message"]["role"] == "custom"

    def test_migrate_v2_to_v3_leaves_non_hook_message_alone(self) -> None:
        entries: list[FileEntry] = [
            {"type": "session", "version": 2, "id": "s1", "timestamp": "t", "cwd": "/"},
            {
                "type": "message",
                "id": "m1",
                "parentId": None,
                "timestamp": "t",
                "message": {"role": "user", "content": "hi"},
            },
        ]
        migrate_to_current_version(entries)
        assert entries[1]["message"]["role"] == "user"

    def test_migrate_to_current_version_skips_current(self) -> None:
        """Mirrors the version-check short-circuit
        (``session-manager-codec.ts:71-73``)."""
        entries: list[FileEntry] = [
            {"type": "session", "version": 3, "id": "s1", "timestamp": "t", "cwd": "/"},
        ]
        # No migration needed; the function returns
        # ``False``.
        assert migrate_to_current_version(entries) is False

    def test_migrate_session_entries_thin_wrapper(self) -> None:
        entries: list[FileEntry] = [
            {"type": "session", "id": "s1", "timestamp": "t", "cwd": "/"},
            {"type": "message", "message": {"role": "user"}},
        ]
        migrate_session_entries(entries)
        # Idempotent: running again on v3 entries
        # is a no-op.
        assert entries[0].get("version") == 3


# ── session_manager_codec — getLatestCompactionEntry
# ────────────────────────────


class TestGetLatestCompactionEntry:
    def test_returns_none_when_no_compaction(self) -> None:
        entries: list[SessionEntry] = [
            {"type": "message", "id": "m1", "parentId": None, "timestamp": "t",
             "message": {"role": "user"}},
        ]
        assert get_latest_compaction_entry(entries) is None

    def test_returns_latest_compaction(self) -> None:
        entries: list[SessionEntry] = [
            {"type": "message", "id": "m1", "parentId": None, "timestamp": "t",
             "message": {"role": "user"}},
            {"type": "compaction", "id": "c1", "parentId": "m1", "timestamp": "t1",
             "summary": "first", "firstKeptEntryId": "m1", "tokensBefore": 100},
            {"type": "message", "id": "m2", "parentId": "c1", "timestamp": "t2",
             "message": {"role": "user"}},
            {"type": "compaction", "id": "c2", "parentId": "m2", "timestamp": "t3",
             "summary": "second", "firstKeptEntryId": "m2", "tokensBefore": 200},
        ]
        latest = get_latest_compaction_entry(entries)
        assert latest is not None
        assert latest["id"] == "c2"
        assert latest["summary"] == "second"

    def test_returns_first_compaction_when_only_one(self) -> None:
        entries: list[SessionEntry] = [
            {"type": "compaction", "id": "c1", "parentId": None, "timestamp": "t",
             "summary": "only", "firstKeptEntryId": "x", "tokensBefore": 1},
        ]
        latest = get_latest_compaction_entry(entries)
        assert latest is not None
        assert latest["id"] == "c1"


# ── session_manager_codec — buildSessionContext
# ──────────────────────────────


def _make_user_entry(id_: str, parent_id, content: str) -> SessionEntry:
    """Helper: build a user-message entry."""
    return {
        "type": "message",
        "id": id_,
        "parentId": parent_id,
        "timestamp": "t",
        "message": {"role": "user", "content": content},
    }


def _make_assistant_entry(id_: str, parent_id, content: str) -> SessionEntry:
    """Helper: build an assistant-message entry."""
    return {
        "type": "message",
        "id": id_,
        "parentId": parent_id,
        "timestamp": "t",
        "message": {"role": "assistant", "content": content},
    }


class TestBuildSessionContext:
    def test_empty_entries_returns_empty_context(self) -> None:
        """Mirrors the ``!leaf`` early return
        (``session-manager-codec.ts:128-130``)."""
        ctx = build_session_context([])
        assert ctx.messages == []
        assert ctx.thinking_level == "off"
        assert ctx.model is None

    def test_falls_back_to_last_entry(self) -> None:
        """Mirrors the ``leaf ??= contextEntries.at(-1)``
        fallback (``session-manager-codec.ts:127``)."""
        entries: list[SessionEntry] = [
            _make_user_entry("m1", None, "hi"),
            _make_assistant_entry("m2", "m1", "hello"),
        ]
        # No leaf_id passed; the function should
        # walk from the last entry back to the root.
        ctx = build_session_context(entries)
        # Both messages should be present, in order.
        assert len(ctx.messages) == 2
        assert ctx.messages[0].get("role") == "user"
        assert ctx.messages[1].get("role") == "assistant"

    def test_walks_parent_chain_to_root(self) -> None:
        """The parent chain ``m3 → m2 → m1`` should
        produce all three messages in order.
        """
        entries: list[SessionEntry] = [
            _make_user_entry("m1", None, "1"),
            _make_assistant_entry("m2", "m1", "2"),
            _make_user_entry("m3", "m2", "3"),
        ]
        # Explicit leaf_id = "m3".
        ctx = build_session_context(entries, leaf_id="m3")
        # All three messages should be present, in
        # walk order (root → leaf).
        assert len(ctx.messages) == 3
        # The leaf is the last message.
        assert ctx.messages[-1].get("content") == "3"
        # The root is the first.
        assert ctx.messages[0].get("content") == "1"

    def test_missing_leaf_id_returns_empty(self) -> None:
        """When the leaf_id is in the dict but not
        in the entries, the function falls back to
        the last entry (matches the OpenClaw
        ``leaf ??= contextEntries.at(-1)``)."""
        entries: list[SessionEntry] = [
            _make_user_entry("m1", None, "hi"),
        ]
        ctx = build_session_context(entries, leaf_id="missing")
        # The fallback uses the last entry.
        assert len(ctx.messages) == 1

    def test_falsy_leaf_id_returns_empty(self) -> None:
        """An empty-string ``leaf_id`` returns the
        empty context (the OpenClaw source's
        ``leafId ? byId.get(leafId)`` short-circuit).
        """
        entries: list[SessionEntry] = [
            _make_user_entry("m1", None, "hi"),
        ]
        ctx = build_session_context(entries, leaf_id="")
        assert ctx.messages == []

    def test_branching_path_only_includes_active_branch(self) -> None:
        """The walk follows the parent chain — a
        sibling branch is not included."""
        entries: list[SessionEntry] = [
            _make_user_entry("root", None, "root"),
            _make_assistant_entry("a", "root", "A"),
            _make_user_entry("b", "root", "B"),
        ]
        # Walk from "b": the chain is b → root.
        # "a" is not on the chain.
        ctx = build_session_context(entries, leaf_id="b")
        assert len(ctx.messages) == 2
        assert ctx.messages[0].get("content") == "root"
        assert ctx.messages[1].get("content") == "B"


# ── session_manager_codec — JSONL parsing
# ──────────────────────────────


class TestParseJsonlEntries:
    def test_parses_valid_jsonl(self) -> None:
        """Mirrors ``parseJsonlEntries``
        (``session-manager-codec.ts:142-162``)."""
        content = "\n".join([
            json.dumps({"type": "session", "version": 3, "id": "s1", "timestamp": "t", "cwd": "/"}),
            json.dumps({"type": "message", "id": "m1", "parentId": None, "timestamp": "t",
                        "message": {"role": "user", "content": "hi"}}),
        ])
        entries = parse_jsonl_entries(content)
        assert len(entries) == 2
        assert entries[0]["type"] == "session"
        assert entries[1]["type"] == "message"

    def test_skips_blank_lines(self) -> None:
        content = "\n\n" + json.dumps(
            {"type": "session", "version": 3, "id": "s1", "timestamp": "t", "cwd": "/"}
        ) + "\n\n"
        entries = parse_jsonl_entries(content)
        assert len(entries) == 1

    def test_skips_malformed_lines(self) -> None:
        """Mirrors the ``try / catch`` that increments
        the ``skipped`` counter
        (``session-manager-codec.ts:151-152``)."""
        content = "\n".join([
            "not json at all",
            json.dumps({"type": "session", "version": 3, "id": "s1", "timestamp": "t", "cwd": "/"}),
            "{broken",
        ])
        entries = parse_jsonl_entries(content)
        # Only the valid line is loaded.
        assert len(entries) == 1
        assert entries[0]["type"] == "session"

    def test_empty_content_returns_empty_list(self) -> None:
        assert parse_jsonl_entries("") == []
        assert parse_jsonl_entries("   \n   \n") == []

    def test_parse_session_entries_is_alias(self) -> None:
        """Mirrors ``parseSessionEntries``
        (``session-manager-codec.ts:87-89``) which
        delegates to ``parseJsonlEntries``."""
        content = json.dumps(
            {"type": "session", "version": 3, "id": "s1", "timestamp": "t", "cwd": "/"}
        )
        assert parse_session_entries(content) == parse_jsonl_entries(content)


# ── session_manager_codec — normalizeLoadedFileEntry
# ───────────────────────


class TestNormalizeLoadedFileEntry:
    def test_string_assistant_content_becomes_array(self) -> None:
        """Mirrors the OpenClaw branch
        (``session-manager-codec.ts:170-173``)."""
        entry = {
            "type": "message",
            "id": "m1",
            "parentId": None,
            "timestamp": "t",
            "message": {"role": "assistant", "content": "hello"},
        }
        result = normalize_loaded_file_entry(entry)
        assert result["message"]["content"] == [
            {"type": "text", "text": "hello"}
        ]

    def test_string_tool_result_content_becomes_array(self) -> None:
        entry = {
            "type": "message",
            "id": "m1",
            "parentId": None,
            "timestamp": "t",
            "message": {"role": "toolResult", "content": "result text"},
        }
        result = normalize_loaded_file_entry(entry)
        assert result["message"]["content"] == [
            {"type": "text", "text": "result text"}
        ]

    def test_object_tool_result_content_becomes_array(self) -> None:
        """Mirrors the OpenClaw branch
        (``session-manager-codec.ts:174-176``)."""
        entry = {
            "type": "message",
            "id": "m1",
            "parentId": None,
            "timestamp": "t",
            "message": {
                "role": "toolResult",
                "content": {"type": "text", "text": "r"},
            },
        }
        result = normalize_loaded_file_entry(entry)
        assert result["message"]["content"] == [
            {"type": "text", "text": "r"}
        ]

    def test_passes_through_other_types(self) -> None:
        # A non-message entry is returned unchanged.
        entry = {"type": "label", "id": "l1", "parentId": None, "timestamp": "t",
                 "targetId": "m1", "label": "x"}
        assert normalize_loaded_file_entry(entry) is entry

    def test_user_message_with_array_content_unchanged(self) -> None:
        entry = {
            "type": "message",
            "id": "m1",
            "parentId": None,
            "timestamp": "t",
            "message": {"role": "user", "content": [{"type": "text", "text": "hi"}]},
        }
        result = normalize_loaded_file_entry(entry)
        # The array form is preserved (no normalization).
        assert result["message"]["content"] == [
            {"type": "text", "text": "hi"}
        ]


# ── session_manager_codec — header + type guards
# ─────────────────────────────


class TestHeaderAndTypeGuards:
    def test_has_readable_session_header(self) -> None:
        entries: list[FileEntry] = [
            {"type": "session", "id": "s1", "timestamp": "t", "cwd": "/"},
            {"type": "message", "id": "m1", "parentId": None, "timestamp": "t",
             "message": {"role": "user"}},
        ]
        assert has_readable_session_header(entries) is True

    def test_has_readable_session_header_missing_id(self) -> None:
        entries: list[FileEntry] = [
            {"type": "session", "timestamp": "t", "cwd": "/"},
        ]
        assert has_readable_session_header(entries) is False

    def test_has_readable_session_header_empty(self) -> None:
        assert has_readable_session_header([]) is False

    def test_is_json_record(self) -> None:
        assert is_json_record({}) is True
        assert is_json_record({"a": 1}) is True
        assert is_json_record([]) is False
        assert is_json_record(None) is False
        assert is_json_record("string") is False
        assert is_json_record(42) is False

    def test_is_session_entry_type(self) -> None:
        """Mirrors the private
        ``isSessionEntryType``
        (``session-manager-codec.ts:189-204``)."""
        for t in [
            "message",
            "thinking_level_change",
            "model_change",
            "compaction",
            "branch_summary",
            "custom",
            "custom_message",
            "label",
            "session_info",
        ]:
            assert is_session_entry_type(t) is True, t
        assert is_session_entry_type("session") is False
        assert is_session_entry_type("unknown") is False
        assert is_session_entry_type(None) is False

    def test_is_indexed_session_entry(self) -> None:
        valid: SessionEntry = {
            "type": "message",
            "id": "m1",
            "parentId": None,
            "timestamp": "t",
            "message": {"role": "user"},
        }
        assert is_indexed_session_entry(valid) is True

        # Missing id.
        no_id = dict(valid)
        no_id.pop("id")
        assert is_indexed_session_entry(no_id) is False

        # Unknown type.
        wrong_type = dict(valid)
        wrong_type["type"] = "session"
        assert is_indexed_session_entry(wrong_type) is False

        # Not a dict.
        assert is_indexed_session_entry("not a dict") is False


# ── session_manager_codec — opaque parsers
# ─────────────────────────────────


class TestOpaqueParsers:
    def test_parse_parent_linked_opaque_entry(self) -> None:
        """Mirrors ``parseParentLinkedOpaqueEntry``
        (``session-manager-codec.ts:215-229``)."""
        record = {
            "type": "custom",
            "id": "x1",
            "parentId": "p1",
            "customType": "my",
        }
        result = parse_parent_linked_opaque_entry(record)
        assert result == {"id": "x1", "parentId": "p1"}

    def test_parse_parent_linked_rejects_session_type(self) -> None:
        record = {"type": "session", "id": "x1", "parentId": None}
        assert parse_parent_linked_opaque_entry(record) is None

    def test_parse_parent_linked_rejects_leaf_type(self) -> None:
        record = {
            "type": "leaf",
            "id": "x1",
            "parentId": "p1",
            "targetId": "t1",
            "timestamp": "t",
        }
        assert parse_parent_linked_opaque_entry(record) is None

    def test_parse_parent_linked_rejects_missing_id(self) -> None:
        record = {"type": "custom", "parentId": "p1"}
        assert parse_parent_linked_opaque_entry(record) is None

    def test_parse_opaque_leaf_entry(self) -> None:
        """Mirrors ``parseOpaqueLeafEntry``
        (``session-manager-codec.ts:231-261``)."""
        record = {
            "type": "leaf",
            "id": "lf1",
            "parentId": "p1",
            "targetId": "t1",
            "timestamp": "t",
        }
        result = parse_opaque_leaf_entry(record)
        assert result == {
            "id": "lf1",
            "parentId": "p1",
            "targetId": "t1",
        }

    def test_parse_opaque_leaf_with_append_mode(self) -> None:
        record = {
            "type": "leaf",
            "id": "lf1",
            "parentId": "p1",
            "targetId": "t1",
            "appendParentId": "ap1",
            "appendMode": "side",
            "timestamp": "t",
        }
        result = parse_opaque_leaf_entry(record)
        assert result is not None
        assert result["appendParentId"] == "ap1"
        assert result["appendMode"] == "side"

    def test_parse_opaque_leaf_rejects_wrong_type(self) -> None:
        record = {"type": "message", "id": "m1"}
        assert parse_opaque_leaf_entry(record) is None


# ── session_manager_codec — partitionSessionFileEntries
# ─────────────────────────────


class TestPartitionSessionFileEntries:
    def test_splits_legacy_and_opaque(self) -> None:
        """Mirrors ``partitionSessionFileEntries``
        (``session-manager-codec.ts:263-298``)."""
        entries: list[FileEntry] = [
            # ``version: 3`` so ``acceptsLegacyEntries``
            # is False; only modern (id'd) entries
            # are accepted as file entries.
            {"type": "session", "version": 3, "id": "s1", "timestamp": "t", "cwd": "/"},
            {"type": "message", "id": "m1", "parentId": None, "timestamp": "t",
             "message": {"role": "user"}},
            # An opaque row — an unknown type that
            # neither matches the discriminator
            # switch nor the indexed-entry check.
            {"type": "unknown_extension_row", "data": {"x": 1}},
        ]
        result = partition_session_file_entries(entries)
        assert len(result["fileEntries"]) == 2
        assert result["fileEntries"][0]["type"] == "session"
        assert result["fileEntries"][1]["type"] == "message"
        # The opaque row is preserved as-is.
        assert len(result["opaqueEntries"]) == 1
        assert result["opaqueEntries"][0]["record"] == {
            "type": "unknown_extension_row",
            "data": {"x": 1},
        }
        # The opaque index is the position in the
        # file-entries list (not the original).
        assert result["opaqueEntries"][0]["index"] == 2
        # The ``fileEntriesByOriginalIndex`` only
        # holds the file entries (the opaque row
        # gets no slot — matches the OpenClaw
        # source's ``fileEntriesByOriginalIndex[
        # originalIndex] = entry`` sparse
        # assignment).
        assert len(result["fileEntriesByOriginalIndex"]) == 2
        assert result["fileEntriesByOriginalIndex"][0]["type"] == "session"
        assert result["fileEntriesByOriginalIndex"][1]["type"] == "message"

    def test_legacy_entries_accepted_when_header_v1(self) -> None:
        """Mirrors the ``acceptsLegacyEntries`` branch
        (``session-manager-codec.ts:274``). When the
        header version is < 2, the partitioner
        accepts entries with the legacy (no-id)
        shape.
        """
        entries: list[FileEntry] = [
            {"type": "session", "version": 1, "id": "s1", "timestamp": "t", "cwd": "/"},
            # Pre-v2 message has no id.
            {"type": "message", "timestamp": "t", "message": {"role": "user"}},
        ]
        result = partition_session_file_entries(entries)
        # The legacy message is treated as a file
        # entry (it will be migrated to v2 by the
        # codec's v1 → v2 step).
        assert len(result["fileEntries"]) == 2
        assert result["opaqueEntries"] == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
