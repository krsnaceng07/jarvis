"""jarvis.agents.embedded_agent_runner.run.attempt_prompt_skip — resolve the prompt-submission skip reason for an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-prompt-skip.ts``.

Public surface:

- :func:`resolve_prompt_submission_skip_reason`

Phase 7.6e — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional


#: Prompt-submission skip reason shape.
PromptSubmissionSkipReason = Dict[str, Any]


#: Installable hook for the resolve-prompt-submission-skip-reason step.
_RESOLVE_PROMPT_SUBMISSION_SKIP_REASON: Callable[
    [Dict[str, Any]], Any
] = lambda _p: None
_DEFAULT_RESOLVE_PROMPT_SUBMISSION_SKIP_REASON = (
    _RESOLVE_PROMPT_SUBMISSION_SKIP_REASON
)


def set_resolve_prompt_submission_skip_reason_hook(
    hook: Callable[[Dict[str, Any]], Any] | None,
) -> None:
    """Install a custom resolvePromptSubmissionSkipReason hook."""
    global _RESOLVE_PROMPT_SUBMISSION_SKIP_REASON
    _RESOLVE_PROMPT_SUBMISSION_SKIP_REASON = (
        _DEFAULT_RESOLVE_PROMPT_SUBMISSION_SKIP_REASON
        if hook is None
        else hook
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_prompt_submission_skip_reason(
    params: Dict[str, Any],
) -> Optional[PromptSubmissionSkipReason]:
    """Resolve the prompt-submission skip reason.

    Mirrors :func:`resolvePromptSubmissionSkipReason`
    (``attempt-prompt-skip.ts``).
    """
    return _RESOLVE_PROMPT_SUBMISSION_SKIP_REASON(dict(params or {}))


__all__ = [
    "PromptSubmissionSkipReason",
    "resolve_prompt_submission_skip_reason",
    "set_resolve_prompt_submission_skip_reason_hook",
]
