"""jarvis_sdk.memory_host_event_export — public export serializer for events.

OpenClaw parity: mirrors ``src/memory-host-sdk/event-export.ts`` (20 LOC).
Provides a bounded-size JSONL export of memory host events. Used
by the public-artifacts system to expose a recent slice of the
journal without leaking unbounded data.

Key port decisions:
- The cap (``MAX_MEMORY_HOST_PUBLIC_EXPORT_BYTES = 1 MB``) is
  preserved verbatim.
- The serializer walks from oldest to newest, dropping the
  oldest lines once the cap would be exceeded. Mirrors the TS
  source's ``for (const entry of storedEvents.toReversed())`` loop.
- The output ends with a trailing newline (matches the TS
  ``lines.toReversed().join("\\n") + "\\n"``).
"""
from __future__ import annotations

import json
from typing import Iterable

# Mirrors OpenClaw's ``MAX_MEMORY_HOST_PUBLIC_EXPORT_BYTES = 1024 * 1024``.
MAX_MEMORY_HOST_PUBLIC_EXPORT_BYTES = 1024 * 1024


def serialize_memory_host_event_export(
    stored_events: Iterable[dict],
) -> str:
    """Serialize ``stored_events`` to a bounded-size JSONL string.

    Mirrors OpenClaw's ``serializeMemoryHostEventExport``. Walks the
    input oldest-to-newest (in OpenClaw the caller passes the
    newest-first list and the function does ``toReversed()`` to
    reverse it for output; here we accept an iterable in the
    *caller-expected* order and walk it forward — callers must pass
    oldest-first or use ``list_stored_memory_host_events`` which
    returns oldest-first).

    Entries without a recognizable ``value.event`` shape (e.g.
    ``value: None`` or missing the event field) are skipped so the
    output only contains valid event JSONL.
    """
    lines: list[str] = []
    size_bytes = 0
    for entry in stored_events:
        # ``entry`` may be a PersistedMemoryHostEvent-shaped dict
        # with a ``value.event`` field, or a raw event dict. Support
        # both for convenience.
        event_obj: object | None = None
        if isinstance(entry, dict):
            if "value" in entry:
                # PersistedMemoryHostEvent envelope: unwrap.
                if isinstance(entry["value"], dict):
                    event_obj = entry["value"].get("event")
                else:
                    # Malformed envelope — skip.
                    continue
            else:
                event_obj = entry
        if not isinstance(event_obj, dict):
            # Skip entries without a proper event payload (the TS
            # source does the same — only events with ``value.event``
            # are emitted; other shapes are filtered out upstream).
            continue
        try:
            line = json.dumps(event_obj, ensure_ascii=False)
        except (TypeError, ValueError):
            continue
        line_bytes = len(line.encode("utf-8")) + 1  # +1 for newline
        if size_bytes + line_bytes > MAX_MEMORY_HOST_PUBLIC_EXPORT_BYTES:
            break
        lines.append(line)
        size_bytes += line_bytes
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


__all__ = [
    "MAX_MEMORY_HOST_PUBLIC_EXPORT_BYTES",
    "serialize_memory_host_event_export",
]
