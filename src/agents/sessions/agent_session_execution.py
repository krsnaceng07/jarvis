"""jarvis.agents.sessions.agent_session_execution — execution layer.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/agent-session-execution.ts``.

Adds two layers on top of the prompting /
models chain:

- **Auto-Retry** — detect retryable
  assistant errors, schedule a retry
  with exponential backoff + rate-limit
  detection, abort in-flight retries.
- **Bash Execution** — execute bash
  commands, record the result in the
  agent state + session log, defer
  recording while the agent is streaming,
  flush pending bash messages.

The OpenClaw source inherits from
``AgentSessionExtensions`` (a thin
extension-binding layer that lands in
6.12f). The Python port inherits from
``AgentSessionModels`` directly — the
extension-binding helpers (runner
re-binding, tool hooks) land in
6.12f. The class hierarchy is preserved
at the public surface; the missing
intermediate subclass is collapsed.

Public surface (mirrors the OpenClaw
source):

- :meth:`AgentSessionExecution.is_retryable_error` — override
  the base no-op stub.
- :meth:`AgentSessionExecution.prepare_retry` — override the
  base no-op stub.
- :meth:`AgentSessionExecution.abort_retry` — override the
  base no-op stub.
- :meth:`AgentSessionExecution.flush_pending_bash_messages`
  — override the base no-op stub.
- :attr:`AgentSessionExecution.is_retrying` — whether a retry
  is in progress.
- :attr:`AgentSessionExecution.auto_retry_enabled` —
  whether auto-retry is enabled.
- :meth:`AgentSessionExecution.set_auto_retry_enabled` —
  toggle the setting.
- :meth:`AgentSessionExecution.execute_bash` — execute a
  bash command.
- :meth:`AgentSessionExecution.record_bash_result` — record
  a bash result in the session.
- :meth:`AgentSessionExecution.abort_bash` — cancel a running
  bash.
- :attr:`AgentSessionExecution.is_bash_running` — whether
  bash is running.
- :attr:`AgentSessionExecution.has_pending_bash_messages` —
  whether there are deferred bash messages.

Phase 6.12e — focused port.
"""
from __future__ import annotations

import logging
import time
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Optional,
)

from .agent_session_models import AgentSessionModels
from .runtime_helpers import (
    classify_rate_limit_window,
    is_context_overflow,
    is_retryable_assistant_error,
    sleep,
)


if TYPE_CHECKING:
    from packages.jarvis_agent_runtime.src.jarvis_agent.types import (  # type: ignore[import-not-found]
        AgentMessage,
        AssistantMessage,
    )
    from packages.jarvis_llm_client.src.jarvis_llm.types import (  # type: ignore[import-not-found]
        Model,
    )
else:
    AgentMessage = Any
    AssistantMessage = Any
    Model = Any


_LOG = logging.getLogger("jarvis.agents.sessions.agent_session_execution")


#: A bash-execution result. Mirrors
#: ``BashResult`` (``bash-executor.ts``).
#: The Python port uses a ``dict`` for
#: the result shape (the OpenClaw source
#: uses an interface).
BashResult = dict

#: A bash-execution message entry. Mirrors
#: ``BashExecutionMessage`` (``messages.ts``).
#: The Python port uses a ``dict``.
BashExecutionMessage = dict

#: Custom bash-operations interface.
#: Mirrors ``BashOperations``
#: (``tools/bash-operations.ts``). The
#: Python port uses a callable type.
BashOperations = Callable[..., Any]


class AgentSessionExecution(AgentSessionModels):
    """The execution layer of the
    :class:`AgentSession` family. Mirrors
    :class:`AgentSessionExecution`
    (``agent-session-execution.ts:12-233``).

    Phase 6.12e port.
    """

    # ------------------------------------------------------------------
    # Auto-Retry
    # ------------------------------------------------------------------

    def is_retryable_error(self, msg: AssistantMessage) -> bool:
        """Check if an error is retryable
        (overloaded, rate limit, server
        errors). Context-overflow errors
        are NOT retryable (handled by
        compaction instead). Mirrors
        :meth:`isRetryableError`
        (``agent-session-execution.ts:21-33``)."""
        stop_reason = _get_field(msg, "stopReason", "stop_reason")
        err = _get_field(msg, "errorMessage", "error_message")
        if stop_reason != "error" or not err:
            return False
        # Context overflow → handled by
        # compaction, not retry.
        context_window = 0
        if self.model:
            if isinstance(self.model, dict):
                context_window = self.model.get("contextWindow") or 0
            else:
                context_window = getattr(self.model, "context_window", 0) or 0
        if context_window and is_context_overflow(msg, context_window):
            return False
        return is_retryable_assistant_error(msg)

    async def prepare_retry(self, msg: AssistantMessage) -> bool:
        """Prepare a retryable error for
        continuation with exponential
        backoff. Mirrors :meth:`prepareRetry`
        (``agent-session-execution.ts:39-95``).

        Returns ``True`` when the caller
        should continue the agent (the
        retry was scheduled), ``False``
        when retry is disabled or the
        attempt limit was reached.
        """
        # Read the retry settings.
        get_retry_settings = getattr(
            self.settings_manager, "get_retry_settings", None
        )
        if callable(get_retry_settings):
            settings = get_retry_settings()
        else:
            get_retry_enabled = getattr(
                self.settings_manager, "get_retry_enabled", None
            )
            enabled = get_retry_enabled() if callable(get_retry_enabled) else True
            get_max = getattr(self.settings_manager, "get_retry_max_attempts", None)
            max_retries = get_max() if callable(get_max) else 3
            get_base = getattr(
                self.settings_manager, "get_retry_base_delay_ms", None
            )
            base_delay = get_base() if callable(get_base) else 1000
            settings = {
                "enabled": enabled,
                "maxRetries": max_retries,
                "baseDelayMs": base_delay,
            }
        if not settings.get("enabled", False):
            return False
        self.retry_count += 1
        max_retries = settings.get("maxRetries", 3)
        if self.retry_count > max_retries:
            # Preserve the completed
            # attempt count so post-run
            # handling can emit the final
            # failure.
            self.retry_count -= 1
            return False
        backoff_delay_ms = settings.get("baseDelayMs", 1000) * 2 ** (
            self.retry_count - 1
        )
        err = _get_field(msg, "errorMessage", "error_message") or ""
        rate_limit_window = classify_rate_limit_window(err)
        retry_after_delay_ms = (
            int(rate_limit_window.get("retryAfterSeconds", 0) * 1000)
            if rate_limit_window.get("kind") == "short"
            and rate_limit_window.get("retryAfterSeconds") is not None
            else 0
        )
        delay_ms = max(backoff_delay_ms, retry_after_delay_ms)
        # Emit the retry-start event.
        self.emit({
            "type": "auto_retry_start",
            "attempt": self.retry_count,
            "maxAttempts": max_retries,
            "delayMs": delay_ms,
            "errorMessage": str(err) or "Unknown error",
        })
        # Remove the error message from
        # the agent state (keep in session
        # for history).
        self._pop_last_assistant_message()
        # Wait with exponential backoff
        # (abortable).
        self.retry_abort_controller = _AbortControllerLike()
        try:
            await sleep(delay_ms, self.retry_abort_controller)
        except Exception:
            # Aborted during sleep — emit
            # the end event so the UI can
            # clean up.
            attempt = self.retry_count
            self.retry_count = 0
            self.emit({
                "type": "auto_retry_end",
                "success": False,
                "attempt": attempt,
                "finalError": "Retry cancelled",
            })
            return False
        finally:
            self.retry_abort_controller = None
        return True

    def abort_retry(self) -> None:
        """Cancel an in-progress retry.
        Mirrors :meth:`abortRetry`
        (``agent-session-execution.ts:100-102``)."""
        if self.retry_abort_controller is not None:
            self.retry_abort_controller.abort()

    @property
    def is_retrying(self) -> bool:
        """Whether a retry is currently in
        progress. Mirrors the ``isRetrying``
        getter (``agent-session-execution.ts:105-107``)."""
        return self.retry_abort_controller is not None

    @property
    def auto_retry_enabled(self) -> bool:
        """Whether auto-retry is enabled.
        Mirrors the ``autoRetryEnabled``
        getter (``agent-session-execution.ts:110-112``)."""
        getter = getattr(
            self.settings_manager, "get_retry_enabled", None
        )
        if callable(getter):
            return bool(getter())
        return True

    def set_auto_retry_enabled(self, enabled: bool) -> None:
        """Toggle the auto-retry setting.
        Mirrors :meth:`setAutoRetryEnabled`
        (``agent-session-execution.ts:117-119``)."""
        setter = getattr(
            self.settings_manager, "set_retry_enabled", None
        )
        if callable(setter):
            setter(bool(enabled))

    # ------------------------------------------------------------------
    # Bash Execution
    # ------------------------------------------------------------------

    async def execute_bash(
        self,
        command: str,
        on_chunk: Optional[Callable[[str], None]] = None,
        options: Optional[dict] = None,
    ) -> BashResult:
        """Execute a bash command + record
        the result in the session.
        Mirrors :meth:`executeBash`
        (``agent-session-execution.ts:133-161``).

        Phase 6.12e — STUB. The OpenClaw
        source delegates to
        :func:`executeBashWithOperations`
        in :mod:`jarvis.agents.sessions.bash_executor`.
        The Python port ships a no-op
        stub that records the result
        without actually executing the
        command. The full bash executor
        integration lands in 6.13+.
        """
        options = options or {}
        exclude_from_context = options.get("excludeFromContext", False)
        operations = options.get("operations")
        _ = (on_chunk, operations)  # Reserved for 6.13+.
        self.bash_abort_controller = _AbortControllerLike()
        try:
            # Stub result. The full impl
            # delegates to the bash
            # executor in 6.13+.
            result: BashResult = {
                "output": "",
                "exitCode": 0,
                "cancelled": False,
                "truncated": False,
            }
            self.record_bash_result(command, result, options)
            _ = exclude_from_context  # Recorded via options.
            return result
        finally:
            self.bash_abort_controller = None

    def record_bash_result(
        self,
        command: str,
        result: BashResult,
        options: Optional[dict] = None,
    ) -> None:
        """Record a bash-execution result
        in the session history. Mirrors
        :meth:`recordBashResult`
        (``agent-session-execution.ts:167-195``)."""
        options = options or {}
        exclude_from_context = options.get("excludeFromContext", False)
        bash_message: BashExecutionMessage = {
            "role": "bashExecution",
            "command": command,
            "output": result.get("output", ""),
            "exitCode": result.get("exitCode", 0),
            "cancelled": result.get("cancelled", False),
            "truncated": result.get("truncated", False),
            "fullOutputPath": result.get("fullOutputPath"),
            "timestamp": _now_ms(),
            "excludeFromContext": exclude_from_context,
        }
        # If the agent is streaming,
        # defer adding to avoid breaking
        # tool_use/tool_result ordering.
        if self.is_streaming:
            self.pending_bash_messages.append(bash_message)
            return
        # Add to agent state immediately.
        state = self.agent.state
        if isinstance(state, dict):
            state.setdefault("messages", []).append(bash_message)
        else:
            existing = getattr(state, "messages", None) or []
            existing.append(bash_message)
            setattr(state, "messages", existing)
        # Save to the session.
        append_message = getattr(
            self.session_manager, "append_message", None
        )
        if callable(append_message):
            append_message(bash_message)

    def abort_bash(self) -> None:
        """Cancel a running bash command.
        Mirrors :meth:`abortBash`
        (``agent-session-execution.ts:200-202``)."""
        if self.bash_abort_controller is not None:
            self.bash_abort_controller.abort()

    @property
    def is_bash_running(self) -> bool:
        """Whether a bash command is
        currently running. Mirrors the
        ``isBashRunning`` getter
        (``agent-session-execution.ts:205-207``)."""
        return self.bash_abort_controller is not None

    @property
    def has_pending_bash_messages(self) -> bool:
        """Whether there are pending bash
        messages waiting to be flushed.
        Mirrors the ``hasPendingBashMessages``
        getter (``agent-session-execution.ts:210-212``)."""
        return len(self.pending_bash_messages) > 0

    def flush_pending_bash_messages(self) -> None:
        """Flush pending bash messages to
        the agent state + session.
        Mirrors :meth:`flushPendingBashMessages`
        (``agent-session-execution.ts:218-232``)."""
        if not self.pending_bash_messages:
            return
        for bash_message in self.pending_bash_messages:
            state = self.agent.state
            if isinstance(state, dict):
                state.setdefault("messages", []).append(bash_message)
            else:
                existing = getattr(state, "messages", None) or []
                existing.append(bash_message)
                setattr(state, "messages", existing)
            append_message = getattr(
                self.session_manager, "append_message", None
            )
            if callable(append_message):
                append_message(bash_message)
        self.pending_bash_messages = []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _pop_last_assistant_message(self) -> None:
        """Remove the last assistant message
        from the agent state (keep it in
        the session log for history)."""
        state = self.agent.state
        if isinstance(state, dict):
            messages = state.get("messages", [])
            if messages and messages[-1].get("role") == "assistant":
                state["messages"] = messages[:-1]
                return
        else:
            messages = getattr(state, "messages", None)
            if messages and len(messages) > 0:
                last = messages[-1]
                role = (
                    last.get("role")
                    if isinstance(last, dict)
                    else getattr(last, "role", None)
                )
                if role == "assistant":
                    setattr(state, "messages", messages[:-1])


# ============================================================================
# Module-level helpers
# ============================================================================


class _AbortControllerLike:
    """Minimal ``AbortController``-like
    helper for the retry / bash abort
    controllers. Mirrors the
    ``AbortController`` shape the
    OpenClaw source uses."""

    def __init__(self) -> None:
        self.aborted: bool = False

    def abort(self) -> None:
        self.aborted = True


def _now_ms() -> int:
    """Return the current epoch ms."""
    return int(time.time() * 1000)


def _get_field(message: Any, camel: str, snake: str) -> Any:
    """Read a field from a message that
    may be a dict or an object. Tries
    the camelCase name first (the
    OpenClaw source's wire format), then
    the snake_case name (the Python
    port's preferred spelling)."""
    if isinstance(message, dict):
        if camel in message:
            return message.get(camel)
        return message.get(snake)
    value = getattr(message, camel, None)
    if value is not None:
        return value
    return getattr(message, snake, None)


__all__ = [
    "AgentSessionExecution",
    "BashExecutionMessage",
    "BashOperations",
    "BashResult",
]
