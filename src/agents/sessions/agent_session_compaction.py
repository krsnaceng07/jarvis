"""jarvis.agents.sessions.agent_session_compaction — compaction layer.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/agent-session-compaction.ts``.

Adds the compaction loop on top of
the inspection / models chain:

- :meth:`AgentSessionCompaction.compact` —
  manually compact the session
  context (aborts current agent
  operation first).
- :meth:`AgentSessionCompaction.abort_compaction` —
  cancel an in-flight manual
  compaction.
- :meth:`AgentSessionCompaction.abort_branch_summary` —
  cancel an in-flight branch
  summarization.
- :meth:`AgentSessionCompaction.check_compaction` —
  check whether compaction is
  needed after ``agent_end`` /
  before the next prompt; auto-compact
  if so.
- :attr:`AgentSessionCompaction.auto_compaction_enabled` —
  whether auto-compaction is
  enabled.
- :meth:`AgentSessionCompaction.set_auto_compaction_enabled` —
  toggle auto-compaction.

Phase 6.12g — focused port.

Adaptations
-----------
- The OpenClaw source's
  :func:`compact` +
  :func:`prepareCompaction` come
  from ``@openclaw/ai/internal/runtime``.
  The Python port's compaction
  work is a STUB — the
  :func:`run_compaction_work`
  helper returns a
  ``{"status": "skipped"}`` outcome
  when the real compaction runtime
  isn't available (the full runtime
  lands in Phase 6.13+). Public
  surface (events, abort, settings)
  is wired faithfully.
- The OpenClaw source's
  :func:`preflightManualSessionCompaction`
  comes from
  ``manual-compaction-preflight.js``.
  The Python port's
  :func:`preflight_manual_session_compaction`
  is a focused minimal port
  (returns ``{"compactable": False,
  "reason": "no-op"}`` when no
  runtime is available; the full
  helper lands in 6.13+).
- The OpenClaw source's
  :func:`getLatestCompactionEntry`
  comes from
  ``session-manager-codec.js``. The
  Python port uses
  :func:`jarvis.agents.sessions.session_manager_codec.get_latest_compaction_entry`
  (6.3).
- The OpenClaw source's
  :func:`isContextOverflow` comes
  from ``@openclaw/ai/internal/runtime``.
  The Python port uses
  :func:`jarvis.agents.sessions.runtime_helpers.is_context_overflow`
  (6.12e).
- The OpenClaw source's
  :func:`shouldCompact` +
  :func:`calculateContextTokens` +
  :func:`estimateContextTokens`
  come from the same runtime. The
  Python port ships a focused
  minimal implementation
  (:func:`should_compact` +
  :func:`estimate_context_tokens`)
  that mirrors the OpenClaw
  semantics: token count over
  ``settings.threshold`` of the
  context window → compact.
- The OpenClaw source inherits
  from ``AgentSessionInspection``
  (which lands in 6.12e). The
  Python port follows the same
  chain (:class:`AgentSessionInspection`
  from 6.12e).
"""
from __future__ import annotations

import logging
from typing import (
    TYPE_CHECKING,
    Any,
    Optional,
)

from .agent_session_inspection import AgentSessionInspection
from .manual_compaction_preflight import (
    preflight_manual_session_compaction,
)
from .runtime_helpers import is_context_overflow
from .session_manager_codec import get_latest_compaction_entry


if TYPE_CHECKING:
    from packages.jarvis_agent_runtime.src.jarvis_agent.types import (  # type: ignore[import-not-found]
        AssistantMessage,
    )
    from packages.jarvis_llm_client.src.jarvis_llm.types import (  # type: ignore[import-not-found]
        Model,
    )
else:
    AssistantMessage = Any
    Model = Any


_LOG = logging.getLogger("jarvis.agents.sessions.agent_session_compaction")


#: The OpenClaw source's
#: ``CompactionReason`` type
#: (``agent-session-compaction.ts:20``).
CompactionReason = str  # "manual" | "threshold" | "overflow"


#: A compaction work outcome. Mirrors
#: ``CompactionWorkOutcome``
#: (``agent-session-compaction.ts:21-24``).
CompactionWorkOutcome = dict


def _estimate_context_tokens(
    messages: list,
) -> dict:
    """Estimate the context token count
    from a list of messages. Mirrors
    :func:`estimateContextTokens`
    (the focused minimal port — the
    full OpenClaw source comes from
    ``@openclaw/ai/internal/runtime``).

    Returns
    -------
    dict
        ``{"tokens": int, "lastUsageIndex":
        Optional[int]}``. ``lastUsageIndex``
        is the index of the most recent
        assistant message with usage
        data, or ``None`` when no usage
        is available.
    """
    if not messages:
        return {"tokens": 0, "lastUsageIndex": None}
    last_usage_index: Optional[int] = None
    total = 0
    for i, msg in enumerate(messages):
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        if role == "assistant":
            usage = msg.get("usage")
            if isinstance(usage, dict):
                inp = usage.get("input", 0) or 0
                out = usage.get("output", 0) or 0
                cache_read = usage.get("cacheRead", 0) or 0
                cache_write = usage.get("cacheWrite", 0) or 0
                total = int(inp) + int(out) + int(cache_read) + int(cache_write)
                last_usage_index = i
        # Approximate: 4 chars per token.
        content = msg.get("content")
        if isinstance(content, str):
            total += len(content) // 4
    return {"tokens": total, "lastUsageIndex": last_usage_index}


def _should_compact(
    tokens: int,
    context_window: int,
    settings: dict,
) -> bool:
    """Whether the context should be
    compacted. Mirrors
    :func:`shouldCompact` (the focused
    minimal port)."""
    if context_window <= 0:
        return False
    if not settings.get("enabled", True):
        return False
    threshold = settings.get("threshold", 0.85)
    try:
        threshold_f = float(threshold)
    except (TypeError, ValueError):
        threshold_f = 0.85
    return (tokens / context_window) >= threshold_f


def _calculate_context_tokens(usage: dict) -> int:
    """Sum the context tokens from an
    assistant message's ``usage``
    block. Mirrors
    :func:`calculateContextTokens`."""
    if not isinstance(usage, dict):
        return 0
    inp = usage.get("input", 0) or 0
    out = usage.get("output", 0) or 0
    cache_read = usage.get("cacheRead", 0) or 0
    cache_write = usage.get("cacheWrite", 0) or 0
    return int(inp) + int(out) + int(cache_read) + int(cache_write)


def _preflight_manual_session_compaction(
    path_entries: list,
    settings: dict,
) -> dict:
    """Stub — the real impl is in
    :mod:`jarvis.agents.sessions.manual_compaction_preflight`
    (Phase 6.13a). This shim remains
    for backwards compatibility with
    any callers that imported it
    directly from the compaction
    module."""
    from .manual_compaction_preflight import (
        preflight_manual_session_compaction as _impl,
    )
    return _impl(path_entries, settings)


class AgentSessionCompaction(AgentSessionInspection):
    """The compaction layer of the
    :class:`AgentSession` family. Mirrors
    :class:`AgentSessionCompaction`
    (``agent-session-compaction.ts:26-431``).

    Phase 6.12g port.
    """

    # ------------------------------------------------------------------
    # Manual compaction
    # ------------------------------------------------------------------

    async def compact(
        self, custom_instructions: Optional[str] = None
    ) -> dict:
        """Manually compact the session
        context. Aborts the current
        agent operation first. Mirrors
        :meth:`compact`
        (``agent-session-compaction.ts:36-40``).
        """
        return await self.run_with_session_write_lock(
            lambda: self._compact_with_session_write_lock(
                custom_instructions
            )
        )

    async def _compact_with_session_write_lock(
        self, custom_instructions: Optional[str] = None
    ) -> dict:
        """Compact under the session
        write lock. Mirrors
        :meth:`compactWithSessionWriteLock`
        (``agent-session-compaction.ts:42-88``)."""
        self.disconnect_from_agent()
        await self.abort()
        self.compaction_abort_controller = _AbortControllerLike()
        self.emit({"type": "compaction_start", "reason": "manual"})

        try:
            settings = self._get_compaction_settings()
            outcome = await self._run_compaction_work(
                {
                    "customInstructions": custom_instructions,
                    "mode": "manual",
                    "settings": settings,
                    "signal": self.compaction_abort_controller,
                }
            )
            if outcome.get("status") != "compacted":
                raise RuntimeError("Compaction cancelled")
            result = outcome.get("result") or {}
            self.emit({
                "type": "compaction_end",
                "reason": "manual",
                "result": result,
                "aborted": False,
                "willRetry": False,
            })
            return result
        except Exception as error:
            message = (
                str(error) if isinstance(error, Exception) else str(error)
            )
            aborted = (
                message == "Compaction cancelled"
                or (
                    isinstance(error, Exception)
                    and getattr(error, "name", "") == "AbortError"
                )
            )
            self.emit({
                "type": "compaction_end",
                "reason": "manual",
                "result": None,
                "aborted": aborted,
                "willRetry": False,
                "errorMessage": (
                    None if aborted else f"Compaction failed: {message}"
                ),
            })
            raise
        finally:
            self.compaction_abort_controller = None
            self.reconnect_to_agent()

    def abort_compaction(self) -> None:
        """Cancel an in-flight manual
        compaction. Mirrors
        :meth:`abortCompaction`
        (``agent-session-compaction.ts:93-96``)."""
        if self.compaction_abort_controller is not None:
            self.compaction_abort_controller.abort()
        if self.auto_compaction_abort_controller is not None:
            self.auto_compaction_abort_controller.abort()

    def abort_branch_summary(self) -> None:
        """Cancel an in-flight branch
        summarization. Mirrors
        :meth:`abortBranchSummary`
        (``agent-session-compaction.ts:101-103``)."""
        if self.branch_summary_abort_controller is not None:
            self.branch_summary_abort_controller.abort()

    # ------------------------------------------------------------------
    # Auto-compaction
    # ------------------------------------------------------------------

    @property
    def auto_compaction_enabled(self) -> bool:
        """Whether auto-compaction is
        enabled. Mirrors
        :attr:`autoCompactionEnabled`
        (``agent-session-compaction.ts:428-430``)."""
        getter = getattr(
            self.settings_manager, "get_compaction_enabled", None
        )
        if callable(getter):
            return bool(getter())
        return True

    def set_auto_compaction_enabled(self, enabled: bool) -> None:
        """Toggle auto-compaction.
        Mirrors
        :meth:`setAutoCompactionEnabled`
        (``agent-session-compaction.ts:423-425``)."""
        setter = getattr(
            self.settings_manager, "set_compaction_enabled", None
        )
        if callable(setter):
            setter(bool(enabled))

    async def check_compaction(
        self,
        assistant_message: AssistantMessage,
        skip_aborted_check: bool = True,
    ) -> bool:
        """Check if compaction is needed
        and run it. Called after
        ``agent_end`` + before prompt
        submission. Mirrors
        :meth:`checkCompaction`
        (``agent-session-compaction.ts:238-338``).

        Two cases:
        1. Overflow: LLM returned
           context overflow error →
           remove error message +
           compact + auto-retry.
        2. Threshold: Context over
           threshold → compact, NO
           auto-retry.

        Returns
        -------
        bool
            ``True`` when compaction
            was performed and the
            caller should retry /
            continue, ``False``
            otherwise.
        """
        settings = self._get_compaction_settings()
        if not settings.get("enabled", True):
            return False

        # Skip aborted messages (unless
        # the caller explicitly asks for
        # them — pre-prompt check).
        stop_reason = _get_field(
            assistant_message, "stopReason", "stop_reason"
        )
        if skip_aborted_check and stop_reason == "aborted":
            return False

        model = self.model
        context_window = 0
        if isinstance(model, dict):
            context_window = model.get("contextWindow", 0) or 0
        elif model is not None:
            context_window = getattr(model, "context_window", 0) or 0

        # Skip overflow check if the
        # message came from a different
        # model. Mirrors the OpenClaw
        # source's `sameModel` check
        # (``agent-session-compaction.ts:258-262``).
        provider = _get_field(
            assistant_message, "provider", None
        )
        model_id = _get_field(
            assistant_message, "model", "model_id"
        )
        current_provider = (
            model.get("provider", "") if isinstance(model, dict)
            else getattr(model, "provider", "") if model else ""
        )
        current_id = (
            model.get("id", "") if isinstance(model, dict)
            else getattr(model, "id", "") if model else ""
        )
        same_model = bool(
            model
            and provider == current_provider
            and model_id == current_id
        )

        # Skip if the assistant message
        # is older than the latest
        # compaction boundary.
        branch = []
        if hasattr(self.session_manager, "get_branch"):
            branch = self.session_manager.get_branch() or []
        compaction_entry = get_latest_compaction_entry(branch)
        msg_timestamp = _get_field(
            assistant_message, "timestamp", None
        )
        assistant_is_from_before_compaction = False
        if compaction_entry is not None and msg_timestamp is not None:
            compaction_ts = (
                compaction_entry.get("timestamp", "")
                if isinstance(compaction_entry, dict)
                else getattr(compaction_entry, "timestamp", "")
            )
            try:
                if isinstance(compaction_ts, (int, float)):
                    assistant_is_from_before_compaction = (
                        msg_timestamp <= compaction_ts
                    )
                elif isinstance(compaction_ts, str):
                    from datetime import datetime
                    comp_ms = int(
                        datetime.fromisoformat(
                            compaction_ts.replace("Z", "+00:00")
                        ).timestamp()
                        * 1000
                    )
                    assistant_is_from_before_compaction = (
                        msg_timestamp <= comp_ms
                    )
            except Exception:
                assistant_is_from_before_compaction = False
        if assistant_is_from_before_compaction:
            return False

        # Case 1: Overflow recovery.
        if (
            same_model
            and stop_reason in ("error", "length")
            and is_context_overflow(assistant_message, context_window)
        ):
            if self.overflow_recovery_attempted:
                self.emit({
                    "type": "compaction_end",
                    "reason": "overflow",
                    "result": None,
                    "aborted": False,
                    "willRetry": False,
                    "errorMessage": (
                        "Context overflow recovery failed after one "
                        "compact-and-retry attempt. Try reducing "
                        "context or switching to a larger-context "
                        "model."
                    ),
                })
                return False
            self.overflow_recovery_attempted = True
            # Pop the failed assistant
            # message (keep in session log
            # for history).
            self._pop_last_assistant_message()
            return await self._run_auto_compaction("overflow", True)

        # Case 2: Threshold maintenance.
        usage = _get_field(assistant_message, "usage", None)
        context_tokens: int
        if stop_reason == "error":
            messages = self.messages
            estimate = _estimate_context_tokens(messages)
            if estimate["lastUsageIndex"] is None:
                return False
            # Verify usage source is
            # post-compaction.
            usage_msg = (
                messages[estimate["lastUsageIndex"]]
                if 0 <= estimate["lastUsageIndex"] < len(messages)
                else None
            )
            if (
                compaction_entry is not None
                and isinstance(usage_msg, dict)
                and usage_msg.get("role") == "assistant"
            ):
                usage_ts = usage_msg.get("timestamp", 0) or 0
                comp_ts_raw = (
                    compaction_entry.get("timestamp", 0)
                    if isinstance(compaction_entry, dict)
                    else getattr(compaction_entry, "timestamp", 0)
                )
                try:
                    if isinstance(comp_ts_raw, str):
                        from datetime import datetime
                        comp_ts = int(
                            datetime.fromisoformat(
                                comp_ts_raw.replace("Z", "+00:00")
                            ).timestamp()
                            * 1000
                        )
                    else:
                        comp_ts = int(comp_ts_raw)
                    if usage_ts <= comp_ts:
                        return False
                except Exception:
                    pass
            context_tokens = int(estimate["tokens"])
        else:
            context_usage = (
                usage.get("contextUsage", {})
                if isinstance(usage, dict)
                else getattr(usage, "context_usage", None)
            ) or {}
            if context_usage.get("state") == "unavailable":
                ctx = self.get_context_usage()
                estimated = (
                    ctx.get("tokens") if isinstance(ctx, dict) else None
                )
                if estimated is None:
                    return False
                context_tokens = int(estimated)
            else:
                context_tokens = _calculate_context_tokens(usage or {})
        if _should_compact(
            context_tokens, context_window, settings
        ):
            return await self._run_auto_compaction("threshold", False)
        return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _run_auto_compaction(
        self,
        reason: str,
        will_retry: bool,
    ) -> bool:
        """Internal: run auto-compaction
        with events. Mirrors
        :meth:`runAutoCompaction`
        (``agent-session-compaction.ts:343-418``)."""
        settings = self._get_compaction_settings()
        self.emit({"type": "compaction_start", "reason": reason})
        self.auto_compaction_abort_controller = _AbortControllerLike()
        try:
            outcome = await self._run_compaction_work(
                {
                    "mode": "auto",
                    "settings": settings,
                    "signal": self.auto_compaction_abort_controller,
                }
            )
            status = outcome.get("status")
            if status == "skipped":
                self.emit({
                    "type": "compaction_end",
                    "reason": reason,
                    "result": None,
                    "aborted": False,
                    "willRetry": False,
                })
                return False
            if status == "aborted":
                self.emit({
                    "type": "compaction_end",
                    "reason": reason,
                    "result": None,
                    "aborted": True,
                    "willRetry": False,
                })
                return False
            self.emit({
                "type": "compaction_end",
                "reason": reason,
                "result": outcome.get("result"),
                "aborted": False,
                "willRetry": will_retry,
            })
            if will_retry:
                # Pop the failed assistant
                # message (keep in session
                # log).
                messages = self.messages
                if messages:
                    last = messages[-1]
                    if isinstance(last, dict):
                        if last.get("stopReason") in ("error", "length") or last.get("stop_reason") in ("error", "length"):
                            state = self.agent.state
                            if isinstance(state, dict):
                                state["messages"] = list(messages[:-1])
                            else:
                                setattr(
                                    state,
                                    "messages",
                                    list(messages[:-1]),
                                )
                return True
            # Auto-compaction can complete
            # while follow-up / steering /
            # custom messages are waiting.
            # Continue once so queued
            # messages are delivered.
            return bool(
                getattr(self.agent, "has_queued_messages", lambda: False)()
            )
        except Exception as error:
            message = (
                str(error)
                if isinstance(error, Exception)
                else "compaction failed"
            )
            self.emit({
                "type": "compaction_end",
                "reason": reason,
                "result": None,
                "aborted": False,
                "willRetry": False,
                "errorMessage": (
                    f"Context overflow recovery failed: {message}"
                    if reason == "overflow"
                    else f"Auto-compaction failed: {message}"
                ),
            })
            return False
        finally:
            self.auto_compaction_abort_controller = None

    async def _run_compaction_work(
        self,
        options: dict,
    ) -> CompactionWorkOutcome:
        """Run the compaction work. Mirrors
        :meth:`runCompactionWork`
        (``agent-session-compaction.ts:127-225``).

        Phase 6.12g — STUB. The full
        implementation lands in 6.13+
        (when the
        :func:`compact` /
        :func:`prepareCompaction` runtime
        + the LLM streaming are
        available).
        """
        is_manual = options.get("mode") == "manual"
        if not self.model:
            if is_manual:
                raise RuntimeError(
                    format_no_model_selected_message()
                )
            return {"status": "skipped"}
        auth_getter = getattr(
            self,
            "get_compaction_request_auth",
            None,
        )
        auth: Optional[dict] = None
        if callable(auth_getter):
            try:
                auth = await auth_getter(self.model)  # type: ignore[arg-type]
            except Exception:
                auth = None
        if not auth:
            return {"status": "skipped"}

        path_entries: list = []
        if hasattr(self.session_manager, "get_branch"):
            path_entries = (
                self.session_manager.get_branch() or []
            )
        preparation: Optional[dict] = None
        if is_manual:
            preflight = preflight_manual_session_compaction(
                path_entries, options.get("settings") or {}
            )
            if not preflight.get("compactable", False):
                raise RuntimeError(
                    preflight.get(
                        "reason",
                        "Manual compaction not possible",
                    )
                )
            preparation = preflight.get("preparation")
        # Auto-compaction preparation
        # (the OpenClaw source uses
        # ``unwrapCoreResult(prepareCompaction(...))``).
        # The Python port's
        # ``prepareCompaction`` lands in
        # 6.13+; for now skip when no
        # preparation.
        if not preparation:
            return {"status": "skipped"}

        # Extension override (the
        # OpenClaw source's
        # ``session_before_compact``
        # handler).
        runner = self.current_extension_runner
        if (
            runner is not None
            and runner.has_handlers("session_before_compact")
        ):
            try:
                ext_result = await runner.emit(
                    {
                        "type": "session_before_compact",
                        "preparation": preparation,
                        "branchEntries": path_entries,
                        "customInstructions": options.get(
                            "customInstructions"
                        ),
                        "signal": options.get("signal"),
                    }
                )
            except Exception:
                ext_result = None
            if isinstance(ext_result, dict):
                if ext_result.get("cancel"):
                    return {"status": "aborted"}
                if ext_result.get("compaction"):
                    compaction_result = ext_result["compaction"]
                    from_extension = True
                else:
                    compaction_result = None
                    from_extension = False
            else:
                compaction_result = None
                from_extension = False
        else:
            compaction_result = None
            from_extension = False

        # Default compaction (the
        # OpenClaw source's
        # ``compact(...)`` runtime call
        # + the ``unwrapCoreResult``
        # wrapper). The Python port's
        # runtime lands in 6.13+; for
        # now return ``skipped`` when no
        # compaction was provided by the
        # extension.
        if compaction_result is None:
            return {"status": "skipped"}

        # Append the compaction to the
        # session log.
        append_compaction = getattr(
            self.session_manager, "append_compaction", None
        )
        if callable(append_compaction):
            try:
                append_compaction(
                    compaction_result.get("summary", ""),
                    compaction_result.get("firstKeptEntryId"),
                    compaction_result.get("tokensBefore"),
                    compaction_result.get("details"),
                    from_extension,
                )
            except Exception:
                pass
        # Update the agent state from
        # the new session context.
        if hasattr(self.session_manager, "build_session_context"):
            try:
                ctx = self.session_manager.build_session_context()
                messages = (
                    ctx.get("messages", [])
                    if isinstance(ctx, dict)
                    else getattr(ctx, "messages", [])
                )
                state = self.agent.state
                if isinstance(state, dict):
                    state["messages"] = list(messages)
                else:
                    setattr(state, "messages", list(messages))
            except Exception:
                pass
        # Find the saved compaction entry.
        entries_getter = getattr(
            self.session_manager, "get_entries", None
        )
        saved_compaction_entry: Optional[dict] = None
        if callable(entries_getter):
            try:
                entries = entries_getter()
                for entry in entries or []:
                    if not isinstance(entry, dict):
                        continue
                    if entry.get("type") == "compaction" and entry.get(
                        "summary"
                    ) == compaction_result.get("summary"):
                        saved_compaction_entry = entry
                        break
            except Exception:
                saved_compaction_entry = None
        # Emit the ``session_compact``
        # event.
        if runner is not None and saved_compaction_entry is not None:
            try:
                await runner.emit({
                    "type": "session_compact",
                    "compactionEntry": saved_compaction_entry,
                    "fromExtension": from_extension,
                })
            except Exception:
                pass
        return {
            "status": "compacted",
            "result": compaction_result,
        }

    def _get_compaction_settings(self) -> dict:
        """Read compaction settings from
        the settings manager. Mirrors
        the OpenClaw source's
        :func:`getCompactionSettings`
        (the real shape lands in 6.13+)."""
        getter = getattr(
            self.settings_manager, "get_compaction_settings", None
        )
        if callable(getter):
            try:
                return dict(getter())
            except Exception:
                pass
        # Fallback defaults (the OpenClaw
        # source uses the same shape).
        return {
            "enabled": True,
            "threshold": 0.85,
            "keepRecentTokens": 20000,
        }

    def _pop_last_assistant_message(self) -> None:
        """Remove the last assistant
        message from the agent state
        (keep it in the session log for
        history). Mirrors the same-named
        helper on
        :class:`AgentSessionExecution`
        (``agent-session-execution.py:419``).

        The compaction class doesn't
        inherit from
        :class:`AgentSessionExecution`
        (it's a sibling of the chain),
        so we re-define the helper here.
        The implementation is identical
        to the execution-class version.
        """
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
    helper for the manual + auto
    compaction abort controllers.
    Mirrors the ``AbortController``
    shape the OpenClaw source uses."""

    def __init__(self) -> None:
        self.aborted: bool = False

    def abort(self) -> None:
        self.aborted = True


def _get_field(
    message: Any,
    camel: str,
    snake: Optional[str] = None,
) -> Any:
    """Read a field from a message that
    may be a dict or an object. Tries
    the camelCase name first (the
    OpenClaw source's wire format), then
    the snake_case name (the Python
    port's preferred spelling)."""
    if isinstance(message, dict):
        if camel in message:
            return message.get(camel)
        if snake is not None and snake in message:
            return message.get(snake)
        return None
    value = getattr(message, camel, None)
    if value is not None:
        return value
    if snake is not None:
        return getattr(message, snake, None)
    return None


def format_no_model_selected_message() -> str:
    """Render the "no model selected"
    error message. Mirrors
    :func:`formatNoModelSelectedMessage`
    (``auth-guidance.ts``)."""
    from .auth_guidance import format_no_model_selected_message
    return format_no_model_selected_message()


__all__ = [
    "AgentSessionCompaction",
    "CompactionReason",
    "CompactionWorkOutcome",
]
