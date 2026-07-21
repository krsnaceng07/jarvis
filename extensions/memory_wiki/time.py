"""time — memory-wiki timestamp resolver.

OpenClaw parity: mirrors ``extensions/memory-wiki/src/time.ts``.

Used by ``log.py`` to stamp vault-init / vault-generation
/ compile / ingest / lint log entries. The helper
delegates to ``jarvis_sdk.timestamp_ms_to_iso_string`` and
falls back to ``datetime.now(UTC)`` for out-of-range
injected values (the same fallback the OpenClaw test
suite uses).
"""

from __future__ import annotations

import time as _time
from datetime import datetime, timezone

from jarvis_sdk import timestamp_ms_to_iso_string


def resolve_memory_wiki_timestamp(now_ms: int | float | None = None) -> str:
    """Return an ISO 8601 string for ``now_ms`` (or the current time).

    Mirrors OpenClaw's ``resolveMemoryWikiTimestamp``.
    Falls back to the current wall clock for injected
    values that are out of the representable
    ``datetime`` range (year > 9999 etc.) and to the
    current wall clock when ``now_ms`` is ``None``.
    Always returns a millisecond-precision UTC string.
    """
    iso = timestamp_ms_to_iso_string(now_ms)
    if iso is not None:
        return iso
    return (
        datetime.fromtimestamp(_time.time(), tz=timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


__all__ = ["resolve_memory_wiki_timestamp"]
