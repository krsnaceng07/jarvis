"""jarvis.agents.embedded_agent_runner.cli_backend_dispatch_eligibility — dispatch eligibility.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/cli-backend-dispatch-eligibility.ts``.

Public surface:

- :func:`resolve_embedded_cli_backend_dispatch_eligibility`

Phase 7.6h-4 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


# Installable hooks ---------------------------------------------------------

_resolve_embedded_cli_backend_dispatch_eligibility_hook = None


def set_resolve_embedded_cli_backend_dispatch_eligibility_hook(fn) -> None:
    global _resolve_embedded_cli_backend_dispatch_eligibility_hook
    _resolve_embedded_cli_backend_dispatch_eligibility_hook = fn


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_embedded_cli_backend_dispatch_eligibility(
    params: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Decide whether an opted-in embedded run would execute through the CLI backend.

    Mirrors :func:`resolveEmbeddedCliBackendDispatchEligibility`
    (``cli-backend-dispatch-eligibility.ts``).
    """
    if _resolve_embedded_cli_backend_dispatch_eligibility_hook is not None:
        v = _resolve_embedded_cli_backend_dispatch_eligibility_hook(params)
        return v if v is None or isinstance(v, dict) else None
    provider = (params.get("provider") or "").strip().lower()
    # Focused minimal port: only `claude-cli` (and any explicit CLI-runtime id
    # declared in the backends runtime) routes to CLI. Other providers fall
    # through to the native passthrough.
    if not provider:
        return None
    if provider in ("claude-cli", "codex-cli", "gemini-cli"):
        return {"provider": provider}
    return None


__all__ = [
    "resolve_embedded_cli_backend_dispatch_eligibility",
    "set_resolve_embedded_cli_backend_dispatch_eligibility_hook",
]
