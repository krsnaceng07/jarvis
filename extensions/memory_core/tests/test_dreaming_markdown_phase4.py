"""Tests for memory_core.dreaming_markdown — Phase 4.4d.

Mirrors the TypeScript ``test_dreaming-markdown.test.ts`` patterns.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path


from extensions.memory_core import dreaming_markdown as dm
from extensions.memory_core import dreaming_dreams_file as df


# ── Format day ──────────────────────────────────────────────────────────


def test_format_memory_dreaming_day_utc() -> None:
    """Without timezone, fall back to UTC day."""
    # 2025-11-15T10:30:00Z
    epoch_ms = int(datetime(2025, 11, 15, 10, 30, tzinfo=timezone.utc).timestamp() * 1000)
    assert dm._format_memory_dreaming_day(epoch_ms) == "2025-11-15"


def test_format_memory_dreaming_day_with_timezone() -> None:
    """With a timezone, the day depends on the timezone offset.

    Use Asia/Kathmandu (UTC+5:45) — a point near midnight UTC will
    flip to a different day in KT.
    """
    # 2025-11-15T18:30:00Z = 2025-11-16T00:15:00 in Kathmandu (+5:45)
    epoch_ms = int(datetime(2025, 11, 15, 18, 30, tzinfo=timezone.utc).timestamp() * 1000)
    assert dm._format_memory_dreaming_day(epoch_ms, "Asia/Kathmandu") == "2025-11-16"
    # Sanity: UTC interpretation gives the original day
    assert dm._format_memory_dreaming_day(epoch_ms, "UTC") == "2025-11-15"


def test_format_memory_dreaming_day_unknown_timezone_falls_back_to_utc() -> None:
    """Unknown timezone names fall back to UTC (matches OpenClaw catch)."""
    epoch_ms = int(datetime(2025, 11, 15, 10, 30, tzinfo=timezone.utc).timestamp() * 1000)
    assert dm._format_memory_dreaming_day(epoch_ms, "Mars/Olympus_Mons") == "2025-11-15"


# ── Path resolvers ──────────────────────────────────────────────────────


def test_resolve_daily_memory_path(tmp_path: Path) -> None:
    """Returns ``<workspace>/memory/<iso>.md``."""
    epoch_ms = int(datetime(2025, 11, 15, 10, 30, tzinfo=timezone.utc).timestamp() * 1000)
    path = dm._resolve_daily_memory_path(str(tmp_path), epoch_ms, "UTC")
    assert path == str(tmp_path / "memory" / "2025-11-15.md")


def test_resolve_separate_report_path(tmp_path: Path) -> None:
    """Returns ``<workspace>/memory/dreaming/<phase>/<iso>.md``."""
    epoch_ms = int(datetime(2025, 11, 15, 10, 30, tzinfo=timezone.utc).timestamp() * 1000)
    light = dm._resolve_separate_report_path(str(tmp_path), "light", epoch_ms, "UTC")
    rem = dm._resolve_separate_report_path(str(tmp_path), "rem", epoch_ms, "UTC")
    deep = dm._resolve_separate_report_path(str(tmp_path), "deep", epoch_ms, "UTC")
    assert light == str(tmp_path / "memory" / "dreaming" / "light" / "2025-11-15.md")
    assert rem == str(tmp_path / "memory" / "dreaming" / "rem" / "2025-11-15.md")
    assert deep == str(tmp_path / "memory" / "dreaming" / "deep" / "2025-11-15.md")


# ── Storage mode predicates ────────────────────────────────────────────


def test_should_write_inline_modes() -> None:
    """Inline writes happen for ``inline`` and ``both`` modes."""
    assert dm._should_write_inline({"mode": "inline"}) is True
    assert dm._should_write_inline({"mode": "both"}) is True
    assert dm._should_write_inline({"mode": "separate"}) is False
    # Missing mode: defaults to "separate" → inline is off.
    assert dm._should_write_inline({}) is False


def test_should_write_separate_modes() -> None:
    """Separate writes happen for ``separate``/``both`` OR legacy ``separateReports``."""
    assert dm._should_write_separate({"mode": "separate"}) is True
    assert dm._should_write_separate({"mode": "both"}) is True
    assert dm._should_write_separate({"mode": "inline"}) is False
    # Legacy flag
    assert dm._should_write_separate({"mode": "inline", "separateReports": True}) is True
    assert dm._should_write_separate({"mode": "inline", "separateReports": False}) is False
    # Defaults
    assert dm._should_write_separate({}) is False


# ── Managed markdown block helper (inlined copy) ──────────────────────


def test_replace_managed_markdown_block_replaces_existing() -> None:
    """If both markers exist, replace the block in place."""
    original = (
        "# Top\n\n## Light Sleep\n\n"
        f"{dm._resolve_phase_markers('light')['start']}\nold body\n"
        f"{dm._resolve_phase_markers('light')['end']}\n\n# Footer\n"
    )
    markers = dm._resolve_phase_markers("light")
    updated = dm._replace_managed_markdown_block(
        original=original,
        body="new body line",
        start_marker=markers["start"],
        end_marker=markers["end"],
        heading="## Light Sleep",
    )
    assert "new body line" in updated
    assert "old body" not in updated
    # Footer preserved
    assert updated.endswith("# Footer\n")


def test_replace_managed_markdown_block_appends_when_missing() -> None:
    """If no block exists, append a new section with markers."""
    markers = dm._resolve_phase_markers("rem")
    original = "# Top\n"
    updated = dm._replace_managed_markdown_block(
        original=original,
        body="rem body line",
        start_marker=markers["start"],
        end_marker=markers["end"],
        heading="## REM Sleep",
    )
    assert updated.startswith("# Top\n")
    assert "## REM Sleep" in updated
    assert markers["start"] in updated
    assert "rem body line" in updated
    assert markers["end"] in updated


# ── write_daily_dreaming_phase_block ───────────────────────────────────


def test_write_daily_phase_block_inline_only(tmp_path: Path) -> None:
    """Storage mode ``inline``: write the managed block, no separate report."""
    result = asyncio.run(
        dm.write_daily_dreaming_phase_block(
            workspace_dir=str(tmp_path),
            phase="light",
            body_lines=["- entry 1", "- entry 2"],
            storage={"mode": "inline"},
        )
    )
    assert "inlinePath" in result
    assert "reportPath" not in result

    # Inline path is `<workspace>/memory/<iso>.md` (UTC day)
    inline = result["inlinePath"]
    assert inline.startswith(str(tmp_path))
    assert inline.endswith(".md")
    assert os.path.isfile(inline)
    content = open(inline, encoding="utf-8").read()
    assert "## Light Sleep" in content
    assert dm._resolve_phase_markers("light")["start"] in content
    assert "- entry 1" in content
    assert "- entry 2" in content


def test_write_daily_phase_block_separate_only(tmp_path: Path) -> None:
    """Storage mode ``separate``: no inline block; write a separate report file."""
    result = asyncio.run(
        dm.write_daily_dreaming_phase_block(
            workspace_dir=str(tmp_path),
            phase="rem",
            body_lines=["rem-1"],
            storage={"mode": "separate"},
        )
    )
    assert "inlinePath" not in result
    assert "reportPath" in result

    report = result["reportPath"]
    assert report.startswith(str(tmp_path))
    # Path is cross-platform: check via os.path components
    expected_suffix = os.path.join("memory", "dreaming", "rem")
    assert expected_suffix in report
    content = open(report, encoding="utf-8").read()
    assert content.startswith("# REM Sleep")
    assert "rem-1" in content


def test_write_daily_phase_block_both(tmp_path: Path) -> None:
    """Storage mode ``both``: write inline + separate report."""
    result = asyncio.run(
        dm.write_daily_dreaming_phase_block(
            workspace_dir=str(tmp_path),
            phase="light",
            body_lines=["- both"],
            storage={"mode": "both"},
        )
    )
    assert "inlinePath" in result
    assert "reportPath" in result
    assert os.path.isfile(result["inlinePath"])
    assert os.path.isfile(result["reportPath"])


def test_write_daily_phase_block_empty_body_uses_placeholder(tmp_path: Path) -> None:
    """Empty body lines → ``- No notable updates.`` placeholder."""
    result = asyncio.run(
        dm.write_daily_dreaming_phase_block(
            workspace_dir=str(tmp_path),
            phase="light",
            body_lines=[],
            storage={"mode": "inline"},
        )
    )
    content = open(result["inlinePath"], encoding="utf-8").read()
    assert "- No notable updates." in content


def test_write_daily_phase_block_replaces_existing_block(tmp_path: Path) -> None:
    """Second call with new body replaces the existing inline block in place."""
    args = {
        "workspace_dir": str(tmp_path),
        "phase": "light",
        "storage": {"mode": "inline"},
    }
    first = asyncio.run(dm.write_daily_dreaming_phase_block(body_lines=["first-unique"], **args))
    second = asyncio.run(dm.write_daily_dreaming_phase_block(body_lines=["second-unique"], **args))
    # Same inline path (same day)
    assert first["inlinePath"] == second["inlinePath"]
    content = open(first["inlinePath"], encoding="utf-8").read()
    assert "second-unique" in content
    assert "first-unique" not in content


# ── write_deep_dreaming_report ─────────────────────────────────────────


def test_write_deep_dreaming_report_updates_dreams(tmp_path: Path) -> None:
    """The deep report always updates ``DREAMS.md`` (delegated to update_deep_dreams_file)."""
    report_path = asyncio.run(
        dm.write_deep_dreaming_report(
            workspace_dir=str(tmp_path),
            body_lines=["- d1", "- d2"],
            storage={"mode": "separate"},  # separate + inline (DREAMS.md is always written)
        )
    )
    # Separate report was written
    assert report_path is not None
    expected_suffix = os.path.join("memory", "dreaming", "deep")
    assert expected_suffix in report_path
    report_content = open(report_path, encoding="utf-8").read()
    assert report_content.startswith("# Deep Sleep")
    assert "- d1" in report_content

    # DREAMS.md also has the deep block
    dreams = (tmp_path / "DREAMS.md").read_text(encoding="utf-8")
    assert "## Deep Sleep" in dreams
    assert df.DEEP_START_MARKER in dreams
    assert df.DEEP_END_MARKER in dreams
    assert "- d1" in dreams
    assert "- d2" in dreams


def test_write_deep_dreaming_report_no_separate(tmp_path: Path) -> None:
    """Storage mode ``inline`` → no separate report, only DREAMS.md updated."""
    report_path = asyncio.run(
        dm.write_deep_dreaming_report(
            workspace_dir=str(tmp_path),
            body_lines=["- only-inline"],
            storage={"mode": "inline"},
        )
    )
    # No separate file
    assert report_path is None
    # But DREAMS.md is still updated
    dreams = (tmp_path / "DREAMS.md").read_text(encoding="utf-8")
    assert "## Deep Sleep" in dreams
    assert "- only-inline" in dreams


def test_write_deep_dreaming_report_empty_body_uses_placeholder(tmp_path: Path) -> None:
    """Empty body lines → ``- No durable changes.`` placeholder in DREAMS.md."""
    asyncio.run(
        dm.write_deep_dreaming_report(
            workspace_dir=str(tmp_path),
            body_lines=[],
            storage={"mode": "inline"},
        )
    )
    dreams = (tmp_path / "DREAMS.md").read_text(encoding="utf-8")
    assert "- No durable changes." in dreams


# ── Event emission (best-effort, no SDK) ───────────────────────────────


def test_emit_completed_event_no_sdk_is_silent(tmp_path: Path) -> None:
    """When the SDK event API isn't available, ``_emit_completed_event`` is a no-op."""
    # Don't monkeypatch; the test environment may or may not expose the
    # SDK. Either way, the call should not raise.
    asyncio.run(
        dm._emit_completed_event(
            workspace_dir=str(tmp_path),
            phase="light",
            now_ms=0,
            line_count=0,
            storage_mode="separate",
            inline_path=None,
            report_path=None,
        )
    )
    # No assertions on output — the helper is best-effort.


# ── Phase markers ──────────────────────────────────────────────────────


def test_resolve_phase_markers_light() -> None:
    """Light phase markers use the ``light`` label."""
    markers = dm._resolve_phase_markers("light")
    assert markers["start"] == "<!-- openclaw:dreaming:light:start -->"
    assert markers["end"] == "<!-- openclaw:dreaming:light:end -->"


def test_resolve_phase_markers_rem() -> None:
    """REM phase markers use the ``rem`` label."""
    markers = dm._resolve_phase_markers("rem")
    assert markers["start"] == "<!-- openclaw:dreaming:rem:start -->"
    assert markers["end"] == "<!-- openclaw:dreaming:rem:end -->"


# ── Phase heading maps ─────────────────────────────────────────────────


def test_daily_phase_headings() -> None:
    """The DAILY_PHASE_HEADINGS map covers light + rem (not deep)."""
    assert dm.DAILY_PHASE_HEADINGS == {
        "light": "## Light Sleep",
        "rem": "## REM Sleep",
    }


def test_daily_phase_labels() -> None:
    """The DAILY_PHASE_LABELS map covers light + rem (not deep)."""
    assert dm.DAILY_PHASE_LABELS == {"light": "light", "rem": "rem"}
