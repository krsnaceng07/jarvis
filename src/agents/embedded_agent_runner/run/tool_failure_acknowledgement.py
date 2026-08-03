"""jarvis.agents.embedded_agent_runner.run.tool_failure_acknowledgement — check for explicit mutating-tool-failure acknowledgement.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/tool-failure-acknowledgement.ts``.

Public surface:

- :func:`has_explicit_mutating_tool_failure_acknowledgement`

Phase 7.6g — focused minimal port.
"""
from __future__ import annotations

import re
from typing import Any


#: Pattern that signals an explicit mutating-tool-failure
#: acknowledgement in the user-visible text. Mirrors the OpenClaw
#: source's inline regex (``tool-failure-acknowledgement.ts``).
_EXPLICIT_MUTATING_TOOL_FAILURE_ACK_RE: "re.Pattern[str]" = re.compile(
    r"\b(?:proceed|continue)\s*(?:with|after)?\s*(?:the|this|that)?\s*"
    r"(?:tool|edit|write|delete|update|mutation|fix|change)s?\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def has_explicit_mutating_tool_failure_acknowledgement(
    text: str,
) -> bool:
    """Return True when ``text`` carries an explicit mutating-tool-failure ack.

    Mirrors :func:`hasExplicitMutatingToolFailureAcknowledgement`
    (``tool-failure-acknowledgement.ts``).
    """
    if not isinstance(text, str) or not text:
        return False
    return bool(_EXPLICIT_MUTATING_TOOL_FAILURE_ACK_RE.search(text))


__all__ = [
    "has_explicit_mutating_tool_failure_acknowledgement",
]
