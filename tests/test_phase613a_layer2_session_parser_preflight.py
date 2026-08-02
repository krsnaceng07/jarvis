"""Phase 6.13a — session_file_parser + manual_compaction_preflight tests.

Verifies the public surface of:

- :func:`parse_session_file_entries_with_warnings`
  — JSONL session-file parser with
  per-line warning + row-by-entry
  map.
- :func:`preflight_manual_session_compaction`
  — manual compaction preflight
  (already-compacted / too-small /
  compactable cases).
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from src.agents.sessions.manual_compaction_preflight import (
    preflight_manual_session_compaction,
)
from src.agents.sessions.session_file_parser import (
    parse_session_file_entries_with_warnings,
)


# ============================================================================
# session_file_parser
# ============================================================================


class TestParseSessionFileEntries:
    def test_empty(self) -> None:
        result = parse_session_file_entries_with_warnings("")
        assert result["entries"] == []
        assert result["warnings"] == []
        assert result["rowByEntry"] == {}

    def test_single_message(self) -> None:
        content = json.dumps({
            "id": "a",
            "type": "message",
            "message": {"role": "user", "content": "hi"},
        })
        result = parse_session_file_entries_with_warnings(content)
        assert len(result["entries"]) == 1
        assert result["entries"][0]["id"] == "a"
        assert result["warnings"] == []
        assert result["rowByEntry"] == {"a": 1}

    def test_multiple_lines(self) -> None:
        lines = [
            json.dumps({
                "id": "a",
                "type": "message",
                "message": {"role": "user", "content": "hi"},
            }),
            json.dumps({
                "id": "b",
                "type": "message",
                "message": {"role": "assistant", "content": "ok"},
            }),
        ]
        content = "\n".join(lines)
        result = parse_session_file_entries_with_warnings(content)
        assert len(result["entries"]) == 2
        assert result["rowByEntry"] == {"a": 1, "b": 2}

    def test_crlf(self) -> None:
        lines = [
            json.dumps({
                "id": "a",
                "type": "message",
                "message": {"role": "user"},
            }),
            json.dumps({
                "id": "b",
                "type": "message",
                "message": {"role": "assistant"},
            }),
        ]
        content = "\r\n".join(lines)
        result = parse_session_file_entries_with_warnings(content)
        assert len(result["entries"]) == 2
        assert result["rowByEntry"] == {"a": 1, "b": 2}

    def test_blank_lines_skipped(self) -> None:
        content = (
            json.dumps({
                "id": "a",
                "type": "message",
                "message": {"role": "user"},
            })
            + "\n\n   \n"
            + json.dumps({
                "id": "b",
                "type": "message",
                "message": {"role": "assistant"},
            })
        )
        result = parse_session_file_entries_with_warnings(content)
        # Blank lines are skipped.
        assert len(result["entries"]) == 2

    def test_invalid_json_warning(self) -> None:
        content = "{not json}\n" + json.dumps({
            "id": "a",
            "type": "message",
            "message": {"role": "user"},
        })
        result = parse_session_file_entries_with_warnings(content)
        assert len(result["entries"]) == 1
        assert result["entries"][0]["id"] == "a"
        assert len(result["warnings"]) == 1
        assert result["warnings"][0]["code"] == "invalid-session-json"
        assert result["warnings"][0]["row"] == 1

    def test_invalid_entry_warning(self) -> None:
        # No "type" key.
        content = '{"id": "a"}\n' + json.dumps({
            "id": "b",
            "type": "message",
            "message": {"role": "user"},
        })
        result = parse_session_file_entries_with_warnings(content)
        assert len(result["entries"]) == 1
        assert result["entries"][0]["id"] == "b"
        assert len(result["warnings"]) == 1
        assert result["warnings"][0]["code"] == "invalid-session-row"
        assert result["warnings"][0]["row"] == 1

    def test_message_without_role_warning(self) -> None:
        # "type=message" but no role.
        content = json.dumps({
            "id": "a",
            "type": "message",
            "message": {"content": "hi"},  # no role
        })
        result = parse_session_file_entries_with_warnings(content)
        assert result["entries"] == []
        assert len(result["warnings"]) == 1
        assert result["warnings"][0]["code"] == "invalid-session-row"

    def test_non_message_entry_valid(self) -> None:
        # Non-message types (compaction,
        # session_info, etc.) are valid
        # without a nested message.
        content = json.dumps({
            "id": "c1",
            "type": "compaction",
            "summary": "...",
        })
        result = parse_session_file_entries_with_warnings(content)
        assert len(result["entries"]) == 1
        assert result["entries"][0]["type"] == "compaction"
        assert result["warnings"] == []

    def test_row_numbers_1indexed(self) -> None:
        content = (
            "\n"  # row 1 (blank, skipped)
            + json.dumps({
                "id": "a",
                "type": "message",
                "message": {"role": "user"},
            })
            + "\n"
            + "garbage\n"  # row 3
            + json.dumps({
                "id": "b",
                "type": "message",
                "message": {"role": "assistant"},
            })
        )
        result = parse_session_file_entries_with_warnings(content)
        assert result["rowByEntry"] == {"a": 2, "b": 4}
        # Garbage row is row 3.
        assert result["warnings"][0]["row"] == 3


# ============================================================================
# manual_compaction_preflight
# ============================================================================


class TestPreflightManualSessionCompaction:
    def test_empty_path(self) -> None:
        result = preflight_manual_session_compaction([], {})
        assert result["compactable"] is False
        assert "small" in result["reason"].lower()

    def test_too_small(self) -> None:
        # Just one entry — not enough to
        # compact.
        result = preflight_manual_session_compaction(
            [{"id": "a", "type": "message"}], {}
        )
        assert result["compactable"] is False
        assert "small" in result["reason"].lower()

    def test_already_compacted(self) -> None:
        result = preflight_manual_session_compaction(
            [
                {"id": "u1", "type": "message"},
                {"id": "u2", "type": "message"},
                {"id": "c1", "type": "compaction", "summary": "x"},
            ],
            {},
        )
        assert result["compactable"] is False
        assert result["reason"] == "Already compacted"

    def test_compactable(self) -> None:
        result = preflight_manual_session_compaction(
            [
                {"id": "u1", "type": "message"},
                {"id": "u2", "type": "message"},
                {"id": "u3", "type": "message"},
            ],
            {"enabled": True, "threshold": 0.85},
        )
        assert result["compactable"] is True
        prep = result["preparation"]
        assert prep["pathEntries"] == [
            {"id": "u1", "type": "message"},
            {"id": "u2", "type": "message"},
            {"id": "u3", "type": "message"},
        ]
        assert prep["settings"] == {
            "enabled": True,
            "threshold": 0.85,
        }

    def test_uses_keep_recent_tokens(self) -> None:
        result = preflight_manual_session_compaction(
            [
                {"id": "u1", "type": "message"},
                {"id": "u2", "type": "message"},
            ],
            {"keepRecentTokens": 5000},
        )
        assert result["compactable"] is True
        assert result["preparation"]["keepRecentTokens"] == 5000

    def test_default_keep_recent_tokens(self) -> None:
        result = preflight_manual_session_compaction(
            [
                {"id": "u1", "type": "message"},
                {"id": "u2", "type": "message"},
            ],
            {},
        )
        assert result["compactable"] is True
        # Default 20000.
        assert result["preparation"]["keepRecentTokens"] == 20000
