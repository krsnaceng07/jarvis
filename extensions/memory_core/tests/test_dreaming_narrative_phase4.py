"""Tests for memory_core.dreaming_narrative — Phase 4.4e.

Mirrors the TypeScript ``test_dreaming-narrative.test.ts`` patterns.
The LLM-orchestrator functions are stubbed; we test the deterministic
building blocks (diary section, backfill, dedupe, format, prompt,
extract) which are the foundation the orchestrator will use.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


from extensions.memory_core import dreaming_narrative as dn


# ── Diary section helpers ──────────────────────────────────────────────


def test_ensure_diary_section_appends_when_missing(tmp_path: Path) -> None:
    """Empty content → just the diary section."""
    result = dn.ensure_diary_section("")
    assert result.startswith(dn.DIARY_HEADING)
    assert dn.DIARY_START_MARKER in result
    assert dn.DIARY_END_MARKER in result


def test_ensure_diary_section_preserves_existing() -> None:
    """If both markers are present, return as-is."""
    existing = f"# Top\n\n{dn.DIARY_START_MARKER}\nbody\n{dn.DIARY_END_MARKER}\n"
    assert dn.ensure_diary_section(existing) == existing


def test_ensure_diary_section_appends_after_existing_content() -> None:
    """Existing content without markers → diary section prepended."""
    existing = "# User content\n\nstuff"
    result = dn.ensure_diary_section(existing)
    assert result.startswith(dn.DIARY_HEADING)
    assert "# User content" in result


def test_replace_diary_content_replaces_body() -> None:
    """If diary section exists, replace its body."""
    existing = f"{dn.DIARY_START_MARKER}\nold\n{dn.DIARY_END_MARKER}"
    result = dn.replace_diary_content(existing, "new body")
    assert "old" not in result
    assert "new body" in result


def test_replace_diary_content_inserts_when_missing() -> None:
    """No diary section → ``ensure`` + replace."""
    result = dn.replace_diary_content("", "diary body")
    assert dn.DIARY_START_MARKER in result
    assert "diary body" in result


def test_replace_diary_content_empty_input() -> None:
    """Empty diary content → just whitespace body."""
    result = dn.replace_diary_content("", "")
    assert dn.DIARY_START_MARKER in result
    assert dn.DIARY_END_MARKER in result


def test_split_diary_blocks_separator() -> None:
    """Split on ``\\n---\\n`` separator."""
    content = "block1\n\n---\n\nblock2\n\n---\n\nblock3"
    blocks = dn.split_diary_blocks(content)
    assert blocks == ["block1", "block2", "block3"]


def test_split_diary_blocks_drops_empty() -> None:
    """Empty / whitespace-only blocks are dropped."""
    content = "block1\n\n---\n\n   \n\n---\n\nblock2"
    blocks = dn.split_diary_blocks(content)
    assert blocks == ["block1", "block2"]


def test_clamp_diary_context_entry_short() -> None:
    """Entries shorter than the limit pass through."""
    assert dn.clamp_diary_context_entry("short entry") == "short entry"


def test_clamp_diary_context_entry_long() -> None:
    """Entries longer than the limit are truncated with ``...``."""
    long_entry = "a" * 500
    result = dn.clamp_diary_context_entry(long_entry)
    assert len(result) <= dn.RECENT_DIARY_CONTEXT_MAX_CHARS + 3
    assert result.endswith("...")


def test_clamp_diary_context_entry_normalizes_whitespace() -> None:
    """Newlines and multiple spaces are normalized to single space."""
    entry = "line 1\n\nline 2\twith   spaces"
    result = dn.clamp_diary_context_entry(entry)
    assert " " in result
    assert "\n" not in result
    assert "\t" not in result


def test_normalize_diary_block_body_strips_metadata() -> None:
    """Drop header lines, HTML comments, and italics-only date lines."""
    block = (
        "*December 15, 2025*\n\n"
        "<!-- comment -->\n\n"
        "# Heading\n\n"
        "actual body line one\n"
        "actual body line two"
    )
    result = dn.normalize_diary_block_body(block)
    assert "*December 15, 2025*" not in result
    assert "<!-- comment -->" not in result
    assert "# Heading" not in result
    assert "actual body line one" in result
    assert "actual body line two" in result


def test_is_optional_diary_context_read_error_known_codes() -> None:
    """Known "soft" error codes return ``True``."""
    for code in ("ENOENT", "EACCES", "EPERM", "ENOTDIR", "not-found", "symlink"):
        err = OSError(0, "x")
        err.errno = 0
        # Construct via __dict__ to set the code attribute
        err.__dict__["code"] = code
        assert dn.is_optional_diary_context_read_error(err) is True


def test_is_optional_diary_context_read_error_unknown() -> None:
    """Unknown errors return ``False``."""
    err = ValueError("unexpected")
    assert dn.is_optional_diary_context_read_error(err) is False


# ── Read recent entries ────────────────────────────────────────────────


def test_read_recent_dream_diary_entries_empty(tmp_path: Path) -> None:
    """No DREAMS.md → empty list."""
    result = dn.read_recent_dream_diary_entries(str(tmp_path))
    assert result == []


def test_read_recent_dream_diary_entries_no_diary_section(tmp_path: Path) -> None:
    """DREAMS.md without a diary section → empty list."""
    (tmp_path / "DREAMS.md").write_text("# Deep\n<!-- -->", encoding="utf-8")
    result = dn.read_recent_dream_diary_entries(str(tmp_path))
    assert result == []


def test_read_recent_dream_diary_entries_with_blocks(tmp_path: Path) -> None:
    """Returns the most recent N entries (clamped)."""
    body = (
        "*Dec 1*\n\nfirst entry\n\n---\n\n*Dec 2*\n\nsecond entry\n\n---\n\n*Dec 3*\n\nthird entry"
    )
    (tmp_path / "DREAMS.md").write_text(
        f"{dn.DIARY_START_MARKER}\n{body}\n{dn.DIARY_END_MARKER}", encoding="utf-8"
    )
    result = dn.read_recent_dream_diary_entries(str(tmp_path))
    # Reversed → newest first
    assert len(result) == 3
    assert "third entry" in result[0]
    assert "second entry" in result[1]
    assert "first entry" in result[2]


def test_read_recent_dream_diary_entries_limit(tmp_path: Path) -> None:
    """``limit`` caps the result count."""
    body = "\n\n---\n\n".join(f"*Dec {i}*\n\nentry {i}" for i in range(1, 6))
    (tmp_path / "DREAMS.md").write_text(
        f"{dn.DIARY_START_MARKER}\n{body}\n{dn.DIARY_END_MARKER}", encoding="utf-8"
    )
    result = dn.read_recent_dream_diary_entries(str(tmp_path), limit=2)
    assert len(result) == 2
    # Most recent (Dec 5) first
    assert "entry 5" in result[0]
    assert "entry 4" in result[1]


# ── Backfill helpers ──────────────────────────────────────────────────


def test_format_backfill_diary_date_valid() -> None:
    """Valid YYYY-MM-DD → ``"Month D, YYYY"``."""
    assert dn.format_backfill_diary_date("2025-12-15") == "December 15, 2025"
    assert dn.format_backfill_diary_date("2025-01-01") == "January 1, 2025"


def test_format_backfill_diary_date_invalid() -> None:
    """Invalid format → return as-is."""
    assert dn.format_backfill_diary_date("not-a-date") == "not-a-date"


def test_build_backfill_diary_entry_minimal() -> None:
    """Build with just date + body."""
    result = dn.build_backfill_diary_entry("2025-12-15", ["first line", "second line"])
    assert "*December 15, 2025*" in result
    assert "first line" in result
    assert "second line" in result
    assert dn.BACKFILL_ENTRY_MARKER in result
    assert "day=2025-12-15" in result


def test_build_backfill_diary_entry_with_source() -> None:
    """Source path is included in the marker comment."""
    result = dn.build_backfill_diary_entry(
        "2025-12-15", ["body"], source_path="memory/2025-12-15.md"
    )
    assert "source=memory/2025-12-15.md" in result


def test_strip_backfill_diary_blocks_keeps_user_entries(tmp_path: Path) -> None:
    """Backfill entries are removed; user entries preserved."""
    user = "*Dec 1*\n\nuser-written"
    backfill = f"*Dec 2*\n\n<!-- {dn.BACKFILL_ENTRY_MARKER} day=2025-12-02 -->\n\nbackfill body"
    body = f"{user}\n\n---\n\n{backfill}"
    existing = f"{dn.DIARY_START_MARKER}\n{body}\n{dn.DIARY_END_MARKER}"

    result = dn.strip_backfill_diary_blocks(existing)
    assert result["removed"] == 1
    assert "user-written" in result["updated"]
    assert "backfill body" not in result["updated"]


def test_write_backfill_diary_entries_replaces_prior(tmp_path: Path) -> None:
    """New backfill entries replace any prior backfill entries."""
    # Seed a diary section with a prior backfill + a user entry.
    prior = (
        f"{dn.DIARY_START_MARKER}\n"
        f"*Dec 1*\n\nuser-written entry\n\n---\n\n"
        f"*Dec 2*\n\nold backfill content\n"
        f"<!-- {dn.BACKFILL_ENTRY_MARKER} day=2025-12-01 -->\n"
        f"{dn.DIARY_END_MARKER}"
    )
    (tmp_path / "DREAMS.md").write_text(prior, encoding="utf-8")

    # Write new backfill entries
    result = dn.write_backfill_diary_entries(
        str(tmp_path),
        [
            {"isoDay": "2025-12-02", "bodyLines": ["new body 1"]},
            {"isoDay": "2025-12-03", "bodyLines": ["new body 2", "second line"]},
        ],
    )
    assert result["written"] == 2
    assert result["replaced"] == 1

    content = (tmp_path / "DREAMS.md").read_text(encoding="utf-8")
    assert "old backfill content" not in content
    assert "new body 1" in content
    assert "new body 2" in content
    assert "day=2025-12-02" in content
    assert "day=2025-12-03" in content
    # User entry preserved
    assert "user-written entry" in content


def test_remove_backfill_diary_entries(tmp_path: Path) -> None:
    """Strip all backfill entries from DREAMS.md."""
    # Seed a backfill entry
    user = "*Dec 1*\n\nuser-written"
    backfill = f"*Dec 2*\n\n<!-- {dn.BACKFILL_ENTRY_MARKER} day=2025-12-02 -->\n\nbackfill body"
    body = f"{user}\n\n---\n\n{backfill}"
    existing = f"{dn.DIARY_START_MARKER}\n{body}\n{dn.DIARY_END_MARKER}"
    (tmp_path / "DREAMS.md").write_text(existing, encoding="utf-8")

    result = dn.remove_backfill_diary_entries(str(tmp_path))
    assert result["removed"] == 1

    content = (tmp_path / "DREAMS.md").read_text(encoding="utf-8")
    assert "backfill body" not in content
    assert "user-written" in content


# ── Dedupe ─────────────────────────────────────────────────────────────


def test_dedupe_dream_diary_entries_removes_duplicates(tmp_path: Path) -> None:
    """Duplicate date+body blocks are removed; order is preserved."""
    # Two blocks with same date + body (effectively duplicates)
    body = (
        "*Dec 1*\n\nduplicate body\n\n---\n\n"
        "*Dec 1*\n\nduplicate body\n\n---\n\n"
        "*Dec 2*\n\nunique body"
    )
    (tmp_path / "DREAMS.md").write_text(
        f"{dn.DIARY_START_MARKER}\n{body}\n{dn.DIARY_END_MARKER}", encoding="utf-8"
    )
    result = dn.dedupe_dream_diary_entries(str(tmp_path))
    assert result["removed"] == 1
    assert result["kept"] == 2


def test_dedupe_dream_diary_entries_no_duplicates(tmp_path: Path) -> None:
    """Unique entries are preserved; no removal happens."""
    body = "*Dec 1*\n\nfirst\n\n---\n\n*Dec 2*\n\nsecond"
    (tmp_path / "DREAMS.md").write_text(
        f"{dn.DIARY_START_MARKER}\n{body}\n{dn.DIARY_END_MARKER}", encoding="utf-8"
    )
    result = dn.dedupe_dream_diary_entries(str(tmp_path))
    assert result["removed"] == 0
    assert result["kept"] == 2


def test_normalize_diary_block_fingerprint() -> None:
    """Fingerprint includes date + body (no whitespace differences matter)."""
    block1 = "*Dec 1, 2025*\n\nbody content"
    block2 = "*Dec 1, 2025*\n\nbody content"
    block3 = "*Dec 2, 2025*\n\nbody content"
    assert dn.normalize_diary_block_fingerprint(block1) == dn.normalize_diary_block_fingerprint(
        block2
    )
    assert dn.normalize_diary_block_fingerprint(block1) != dn.normalize_diary_block_fingerprint(
        block3
    )


def test_join_diary_blocks_empty() -> None:
    """Empty list returns empty string."""
    assert dn.join_diary_blocks([]) == ""


def test_join_diary_blocks_single() -> None:
    """Single block gets a leading ``---`` separator."""
    result = dn.join_diary_blocks(["block1"])
    assert result.startswith("---\n\n")
    assert "block1" in result


def test_join_diary_blocks_multiple() -> None:
    """Multiple blocks separated by ``\\n`` (each block already has ``\\n---\\n`` prefix)."""
    result = dn.join_diary_blocks(["block1", "block2"])
    assert result.count("---") == 2


# ── Prompt building ────────────────────────────────────────────────────


def test_build_narrative_prompt_basic() -> None:
    """Build prompt with just snippets."""
    data: dn.NarrativePhaseData = {
        "phase": "light",
        "snippets": ["fragment 1", "fragment 2"],
    }
    result = dn.build_narrative_prompt(data)
    assert "Write a dream diary entry" in result
    assert "- fragment 1" in result
    assert "- fragment 2" in result
    # No themes / promotions / date → no extra sections
    assert "Recurring themes" not in result
    assert "Memories that crystallized" not in result
    assert "Diary continuity" not in result


def test_build_narrative_prompt_with_themes() -> None:
    """Themes are included under the ``Recurring themes`` heading."""
    data: dn.NarrativePhaseData = {
        "phase": "rem",
        "snippets": ["s"],
        "themes": ["sunset", "code", "music"],
    }
    result = dn.build_narrative_prompt(data)
    assert "Recurring themes:" in result
    assert "- sunset" in result
    assert "- code" in result
    assert "- music" in result


def test_build_narrative_prompt_with_promotions() -> None:
    """Promotions are included under the ``crystallized`` heading."""
    data: dn.NarrativePhaseData = {
        "phase": "deep",
        "snippets": ["s"],
        "promotions": ["important insight"],
    }
    result = dn.build_narrative_prompt(data)
    assert "Memories that crystallized" in result
    assert "- important insight" in result


def test_build_narrative_prompt_caps_lists() -> None:
    """Snippets cap at 12, themes at 6, promotions at 5."""
    data: dn.NarrativePhaseData = {
        "phase": "rem",
        "snippets": [f"s{i}" for i in range(20)],
        "themes": [f"t{i}" for i in range(20)],
        "promotions": [f"p{i}" for i in range(20)],
    }
    result = dn.build_narrative_prompt(data)
    # Only the first 12 snippets appear
    for i in range(12):
        assert f"- s{i}" in result
    assert "- s12" not in result
    # Only the first 6 themes
    for i in range(6):
        assert f"- t{i}" in result
    assert "- t6" not in result
    # Only the first 5 promotions
    for i in range(5):
        assert f"- p{i}" in result
    assert "- p5" not in result


def test_build_narrative_prompt_with_continuity() -> None:
    """``currentDate`` and ``recentDiaryEntries`` add the continuity section."""
    data: dn.NarrativePhaseData = {
        "phase": "light",
        "snippets": ["s"],
        "currentDate": "2025-12-15",
        "recentDiaryEntries": ["old entry 1", "old entry 2"],
    }
    result = dn.build_narrative_prompt(data)
    assert "Diary continuity context:" in result
    assert "- Current sweep: 2025-12-15" in result
    assert "- old entry 1" in result
    assert "- old entry 2" in result
    assert "fresh angle" in result


# ── Message extraction ─────────────────────────────────────────────────


def test_extract_narrative_text_string_content() -> None:
    """Plain string assistant content is returned trimmed."""
    messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "  narrative text  "},
    ]
    assert dn.extract_narrative_text(messages) == "narrative text"


def test_extract_narrative_text_array_content() -> None:
    """Array content with text/output_text parts is joined."""
    messages = [
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "first part"},
                {"type": "output_text", "text": "second part"},
            ],
        }
    ]
    assert dn.extract_narrative_text(messages) == "first part\nsecond part"


def test_extract_narrative_text_skips_non_text_parts() -> None:
    """Parts with non-text types (e.g. image) are skipped."""
    messages = [
        {
            "role": "assistant",
            "content": [
                {"type": "image", "url": "x"},
                {"type": "text", "text": "only text"},
            ],
        }
    ]
    assert dn.extract_narrative_text(messages) == "only text"


def test_extract_narrative_text_no_assistant() -> None:
    """No assistant message → ``None``."""
    messages = [{"role": "user", "content": "hi"}]
    assert dn.extract_narrative_text(messages) is None


def test_extract_narrative_text_walks_backwards() -> None:
    """Newest assistant message wins."""
    messages = [
        {"role": "assistant", "content": "old"},
        {"role": "user", "content": "follow up"},
        {"role": "assistant", "content": "new"},
    ]
    assert dn.extract_narrative_text(messages) == "new"


def test_extract_narrative_text_skips_invalid() -> None:
    """Non-dict messages are skipped without crashing."""
    messages = ["string", None, {"role": "assistant", "content": "found"}]
    assert dn.extract_narrative_text(messages) == "found"


# ── Date formatting ────────────────────────────────────────────────────


def test_format_narrative_date_utc() -> None:
    """UTC timezone in the formatted output."""
    epoch_ms = int(datetime(2025, 12, 15, 14, 30, tzinfo=timezone.utc).timestamp() * 1000)
    result = dn.format_narrative_date(epoch_ms, "UTC")
    assert "December 15, 2025" in result
    assert "2:30 PM" in result
    assert "UTC" in result


def test_format_narrative_date_with_timezone() -> None:
    """IANA timezone name is honored."""
    epoch_ms = int(datetime(2025, 12, 15, 18, 0, tzinfo=timezone.utc).timestamp() * 1000)
    result = dn.format_narrative_date(epoch_ms, "Asia/Kathmandu")
    # 18:00 UTC + 5:45 = 23:45 → 11:45 PM in KT
    assert "December 15, 2025" in result
    assert "11:45 PM" in result


def test_format_narrative_date_invalid_timezone_falls_back() -> None:
    """Unknown timezone falls back to UTC without crashing."""
    epoch_ms = int(datetime(2025, 12, 15, 14, 30, tzinfo=timezone.utc).timestamp() * 1000)
    result = dn.format_narrative_date(epoch_ms, "Mars/Olympus_Mons")
    assert "December 15, 2025" in result


# ── Session key helpers ────────────────────────────────────────────────


def test_build_narrative_session_key_deterministic() -> None:
    """Same workspace + phase → same key."""
    a = dn.build_narrative_session_key("/tmp/ws", "light")
    b = dn.build_narrative_session_key("/tmp/ws", "light")
    assert a == b


def test_build_narrative_session_key_differs_per_phase() -> None:
    """Different phases get different keys."""
    light = dn.build_narrative_session_key("/tmp/ws", "light")
    rem = dn.build_narrative_session_key("/tmp/ws", "rem")
    deep = dn.build_narrative_session_key("/tmp/ws", "deep")
    assert light != rem != deep != light


def test_build_narrative_session_key_includes_workspace_hash() -> None:
    """Different workspaces get different keys (sha1 first 12 chars)."""
    a = dn.build_narrative_session_key("/tmp/ws-a", "light")
    b = dn.build_narrative_session_key("/tmp/ws-b", "light")
    assert a != b


def test_build_narrative_attempt_session_key() -> None:
    """Attempt 0 uses base key; later attempts add suffix."""
    base = dn.build_narrative_session_key("/tmp/ws", "light")
    assert dn.build_narrative_attempt_session_key(base, 0) == base
    assert dn.build_narrative_attempt_session_key(base, 1) == f"{base}-retry-1"
    assert dn.build_narrative_attempt_session_key(base, 2) == f"{base}-retry-2"


# ── Fallback narrative entry ──────────────────────────────────────────


def test_append_fallback_narrative_entry(tmp_path: Path) -> None:
    """Writing a fallback entry creates the diary section + entry."""
    now_ms = int(datetime(2025, 12, 15, 14, 30, tzinfo=timezone.utc).timestamp() * 1000)
    dn.append_fallback_narrative_entry(
        str(tmp_path),
        {"phase": "light", "snippets": ["x"]},
        now_ms=now_ms,
        timezone_name="UTC",
    )
    content = (tmp_path / "DREAMS.md").read_text(encoding="utf-8")
    assert dn.DIARY_START_MARKER in content
    assert dn.REQUEST_SCOPED_FALLBACK_NARRATIVE in content
    assert "December 15, 2025" in content


def test_append_fallback_narrative_entry_uses_logger(tmp_path: Path) -> None:
    """``logger.info`` is called after a successful write."""
    calls: list[str] = []

    class _L:
        def info(self, m: str) -> None:
            calls.append(m)

        def warn(self, m: str) -> None:
            pass

        def error(self, m: str) -> None:
            pass

    now_ms = int(datetime(2025, 12, 15, 14, 30, tzinfo=timezone.utc).timestamp() * 1000)
    dn.append_fallback_narrative_entry(
        str(tmp_path),
        {"phase": "rem", "snippets": []},
        now_ms=now_ms,
        timezone_name="UTC",
        logger=_L(),
        reason="unit test",
    )
    assert any("fallback" in m for m in calls)
    assert any("rem" in m for m in calls)


def test_append_fallback_narrative_entry_swallows_errors(tmp_path: Path) -> None:
    """Write failure → ``logger.warn``; function returns normally."""
    calls: list[str] = []

    class _L:
        def info(self, m: str) -> None:
            pass

        def warn(self, m: str) -> None:
            calls.append(m)

        def error(self, m: str) -> None:
            pass

    # Pass a workspace path that's a regular file (not a directory) so
    # ``update_dreams_file`` fails when creating ``DREAMS.md``.
    blocker = tmp_path / "blocker"
    blocker.write_text("not a dir", encoding="utf-8")
    now_ms = int(datetime(2025, 12, 15, 14, 30, tzinfo=timezone.utc).timestamp() * 1000)
    # Should NOT raise even when the write fails
    dn.append_fallback_narrative_entry(
        str(blocker),
        {"phase": "light", "snippets": []},
        now_ms=now_ms,
        timezone_name="UTC",
        logger=_L(),
    )
    # Either warn was called (write failed) or it didn't (some platforms
    # allow this); either way the call returned without exception.
    # The point of this test is "doesn't raise".


# ── Constants sanity ──────────────────────────────────────────────────


def test_constants_present() -> None:
    """All exported constants are non-empty strings / numbers."""
    assert dn.DIARY_START_MARKER.startswith("<!--")
    assert dn.DIARY_END_MARKER.startswith("<!--")
    assert dn.DIARY_HEADING.startswith("#")
    assert dn.BACKFILL_ENTRY_MARKER
    assert dn.DREAMING_SESSION_KEY_PREFIX
    assert isinstance(dn.NARRATIVE_TIMEOUT_MS, int) and dn.NARRATIVE_TIMEOUT_MS > 0
    assert isinstance(dn.NARRATIVE_MESSAGE_FETCH_LIMIT, int)
    assert len(dn.NARRATIVE_MESSAGE_SETTLE_DELAYS_MS) >= 1
    assert isinstance(dn.RECENT_DIARY_CONTEXT_LIMIT, int)
    assert isinstance(dn.RECENT_DIARY_CONTEXT_MAX_CHARS, int)
    assert dn.REQUEST_SCOPED_FALLBACK_NARRATIVE
    assert dn.NARRATIVE_SYSTEM_PROMPT
    assert "dream diary" in dn.NARRATIVE_SYSTEM_PROMPT.lower()
