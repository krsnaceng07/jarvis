"""Tests for jarvis_cron_core parser."""

from __future__ import annotations

from datetime import datetime

from jarvis_cron_core.parser import (
    cron_matches,
    field_matches,
    is_iso_timestamp,
)


def test_field_matches() -> None:
    assert field_matches("*", 5, 0, 59)
    assert field_matches("*/5", 10, 0, 59)
    assert not field_matches("*/5", 7, 0, 59)
    assert field_matches("1-5", 3, 0, 59)
    assert not field_matches("1-5", 6, 0, 59)
    assert field_matches("1,3,5", 3, 0, 59)
    assert not field_matches("1,3,5", 4, 0, 59)


def test_cron_matches() -> None:
    # 2026-09-30 is Wednesday (weekday 2 in Python: Mon=0, Tue=1, Wed=2)
    dt = datetime(2026, 9, 30, 14, 30)
    assert cron_matches("30 14 * * *", dt)
    assert cron_matches("*/15 14 * * 2", dt)
    assert not cron_matches("0 14 * * *", dt)
    assert not cron_matches("30 15 * * *", dt)


def test_is_iso_timestamp() -> None:
    assert is_iso_timestamp("2026-09-30T14:30:00")
    assert is_iso_timestamp("2026-01-01T00:00:00.000Z")
    assert not is_iso_timestamp("*/5 * * * *")
    assert not is_iso_timestamp("not-a-timestamp")
