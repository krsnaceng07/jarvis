"""jarvis.agents.sessions.tools.truncate — session tool truncation facade.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/tools/truncate.ts``.

Phase 6.10a — truncation re-export.

The OpenClaw source's ``truncate.ts`` is a
pure re-export of the shared harness
truncation utilities. The Python port does
the same — re-exports the canonical helpers
from :mod:`jarvis_agent.truncate` so the
session tools + agent harness rendering use
one byte/line truncation contract
end-to-end.
"""
from __future__ import annotations

from jarvis_agent.truncate import (
    DEFAULT_MAX_BYTES,
    DEFAULT_MAX_LINES,
    GREP_MAX_LINE_LENGTH,
    TruncationResult,
    format_size,
    truncate_head,
    truncate_line,
    truncate_tail,
)


__all__ = [
    "DEFAULT_MAX_BYTES",
    "DEFAULT_MAX_LINES",
    "GREP_MAX_LINE_LENGTH",
    "TruncationResult",
    "format_size",
    "truncate_head",
    "truncate_line",
    "truncate_tail",
]
