"""jarvis.agents.embedded_agent_runner.model_context_tokens — read model context-token metadata.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/model-context-tokens.ts``.

Public surface (mirrors the OpenClaw source):

- :func:`read_agent_model_context_tokens` — return the
  context-token metadata from a resolved model record, or
  ``None`` if the field is missing or non-finite.

Phase 7.3a — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Optional


def read_agent_model_context_tokens(
    model: Any,
) -> Optional[int]:
    """Read context-token metadata from a resolved model record.

    Mirrors :func:`readAgentModelContextTokens``
    (``model-context-tokens.ts:13-18``).
    """
    if model is None:
        return None
    if isinstance(model, dict):
        value = model.get("contextTokens")
    else:
        value = getattr(model, "contextTokens", None)
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        import math
        if not math.isfinite(value):
            return None
        try:
            return int(value)
        except (TypeError, ValueError, OverflowError):
            return None
    return None


__all__ = ["read_agent_model_context_tokens"]
