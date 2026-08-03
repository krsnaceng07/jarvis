"""jarvis.agents.embedded_agent_runner.run.attempt_session_lock — own + lock the session file for an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt.session-lock.ts``.

Public surface:

Constants:

- :data:`MAX_BENIGN_SESSION_FENCE_ADVANCE_BYTES`
- :data:`MAX_BENIGN_SESSION_FENCE_REWRITE_BYTES`
- :data:`MAX_BENIGN_SESSION_FENCE_REWRITE_RESULT_BYTES`
- :data:`MAX_BENIGN_SESSION_FENCE_CONTENT_DIGEST_BYTES`
- :data:`MAX_SAFE_FILE_OFFSET`

Types:

- :data:`EmbeddedAttemptSessionFileOwner`
- :data:`EmbeddedAttemptSessionLockController`
- :data:`EmbeddedAttemptSessionTakeoverError`

Functions:

- :func:`acquire_embedded_attempt_session_file_owner` (async)
- :func:`create_embedded_attempt_session_lock_controller` (async)
- :func:`install_prompt_submission_lock_release`

Phase 7.6f-1 — focused minimal port.

The OpenClaw source is the largest single file in the run/
subdir (~74K) and tightly couples session-file ownership, session-
lock takeover, and prompt-submission lock-release. The Python port
keeps the public surface and delegates the heavy work to
installable hooks so the host can plug in the real layers as they
land.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Max benign session-fence advance bytes. Mirrors
#: :data:`MAX_BENIGN_SESSION_FENCE_ADVANCE_BYTES`
#: (``attempt.session-lock.ts``).
MAX_BENIGN_SESSION_FENCE_ADVANCE_BYTES: int = 1024 * 1024


#: Max benign session-fence rewrite bytes. Mirrors
#: :data:`MAX_BENIGN_SESSION_FENCE_REWRITE_BYTES`
#: (``attempt.session-lock.ts``).
MAX_BENIGN_SESSION_FENCE_REWRITE_BYTES: int = 8 * 1024 * 1024


#: Max benign session-fence rewrite-result bytes. Mirrors
#: :data:`MAX_BENIGN_SESSION_FENCE_REWRITE_RESULT_BYTES`
#: (``attempt.session-lock.ts``).
MAX_BENIGN_SESSION_FENCE_REWRITE_RESULT_BYTES: int = 8 * 1024 * 1024


#: Max benign session-fence content-digest bytes. Mirrors
#: :data:`MAX_BENIGN_SESSION_FENCE_CONTENT_DIGEST_BYTES`
#: (``attempt.session-lock.ts``).
MAX_BENIGN_SESSION_FENCE_CONTENT_DIGEST_BYTES: int = 32 * 1024 * 1024


#: Max safe file offset (BigInt). Mirrors
#: :data:`MAX_SAFE_FILE_OFFSET` (``attempt.session-lock.ts``).
MAX_SAFE_FILE_OFFSET: int = 2**53 - 1


#: Embedded-attempt session-file owner.
EmbeddedAttemptSessionFileOwner = Dict[str, Any]


#: Embedded-attempt session-lock controller.
EmbeddedAttemptSessionLockController = Dict[str, Any]


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


#: Hook for the acquire-session-file-owner step.
_ACQUIRE_EMBEDDED_ATTEMPT_SESSION_FILE_OWNER: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_acquire_embedded_attempt_session_file_owner_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom acquireEmbeddedAttemptSessionFileOwner hook."""
    global _ACQUIRE_EMBEDDED_ATTEMPT_SESSION_FILE_OWNER
    _ACQUIRE_EMBEDDED_ATTEMPT_SESSION_FILE_OWNER = hook


#: Hook for the create-session-lock-controller step.
_CREATE_EMBEDDED_ATTEMPT_SESSION_LOCK_CONTROLLER: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_create_embedded_attempt_session_lock_controller_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom createEmbeddedAttemptSessionLockController hook."""
    global _CREATE_EMBEDDED_ATTEMPT_SESSION_LOCK_CONTROLLER
    _CREATE_EMBEDDED_ATTEMPT_SESSION_LOCK_CONTROLLER = hook


#: Hook for the install-prompt-submission-lock-release step.
_INSTALL_PROMPT_SUBMISSION_LOCK_RELEASE: Callable[
    [Dict[str, Any]], Any
] = lambda _p: None


def set_install_prompt_submission_lock_release_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom installPromptSubmissionLockRelease hook."""
    global _INSTALL_PROMPT_SUBMISSION_LOCK_RELEASE
    _INSTALL_PROMPT_SUBMISSION_LOCK_RELEASE = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class EmbeddedAttemptSessionTakeoverError(Exception):
    """Raised when a session takeover cannot be safely performed.

    Mirrors :class:`EmbeddedAttemptSessionTakeoverError`
    (``attempt.session-lock.ts``).
    """

    def __init__(self, message: str, takeover: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.takeover = takeover or {}


async def acquire_embedded_attempt_session_file_owner(
    params: Dict[str, Any],
) -> EmbeddedAttemptSessionFileOwner:
    """Acquire the embedded-attempt session-file owner.

    Mirrors :func:`acquireEmbeddedAttemptSessionFileOwner`
    (``attempt.session-lock.ts``).
    """
    owner: Any = await _maybe_await(
        _ACQUIRE_EMBEDDED_ATTEMPT_SESSION_FILE_OWNER(dict(params or {}))
    )
    if not isinstance(owner, dict):
        owner = {}
    return {
        "sessionFile": owner.get("sessionFile") or params.get("sessionFile"),
        "owner": owner.get("owner"),
        "released": bool(owner.get("released", False)),
    }


async def create_embedded_attempt_session_lock_controller(
    params: Dict[str, Any],
) -> EmbeddedAttemptSessionLockController:
    """Create the embedded-attempt session-lock controller.

    Mirrors :func:`createEmbeddedAttemptSessionLockController`
    (``attempt.session-lock.ts``).
    """
    controller: Any = await _maybe_await(
        _CREATE_EMBEDDED_ATTEMPT_SESSION_LOCK_CONTROLLER(
            dict(params or {})
        )
    )
    if not isinstance(controller, dict):
        controller = {}
    return {
        "sessionLockController": controller.get("sessionLockController"),
        "withOwnedSessionWriteLock": controller.get(
            "withOwnedSessionWriteLock"
        ),
    }


def install_prompt_submission_lock_release(
    params: Dict[str, Any],
) -> Any:
    """Install the prompt-submission lock release.

    Mirrors :func:`installPromptSubmissionLockRelease`
    (``attempt.session-lock.ts``).
    """
    return _INSTALL_PROMPT_SUBMISSION_LOCK_RELEASE(dict(params or {}))


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "EmbeddedAttemptSessionFileOwner",
    "EmbeddedAttemptSessionLockController",
    "EmbeddedAttemptSessionTakeoverError",
    "MAX_BENIGN_SESSION_FENCE_ADVANCE_BYTES",
    "MAX_BENIGN_SESSION_FENCE_CONTENT_DIGEST_BYTES",
    "MAX_BENIGN_SESSION_FENCE_REWRITE_BYTES",
    "MAX_BENIGN_SESSION_FENCE_REWRITE_RESULT_BYTES",
    "MAX_SAFE_FILE_OFFSET",
    "acquire_embedded_attempt_session_file_owner",
    "create_embedded_attempt_session_lock_controller",
    "install_prompt_submission_lock_release",
    "set_acquire_embedded_attempt_session_file_owner_hook",
    "set_create_embedded_attempt_session_lock_controller_hook",
    "set_install_prompt_submission_lock_release_hook",
]
