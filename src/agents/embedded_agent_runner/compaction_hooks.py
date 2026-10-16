"""jarvis.agents.embedded_agent_runner.compaction_hooks — run compaction hooks + side effects.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/compaction-hooks.ts``.

Public surface (mirrors the OpenClaw source):

- :func:`run_post_compaction_side_effects` — emit transcript update +
  post-compaction memory sync.
- :func:`as_compaction_hook_runner` — narrow adapter over the global
  hook runner.
- :func:`build_before_compaction_hook_metrics` — build before-hook
  metrics, tolerating provider estimation failures.
- :func:`run_before_compaction_hooks` — fire internal + plugin
  before-compaction hooks.
- :func:`estimate_tokens_after_compaction` — sanity-check the
  post-compaction token count.
- :func:`run_after_compaction_hooks` — fire internal + plugin
  after-compaction hooks.

Phase 7.2b-1 — focused minimal port.

The OpenClaw source has deep integrations with hook runners, the
session transcript emitter, and the memory search manager. The
Python port keeps the public function signatures and the core
control flow, but the side effects (transcript emit, memory sync)
delegate to a small :class:`_SideEffectSink` that the host can
replace in tests. By default the sink is a no-op; callers (like the
``compact`` orchestrator) wire the real sink before they invoke the
side effects.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional

from .logger import log


#: Valid modes for post-compaction index sync.
PostCompactionIndexSyncMode = str  # "off" | "async" | "await"


def _resolve_post_compaction_index_sync_mode(
    config: Optional[Dict[str, Any]] = None,
) -> PostCompactionIndexSyncMode:
    """Resolve the post-compaction index sync mode.

    Mirrors :func:`resolvePostCompactionIndexSyncMode`
    (``compaction-hooks.ts:15-21``).
    """
    mode = (
        (config or {}).get("agents", {})
        .get("defaults", {})
        .get("compaction", {})
        .get("postIndexSync")
    )
    if mode in ("off", "async", "await"):
        return mode
    return "async"


def _emit_session_transcript_update(
    session_file: str,
    session_key: Optional[str],
    session_id: Optional[str],
    agent_id: Optional[str],
) -> None:
    """Emit a transcript-update notification.

    Mirrors :func:`emitSessionTranscriptUpdate` from
    ``transcript-events.ts``. The Python port delegates to a
    :data:`_TRANSCRIPT_SINK` callable that the host can replace.
    """
    payload: Dict[str, Any] = {"sessionFile": session_file}
    if session_key is not None:
        payload["sessionKey"] = session_key
    if session_id is not None:
        payload["sessionId"] = session_id
    if agent_id is not None:
        payload["agentId"] = agent_id
    sink = _TRANSCRIPT_SINK
    if sink is not None:
        try:
            sink(payload)
        except Exception as err:
            log.warning("transcript emit failed: %s", err)


#: Sink for transcript-update events. Replace in tests to capture
#: what was emitted.
_TRANSCRIPT_SINK: Optional[Callable[[Dict[str, Any]], None]] = None


def set_transcript_sink(
    sink: Optional[Callable[[Dict[str, Any]], None]],
) -> None:
    """Install a custom transcript-update sink. Pass ``None`` to clear."""
    global _TRANSCRIPT_SINK
    _TRANSCRIPT_SINK = sink


async def _run_post_compaction_session_memory_sync(
    config: Optional[Dict[str, Any]],
    session_key: Optional[str],
    session_id: Optional[str],
    agent_id: Optional[str],
    session_file: str,
) -> None:
    """Run the post-compaction session memory sync.

    Mirrors :func:`runPostCompactionSessionMemorySync`
    (``compaction-hooks.ts:23-75``). The Python port delegates to
    :data:`_MEMORY_SYNC` which the host can replace; by default it
    is a no-op.
    """
    if not config:
        return
    session_file = (session_file or "").strip()
    if not session_file:
        return
    sync = _MEMORY_SYNC
    if sync is None:
        return
    try:
        await sync(
            config=config,
            session_key=session_key,
            session_id=session_id,
            agent_id=agent_id,
            session_file=session_file,
        )
    except Exception as err:
        log.warning("memory sync skipped (post-compaction): %s", err)


#: Async sink for post-compaction memory sync. The host replaces
#: this with the real memory manager integration.
_MEMORY_SYNC: Optional[
    Callable[..., Awaitable[None]]
] = None


def set_memory_sync_sink(
    sink: Optional[Callable[..., Awaitable[None]]],
) -> None:
    """Install a custom memory sync sink. Pass ``None`` to clear."""
    global _MEMORY_SYNC
    _MEMORY_SYNC = sink


async def _sync_post_compaction_session_memory(
    config: Optional[Dict[str, Any]],
    session_key: Optional[str],
    session_id: Optional[str],
    agent_id: Optional[str],
    session_file: str,
    mode: PostCompactionIndexSyncMode,
) -> None:
    """Honor the configured sync mode (``off`` / ``async`` / ``await``).

    Mirrors :func:`syncPostCompactionSessionMemory`
    (``compaction-hooks.ts:77-102``).
    """
    if mode == "off" or not config:
        return
    sync_task = _run_post_compaction_session_memory_sync(
        config=config,
        session_key=session_key,
        session_id=session_id,
        agent_id=agent_id,
        session_file=session_file,
    )
    if mode == "await":
        await sync_task
    else:
        # async mode: do not hold the user turn open
        return None


async def run_post_compaction_side_effects(
    config: Optional[Dict[str, Any]] = None,
    session_key: Optional[str] = None,
    session_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    session_file: str = "",
) -> None:
    """Run post-compaction transcript + memory side effects.

    Mirrors :func:`runPostCompactionSideEffects`
    (``compaction-hooks.ts:105-130``).
    """
    session_file = (session_file or "").strip()
    if not session_file:
        return
    _emit_session_transcript_update(
        session_file=session_file,
        session_key=session_key,
        session_id=session_id,
        agent_id=agent_id,
    )
    await _sync_post_compaction_session_memory(
        config=config,
        session_key=session_key,
        session_id=session_id,
        agent_id=agent_id,
        session_file=session_file,
        mode=_resolve_post_compaction_index_sync_mode(config),
    )


def as_compaction_hook_runner(
    hook_runner: Any,
) -> Optional["CompactionHookRunner"]:
    """Narrow a global hook runner down to the compaction surface.

    Mirrors :func:`asCompactionHookRunner`
    (``compaction-hooks.ts:163-174``).
    """
    if not hook_runner:
        return None
    return CompactionHookRunner(
        has_hooks=getattr(hook_runner, "hasHooks", None),
        run_before=getattr(hook_runner, "runBeforeCompaction", None),
        run_after=getattr(hook_runner, "runAfterCompaction", None),
    )


class CompactionHookRunner:
    """Narrow adapter over the global hook runner methods used by compaction.

    Mirrors the ``CompactionHookRunner`` type from
    (``compaction-hooks.ts:133-160``).
    """

    def __init__(
        self,
        has_hooks: Optional[Callable[[Optional[str]], bool]] = None,
        run_before: Optional[Callable[..., Any]] = None,
        run_after: Optional[Callable[..., Any]] = None,
    ) -> None:
        self._has_hooks = has_hooks
        self._run_before = run_before
        self._run_after = run_after

    def has_hooks(self, hook_name: Optional[str] = None) -> bool:
        if self._has_hooks is None:
            return False
        try:
            return bool(self._has_hooks(hook_name))
        except Exception:
            return False

    async def run_before_compaction(
        self,
        metrics: Dict[str, Any],
        context: Dict[str, Any],
    ) -> None:
        if self._run_before is None:
            return
        try:
            result = self._run_before(metrics, context)
            if result is not None and hasattr(result, "__await__"):
                await result
        except Exception as err:
            log.warning("before_compaction hook failed: %s", err)

    async def run_after_compaction(
        self,
        metrics: Dict[str, Any],
        context: Dict[str, Any],
    ) -> None:
        if self._run_after is None:
            return
        try:
            result = self._run_after(metrics, context)
            if result is not None and hasattr(result, "__await__"):
                await result
        except Exception as err:
            log.warning("after_compaction hook failed: %s", err)


def _estimate_token_count_safe(
    messages: List[Any],
    estimate_tokens_fn: Callable[[Any], int],
) -> Optional[int]:
    """Estimate token count for a list of messages.

    Mirrors :func:`estimateTokenCountSafe`
    (``compaction-hooks.ts:176-189``). Returns ``None`` if the
    estimator raises.
    """
    try:
        total = 0
        for message in messages:
            total += int(estimate_tokens_fn(message))
        return total
    except Exception:
        return None


def build_before_compaction_hook_metrics(
    original_messages: List[Any],
    current_messages: List[Any],
    observed_token_count: Optional[int],
    estimate_tokens_fn: Callable[[Any], int],
) -> Dict[str, Any]:
    """Build the before-hook metrics, tolerating provider estimation failures.

    Mirrors :func:`buildBeforeCompactionHookMetrics`
    (``compaction-hooks.ts:192-206``).
    """
    token_count_before = (
        observed_token_count
        if observed_token_count is not None
        else _estimate_token_count_safe(current_messages, estimate_tokens_fn)
    )
    return {
        "messageCountOriginal": len(original_messages),
        "tokenCountOriginal": _estimate_token_count_safe(
            original_messages, estimate_tokens_fn
        ),
        "messageCountBefore": len(current_messages),
        "tokenCountBefore": token_count_before,
    }


async def run_before_compaction_hooks(
    hook_runner: Optional[CompactionHookRunner] = None,
    session_id: str = "",
    session_key: Optional[str] = None,
    session_agent_id: str = "",
    workspace_dir: str = "",
    message_provider: Optional[str] = None,
    metrics: Optional[Dict[str, Any]] = None,
    on_hook_messages: Optional[Callable[[Dict[str, Any]], Any]] = None,
) -> Dict[str, Any]:
    """Run internal + plugin before-compaction hooks.

    Mirrors :func:`runBeforeCompactionHooks`
    (``compaction-hooks.ts:209-276``).
    """
    metrics = metrics or {}
    missing_session_key = not (session_key or "").strip()
    hook_session_key = (session_key or "").strip() or session_id
    internal_sink = _INTERNAL_HOOK_SINK
    if internal_sink is not None:
        try:
            await internal_sink(
                phase="before",
                session_id=session_id,
                hook_session_key=hook_session_key,
                missing_session_key=missing_session_key,
                metrics=metrics,
            )
        except Exception as err:
            log.warning("session:compact:before hook failed: %s", err)
    if hook_runner is not None and hook_runner.has_hooks("before_compaction"):
        try:
            await hook_runner.run_before_compaction(
                metrics={
                    "messageCount": metrics.get("messageCountBefore"),
                    "tokenCount": metrics.get("tokenCountBefore"),
                },
                context={
                    "sessionId": session_id,
                    "agentId": session_agent_id,
                    "sessionKey": hook_session_key,
                    "workspaceDir": workspace_dir,
                    "messageProvider": message_provider,
                },
            )
        except Exception as err:
            log.warning("before_compaction hook failed: %s", err)
    return {
        "hookSessionKey": hook_session_key,
        "missingSessionKey": missing_session_key,
    }


#: Internal hook sink (typed payload). Replace in tests to capture
#: what was emitted.
_INTERNAL_HOOK_SINK: Optional[Callable[..., Awaitable[Any]]] = None


def set_internal_hook_sink(
    sink: Optional[Callable[..., Awaitable[Any]]],
) -> None:
    """Install a custom internal hook sink. Pass ``None`` to clear."""
    global _INTERNAL_HOOK_SINK
    _INTERNAL_HOOK_SINK = sink


def estimate_tokens_after_compaction(
    messages_after: List[Any],
    observed_token_count: Optional[int],
    full_session_tokens_before: int,
    estimate_tokens_fn: Callable[[Any], int],
) -> Optional[int]:
    """Estimate post-compaction tokens and reject impossible growth.

    Mirrors :func:`estimateTokensAfterCompaction`
    (``compaction-hooks.ts:279-298``).
    """
    tokens_after = _estimate_token_count_safe(messages_after, estimate_tokens_fn)
    if tokens_after is None:
        return None
    sanity_baseline = (
        observed_token_count
        if observed_token_count is not None
        else full_session_tokens_before
    )
    if sanity_baseline > 0:
        allowed = (
            sanity_baseline
            if observed_token_count is not None
            else sanity_baseline * 1.1
        )
        if tokens_after > allowed:
            return None
    return tokens_after


async def run_after_compaction_hooks(
    hook_runner: Optional[CompactionHookRunner] = None,
    session_id: str = "",
    session_agent_id: str = "",
    hook_session_key: str = "",
    missing_session_key: bool = False,
    workspace_dir: str = "",
    message_provider: Optional[str] = None,
    message_count_after: int = 0,
    tokens_after: Optional[int] = None,
    compacted_count: int = 0,
    session_file: str = "",
    previous_session_id: Optional[str] = None,
    summary_length: Optional[int] = None,
    tokens_before: Optional[int] = None,
    first_kept_entry_id: Optional[str] = None,
    on_hook_messages: Optional[Callable[[Dict[str, Any]], Any]] = None,
) -> None:
    """Run internal + plugin after-compaction hooks.

    Mirrors :func:`runAfterCompactionHooks`
    (``compaction-hooks.ts:301-376``).
    """
    internal_sink = _INTERNAL_HOOK_SINK
    if internal_sink is not None:
        try:
            await internal_sink(
                phase="after",
                session_id=session_id,
                hook_session_key=hook_session_key,
                missing_session_key=missing_session_key,
                payload={
                    "sessionId": session_id,
                    "messageCount": message_count_after,
                    "tokenCount": tokens_after,
                    "compactedCount": compacted_count,
                    "summaryLength": summary_length,
                    "tokensBefore": tokens_before,
                    "tokensAfter": tokens_after,
                    "firstKeptEntryId": first_kept_entry_id,
                },
            )
        except Exception as err:
            log.warning("session:compact:after hook failed: %s", err)
    if hook_runner is not None and hook_runner.has_hooks("after_compaction"):
        metrics: Dict[str, Any] = {
            "messageCount": message_count_after,
            "tokenCount": tokens_after,
            "compactedCount": compacted_count,
            "sessionFile": session_file,
        }
        if previous_session_id is not None:
            metrics["previousSessionId"] = previous_session_id
        try:
            await hook_runner.run_after_compaction(
                metrics=metrics,
                context={
                    "sessionId": session_id,
                    "agentId": session_agent_id,
                    "sessionKey": hook_session_key,
                    "workspaceDir": workspace_dir,
                    "messageProvider": message_provider,
                },
            )
        except Exception as err:
            log.warning("after_compaction hook failed: %s", err)


__all__ = [
    "CompactionHookRunner",
    "as_compaction_hook_runner",
    "build_before_compaction_hook_metrics",
    "estimate_tokens_after_compaction",
    "run_after_compaction_hooks",
    "run_before_compaction_hooks",
    "run_post_compaction_side_effects",
    "set_internal_hook_sink",
    "set_memory_sync_sink",
    "set_transcript_sink",
]
