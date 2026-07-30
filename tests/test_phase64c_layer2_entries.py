"""Phase 6.4c — Layer 2 session entry operations.

Tests for
:class:`jarvis.agents.sessions.session_manager_entries.SessionManagerEntries`.

- ``append_message`` / ``append_thinking_level_change`` /
  ``append_model_change`` / ``append_compaction`` /
  ``append_custom_entry`` / ``append_session_info`` /
  ``append_custom_message_entry`` /
  ``append_label_change`` — typed append
  helpers.
- ``get_leaf_id`` / ``get_leaf_entry`` /
  ``get_entry`` / ``get_children`` /
  ``get_label`` / ``get_branch`` /
  ``get_header`` / ``get_entries`` /
  ``get_tree`` / ``get_session_name`` /
  ``build_session_context``.
- ``branch`` / ``branch_with_summary`` /
  ``reset_leaf`` — branch mutators.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.agents.sessions import (  # noqa: E402
    CURRENT_SESSION_VERSION,
    SessionManagerEntries,
)


# ── Helpers ─────────────────────────────────────────────────────


def _v3_header(cwd: str = "/some/cwd", sid: str = "s1") -> dict:
    return {
        "type": "session",
        "version": CURRENT_SESSION_VERSION,
        "id": sid,
        "timestamp": "2026-01-01T00:00:00.000Z",
        "cwd": cwd,
    }


def _v3_message(
    msg_id: str,
    role: str = "user",
    parent_id: object = None,
    content: str = "hi",
) -> dict:
    return {
        "type": "message",
        "id": msg_id,
        "parentId": parent_id,
        "timestamp": "2026-01-01T00:00:00.000Z",
        "message": {"role": role, "content": content},
    }


def _write_session_file(file_path: str, header: dict, *entries: dict) -> None:
    lines = [json.dumps(header)] + [json.dumps(e) for e in entries]
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# ── Typed append helpers ─────────────────────────────────────


class TestAppendMessage:
    def test_appends_user_message(self, tmp_path) -> None:
        sm = SessionManagerEntries(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=str(tmp_path / "session.jsonl"),
            persist=True,
        )
        msg_id = sm.append_message({"role": "user", "content": "hi"})
        # The entry is in the file-entries.
        assert any(
            e.get("id") == msg_id
            and e.get("type") == "message"
            and e.get("message", {}).get("role") == "user"
            for e in sm.file_entries
        )
        # The leaf is the new message.
        assert sm.leaf_id == msg_id

    def test_appends_assistant_message_persists(self, tmp_path) -> None:
        file_path = str(tmp_path / "session.jsonl")
        sm = SessionManagerEntries(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=file_path,
            persist=True,
        )
        sm.append_message({"role": "user", "content": "hi"})
        sm.append_message({"role": "assistant", "content": "hello"})
        # The file was written (first assistant
        # message flushes the full file).
        assert os.path.exists(file_path)
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        # The session header + both messages are
        # in the file.
        assert "session" in content
        assert content.count('"role": "user"') >= 1
        assert content.count('"role": "assistant"') >= 1


class TestAppendThinkingLevelChange:
    def test_appends_thinking_level(self, tmp_path) -> None:
        sm = SessionManagerEntries(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=str(tmp_path / "session.jsonl"),
            persist=True,
        )
        sm.append_thinking_level_change("medium")
        # The entry is in the file-entries.
        assert any(
            e.get("type") == "thinking_level_change"
            and e.get("thinkingLevel") == "medium"
            for e in sm.file_entries
        )


class TestAppendModelChange:
    def test_appends_model_change(self, tmp_path) -> None:
        sm = SessionManagerEntries(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=str(tmp_path / "session.jsonl"),
            persist=True,
        )
        sm.append_model_change("anthropic", "claude-3-5-sonnet")
        # The entry is in the file-entries.
        assert any(
            e.get("type") == "model_change"
            and e.get("provider") == "anthropic"
            and e.get("modelId") == "claude-3-5-sonnet"
            for e in sm.file_entries
        )


class TestAppendCompaction:
    def test_appends_compaction(self, tmp_path) -> None:
        sm = SessionManagerEntries(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=str(tmp_path / "session.jsonl"),
            persist=True,
        )
        # First add a message so the
        # compaction's first_kept_entry_id is
        # known.
        sm.append_message({"role": "user", "content": "hi"})
        compaction_id = sm.append_compaction(
            "summary text", first_kept_entry_id=sm.get_leaf_id(), tokens_before=100
        )
        # The compaction is in the file-entries.
        compaction = next(
            e for e in sm.file_entries if e.get("id") == compaction_id
        )
        assert compaction["type"] == "compaction"
        assert compaction["summary"] == "summary text"
        assert compaction["tokensBefore"] == 100


class TestAppendCustomEntry:
    def test_appends_custom_entry(self, tmp_path) -> None:
        sm = SessionManagerEntries(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=str(tmp_path / "session.jsonl"),
            persist=True,
        )
        sm.append_custom_entry("my_type", {"key": "value"})
        # The custom entry is in the file-entries.
        assert any(
            e.get("type") == "custom"
            and e.get("customType") == "my_type"
            and e.get("data") == {"key": "value"}
            for e in sm.file_entries
        )


class TestAppendSessionInfo:
    def test_appends_session_info(self, tmp_path) -> None:
        sm = SessionManagerEntries(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=str(tmp_path / "session.jsonl"),
            persist=True,
        )
        sm.append_session_info("My Session")
        # The session_info entry is in the file-
        # entries.
        assert any(
            e.get("type") == "session_info" and e.get("name") == "My Session"
            for e in sm.file_entries
        )

    def test_strips_newlines(self, tmp_path) -> None:
        """``append_session_info`` strips CR/LF."""
        sm = SessionManagerEntries(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=str(tmp_path / "session.jsonl"),
            persist=True,
        )
        sm.append_session_info("My\nSession\nName")
        # The name is sanitised.
        info = next(
            e for e in sm.file_entries if e.get("type") == "session_info"
        )
        assert info["name"] == "My Session Name"


class TestAppendCustomMessageEntry:
    def test_appends_custom_message(self, tmp_path) -> None:
        sm = SessionManagerEntries(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=str(tmp_path / "session.jsonl"),
            persist=True,
        )
        sm.append_custom_message_entry(
            "my_type", "content", display=True
        )
        # The custom message entry is in the
        # file-entries.
        assert any(
            e.get("type") == "custom_message"
            and e.get("customType") == "my_type"
            and e.get("content") == "content"
            and e.get("display") is True
            for e in sm.file_entries
        )


class TestAppendLabelChange:
    def test_appends_label_change(self, tmp_path) -> None:
        sm = SessionManagerEntries(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=str(tmp_path / "session.jsonl"),
            persist=True,
        )
        # Add a message to label.
        msg_id = sm.append_message({"role": "user", "content": "hi"})
        sm.append_label_change(msg_id, "important")
        # The label is recorded.
        assert sm.get_label(msg_id) == "important"
        # The label entry is in the file-entries.
        assert any(
            e.get("type") == "label"
            and e.get("targetId") == msg_id
            and e.get("label") == "important"
            for e in sm.file_entries
        )

    def test_clears_label_on_none(self, tmp_path) -> None:
        sm = SessionManagerEntries(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=str(tmp_path / "session.jsonl"),
            persist=True,
        )
        msg_id = sm.append_message({"role": "user", "content": "hi"})
        sm.append_label_change(msg_id, "important")
        assert sm.get_label(msg_id) == "important"
        # Clear with None.
        sm.append_label_change(msg_id, None)
        assert sm.get_label(msg_id) is None

    def test_label_unknown_entry_raises(self, tmp_path) -> None:
        sm = SessionManagerEntries(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=str(tmp_path / "session.jsonl"),
            persist=True,
        )
        with pytest.raises(RuntimeError, match="not found"):
            sm.append_label_change("nonexistent", "label")


# ── Getters ──────────────────────────────────────────────────


class TestGetters:
    def test_get_leaf_id_and_entry(self, tmp_path) -> None:
        sm = SessionManagerEntries(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=str(tmp_path / "session.jsonl"),
            persist=True,
        )
        msg_id = sm.append_message({"role": "user", "content": "hi"})
        assert sm.get_leaf_id() == msg_id
        leaf = sm.get_leaf_entry()
        assert leaf is not None
        assert leaf["id"] == msg_id

    def test_get_entry(self, tmp_path) -> None:
        sm = SessionManagerEntries(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=str(tmp_path / "session.jsonl"),
            persist=True,
        )
        msg_id = sm.append_message({"role": "user", "content": "hi"})
        entry = sm.get_entry(msg_id)
        assert entry is not None
        assert entry["id"] == msg_id

    def test_get_entry_unknown_returns_none(self, tmp_path) -> None:
        sm = SessionManagerEntries(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=str(tmp_path / "session.jsonl"),
            persist=True,
        )
        assert sm.get_entry("nonexistent") is None

    def test_get_children(self, tmp_path) -> None:
        sm = SessionManagerEntries(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=str(tmp_path / "session.jsonl"),
            persist=True,
        )
        # Branched tree: m1 (parent), m2a + m2b
        # both children of m1.
        m1 = sm.append_message({"role": "user", "content": "hi"})
        # Reset leaf to m1, then append two
        # children.
        sm.branch(m1)
        sm.append_message({"role": "assistant", "content": "a"})
        sm.branch(m1)
        sm.append_message({"role": "assistant", "content": "b"})
        children = sm.get_children(m1)
        assert len(children) == 2

    def test_get_header(self, tmp_path) -> None:
        sm = SessionManagerEntries(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=str(tmp_path / "session.jsonl"),
            persist=True,
        )
        header = sm.get_header()
        assert header is not None
        assert header["type"] == "session"
        assert header["version"] == CURRENT_SESSION_VERSION

    def test_get_entries(self, tmp_path) -> None:
        sm = SessionManagerEntries(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=str(tmp_path / "session.jsonl"),
            persist=True,
        )
        sm.append_message({"role": "user", "content": "a"})
        sm.append_message({"role": "assistant", "content": "b"})
        entries = sm.get_entries()
        # The session header is NOT included.
        assert all(e.get("type") != "session" for e in entries)
        # Both messages are included.
        assert len(entries) >= 2

    def test_get_session_name(self, tmp_path) -> None:
        sm = SessionManagerEntries(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=str(tmp_path / "session.jsonl"),
            persist=True,
        )
        sm.append_session_info("My Session")
        assert sm.get_session_name() == "My Session"

    def test_get_session_name_no_info(self, tmp_path) -> None:
        sm = SessionManagerEntries(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=str(tmp_path / "session.jsonl"),
            persist=True,
        )
        assert sm.get_session_name() is None

    def test_build_session_context(self, tmp_path) -> None:
        sm = SessionManagerEntries(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=str(tmp_path / "session.jsonl"),
            persist=True,
        )
        sm.append_message({"role": "user", "content": "hi"})
        sm.append_message({"role": "assistant", "content": "hello"})
        ctx = sm.build_session_context()
        # The context has the messages.
        assert ctx is not None
        assert len(ctx.messages) == 2
        assert ctx.messages[0]["role"] == "user"
        assert ctx.messages[1]["role"] == "assistant"


# ── Branch mutators ─────────────────────────────────────────


class TestBranch:
    def test_branch_to_earlier_entry(self, tmp_path) -> None:
        sm = SessionManagerEntries(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=str(tmp_path / "session.jsonl"),
            persist=True,
        )
        m1 = sm.append_message({"role": "user", "content": "hi"})
        sm.append_message({"role": "assistant", "content": "hello"})
        # Branch back to m1.
        sm.branch(m1)
        # The leaf is m1.
        assert sm.get_leaf_id() == m1
        # A new append extends from m1.
        m3 = sm.append_message({"role": "user", "content": "again"})
        assert sm.get_leaf_id() == m3
        # m3's parent is m1.
        entry = sm.get_entry(m3)
        assert entry["parentId"] == m1

    def test_branch_unknown_raises(self, tmp_path) -> None:
        sm = SessionManagerEntries(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=str(tmp_path / "session.jsonl"),
            persist=True,
        )
        sm.append_message({"role": "user", "content": "hi"})
        with pytest.raises(RuntimeError, match="not found"):
            sm.branch("nonexistent")

    def test_reset_leaf(self, tmp_path) -> None:
        sm = SessionManagerEntries(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=str(tmp_path / "session.jsonl"),
            persist=True,
        )
        sm.append_message({"role": "user", "content": "hi"})
        assert sm.get_leaf_id() is not None
        sm.reset_leaf()
        assert sm.get_leaf_id() is None
        assert sm.append_parent_id is None

    def test_branch_with_summary(self, tmp_path) -> None:
        sm = SessionManagerEntries(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=str(tmp_path / "session.jsonl"),
            persist=True,
        )
        m1 = sm.append_message({"role": "user", "content": "hi"})
        sm.append_message({"role": "assistant", "content": "hello"})
        # Branch with summary.
        summary_id = sm.branch_with_summary(m1, "branched here")
        # The summary entry is in the file-entries.
        summary = next(
            e for e in sm.file_entries if e.get("id") == summary_id
        )
        assert summary["type"] == "branch_summary"
        assert summary["summary"] == "branched here"
        assert summary["fromId"] == m1


# ── getBranch / getTree ──────────────────────────────────────


class TestGetBranchAndTree:
    def test_get_branch_returns_path(self, tmp_path) -> None:
        sm = SessionManagerEntries(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=str(tmp_path / "session.jsonl"),
            persist=True,
        )
        m1 = sm.append_message({"role": "user", "content": "hi"})
        m2 = sm.append_message({"role": "assistant", "content": "hello"})
        branch = sm.get_branch()
        # The branch goes from m1 → m2 (in
        # chronological order).
        ids = [e["id"] for e in branch]
        assert ids == [m1, m2]

    def test_get_branch_from_specific_id(self, tmp_path) -> None:
        sm = SessionManagerEntries(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=str(tmp_path / "session.jsonl"),
            persist=True,
        )
        m1 = sm.append_message({"role": "user", "content": "hi"})
        sm.append_message({"role": "assistant", "content": "hello"})
        # From m1, the branch is just [m1].
        branch = sm.get_branch(from_id=m1)
        assert len(branch) == 1
        assert branch[0]["id"] == m1

    def test_get_tree(self, tmp_path) -> None:
        sm = SessionManagerEntries(
            cwd="/some/cwd",
            session_dir=str(tmp_path),
            session_file=str(tmp_path / "session.jsonl"),
            persist=True,
        )
        sm.append_message({"role": "user", "content": "hi"})
        sm.append_message({"role": "assistant", "content": "hello"})
        tree = sm.get_tree()
        # The tree has at least one root.
        assert len(tree) >= 1
        # The first node has the user message
        # as the leaf root.
        leaves = []
        stack = list(tree)
        while stack:
            node = stack.pop()
            if not node["children"]:
                leaves.append(node)
            else:
                stack.extend(node["children"])
        assert any(
            l["entry"]["message"]["role"] == "assistant" for l in leaves
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
