"""jarvis_normalization_core.json_coerce — non-throwing JSON parsing.

OpenClaw parity: mirrors ``@openclaw/normalization-core/json-coercion``
(``safeParseJson``, ``safeParseJsonRecord``).

Python's ``json.loads`` accepts ``NaN``/``Infinity`` constants that
``JSON.parse`` rejects, so constants are refused explicitly to keep
the accept language identical.
"""

from __future__ import annotations

import json
import re
from typing import Any

#: Payload must open with ``{`` (after leading whitespace) to be a record.
_RECORD_OPEN_RE = re.compile(r"[\t\n\r ]*\{")


def _reject_constant(value: str) -> Any:
    raise ValueError(f"invalid JSON constant: {value!r}")


def safe_parse_json(value: object) -> Any:
    """Parse JSON without throwing; ``None`` for invalid input."""
    if not isinstance(value, str):
        return None
    try:
        return json.loads(value, parse_constant=_reject_constant)
    except ValueError:
        return None


def safe_parse_json_record(value: object) -> dict[str, Any] | None:
    """Parse JSON into a non-array record; ``None`` for every other result."""
    if not isinstance(value, str) or not _RECORD_OPEN_RE.match(value):
        return None
    parsed = safe_parse_json(value)
    return parsed if isinstance(parsed, dict) else None


__all__ = ["safe_parse_json", "safe_parse_json_record"]
