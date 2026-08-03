"""jarvis.agents.embedded_agent_runner.run — public embedded-agent run entrypoint.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run.ts``.

This module re-exports :func:`run_embedded_agent` from the orchestrator.

Phase 7.6h-3 — focused minimal port.
"""
from __future__ import annotations

from .run_orchestrator import run_embedded_agent


__all__ = ["run_embedded_agent"]
