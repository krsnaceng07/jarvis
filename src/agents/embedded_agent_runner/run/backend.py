"""jarvis.agents.embedded_agent_runner.run.backend — detect the active backend.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/backend.ts``.

Public surface:

- :func:`detect_active_backend`

Phase 7.6h-2 — focused minimal port.
"""
from __future__ import annotations

import os
from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Known backend ids.
BACKEND_CLAUDE: str = "claude"
BACKEND_CODEX: str = "codex"
BACKEND_GEMINI: str = "gemini"


# ---------------------------------------------------------------------------
# Helpers (ported as-is)
# ---------------------------------------------------------------------------


def _detect_active_backend() -> str:
    """Detect the active backend from the environment.

    Mirrors :func:`detectActiveBackend` (``backend.ts``).
    """
    backend = os.environ.get("OPENCLAW_BACKEND", "").strip().lower()
    if backend in (BACKEND_CLAUDE, BACKEND_CODEX, BACKEND_GEMINI):
        return backend
    if os.environ.get("CLAUDECODE"):
        return BACKEND_CLAUDE
    if os.environ.get("CODEX_HOME"):
        return BACKEND_CODEX
    if os.environ.get("GEMINI_API_KEY"):
        return BACKEND_GEMINI
    return BACKEND_CLAUDE


#: Cache the detected backend.
_DETECTED_BACKEND: Optional[str] = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_active_backend() -> str:
    """Return the active backend id.

    Mirrors :func:`detectActiveBackend` (``backend.ts``).
    """
    global _DETECTED_BACKEND
    if _DETECTED_BACKEND is None:
        _DETECTED_BACKEND = _detect_active_backend()
    return _DETECTED_BACKEND


def reset_active_backend_cache() -> None:
    """Reset the cached active-backend detection."""
    global _DETECTED_BACKEND
    _DETECTED_BACKEND = None


__all__ = [
    "BACKEND_CLAUDE",
    "BACKEND_CODEX",
    "BACKEND_GEMINI",
    "detect_active_backend",
    "reset_active_backend_cache",
]
