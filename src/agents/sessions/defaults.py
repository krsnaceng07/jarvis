"""jarvis.agents.sessions.defaults — session defaults.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/defaults.ts``.

Centralizes fallback thinking settings for sessions
without model-specific overrides.

Parity
======
- ``DEFAULT_THINKING_LEVEL: ThinkingLevel = "medium"`` —
  the canonical OpenClaw constant. Matches
  ``defaults.ts:9`` exactly.
- The single export is a module-level constant (not
  a function), matching the OpenClaw source.

Phase 6.0 — scaffolding + helpers + small types. This
module has no dependencies and is safe to port first.
"""
from __future__ import annotations

from typing import Literal

# Mirror the OpenClaw ``ThinkingLevel`` union; the
# canonical enum lives in ``jarvis_agent.types`` (the
# agent-core port) so we keep the local literal in
# lockstep.
ThinkingLevel = Literal[
    "off", "minimal", "low", "medium", "high", "xhigh", "max"
]

#: Default thinking level for sessions that do not
#: specify a model-specific override. Mirrors
#: ``DEFAULT_THINKING_LEVEL`` in
#: ``openclaw-main/src/agents/sessions/defaults.ts:9``.
DEFAULT_THINKING_LEVEL: ThinkingLevel = "medium"


#: Mirrors ``DEFAULT_PROVIDER``
#: (``openclaw-main/src/agents/defaults.ts:3``).
#: Phase 6.7c re-uses this for the
#: model-resolver's "no model found" fallback
#: selection.
DEFAULT_PROVIDER: str = "openai"


#: Mirrors ``DEFAULT_MODEL``
#: (``openclaw-main/src/agents/defaults.ts:4``).
DEFAULT_MODEL: str = "gpt-5.6-sol"


#: The full ordered list of thinking
#: levels. Mirrors the OpenClaw source's
#: ``THINKING_LEVELS`` local in
#: ``agent-session-models.ts:12``. The
#: base list (``THINKING_LEVELS_BASE``)
#: mirrors the OpenClaw literal; the
#: Python port extends it with the
#: ``"xhigh"`` + ``"max"`` levels that
#: the OpenClaw ``ThinkingLevel`` union
#: already accepts (Phase 6.0).
THINKING_LEVELS: tuple[ThinkingLevel, ...] = (
    "off",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
)


__all__ = [
    "DEFAULT_MODEL",
    "DEFAULT_PROVIDER",
    "DEFAULT_THINKING_LEVEL",
    "THINKING_LEVELS",
    "ThinkingLevel",
]
