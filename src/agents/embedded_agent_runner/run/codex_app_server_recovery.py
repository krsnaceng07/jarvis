"""jarvis.agents.embedded_agent_runner.run.codex_app_server_recovery — codex-app-server recovery helpers.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/codex-app-server-recovery.ts``.

Public surface:

Functions:

- :func:`has_codex_app_server_recovery_retry_budget`
- :func:`resolve_codex_app_server_recovery_retry`

Phase 7.6g — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Callable, Dict


#: Installable hook for the has-codex-app-server-recovery-retry-budget step.
_HAS_CODEX_APP_SERVER_RECOVERY_RETRY_BUDGET: Callable[
    [Dict[str, Any]], bool
] = lambda _p: False


def set_has_codex_app_server_recovery_retry_budget_hook(
    hook: Callable[[Dict[str, Any]], bool],
) -> None:
    """Install a custom hasCodexAppServerRecoveryRetryBudget hook."""
    global _HAS_CODEX_APP_SERVER_RECOVERY_RETRY_BUDGET
    _HAS_CODEX_APP_SERVER_RECOVERY_RETRY_BUDGET = hook


#: Installable hook for the resolve-codex-app-server-recovery-retry step.
_RESOLVE_CODEX_APP_SERVER_RECOVERY_RETRY: Callable[
    [Dict[str, Any]], Any
] = lambda _p: None


def set_resolve_codex_app_server_recovery_retry_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom resolveCodexAppServerRecoveryRetry hook."""
    global _RESOLVE_CODEX_APP_SERVER_RECOVERY_RETRY
    _RESOLVE_CODEX_APP_SERVER_RECOVERY_RETRY = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def has_codex_app_server_recovery_retry_budget(
    params: Dict[str, Any],
) -> bool:
    """Return True when the codex-app-server recovery has retry budget.

    Mirrors :func:`hasCodexAppServerRecoveryRetryBudget`
    (``codex-app-server-recovery.ts``).
    """
    return _HAS_CODEX_APP_SERVER_RECOVERY_RETRY_BUDGET(dict(params or {}))


def resolve_codex_app_server_recovery_retry(
    params: Dict[str, Any],
) -> Any:
    """Resolve the codex-app-server recovery retry.

    Mirrors :func:`resolveCodexAppServerRecoveryRetry`
    (``codex-app-server-recovery.ts``).
    """
    return _RESOLVE_CODEX_APP_SERVER_RECOVERY_RETRY(dict(params or {}))


__all__ = [
    "has_codex_app_server_recovery_retry_budget",
    "resolve_codex_app_server_recovery_retry",
    "set_has_codex_app_server_recovery_retry_budget_hook",
    "set_resolve_codex_app_server_recovery_retry_hook",
]
