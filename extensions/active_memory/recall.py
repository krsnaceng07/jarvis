"""recall — top-level recall orchestration.

OpenClaw parity: mirrors ``extensions/active-memory/recall.ts``.

Phase 4.2b step 3: ports the recall orchestration. The
flow is:

1. Honour ``abortSignal`` (re-raise if already aborted).
2. Build a cache key (skipped for conversation recall —
   eligibility may have changed since the last run).
3. Return 'maybe' serve the cached result.
4. Build the model resolution chain
   (``config.model`` -> current run -> agent primary ->
   ``config.modelFallback``).
5. Short-circuit on the circuit breaker (per
   agent / model / consecutive timeouts).
6. Resolve the run context (parent session key, store
   path, fastMode from session or agent config).
7. Race the sub-agent against the watchdog timeout and
   the terminal-memory-search watch.
8. On timeout: build ``timeout`` or ``timeout_partial``,
   record the circuit-breaker timeout, schedule
   memory-search cleanup.
9. On terminal-memory-search result: bail out with
   ``unavailable`` (the recall result).
10. On successful sub-agent: build ``ok`` /
    ``failed`` / ``unavailable`` / ``no_relevant_memory``,
    reset the circuit breaker, write the result to the
    cache (if eligible).

Surface
-------
- ``format_active_memory_fast_mode`` — render the
  ``ActiveMemoryFastMode`` as ``"inherit"`` / ``"on"`` /
  ``"off"`` / ``"auto"`` for log lines.
- ``prepare_recall_run_context`` — resolve the parent
  session key, store path, and effective fastMode for
  the recall run.
- ``maybe_resolve_active_recall`` — the top-level entry
  point. Returns the ``ActiveRecallResult`` (ok / failed
  / unavailable / no_relevant_memory / timeout /
  timeout_partial).

Dependencies
============
- ``jarvis_normalization_core.text_utility.truncate_utf16_safe``
- ``jarvis_sdk.as_optional_record`` /
  ``normalize_optional_string``
- ``extensions.active_memory.query.get_model_ref``
- ``extensions.active_memory.transcript_watch.watch_terminal_memory_search_result``
- ``extensions.active_memory.transcript_result.{build_subagent_recall_result, build_timeout_recall_result, read_partial_timeout_data}``
- ``extensions.active_memory.recall_state`` — TTL cache,
  circuit breaker, log helpers, cleanup scheduler.
- ``extensions.active_memory.session.{build_persisted_debug_summary, build_plugin_status_line, persist_plugin_status_lines, resolve_canonical_session_key_from_session_id}``
- ``extensions.active_memory.config.normalize_active_memory_fast_mode``
- ``extensions.active_memory.types`` — recall-flow types
  and constants.
"""

# pyright: reportOptionalMemberAccess=false
# pyright: reportAssignmentType=false
# ruff: noqa: SIM105, S110, PLR0911, PLR0912, PLR0915, PLR2004, C901, PLR0917, N803, N806, RET504

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import Any, cast

from jarvis_sdk import (
    as_optional_record,
    resolve_agent_config,
)

from .config import normalize_active_memory_fast_mode
from .query import get_model_ref
from .recall_state import (
    build_cache_key,
    build_circuit_breaker_key,
    get_cached_result,
    is_circuit_breaker_open,
    record_circuit_breaker_timeout,
    reset_circuit_breaker,
    schedule_memory_search_cleanup_after_timeout,
    set_cached_result,
    should_cache_result,
    to_single_line_log_value,
)
from .session import (
    build_persisted_debug_summary,
    build_plugin_status_line,
    persist_plugin_status_lines,
    resolve_canonical_session_key_from_session_id,
)
from .transcript_result import (
    build_subagent_recall_result,
    build_timeout_recall_result,
    read_partial_timeout_data,
)
from .transcript_watch import watch_terminal_memory_search_result
from .types import (
    ActiveMemoryFastMode,
    ActiveMemorySearchDebug,
    ActiveMemoryTranscriptSource,
    ActiveRecallResult,
    ResolvedActiveRecallPluginConfig,
    TerminalMemorySearchWatch,
)


def format_active_memory_fast_mode(fast_mode: ActiveMemoryFastMode | None) -> str:
    """Render ``fastMode`` for log lines."""
    if fast_mode is None:
        return "inherit"
    if fast_mode is True:
        return "on"
    if fast_mode is False:
        return "off"
    return "auto"


def prepare_recall_run_context(params: dict[str, Any]) -> dict[str, Any]:
    """Resolve the parent session key, store path, fastMode.

    Mirrors OpenClaw's ``prepareRecallRunContext``. The
    parent session key falls back to the canonical session
    key resolved from the ``sessionId``. The fastMode
    is read from the session entry (per-session override)
    then from the agent config (``fastModeDefault``).
    """
    api = params.get("api")
    runtime_config = params.get("runtimeConfig")
    config = params.get("config")
    agent_id = params.get("agentId", "")
    parent_session_key = params.get("sessionKey")
    if not parent_session_key and api is not None:
        parent_session_key = resolve_canonical_session_key_from_session_id(
            {
                "api": api,
                "agentId": agent_id,
                "sessionId": params.get("sessionId"),
            }
        )
    if api is not None and hasattr(api.runtime.agent, "session"):
        store_path = api.runtime.agent.session.resolve_store_path(
            as_optional_record(runtime_config or {}).get("session", {}).get("store")
            if isinstance(runtime_config, dict)
            else None,
            {"agentId": agent_id},
        )
    else:
        store_path = ""
    if config.get("fastMode") is not None:
        return {
            "parentSessionKey": parent_session_key,
            "storePath": store_path,
            "fastMode": config.get("fastMode"),
        }
    session_fast_mode: Any = None
    if parent_session_key and api is not None and hasattr(api.runtime.agent, "session"):
        try:
            session_entry = api.runtime.agent.session.get_session_entry(
                {
                    "agentId": agent_id,
                    "sessionKey": parent_session_key,
                    "storePath": store_path,
                    "readConsistency": "latest",
                }
            )
            if isinstance(session_entry, dict):
                session_fast_mode = session_entry.get("fastMode")
        except Exception:
            session_fast_mode = None
    fast_mode = normalize_active_memory_fast_mode(
        session_fast_mode
    ) or normalize_active_memory_fast_mode(
        (resolve_agent_config(runtime_config, agent_id) or {}).get("fastModeDefault")
    )
    return {
        "parentSessionKey": parent_session_key,
        "storePath": store_path,
        "fastMode": fast_mode,
    }


async def maybe_resolve_active_recall(
    params: dict[str, Any],
) -> ActiveRecallResult:
    """The top-level recall entry point.

    Mirrors OpenClaw's ``maybeResolveActiveRecall``. The
    flow is documented at the top of this module.
    """
    api = params.get("api")
    runtime_config = params.get("runtimeConfig")
    config: ResolvedActiveRecallPluginConfig = params["config"]
    agent_id: str = params.get("agentId", "")
    session_key: str | None = params.get("sessionKey")
    session_id: str | None = params.get("sessionId")
    abort_signal: Any = params.get("abortSignal")
    started_at = int(time.time() * 1000)

    # Step 1: abort pre-check.
    if abort_signal is not None and hasattr(abort_signal, "throw_if_aborted"):
        try:
            abort_signal.throw_if_aborted()
        except BaseException:
            raise

    # Step 2: cache key (skipped for conversation recall —
    # eligibility may have changed since the last run).
    cache_key: str | None = None
    if not params.get("conversationRecall"):
        cache_key = build_cache_key(
            {
                "agentId": agent_id,
                "sessionKey": session_key,
                "sessionId": session_id,
                "query": params.get("query", ""),
            }
        )

    # Step 3: serve cached result.
    cached: ActiveRecallResult | None = None
    if cache_key:
        cached = get_cached_result(cache_key)

    # Step 4: model resolution chain.
    resolved_model_ref = get_model_ref(
        runtime_config,
        agent_id,
        config,
        {
            "modelProviderId": params.get("currentModelProviderId"),
            "modelId": params.get("currentModelId"),
        },
    )

    def _build_log_prefix(fast_mode: ActiveMemoryFastMode | None) -> str:
        return " ".join(
            [
                f"active-memory: agent={to_single_line_log_value(agent_id)}",
                f"session={to_single_line_log_value(session_key or session_id or 'none')}",
                *(
                    [f"activeProvider={to_single_line_log_value(resolved_model_ref['provider'])}"]
                    if resolved_model_ref and resolved_model_ref.get("provider")
                    else []
                ),
                *(
                    [f"activeModel={to_single_line_log_value(resolved_model_ref['model'])}"]
                    if resolved_model_ref and resolved_model_ref.get("model")
                    else []
                ),
                f"thinking={config.get('thinking', 'off')}",
                f"fast={format_active_memory_fast_mode(fast_mode)}",
            ]
        )

    log_prefix = _build_log_prefix(config.get("fastMode"))
    if cached is not None:
        if abort_signal is not None and hasattr(abort_signal, "throw_if_aborted"):
            abort_signal.throw_if_aborted()
        await persist_plugin_status_lines(
            {
                "api": api,
                "agentId": agent_id,
                "sessionKey": session_key,
                "statusLine": (
                    f"{build_plugin_status_line({'result': cached, 'config': config})} cached"
                ),
                "debugSummary": build_persisted_debug_summary(cached),
                "searchDebug": cached.get("searchDebug"),
            }
        )
        if abort_signal is not None and hasattr(abort_signal, "throw_if_aborted"):
            abort_signal.throw_if_aborted()
        if config.get("logging"):
            try:
                api.logger.info(
                    f"{log_prefix} cached status={cached.get('status')} "
                    f"summaryChars={len(cached.get('summary') or '')} "
                    f"queryChars={len(params.get('query', ''))}"
                )
            except Exception:
                pass
        return cached

    # Step 5: circuit breaker.
    cb_key = build_circuit_breaker_key(
        agent_id,
        resolved_model_ref.get("provider") if resolved_model_ref else None,
        resolved_model_ref.get("model") if resolved_model_ref else None,
    )
    timeout_cleanup_scheduled = False

    def _schedule_timeout_cleanup() -> None:
        nonlocal timeout_cleanup_scheduled
        if timeout_cleanup_scheduled:
            return
        timeout_cleanup_scheduled = True
        schedule_memory_search_cleanup_after_timeout(api, log_prefix, agent_id)

    circuit_breaker_timeout_recorded = False

    def _record_recall_timeout() -> None:
        nonlocal circuit_breaker_timeout_recorded
        if not circuit_breaker_timeout_recorded:
            circuit_breaker_timeout_recorded = True
            record_circuit_breaker_timeout(cb_key)
        _schedule_timeout_cleanup()

    if is_circuit_breaker_open(
        cb_key,
        config.get("circuitBreakerMaxTimeouts") or 0,
        config.get("circuitBreakerCooldownMs") or 0,
    ):
        result: ActiveRecallResult = {
            "status": "timeout",
            "elapsedMs": 0,
            "summary": None,
        }
        if config.get("logging"):
            try:
                api.logger.info(
                    f"{log_prefix} skipped (circuit breaker open after consecutive timeouts)"
                )
            except Exception:
                pass
        if abort_signal is not None and hasattr(abort_signal, "throw_if_aborted"):
            abort_signal.throw_if_aborted()
        await persist_plugin_status_lines(
            {
                "api": api,
                "agentId": agent_id,
                "sessionKey": session_key,
                "statusLine": (
                    f"{build_plugin_status_line({'result': result, 'config': config})} "
                    f"circuit-breaker"
                ),
            }
        )
        return result

    # Step 6: run context.
    run_context = prepare_recall_run_context(params)
    log_prefix = _build_log_prefix(run_context.get("fastMode"))

    if config.get("logging"):
        try:
            api.logger.info(
                f"{log_prefix} start timeoutMs={config.get('timeoutMs', 0)} "
                f"queryChars={len(params.get('query', ''))} "
                f"searchQueryChars={len(params.get('searchQuery', ''))}"
            )
        except Exception:
            pass

    # Step 7: race the sub-agent against the watchdog timeout
    # and the terminal-memory-search watch.
    controller = _new_abort_controller()

    def _abort_from_parent() -> None:
        _abort_controller(controller, _abort_reason(abort_signal))

    if abort_signal is not None and hasattr(abort_signal, "add_event_listener"):
        try:
            abort_signal.add_event_listener("abort", _abort_from_parent, once=True)  # type: ignore[arg-type]
        except (NotImplementedError, TypeError):  # pragma: no cover
            pass
    if abort_signal is not None and getattr(abort_signal, "aborted", False):
        _abort_from_parent()
    timeout_sentinel = object()
    transcript_sources: list[ActiveMemoryTranscriptSource] = []
    recall_timed_out = False
    watchdog_timeout_ms = (config.get("timeoutMs") or 0) + (config.get("setupGraceTimeoutMs") or 0)
    timeout_handle: Any = None

    def _start_watchdog() -> Any:
        def _on_watchdog() -> None:
            nonlocal recall_timed_out
            if abort_signal is not None and getattr(abort_signal, "aborted", False):
                return
            recall_timed_out = True
            _abort_controller(
                controller, RuntimeError(f"active-memory timeout after {watchdog_timeout_ms}ms")
            )

        try:
            loop = asyncio.get_running_loop()
            return loop.call_later(max(0, int(watchdog_timeout_ms)) / 1000.0, _on_watchdog)
        except RuntimeError:  # pragma: no cover
            return None

    def _clear_watchdog(handle: Any) -> None:
        if handle is not None:
            with _Suppress(Exception):
                handle.cancel()

    def _make_timeout_promise() -> Any:
        future: asyncio.Future[Any] = asyncio.get_event_loop().create_future()

        def _on_abort() -> None:
            if not future.done():
                future.set_result(timeout_sentinel)

        if hasattr(controller, "signal") and hasattr(controller.signal, "add_event_listener"):
            try:
                controller.signal.add_event_listener("abort", _on_abort, once=True)  # type: ignore[arg-type]
            except (NotImplementedError, TypeError):  # pragma: no cover
                pass
        return future

    timeout_handle = _start_watchdog()
    timeout_promise = _make_timeout_promise()
    terminal_watch: TerminalMemorySearchWatch | None = None
    recall_in_flight = False
    try:
        recall_in_flight = True
        from .recall_run import run_recall_subagent  # local import to avoid cycle

        subagent_promise = run_recall_subagent(
            {
                **params,
                "modelRef": resolved_model_ref,
                "parentSessionKey": run_context.get("parentSessionKey"),
                "storePath": run_context.get("storePath", ""),
                "fastMode": run_context.get("fastMode"),
                "abortSignal": getattr(controller, "signal", None),
                "onTranscriptSources": lambda sources: _set_sources(transcript_sources, sources),
            }
        )
        terminal_watch = watch_terminal_memory_search_result(
            {
                "getTranscriptSources": lambda: list(transcript_sources),
                "abortSignal": getattr(controller, "signal", None),
                "toolsAllow": config.get("toolsAllow") or (),
            }
        )
        # Silently catch late rejections after timeout so they
        # don't become unhandled promise rejections.
        if hasattr(subagent_promise, "add_done_callback"):

            def _swallow(_task: Any) -> None:
                pass

            subagent_promise.add_done_callback(_swallow)

        race_result = await asyncio.wait(
            [
                _ensure_task(subagent_promise),
                _ensure_task(timeout_promise),
                _ensure_task(terminal_watch["promise"]),
            ],
            return_when=asyncio.FIRST_COMPLETED,
        )
        race_result = race_result.pop().result() if race_result else timeout_sentinel
        if terminal_watch is not None:
            terminal_watch["stop"]()
        fallback_search_debug: ActiveMemorySearchDebug | None = None
        fallback_has_usable_memory_result = False
        if (
            race_result is not timeout_sentinel
            and isinstance(race_result, dict)
            and "status" in race_result
            and race_result.get("hasUsableMemoryResult")
        ):
            # A later unavailable call must not discard a
            # summary grounded in an earlier successful recall.
            # The existing watchdog remains the deadline.
            fallback_search_debug = race_result.get("searchDebug")
            fallback_has_usable_memory_result = True
            race_result = await _race_subagent_timeout(subagent_promise, timeout_promise)
        if race_result is not timeout_sentinel:
            recall_in_flight = False

        if race_result is timeout_sentinel:
            if recall_timed_out:
                _record_recall_timeout()
            elif (
                abort_signal is not None
                and getattr(abort_signal, "aborted", False)
                and recall_in_flight
            ):
                _schedule_timeout_cleanup()
            elapsed_ms = int(time.time() * 1000) - started_at
            if fallback_has_usable_memory_result:
                result = cast(  # type: ignore[name-defined]
                    ActiveRecallResult,
                    {
                        "status": "timeout",
                        "elapsedMs": elapsed_ms,
                        "summary": None,
                        "searchDebug": fallback_search_debug,
                    },
                )
            else:
                result = await build_timeout_recall_result(
                    {
                        "elapsedMs": elapsed_ms,
                        "maxSummaryChars": config.get("maxSummaryChars") or 0,
                        "transcriptSources": list(transcript_sources),
                        "subagentPromise": subagent_promise,
                        "toolsAllow": config.get("toolsAllow") or (),
                    }
                )
            if config.get("logging"):
                try:
                    api.logger.info(
                        f"{log_prefix} done status={result.get('status')} "
                        f"elapsedMs={result.get('elapsedMs', 0)} "
                        f"summaryChars={len(result.get('summary') or '')}"
                    )
                except Exception:
                    pass
            if abort_signal is not None and hasattr(abort_signal, "throw_if_aborted"):
                abort_signal.throw_if_aborted()
            await persist_plugin_status_lines(
                {
                    "api": api,
                    "agentId": agent_id,
                    "sessionKey": session_key,
                    "statusLine": build_plugin_status_line({"result": result, "config": config}),
                    "debugSummary": build_persisted_debug_summary(result),
                    "searchDebug": result.get("searchDebug"),
                }
            )
            if abort_signal is not None and hasattr(abort_signal, "throw_if_aborted"):
                abort_signal.throw_if_aborted()
            return result

        if isinstance(race_result, dict) and "status" in race_result:
            _abort_controller(
                controller, RuntimeError("active-memory terminal memory search result")
            )
            result = cast(  # type: ignore[name-defined]
                ActiveRecallResult,
                {
                    "status": race_result["status"],
                    "elapsedMs": int(time.time() * 1000) - started_at,
                    "summary": None,
                    "searchDebug": race_result.get("searchDebug"),
                },
            )
            if config.get("logging"):
                try:
                    api.logger.info(
                        f"{log_prefix} done status={result.get('status')} "
                        f"elapsedMs={result.get('elapsedMs', 0)} "
                        f"summaryChars={len(result.get('summary') or '')}"
                    )
                except Exception:
                    pass
            reset_circuit_breaker(cb_key)
            if abort_signal is not None and hasattr(abort_signal, "throw_if_aborted"):
                abort_signal.throw_if_aborted()
            await persist_plugin_status_lines(
                {
                    "api": api,
                    "agentId": agent_id,
                    "sessionKey": session_key,
                    "statusLine": build_plugin_status_line({"result": result, "config": config}),
                    "searchDebug": result.get("searchDebug"),
                }
            )
            if abort_signal is not None and hasattr(abort_signal, "throw_if_aborted"):
                abort_signal.throw_if_aborted()
            if cache_key and should_cache_result(result):
                set_cached_result(cache_key, result, config.get("cacheTtlMs") or 0)
            return result

        # Successful sub-agent result.
        transcript_path = (
            race_result.get("transcriptPath") if isinstance(race_result, dict) else None
        )
        if config.get("logging") and transcript_path:
            with contextlib.suppress(Exception):
                api.logger.info(f"{log_prefix} transcript={transcript_path}")

        result = build_subagent_recall_result(
            {
                "subagentResult": race_result,
                "fallbackSearchDebug": fallback_search_debug,
                "fallbackHasUsableMemoryResult": fallback_has_usable_memory_result,
                "elapsedMs": int(time.time() * 1000) - started_at,
                "maxSummaryChars": config.get("maxSummaryChars") or 0,
            }
        )
        if config.get("logging"):
            try:
                api.logger.info(
                    f"{log_prefix} done status={result.get('status')} "
                    f"elapsedMs={result.get('elapsedMs', 0)} "
                    f"summaryChars={len(result.get('summary') or '')}"
                )
            except Exception:
                pass
        reset_circuit_breaker(cb_key)
        if abort_signal is not None and hasattr(abort_signal, "throw_if_aborted"):
            abort_signal.throw_if_aborted()
        await persist_plugin_status_lines(
            {
                "api": api,
                "agentId": agent_id,
                "sessionKey": session_key,
                "statusLine": build_plugin_status_line({"result": result, "config": config}),
                "debugSummary": build_persisted_debug_summary(result),
                "searchDebug": result.get("searchDebug"),
            }
        )
        if abort_signal is not None and hasattr(abort_signal, "throw_if_aborted"):
            abort_signal.throw_if_aborted()
        if cache_key and should_cache_result(result):
            set_cached_result(cache_key, result, config.get("cacheTtlMs") or 0)
        return result
    except BaseException as exc:
        if abort_signal is not None and getattr(abort_signal, "aborted", False):
            if recall_timed_out:
                _record_recall_timeout()
            elif recall_in_flight:
                _schedule_timeout_cleanup()
            if hasattr(abort_signal, "throw_if_aborted"):
                abort_signal.throw_if_aborted()
        if getattr(controller, "signal", None) is not None and getattr(
            controller.signal, "aborted", False
        ):
            if recall_timed_out:
                _record_recall_timeout()
            partial_data = read_partial_timeout_data(exc)
            result = await build_timeout_recall_result(
                {
                    "elapsedMs": int(time.time() * 1000) - started_at,
                    "maxSummaryChars": config.get("maxSummaryChars") or 0,
                    "transcriptSources": list(transcript_sources),
                    "rawReply": partial_data.get("rawReply"),
                    "searchDebug": partial_data.get("searchDebug"),
                    "hasUnavailableMemorySearchResult": bool(
                        partial_data.get("hasUnavailableMemorySearchResult")
                    ),
                    "toolsAllow": config.get("toolsAllow") or (),
                }
            )
            if config.get("logging"):
                try:
                    api.logger.info(
                        f"{log_prefix} done status={result.get('status')} "
                        f"elapsedMs={result.get('elapsedMs', 0)} "
                        f"summaryChars={len(result.get('summary') or '')}"
                    )
                except Exception:
                    pass
            if abort_signal is not None and hasattr(abort_signal, "throw_if_aborted"):
                abort_signal.throw_if_aborted()
            await persist_plugin_status_lines(
                {
                    "api": api,
                    "agentId": agent_id,
                    "sessionKey": session_key,
                    "statusLine": build_plugin_status_line({"result": result, "config": config}),
                    "debugSummary": build_persisted_debug_summary(result),
                    "searchDebug": result.get("searchDebug"),
                }
            )
            if abort_signal is not None and hasattr(abort_signal, "throw_if_aborted"):
                abort_signal.throw_if_aborted()
            return result
        if config.get("logging"):
            try:
                api.logger.warn(
                    f"{log_prefix} failed error={to_single_line_log_value(str(exc))}; skipping recall"
                )
            except Exception:
                pass
        result = cast(  # type: ignore[name-defined]
            ActiveRecallResult,
            {
                "status": "failed",
                "elapsedMs": int(time.time() * 1000) - started_at,
                "summary": None,
            },
        )
        if abort_signal is not None and hasattr(abort_signal, "throw_if_aborted"):
            abort_signal.throw_if_aborted()
        await persist_plugin_status_lines(
            {
                "api": api,
                "agentId": agent_id,
                "sessionKey": session_key,
                "statusLine": build_plugin_status_line({"result": result, "config": config}),
                "searchDebug": result.get("searchDebug"),
            }
        )
        return result
    finally:
        if abort_signal is not None and hasattr(abort_signal, "remove_event_listener"):
            with _Suppress(Exception):
                abort_signal.remove_event_listener("abort", _abort_from_parent)
        if terminal_watch is not None:
            with _Suppress(Exception):
                terminal_watch["stop"]()
        _clear_watchdog(timeout_handle)


# ── Internal helpers (imported lazily) ───────────────────────────


def _abort_reason(abort_signal: Any) -> Any:
    if abort_signal is None:
        return None
    return getattr(abort_signal, "reason", None)


def _abort_controller(controller: Any, reason: Any) -> None:
    """Trigger an abort on the local ``controller``."""
    if hasattr(controller, "abort"):
        with _Suppress(Exception):
            controller.abort(reason)
    elif hasattr(controller, "signal") and hasattr(controller.signal, "aborted"):
        with _Suppress(Exception):
            controller.signal.aborted = True


def _new_abort_controller() -> Any:
    """Create a small abort-controller / signal pair.

    Mirrors ``new AbortController()`` in OpenClaw. We avoid
    ``asyncio``'s own ``AbortSignal`` because the host's
    signal may come from a different loop / thread; the
    recall loop only needs ``abort()`` and ``aborted``.
    """

    class _Signal:
        def __init__(self) -> None:
            self.aborted = False
            self.reason: Any = None

    class _Controller:
        def __init__(self) -> None:
            self.signal = _Signal()

        def abort(self, reason: Any = None) -> None:
            self.signal.aborted = True
            self.signal.reason = reason

    return _Controller()


def _ensure_task(awaitable: Any) -> Any:
    """Wrap a coroutine / future in an ``asyncio.Task``.

    Mirrors OpenClaw's pattern of racing three values. If
    the value is already a coroutine, schedule it. If it's
    a future, return as-is.
    """
    if asyncio.iscoroutine(awaitable) or asyncio.isfuture(awaitable):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return awaitable
        if asyncio.iscoroutine(awaitable):
            return asyncio.ensure_future(awaitable, loop=loop)
    return awaitable


async def _race_subagent_timeout(subagent_promise: Any, timeout_promise: Any) -> Any:
    """Race the sub-agent against the timeout, return whoever finishes first."""
    done, _pending = await asyncio.wait(
        [_ensure_task(subagent_promise), _ensure_task(timeout_promise)],
        return_when=asyncio.FIRST_COMPLETED,
    )
    return done.pop().result() if done else timeout_promise


def _set_sources(target: list, sources: Any) -> None:
    """Update the captured ``transcript_sources`` list."""
    target.clear()
    if isinstance(sources, list):
        target.extend(sources)
    elif sources:
        target.append(sources)


class _Suppress:
    """Inline ``contextlib.suppress`` replacement that accepts a single class."""

    def __init__(self, *exceptions: type) -> None:
        self._exceptions = exceptions

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return exc_type is not None and issubclass(exc_type, self._exceptions)


__all__ = [
    "format_active_memory_fast_mode",
    "maybe_resolve_active_recall",
    "prepare_recall_run_context",
]
