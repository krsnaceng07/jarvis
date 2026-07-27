"""Tool validation facade for callers that import validation from the agent.

Port of ``packages/agent-core/src/validation.ts`` (2 lines).

The implementation lives in :mod:`jarvis_llm.validation`, mirroring
OpenClaw's split: ``agent-core`` re-exports from ``@openclaw/ai``. Keeping
the facade — rather than having agent callers import ``jarvis_llm``
directly — preserves the package boundary, so a later change to where
validation lives stays a one-line edit here.
"""

from __future__ import annotations

from jarvis_llm.validation import validate_tool_arguments, validate_tool_call

__all__ = ["validate_tool_arguments", "validate_tool_call"]
