"""Tests for extensions/memory_wiki/time.py.

Phase 4.3a: ports the active-memory
``resolveMemoryWikiTimestamp`` helper. The tests focus on:

- A valid injected timestamp produces the expected
  ISO 8601 string with millisecond precision.
- An out-of-range injected timestamp falls back to
  the current wall clock.
- A ``None`` injected timestamp resolves to the
  current wall clock.
"""

# pyright: reportArgumentType=false
# pyright: reportAttributeAccessIssue=false
# pyright: reportCallIssue=false
# pyright: reportGeneralTypeIssues=false
# pyright: reportIndexIssue=false
# pyright: reportOptionalMemberAccess=false
# pyright: reportOptionalSubscript=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportReturnType=false
# pyright: reportTypedDictNotRequiredAccess=false

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
for _candidate in (
    ROOT / "packages" / "plugin_sdk" / "src",
    ROOT / "apps" / "desktop" / "src",
):
    _candidate_str = str(_candidate)
    if _candidate_str not in sys.path:
        sys.path.insert(0, _candidate_str)

import pytest  # noqa: E402

from extensions.memory_wiki.time import resolve_memory_wiki_timestamp  # noqa: E402


class TestResolveMemoryWikiTimestamp:
    def test_valid_injected_timestamp(self) -> None:
        # 2026-04-05T12:00:00.000Z
        ts_ms = int(datetime(2026, 4, 5, 12, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
        out = resolve_memory_wiki_timestamp(ts_ms)
        assert out == "2026-04-05T12:00:00.000Z"

    def test_out_of_range_injected_timestamp_falls_back_to_now(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Anything past year 9999 makes ``datetime`` raise
        # OverflowError; the helper must fall back to the
        # current wall clock instead of propagating.
        # We mock ``time.time`` to return a known
        # wall-clock value so the assertion is
        # deterministic.
        fixed_now = 1_780_000_000.0
        monkeypatch.setattr("extensions.memory_wiki.time._time.time", lambda: fixed_now)
        out = resolve_memory_wiki_timestamp(8_640_000_000_000_001)
        # Parse the output and compare to the expected
        # wall-clock UTC datetime, ignoring the
        # floating-point rounding on the seconds.
        parsed = datetime.fromisoformat(out.replace("Z", "+00:00"))
        expected = datetime.fromtimestamp(fixed_now, tz=timezone.utc)
        assert abs((parsed - expected).total_seconds()) < 0.001
        assert out.endswith("Z")

    def test_none_injected_timestamp_uses_now(self) -> None:
        # The fallback path is exercised whenever
        # ``now_ms`` is None; the only contract is that
        # the helper returns a valid ISO string.
        out = resolve_memory_wiki_timestamp(None)
        assert out.endswith("Z")
        # The string should round-trip back to a
        # recent datetime.
        parsed = datetime.fromisoformat(out.replace("Z", "+00:00"))
        delta = abs((datetime.now(tz=timezone.utc) - parsed).total_seconds())
        assert delta < 5

    def test_returns_millisecond_precision(self) -> None:
        ts_ms = int(datetime(2026, 1, 2, 3, 4, 5, 678_000, tzinfo=timezone.utc).timestamp() * 1000)
        out = resolve_memory_wiki_timestamp(ts_ms)
        assert out == "2026-01-02T03:04:05.678Z"
