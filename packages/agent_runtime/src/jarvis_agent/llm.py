"""jarvis_agent.llm — provider-layer compatibility barrel.

OpenClaw parity: ``packages/agent-core/src/llm.ts`` (2 lines):
``export * from "@openclaw/ai"``.

Consumers that imported LLM primitives through agent-core keep working
without depending on the provider package directly. New code should import
from :mod:`jarvis_llm`; this module exists so the agent package's surface
matches the TS package's surface file-for-file.
"""

from __future__ import annotations

from jarvis_llm import *  # noqa: F403 - parity: `export * from "@openclaw/ai"`
from jarvis_llm import __all__ as _llm_all

__all__ = list(_llm_all)
