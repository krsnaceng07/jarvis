"""jarvis.agents.sessions.session_file_parser — session-file JSONL parser.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/session-file-parser.ts``.

Public surface (matches the OpenClaw
source):

- :func:`parse_session_file_entries_with_warnings` —
  parse a session-file content
  string into a list of file entries
  + a list of warnings + a
  row-by-entry map. Mirrors
  :func:`parseSessionFileEntriesWithWarnings`
  (``session-file-parser.ts:19-46``).

Phase 6.13a — focused port.

Adaptations
-----------
- The OpenClaw source's
  :func:`isRecord` helper comes
  from
  ``@openclaw/normalization-core/record-coerce``.
  The Python port uses
  :func:`isinstance(value, dict)`
  for the same shape guard.
- The OpenClaw source's
  :class:`FileEntry` type lives
  in :mod:`session-manager.ts`. The
  Python port uses plain ``dict`` at
  runtime (the TypedDict lands in
  6.13+).
"""
from __future__ import annotations

import json
import logging
from typing import Any


_LOG = logging.getLogger("jarvis.agents.sessions.session_file_parser")


#: A session-file parse warning. Mirrors
#: :class:`SessionFileParseWarning`
#: (``session-file-parser.ts:4-7``).
#: The Python port uses a plain dict.
SessionFileParseWarning = dict


def _is_session_file_entry(value: Any) -> bool:
    """Return ``True`` when ``value``
    is a valid session-file entry.
    Mirrors :func:`isSessionFileEntry`
    (``session-file-parser.ts:9-17``).

    Validation:
    - ``value`` is a ``dict`` +
      ``value["type"]`` is a string.
    - For ``"message"`` entries, the
      nested ``value["message"]`` is a
      ``dict`` with a string ``role``.
    """
    if not isinstance(value, dict):
        return False
    if not isinstance(value.get("type"), str):
        return False
    if value.get("type") != "message":
        return True
    message = value.get("message")
    return isinstance(message, dict) and isinstance(
        message.get("role"), str
    )


def parse_session_file_entries_with_warnings(
    content: str,
) -> dict:
    """Parse a session-file content
    string into a list of file entries
    + a list of warnings + a
    row-by-entry map. Mirrors
    :func:`parseSessionFileEntriesWithWarnings`
    (``session-file-parser.ts:19-46``).

    The function tolerates
    ``\\r\\n`` + ``\\n`` line
    endings (the OpenClaw source uses
    ``content.split(/\\r?\\n/u)``).
    Empty lines are skipped. Per-line
    failures emit a warning with the
    row number (1-indexed).

    Returns
    -------
    dict
        ``{"entries": list,
        "warnings": list,
        "rowByEntry": dict[id -> int]}``
        — the Python port's
        ``rowByEntry`` is a plain
        ``dict`` keyed by the entry's
        ``id`` (the OpenClaw source uses
        a ``Map`` keyed by the entry
        object reference; the Python
        port uses the entry's ``id``
        for hashability).
    """
    entries: list = []
    warnings: list = []
    row_by_entry: dict = {}
    rows = content.split("\r\n") if "\r\n" in content else content.split("\n")
    for index, raw_line in enumerate(rows):
        line = raw_line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except (ValueError, TypeError):
            warnings.append({
                "code": "invalid-session-json",
                "row": index + 1,
            })
            continue
        if not _is_session_file_entry(entry):
            warnings.append({
                "code": "invalid-session-row",
                "row": index + 1,
            })
            continue
        entries.append(entry)
        entry_id = entry.get("id")
        if entry_id is not None:
            row_by_entry[entry_id] = index + 1
    return {
        "entries": entries,
        "warnings": warnings,
        "rowByEntry": row_by_entry,
    }


# ============================================================================
# Backwards-compat alias (camelCase
# OpenClaw-style name).
# ============================================================================


parseSessionFileEntriesWithWarnings = (
    parse_session_file_entries_with_warnings
)


__all__ = [
    "SessionFileParseWarning",
    "parse_session_file_entries_with_warnings",
    "parseSessionFileEntriesWithWarnings",
]
