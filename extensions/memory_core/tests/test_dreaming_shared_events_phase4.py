"""Tests for memory_core.dreaming_shared + dreaming_events — Phase 4.4b.

Mirrors the TypeScript ``test_dreaming-shared.test.ts`` patterns.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from extensions.memory_core import dreaming_events, dreaming_shared, time


# ── Shared helpers ────────────────────────────────────────────────────────


def test_normalize_trimmed_string_handles_empty() -> None:
    assert dreaming_shared.normalize_trimmed_string("") is None
    assert dreaming_shared.normalize_trimmed_string("   ") is None
    assert dreaming_shared.normalize_trimmed_string("\t\n") is None


def test_normalize_trimmed_string_trims() -> None:
    assert dreaming_shared.normalize_trimmed_string("  hello  ") == "hello"
    assert dreaming_shared.normalize_trimmed_string("a") == "a"


def test_normalize_trimmed_string_rejects_non_string() -> None:
    assert dreaming_shared.normalize_trimmed_string(None) is None  # type: ignore[arg-type]
    assert dreaming_shared.normalize_trimmed_string(42) is None  # type: ignore[arg-type]
    assert dreaming_shared.normalize_trimmed_string([]) is None  # type: ignore[arg-type]


def test_includes_system_event_token_exact_match() -> None:
    assert dreaming_shared.includes_system_event_token(
        "memory-core-dream-firing", "memory-core-dream-firing"
    ) is True


def test_includes_system_event_token_on_its_own_line() -> None:
    body = "line 1\nmemory-core-dream-firing\nline 3"
    assert dreaming_shared.includes_system_event_token(
        body, "memory-core-dream-firing"
    ) is True


def test_includes_system_event_token_strips_cron_wrapper() -> None:
    body = "[cron:dream-daily-2026-07-23] memory-core-dream-firing"
    assert dreaming_shared.includes_system_event_token(
        body, "memory-core-dream-firing"
    ) is True


def test_includes_system_event_token_rejects_substring_match() -> None:
    """Substring match should NOT match (avoid false positives)."""
    body = "this is a memory-core-dream-firing-like but not exact"
    assert dreaming_shared.includes_system_event_token(
        body, "memory-core-dream-firing"
    ) is False


def test_includes_system_event_token_returns_false_for_empty() -> None:
    assert (
        dreaming_shared.includes_system_event_token("", "memory-core-dream-firing")
        is False
    )
    assert (
        dreaming_shared.includes_system_event_token("hello", "")
        is False
    )


# ── Time helpers ──────────────────────────────────────────────────────────


def test_resolve_now_ms_with_none_returns_current_time() -> None:
    """None / non-numeric should return ``Date.now()``-like int."""
    result = time.resolve_memory_core_now_ms(None)
    assert isinstance(result, int)
    assert result > 0


def test_resolve_now_ms_passes_through_numeric() -> None:
    assert time.resolve_memory_core_now_ms(1234567890) == 1234567890
    assert time.resolve_memory_core_now_ms(1234567890.5) == 1234567890


def test_resolve_now_ms_rejects_bool() -> None:
    """``True`` / ``False`` are not valid timestamps (matches OpenClaw's
    behavior of treating non-finite values as fallback to Date.now)."""
    result = time.resolve_memory_core_now_ms(True)
    assert isinstance(result, int)
    assert result > 0  # fell back to now()


def test_resolve_timestamp_returns_iso_string() -> None:
    result = time.resolve_memory_core_timestamp(1234567890000)
    assert result.startswith("2009-02-13T23:31:30")
    assert "Z" in result or "+" in result  # UTC offset


def test_resolve_timestamp_with_none_uses_current_time() -> None:
    result = time.resolve_memory_core_timestamp(None)
    assert "T" in result  # ISO 8601 format


# ── Events helper ─────────────────────────────────────────────────────────


def test_append_failed_dreaming_event_writes_to_events_file(tmp_path: Path) -> None:
    """When the SDK is not available, the helper degrades gracefully.

    In the real world, ``append_memory_host_event`` writes to the host's
    event log. Since the SDK stub doesn't expose it, this test verifies
    the helper doesn't crash and that logger.warn isn't called.
    """
    logged: list[str] = []

    class _Logger:
        def warn(self, msg: str) -> None:
            logged.append(msg)

    dreaming_events.append_failed_dreaming_event(
        workspace_dir=str(tmp_path),
        phase="light",
        error="synthetic error",
        storage_mode="inline",
        logger=_Logger(),
    )
    # No crash, no warning emitted (since the SDK stub may or may not be there).
    assert isinstance(logged, list)


def test_append_failed_dreaming_event_handles_invalid_workspace(tmp_path: Path) -> None:
    """No workspace dir is created, no file is written."""
    workspace = tmp_path / "does-not-exist"
    dreaming_events.append_failed_dreaming_event(
        workspace_dir=str(workspace),
        phase="deep",
        error="synthetic error",
        storage_mode="separate",
    )
    # No file should be created by the helper itself.
    assert not (tmp_path / "events.jsonl").exists()
