"""memory_core.dreaming_shared — shared helpers for the dreaming pipeline.

OpenClaw parity: mirrors ``extensions/memory-core/src/dreaming-shared.ts``
(31 LOC). Provides:

- ``as_record`` — re-export of ``asNullableRecord`` from the SDK's
  string-coerce runtime.
- ``format_error_message`` — re-export of ``formatErrorMessage`` from
  the SDK's error runtime.
- ``normalize_trimmed_string`` — strim-whitespace + drop-empty.
- ``includes_system_event_token`` — line-by-line substring match for
  the dreaming system event token (used to detect cron firings).
"""

from __future__ import annotations

from typing import Any


# ── Re-exports from jarvis_sdk string-coerce ────────────────────────────
# Mirrors OpenClaw's:
#   export { asNullableRecord as asRecord } from "openclaw/plugin-sdk/string-coerce-runtime";
# The JARVIS SDK exposes ``as_optional_record`` (Python idiomatic name).
# We re-export it under both names so callers can use either
# ``from extensions.memory_core.dreaming_shared import as_record``
# (OpenClaw-compatible) or ``as_optional_record`` (JARVIS-idiomatic).
from jarvis_normalization_core.string_coerce import as_optional_record as as_record  # type: ignore[attr-defined]


def format_error_message(err: object) -> str:
    """Format an exception / error value as a single-line string.

    Mirrors OpenClaw's ``formatErrorMessage`` from
    ``openclaw/plugin-sdk/error-runtime``. The JARVIS SDK doesn't yet
    have an ``error_runtime`` module (planned for a future phase), so
    we inline a minimal Python equivalent that handles:
    - ``Exception`` instances → ``type(message) + str(message)`` (single line)
    - ``str`` instances → the string itself (single line, no newlines)
    - everything else → ``type(err).__name__``
    """
    if isinstance(err, BaseException):
        msg = str(err) or err.__class__.__name__
        # Collapse newlines for single-line log output.
        msg = " ".join(msg.split())
        return f"{err.__class__.__name__}: {msg}"
    if isinstance(err, str):
        return " ".join(err.split())
    return type(err).__name__


# ── Local helpers ─────────────────────────────────────────────────────────


def normalize_trimmed_string(value: Any) -> str | None:
    """Trim whitespace; return ``None`` if the result is empty.

    Mirrors OpenClaw's ``normalizeTrimmedString``. Accepts ``unknown``
    (per the OpenClaw signature) — non-strings return ``None``.
    """
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed if len(trimmed) > 0 else None


# OpenClaw cron wrappers emit lines like:
#   [cron:dream-daily-2026-07-23] dreaming daily sweep fired
# We need to recognize the "system event token" (e.g. the cron tag) on
# its own line, NOT as a substring of a longer user message (to avoid
# false positives).
_CRON_WRAPPER_PREFIX = "[cron:"


def includes_system_event_token(cleaned_body: str, event_text: str) -> bool:
    """Return ``True`` if ``cleaned_body`` contains ``event_text`` as a
    standalone line (after stripping a known ``[cron:<id>]`` wrapper).

    Mirrors OpenClaw's ``includesSystemEventToken``. Used by the dreaming
    pipeline to detect that a cron job actually fired (vs. a user message
    that happens to mention the cron tag in passing).

    Rules:
    1. Both inputs are normalized via ``normalize_trimmed_string``.
    2. If either is empty/None, return ``False``.
    3. If the body equals the event text exactly, return ``True``.
    4. Otherwise split the body by newlines and check each line:
       a. If the trimmed line equals the event text, return ``True``.
       b. If the line starts with ``[cron:<id>]`` and the remainder (after
          the prefix + space) equals the event text, return ``True``.
       c. Otherwise continue.
    5. If no line matched, return ``False``.
    """
    normalized_body = normalize_trimmed_string(cleaned_body)
    normalized_event = normalize_trimmed_string(event_text)
    if normalized_body is None or normalized_event is None:
        return False
    if normalized_body == normalized_event:
        return True
    for line in normalized_body.splitlines():
        trimmed = line.strip()
        if trimmed == normalized_event:
            return True
        # Strip the [cron:<id>] prefix if present.
        if trimmed.startswith(_CRON_WRAPPER_PREFIX):
            rest = trimmed[len(_CRON_WRAPPER_PREFIX) :]
            closing = rest.find("]")
            if closing != -1:
                stripped = rest[closing + 1 :].strip()
                if stripped == normalized_event:
                    return True
    return False


__all__ = [
    # Re-exports
    "as_record",
    "format_error_message",
    # Local helpers
    "normalize_trimmed_string",
    "includes_system_event_token",
]
