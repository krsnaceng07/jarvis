"""index — active-memory plugin entry: hooks, slash command, doctor.

OpenClaw parity: mirrors ``extensions/active-memory/index.ts``.

Phase 4.2c: the main plugin entry that wires:

- The ``/active-memory`` slash command (status / on /
  off / help; with ``--global`` to mutate the operator's
  config file via the host's ``mutateConfigFile``). The
  global mutation is admin-gated via the
  ``lacks_admin_to_mutate_active_memory_global`` check.
- The ``before_prompt_build`` hook. The hook enforces a
  preflight deadline (separate from the recall deadline)
  so the eligibility / config / session-disabled checks
  cannot consume recall settlement time. The full recall
  flow is delegated to ``maybe_resolve_active_recall``.

The 4.2c commit closes the active-memory port: with
this file + the doctor migration in
``doctor_contract_api.py``, the active-memory plugin
is feature-complete against OpenClaw's index.

Surface
-------
- ``register_active_memory(api)`` — the host-facing
  registration entry point. Mirrors OpenClaw's
  ``register(api)`` callback.
- ``build_active_memory_testing()`` — re-exports the
  small surface other modules / tests use to reset
  module-level state + drive the recall flow.

Dependencies
============
- ``extensions.active_memory.config`` — config parse +
  deprecation warning + test hooks.
- ``extensions.active_memory.prompt`` — ``build_prompt_prefix``.
- ``extensions.active_memory.query`` — ``get_model_ref``,
  ``build_query``, ``build_search_query``,
  ``extract_recent_turns``.
- ``extensions.active_memory.recall`` — ``maybe_resolve_active_recall``.
- ``extensions.active_memory.recall_state`` — log helpers.
- ``extensions.active_memory.session_policy`` —
  ``is_session_active_memory_disabled``,
  ``set_session_active_memory_disabled``,
  ``is_eligible_interactive_session``, etc.
- ``extensions.active_memory.session`` — status-line +
  canonical-session-key + agent-id helpers.
- ``extensions.active_memory.transcript`` — ``create_active_memory_hook_deadline``.
- ``extensions.active_memory.types`` — recall-flow types
  + the memory-core plugin id constant.
- ``jarvis_sdk.normalize_plugins_config``,
  ``jarvis_sdk.resolve_live_plugin_config_object``.
- The host provides ``api.runtime.config.mutateConfigFile``,
  ``api.runtime.config.current``, the
  ``before_prompt_build`` hook bus, and the slash-command
  router.
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any, cast

from jarvis_sdk import normalize_plugins_config, resolve_live_plugin_config_object

from .config import (
    apply_cli_runtime_recall_timeout_default,
    has_deprecated_model_fallback_policy,
    is_missing_registered_memory_tools_error,
    normalize_plugin_config,
    reset_active_memory_config_for_tests,
    set_minimum_timeout_ms_for_tests,
    set_setup_grace_timeout_ms_for_tests,
)
from .doctor_contract_api import state_migrations
from .prompt import build_prompt_prefix
from .query import build_query, build_search_query, extract_recent_turns, get_model_ref
from .recall import maybe_resolve_active_recall
from .recall_state import to_single_line_log_value
from .session import (
    build_plugin_status_line,
    persist_plugin_status_lines,
    resolve_canonical_session_key_from_session_id,
    resolve_status_update_agent_id,
)
from .session_policy import (
    ACTIVE_MEMORY_GLOBAL_MUTATION_ADMIN_REQUIRED_TEXT,
    format_active_memory_command_help,
    has_remember_across_conversations_agent,
    is_active_memory_globally_enabled,
    is_active_memory_plugin_enabled,
    is_allowed_chat_id,
    is_allowed_chat_type,
    is_eligible_interactive_session,
    is_enabled_for_agent,
    is_private_recall_destination,
    is_session_active_memory_disabled,
    lacks_admin_to_mutate_active_memory_global,
    resolve_command_session_key,
    set_session_active_memory_disabled,
    should_remember_across_conversations,
    should_skip_active_memory_for_harness_session,
    update_active_memory_global_enabled_in_config,
)
from .transcript import create_active_memory_hook_deadline
from .transcript_result import (
    reset_active_memory_transcript_for_tests,
    set_timeout_partial_data_grace_ms_for_tests,
)
from .transcript_watch import read_active_memory_search_debug
from .types import (
    HOOK_TIMEOUT_RECOVERY_GRACE_MS,
    MAX_SETUP_GRACE_TIMEOUT_MS,
    MAX_TIMEOUT_MS,
    ConversationRecallContext,
)

# Mirrors OpenClaw's:
#   const MEMORY_CORE_PLUGIN_ID = "memory-core";
MEMORY_CORE_PLUGIN_ID = "memory-core"

_log = logging.getLogger("extensions.active_memory")


def _read_current_config(api: Any) -> Any:
    """Read the live config via the host's runtime, fall back to ``api.config``.

    Mirrors OpenClaw's ``readCurrentConfig`` closure.
    """
    try:
        runtime = getattr(api, "runtime", None)
        runtime_config = getattr(runtime, "config", None) if runtime else None
        current = getattr(runtime_config, "current", None) if runtime_config else None
        if callable(current):
            return current()
        return getattr(api, "config", None)
    except Exception:
        return getattr(api, "config", None)


def _warn_deprecated_model_fallback_policy(api: Any, plugin_config: Any) -> None:
    """Log the model-fallback-policy deprecation warning.

    Mirrors OpenClaw's ``warnDeprecatedModelFallbackPolicy``.
    """
    if not has_deprecated_model_fallback_policy(plugin_config):
        return
    logger = getattr(api, "logger", None)
    warn = getattr(logger, "warn", None) if logger else None
    if not callable(warn):
        return
    warn(
        "active-memory: config.modelFallbackPolicy is deprecated and no longer changes runtime behavior. "
        "config.modelFallback is a chain-resolution last-resort (consulted only when config.model, "
        "the current run's model, and the agent's configured default all resolve to nothing) — "
        "it is NOT a runtime failover that substitutes a different model when the resolved model errors out."
    )


def register_active_memory(api: Any) -> None:  # noqa: PLR0915 — mirrors OpenClaw's full registration surface
    """Register the active-memory plugin's surface with the host.

    Mirrors OpenClaw's ``register(api)`` callback.

    Wires:

    1. The ``/active-memory`` slash command (status / on /
       off / help; ``--global`` for admin-gated operator
       config mutation).
    2. The ``before_prompt_build`` hook (preflight
       eligibility + config refresh + session toggle check
       + harness skip + recall race).
    """
    # Suppress unused import warnings for items that are
    # re-exported below or used in the testing helpers.
    _ = (
        build_plugin_status_line,
        read_active_memory_search_debug,
        is_missing_registered_memory_tools_error,
    )

    # Read + normalize the static plugin config.
    plugin_config = getattr(api, "pluginConfig", None) or {}
    config = normalize_plugin_config(plugin_config, _read_current_config(api))
    _warn_deprecated_model_fallback_policy(api, plugin_config)

    def _refresh_live_config_from_runtime() -> Any:
        """Refresh ``config`` from the live runtime config.

        Mirrors OpenClaw's ``refreshLiveConfigFromRuntime``.
        Resolves the live plugin config object via the
        host's runtime, falls back to a disabled
        configuration when the live config doesn't have a
        remembered-across-conversations agent, and
        re-normalizes the result.
        """
        nonlocal config
        runtime = getattr(api, "runtime", None)
        runtime_config = getattr(runtime, "config", None) if runtime else None
        current = getattr(runtime_config, "current", None) if runtime_config else None
        current_fn: Any = current if callable(current) else None
        live_plugin_config = resolve_live_plugin_config_object(
            current_fn,
            "active-memory",
            plugin_config if isinstance(plugin_config, dict) else {},
        )
        live_config = _read_current_config(api)
        fallback_config: dict[str, Any] = (
            {}
            if live_config and has_remember_across_conversations_agent(live_config)
            else {"enabled": False}
        )
        if live_config and not is_active_memory_plugin_enabled(live_config):
            effective_plugin_config: dict[str, Any] = {"enabled": False}
        else:
            effective_plugin_config = (
                live_plugin_config if live_plugin_config is not None else fallback_config
            )
        config = normalize_plugin_config(effective_plugin_config, live_config)
        if live_plugin_config is not None:
            _warn_deprecated_model_fallback_policy(api, live_plugin_config)
        return live_config

    # ── Slash command ───────────────────────────────────────
    if hasattr(api, "register_command"):

        async def _active_memory_command_handler(ctx: dict[str, Any]) -> dict[str, Any]:  # noqa: PLR0911 — mirrors OpenClaw's per-tool branching
            args_raw = ctx.get("args") or ""
            tokens = [arg for arg in args_raw.split() if arg]
            is_global = "--global" in tokens
            action = next(
                (arg.lower() for arg in tokens if arg != "--global"),
                "status",
            )
            if action == "help":
                return {"text": format_active_memory_command_help()}
            live_config = _refresh_live_config_from_runtime()
            if is_global:
                runtime = getattr(api, "runtime", None)
                runtime_config = getattr(runtime, "config", None) if runtime else None
                current = runtime_config.current() if runtime_config else live_config
                if action == "status":
                    on = is_active_memory_globally_enabled(current) if current else False
                    return {"text": f"Active Memory: {'on' if on else 'off'} globally."}
                if lacks_admin_to_mutate_active_memory_global(
                    {
                        "senderIsOwner": ctx.get("senderIsOwner"),
                        "gatewayClientScopes": ctx.get("gatewayClientScopes"),
                    }
                ):
                    return {"text": ACTIVE_MEMORY_GLOBAL_MUTATION_ADMIN_REQUIRED_TEXT}
                if action in ("on", "enable", "enabled"):
                    await _mutate_active_memory_global(api, True)
                    _refresh_live_config_from_runtime()
                    return {"text": "Active Memory: on globally."}
                if action in ("off", "disable", "disabled"):
                    await _mutate_active_memory_global(api, False)
                    _refresh_live_config_from_runtime()
                    return {"text": "Active Memory: off globally."}
            session_key = resolve_command_session_key(
                {
                    "api": api,
                    "config": config,
                    "sessionKey": ctx.get("sessionKey"),
                    "sessionId": ctx.get("sessionId"),
                }
            )
            if not session_key:
                return {
                    "text": (
                        "Active Memory: session toggle unavailable because this command "
                        "has no session context."
                    )
                }
            command_agent_id = resolve_status_update_agent_id({"sessionKey": session_key})
            command_live_config = _read_current_config(api) or getattr(api, "config", None)
            command_recall_enabled = is_enabled_for_agent(config, command_agent_id) or (
                bool(config.get("enabled"))
                and should_remember_across_conversations(command_live_config, command_agent_id)
            )
            if not command_recall_enabled:
                return {"text": "Active Memory: off for this session."}
            if action == "status":
                disabled = await is_session_active_memory_disabled(
                    {"api": api, "sessionKey": session_key}
                )
                return {"text": f"Active Memory: {'off' if disabled else 'on'} for this session."}
            if action in ("on", "enable", "enabled"):
                await set_session_active_memory_disabled(
                    {"api": api, "sessionKey": session_key, "disabled": False}
                )
                return {"text": "Active Memory: on for this session."}
            if action in ("off", "disable", "disabled"):
                await set_session_active_memory_disabled(
                    {"api": api, "sessionKey": session_key, "disabled": True}
                )
                await persist_plugin_status_lines(
                    {
                        "api": api,
                        "agentId": resolve_status_update_agent_id({"sessionKey": session_key}),
                        "sessionKey": session_key,
                    }
                )
                return {"text": "Active Memory: off for this session."}
            return {
                "text": f"Unknown Active Memory action: {action}\n\n{format_active_memory_command_help()}"
            }

        api.register_command(
            {
                "name": "active-memory",
                "description": "Enable, disable, or inspect Active Memory for this session.",
                "accepts_args": True,
                "expose_sender_is_owner": True,
                "handler": _active_memory_command_handler,
            }
        )

    # ── before_prompt_build hook ──────────────────────────────
    # Preflight and recall own separate deadlines. Reserve
    # enough hook time for both maxima so preflight latency
    # cannot consume recall settlement time.
    before_prompt_build_timeout_ms = (
        MAX_TIMEOUT_MS + MAX_SETUP_GRACE_TIMEOUT_MS + HOOK_TIMEOUT_RECOVERY_GRACE_MS * 2
    )

    async def _before_prompt_build(  # noqa: PLR0915 — mirrors OpenClaw's hook setup
        event: dict[str, Any], ctx: dict[str, Any]
    ) -> dict[str, Any] | None:
        """The pre-prompt recall hook.

        Mirrors OpenClaw's ``before_prompt_build`` handler.
        """
        _refresh_live_config_from_runtime()
        live_config = _read_current_config(api) or getattr(api, "config", None)
        # The hook deadline, watchdog, and embedded-run
        # budget all flow from this config, so the
        # CLI-runtime default raise must happen before any
        # of them are armed.
        timeout_agent_id = resolve_status_update_agent_id(ctx)
        timeout_model_ref = (
            get_model_ref(
                live_config,
                timeout_agent_id,
                config,
                {
                    "modelProviderId": ctx.get("modelProviderId"),
                    "modelId": ctx.get("modelId"),
                },
            )
            if timeout_agent_id
            else {
                "provider": ctx.get("modelProviderId"),
                "model": ctx.get("modelId"),
            }
        ) or {}
        cli_dispatch_eligibility = _resolve_cli_backend_dispatch_eligibility(
            api,
            timeout_model_ref.get("provider"),
            timeout_model_ref.get("model"),
            live_config,
            timeout_agent_id,
        )
        invocation_config = apply_cli_runtime_recall_timeout_default(
            config,
            cli_dispatch_eligibility is not None,
        )
        live_recall_timeout_ms = (
            invocation_config.get("timeoutMs", 0)
            + invocation_config.get("setupGraceTimeoutMs", 0)
            + HOOK_TIMEOUT_RECOVERY_GRACE_MS
        )
        deadline_controller = _new_hook_abort_controller()
        hook_deadline = create_active_memory_hook_deadline()

        def _arm_hook_deadline(timeout_ms: int, phase: str) -> None:
            hook_deadline["arm"](
                timeout_ms,
                lambda: _on_hook_deadline(api, deadline_controller, phase, timeout_ms),
            )

        _arm_hook_deadline(HOOK_TIMEOUT_RECOVERY_GRACE_MS, "preflight")

        async def _handler() -> dict[str, Any] | None:  # noqa: PLR0911, PLR0912 — mirrors OpenClaw's recall state machine
            try:
                resolved_agent_id = resolve_status_update_agent_id(ctx)
                resolved_session_key = (ctx.get("sessionKey") or "").strip() or (
                    resolve_canonical_session_key_from_session_id(
                        {
                            "api": api,
                            "agentId": resolved_agent_id or "",
                            "sessionId": ctx.get("sessionId"),
                        }
                    )
                    if resolved_agent_id
                    else None
                )
                effective_agent_id = resolved_agent_id or resolve_status_update_agent_id(
                    {"sessionKey": resolved_session_key}
                )
                if should_skip_active_memory_for_harness_session(
                    {
                        "api": api,
                        "agentId": effective_agent_id,
                        "sessionKey": resolved_session_key,
                    }
                ):
                    return None
                session_disabled = await is_session_active_memory_disabled(
                    {
                        "api": api,
                        "sessionKey": resolved_session_key,
                    }
                )
                if _is_aborted(deadline_controller):
                    raise _abort_error(deadline_controller)
                if session_disabled:
                    await persist_plugin_status_lines(
                        {
                            "api": api,
                            "agentId": effective_agent_id,
                            "sessionKey": resolved_session_key,
                        }
                    )
                    return None
                session_context = {
                    **ctx,
                    "sessionKey": resolved_session_key or ctx.get("sessionKey"),
                }
                if not is_eligible_interactive_session(session_context):
                    await persist_plugin_status_lines(
                        {
                            "api": api,
                            "agentId": effective_agent_id,
                            "sessionKey": resolved_session_key,
                        }
                    )
                    return None
                destination_context = {
                    **session_context,
                    "mainKey": (
                        (live_config.get("session") or {}).get("mainKey")
                        if isinstance(live_config, dict)
                        else None
                    )
                    or (getattr(api.config, "session", None) or {}).get("mainKey")
                    if isinstance(getattr(api.config, "session", None), dict)
                    else None,
                }
                active_memory_configured = is_enabled_for_agent(
                    invocation_config, effective_agent_id
                )
                chat_id_allowed = is_allowed_chat_id(
                    invocation_config,
                    {
                        "sessionKey": destination_context.get("sessionKey"),
                        "messageProvider": destination_context.get("messageProvider"),
                        "channelId": destination_context.get("channelId"),
                    },
                )
                active_memory_allowed = (
                    active_memory_configured
                    and is_allowed_chat_type(invocation_config, destination_context)
                    and chat_id_allowed
                )
                product_recall_requested = bool(
                    invocation_config.get("enabled")
                    and resolved_session_key
                    and should_remember_across_conversations(live_config, effective_agent_id)
                    and is_private_recall_destination(destination_context)
                    and chat_id_allowed
                )
                if not isinstance(live_config, dict):
                    memory_slot = None
                else:
                    plugins_section = live_config.get("plugins")
                    normalized_plugins = normalize_plugins_config(plugins_section)
                    memory_slot = normalized_plugins.get("slots", {}).get("memory")
                product_recall_eligible = (
                    product_recall_requested and memory_slot == MEMORY_CORE_PLUGIN_ID
                )
                if product_recall_requested and not product_recall_eligible:
                    _log_warning(
                        api,
                        "active-memory: the current memory provider does not support "
                        "protected private transcript recall; skipping Remember "
                        "across conversations",
                    )
                product_recall_allowed = product_recall_eligible and bool(
                    "memory_search" in (invocation_config.get("toolsAllow") or [])
                )
                if product_recall_eligible and not product_recall_allowed:
                    _log_warning(
                        api,
                        "active-memory: memory_search is unavailable; skipping "
                        "Remember across conversations private transcript recall",
                    )
                if not active_memory_allowed and not product_recall_allowed:
                    await persist_plugin_status_lines(
                        {
                            "api": api,
                            "agentId": effective_agent_id,
                            "sessionKey": resolved_session_key,
                        }
                    )
                    return None
                conversation_recall: ConversationRecallContext | None = cast(
                    ConversationRecallContext | None,
                    (
                        {
                            "anchorSessionKey": resolved_session_key or "",
                            "scope": "same-agent-private",
                            "corpus": "configured" if active_memory_allowed else "sessions",
                        }
                        if product_recall_allowed and resolved_session_key
                        else None
                    ),
                )
                recall_config = (
                    {**invocation_config, "toolsAllow": ["memory_search"]}
                    if product_recall_allowed and not active_memory_allowed
                    else invocation_config
                )
                recent_turns = extract_recent_turns(event.get("messages") or [])
                query = build_query(
                    {
                        "latestUserMessage": event.get("prompt", ""),
                        "recentTurns": recent_turns,
                        "config": recall_config,
                    }
                )
                search_query = build_search_query(
                    {
                        "latestUserMessage": event.get("prompt", ""),
                        "recentTurns": recent_turns,
                    }
                )
                # Start recall with its full configured
                # budget. The preceding session / config
                # checks must not consume abort-settlement
                # time.
                _arm_hook_deadline(live_recall_timeout_ms, "recall")
                result = await maybe_resolve_active_recall(
                    {
                        "api": api,
                        "runtimeConfig": live_config,
                        "config": recall_config,
                        "agentId": effective_agent_id,
                        "sessionKey": resolved_session_key,
                        "sessionId": ctx.get("sessionId"),
                        "messageProvider": ctx.get("messageProvider"),
                        "channelId": ctx.get("channelId"),
                        "query": query,
                        "searchQuery": search_query,
                        "currentModelProviderId": ctx.get("modelProviderId"),
                        "currentModelId": ctx.get("modelId"),
                        "conversationRecall": conversation_recall,
                        "abortSignal": _get_signal(deadline_controller),
                    }
                )
                if _is_aborted(deadline_controller):
                    raise _abort_error(deadline_controller)
                summary = result.get("summary")
                if not summary:
                    return None
                prompt_prefix = build_prompt_prefix(summary)
                if not prompt_prefix:
                    return None
                return {"prependContext": prompt_prefix}
            except BaseException as exc:
                if _is_aborted(deadline_controller):
                    return None
                if isinstance(exc, BaseException) and not isinstance(exc, Exception):
                    raise
                _log_warning(
                    api,
                    f"active-memory: before_prompt_build failed, skipping memory lookup: "
                    f"{to_single_line_log_value(str(exc))}",
                )
                return None

        try:
            outcome = await _race_handler_with_deadline(_handler(), hook_deadline["promise"])
            return None if _is_deadline_sentinel(outcome) else outcome
        finally:
            hook_deadline["stop"]()

    if hasattr(api, "on"):
        api.on(
            "before_prompt_build",
            _before_prompt_build,
            {"timeoutMs": before_prompt_build_timeout_ms},
        )


# ── Module-level helpers ────────────────────────────────────────


async def _mutate_active_memory_global(api: Any, enabled: bool) -> None:
    """Mutate the operator's config file to enable/disable active-memory globally.

    Mirrors OpenClaw's ``api.runtime.config.mutateConfigFile({...})`` call.
    """
    runtime = getattr(api, "runtime", None)
    runtime_config = getattr(runtime, "config", None) if runtime else None
    mutate = getattr(runtime_config, "mutate_config_file", None) if runtime_config else None
    if not callable(mutate):
        return

    def _mutate(draft: Any) -> None:
        next_config = update_active_memory_global_enabled_in_config(draft, enabled)
        if isinstance(draft, dict) and isinstance(next_config, dict):
            draft.clear()
            draft.update(next_config)
        else:
            for key in list(getattr(draft, "__dict__", {}) or []):
                setattr(draft, key, getattr(next_config, key, None))

    try:
        result = mutate({"afterWrite": {"mode": "auto"}, "mutate": _mutate})
        if hasattr(result, "__await__"):
            await result  # type: ignore[arg-type,misc]
    except Exception:  # noqa: S110 — best-effort config mutate
        pass


def _log_warning(api: Any, message: str) -> None:
    """Best-effort ``api.logger.warn?.()`` wrapper."""
    logger = getattr(api, "logger", None)
    if logger is None:
        return
    warn = getattr(logger, "warn", None)
    if callable(warn):
        with contextlib.suppress(Exception):
            warn(message)


def _resolve_cli_backend_dispatch_eligibility(
    api: Any,
    provider: Any,
    model: Any,
    live_config: Any,
    agent_id: Any,
) -> Any:
    """Resolve CLI backend dispatch eligibility for the recall.

    Mirrors OpenClaw's
    ``api.runtime.agent.resolveCliBackendDispatchEligibility``.
    """
    runtime = getattr(api, "runtime", None)
    runtime_agent = getattr(runtime, "agent", None) if runtime else None
    resolver = (
        getattr(runtime_agent, "resolve_cli_backend_dispatch_eligibility", None)
        if runtime_agent
        else None
    )
    if not callable(resolver):
        return None
    params: dict[str, Any] = {
        "provider": provider,
        "model": model,
        "config": live_config,
    }
    if agent_id:
        from jarvis_sdk import resolve_agent_dir, resolve_agent_workspace_dir

        params["agentId"] = agent_id
        params["agentDir"] = resolve_agent_dir(live_config or {}, agent_id)
        params["workspaceDir"] = resolve_agent_workspace_dir(live_config or {}, agent_id)
    try:
        return resolver(params)
    except Exception:
        return None


def _new_hook_abort_controller() -> Any:
    """Create a small abort controller for the hook deadline."""

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


def _get_signal(controller: Any) -> Any:
    return getattr(controller, "signal", None)


def _is_aborted(controller: Any) -> bool:
    signal = _get_signal(controller)
    return signal is not None and getattr(signal, "aborted", False)


def _abort_error(controller: Any) -> BaseException:
    signal = _get_signal(controller)
    reason = getattr(signal, "reason", None) if signal is not None else None
    if isinstance(reason, BaseException):
        return reason
    err = TimeoutError("active-memory hook deadline exceeded")
    err.name = "AbortError"
    return err


async def _on_hook_deadline(api: Any, controller: Any, phase: str, timeout_ms: int) -> None:
    """Handler called by the hook deadline on timeout."""
    if _is_aborted(controller):
        return
    _abort_controller(
        controller, RuntimeError(f"active-memory {phase} timeout after {timeout_ms}ms")
    )
    _log_warning(
        api,
        f"active-memory: before_prompt_build {phase} timed out after {timeout_ms}ms; "
        f"skipping memory lookup",
    )


def _abort_controller(controller: Any, reason: Any) -> None:
    if hasattr(controller, "abort"):
        with contextlib.suppress(Exception):
            controller.abort(reason)
    elif hasattr(controller, "signal") and hasattr(controller.signal, "aborted"):
        with contextlib.suppress(Exception):
            controller.signal.aborted = True


def _is_deadline_sentinel(value: Any) -> bool:
    """A non-string, non-bool, non-int, non-dict sentinel from the deadline.

    Mirrors OpenClaw's ``typeof result === "symbol"`` check.
    The deadline helper resolves with a Python ``object()``
    sentinel; we detect it by type — anything that isn't a
    recognized result type.
    """
    return not isinstance(value, dict | type(None) | bool | int | float | str | list | tuple)


async def _race_handler_with_deadline(handler_coro: Any, deadline_promise: Any) -> Any:
    """Race the recall handler against the hook deadline.

    Mirrors OpenClaw's
    ``Promise.race([handlerPromise, hookDeadline.promise])``.
    """
    import asyncio

    async def _await_deadline() -> Any:
        # The deadline future is owned by the
        # create_active_memory_hook_deadline helper; we
        # just await it. The future is resolved with a
        # sentinel object when the deadline fires.
        try:
            return await asyncio.shield(deadline_promise)
        except asyncio.CancelledError:
            return object()

    handler_task = asyncio.ensure_future(handler_coro)
    deadline_task = asyncio.ensure_future(_await_deadline())
    done, _pending = await asyncio.wait(
        [handler_task, deadline_task],
        return_when=asyncio.FIRST_COMPLETED,
    )
    winner = next(iter(done)) if done else None
    if winner is handler_task:
        deadline_task.cancel()
        return winner.result() if winner is not None else None
    handler_task.cancel()
    if winner is None:
        return None
    return winner.result()


async def _await_value(awaitable: Any) -> Any:
    """Await an arbitrary awaitable; return its result."""
    return await awaitable


# ── Testing surface (re-exports) ─────────────────────────────────


def build_active_memory_testing() -> dict[str, Any]:
    """Re-export the small surface other modules / tests use.

    Mirrors OpenClaw's ``testing`` export at the bottom of
    ``index.ts``.
    """
    from . import recall_state as _recall_state_module

    def _reset_active_recall_cache_for_tests() -> None:
        _recall_state_module.reset_active_recall_state_for_tests()
        reset_active_memory_config_for_tests()
        reset_active_memory_transcript_for_tests()

    return {
        "buildSearchQuery": build_search_query,
        "buildCacheKey": _recall_state_module.build_cache_key,
        "buildCircuitBreakerKey": _recall_state_module.build_circuit_breaker_key,
        "buildPromptPrefix": build_prompt_prefix,
        "buildPluginStatusLine": build_plugin_status_line,
        "getCachedResult": _recall_state_module.get_cached_result,
        "getCircuitBreakerEntry": _recall_state_module.get_circuit_breaker_entry,
        "isCircuitBreakerOpen": _recall_state_module.is_circuit_breaker_open,
        "isMissingRegisteredMemoryToolsError": is_missing_registered_memory_tools_error,
        "normalizePluginConfig": normalize_plugin_config,
        "readActiveMemorySearchDebug": read_active_memory_search_debug,
        "readPartialAssistantText": _get_read_partial_assistant_text(),
        "resetActiveRecallCacheForTests": _reset_active_recall_cache_for_tests,
        "setMinimumTimeoutMsForTests": set_minimum_timeout_ms_for_tests,
        "setSetupGraceTimeoutMsForTests": set_setup_grace_timeout_ms_for_tests,
        "setTimeoutPartialDataGraceMsForTests": (set_timeout_partial_data_grace_ms_for_tests),
        "setCachedResult": _recall_state_module.set_cached_result,
        "shouldCacheResult": _recall_state_module.should_cache_result,
    }


def _get_read_partial_assistant_text() -> Any:
    from .transcript_result import read_partial_assistant_text

    return read_partial_assistant_text


__all__ = [
    "MEMORY_CORE_PLUGIN_ID",
    "build_active_memory_testing",
    "register_active_memory",
    "state_migrations",
]
