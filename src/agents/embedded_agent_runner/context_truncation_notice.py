"""jarvis.agents.embedded_agent_runner.context_truncation_notice — shared truncation notice text.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/context-truncation-notice.ts``.

Public surface:

- :func:`format_context_limit_truncation_notice`

Phase 7.6h-3 — focused minimal port.
"""
from __future__ import annotations

import math


CONTEXT_LIMIT_TRUNCATION_NOTICE = "more characters truncated"
CONTEXT_LIMIT_TRUNCATION_HINT = "rerun with narrower args if needed"


def format_context_limit_truncation_notice(truncated_chars: int) -> str:
    """Format a compact notice that preserves the approximate number of omitted characters.

    Mirrors :func:`formatContextLimitTruncationNotice` (``context-truncation-notice.ts``).
    """
    safe_chars = max(1, int(math.floor(truncated_chars or 0)))
    return (
        f"[... {safe_chars} {CONTEXT_LIMIT_TRUNCATION_NOTICE}; "
        f"{CONTEXT_LIMIT_TRUNCATION_HINT}]"
    )


__all__ = [
    "CONTEXT_LIMIT_TRUNCATION_NOTICE",
    "CONTEXT_LIMIT_TRUNCATION_HINT",
    "format_context_limit_truncation_notice",
]
