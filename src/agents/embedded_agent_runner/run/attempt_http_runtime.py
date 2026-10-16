"""jarvis.agents.embedded_agent_runner.run.attempt_http_runtime — configure the embedded-attempt HTTP runtime.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-http-runtime.ts``.

Public surface:

- :func:`configure_embedded_attempt_http_runtime`

Phase 7.6e — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Callable, Dict


#: Default HTTP runtime timeout (ms). Mirrors the inline default in
#: ``attempt-http-runtime.ts``.
DEFAULT_EMBEDDED_ATTEMPT_HTTP_TIMEOUT_MS: int = 60_000


#: Installable hook for the configure-embedded-attempt-http-runtime step.
_CONFIGURE_EMBEDDED_ATTEMPT_HTTP_RUNTIME: Callable[
    [Dict[str, Any]], Any
] = lambda _p: None


def set_configure_embedded_attempt_http_runtime_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom configureEmbeddedAttemptHttpRuntime hook."""
    global _CONFIGURE_EMBEDDED_ATTEMPT_HTTP_RUNTIME
    _CONFIGURE_EMBEDDED_ATTEMPT_HTTP_RUNTIME = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def configure_embedded_attempt_http_runtime(
    params: Dict[str, Any],
) -> None:
    """Configure the embedded-attempt HTTP runtime.

    Mirrors :func:`configureEmbeddedAttemptHttpRuntime`
    (``attempt-http-runtime.ts``).
    """
    timeout_ms = int(
        params.get("timeoutMs", DEFAULT_EMBEDDED_ATTEMPT_HTTP_TIMEOUT_MS)
        or DEFAULT_EMBEDDED_ATTEMPT_HTTP_TIMEOUT_MS
    )
    _CONFIGURE_EMBEDDED_ATTEMPT_HTTP_RUNTIME({"timeoutMs": timeout_ms})


__all__ = [
    "DEFAULT_EMBEDDED_ATTEMPT_HTTP_TIMEOUT_MS",
    "configure_embedded_attempt_http_runtime",
    "set_configure_embedded_attempt_http_runtime_hook",
]
