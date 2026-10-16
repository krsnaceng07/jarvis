"""Learning plugin — hooks the learning engine into the JARVIS runtime.

Registers HookBus listeners connecting the learning engine into the live agent loop
with event idempotency, scoped failure pattern checks, and debounced reflection.
All hooks are non-blocking, exception-contained, and strictly observational.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from jarvis_learning import LearningEngine
from jarvis_learning.events import AgentContext, EventIdempotencyStore

logger = logging.getLogger(__name__)

# Verification & runtime activation status flags
learning_plugin_loaded: bool = True
hook_registration_successful: bool = True
hook_events_received: int = 0
strategy_retrieval_events: int = 0
experience_records_created: int = 0
routing_decisions_recorded: int = 0
duplicate_events_suppressed: int = 0

# Singleton engine & idempotency store instances
_engine: LearningEngine | None = None
_idempotency_store: EventIdempotencyStore | None = None


def get_engine() -> LearningEngine:
    """Return the singleton learning engine, creating it if needed."""
    global _engine, _idempotency_store  # noqa: PLW0603
    if _engine is None:
        _engine = LearningEngine()
        _engine.startup()
        _idempotency_store = EventIdempotencyStore(db=_engine.db)
        logger.info("learning engine and idempotency store initialized")
    return _engine


def get_idempotency_store() -> EventIdempotencyStore:
    """Return the shared event idempotency store."""
    global _idempotency_store  # noqa: PLW0603
    if _idempotency_store is None:
        engine = get_engine()
        _idempotency_store = EventIdempotencyStore(db=engine.db)
    return _idempotency_store


def _extract_event_and_context(
    payload: Any = None, context: Any = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Universally extract event payload and execution context across hook callers.

    Supports:
    - OpenClaw 2-arg adapter: payload={"event": {...}, "hookCtx": {...}}
    - Flat HookBus dispatch: payload={"tool": ..., "args": ..., "call_id": ...}
    - Object-based events/context with dataclass or attribute access
    - Direct calls passing (event, context)
    """
    ev: dict[str, Any] = {}
    ctx: dict[str, Any] = {}

    if isinstance(payload, dict):
        if "event" in payload and isinstance(payload["event"], dict):
            ev = dict(payload["event"])
            if "hookCtx" in payload and isinstance(payload["hookCtx"], dict):
                ctx = dict(payload["hookCtx"])
        else:
            ev = dict(payload)
            if "hookCtx" in payload and isinstance(payload["hookCtx"], dict):
                ctx = dict(payload["hookCtx"])
    elif payload is not None:
        # Attribute-based event object
        ev = {
            "tool": getattr(
                payload, "tool", getattr(payload, "tool_name", getattr(payload, "toolName", ""))
            ),
            "args": getattr(
                payload, "args", getattr(payload, "tool_args", getattr(payload, "params", {}))
            ),
            "call_id": getattr(
                payload,
                "call_id",
                getattr(payload, "tool_call_id", getattr(payload, "toolCallId", "")),
            ),
            "attemptId": getattr(payload, "attemptId", getattr(payload, "attempt_id", 1)),
            "result": getattr(payload, "result", getattr(payload, "tool_result", None)),
            "is_error": getattr(payload, "is_error", getattr(payload, "error", False)),
            "messages": getattr(payload, "messages", []),
            "lastUserInput": getattr(
                payload,
                "lastUserInput",
                getattr(payload, "last_user_input", getattr(payload, "user_input", "")),
            ),
            "claimed_outcome": getattr(payload, "claimed_outcome", ""),
        }

    if isinstance(context, dict):
        ctx.update(context)
    elif context is not None:
        ctx.update(
            {
                "agentId": getattr(context, "agentId", getattr(context, "agent_id", "default")),
                "sessionId": getattr(
                    context, "sessionId", getattr(context, "session_id", "default")
                ),
                "attemptId": getattr(context, "attemptId", getattr(context, "attempt_id", 1)),
                "lastUserInput": getattr(
                    context, "lastUserInput", getattr(context, "last_user_input", "")
                ),
            }
        )

    return ev, ctx


# ── Hook Handlers ─────────────────────────────────────────────


async def on_before_prompt_build(
    payload: Any = None, context: Any = None, **kwargs: Any
) -> dict[str, Any] | None:
    """Inject learned strategies and relevant patterns before prompt compilation."""
    global strategy_retrieval_events, hook_events_received  # noqa: PLW0603
    hook_events_received += 1

    try:
        ev, ctx = _extract_event_and_context(payload, context)
        engine = get_engine()
        user_input = ""

        messages = ev.get("messages", [])
        if isinstance(messages, list):
            for msg in reversed(messages):
                if isinstance(msg, dict) and msg.get("role") == "user":
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                user_input = block.get("text", "")
                                break
                    elif isinstance(content, str):
                        user_input = content
                    break

        if not user_input:
            user_input = ctx.get("lastUserInput") or ev.get("lastUserInput") or ""

        if not user_input:
            return None

        strategy_retrieval_events += 1
        agent_id = str(ctx.get("agentId") or ctx.get("agent_id") or "default")
        session_id = str(ctx.get("sessionId") or ctx.get("session_id") or "default")
        workspace_id = str(ctx.get("workspaceId") or ctx.get("workspace_id") or "default")

        # 1. Evaluate task continuity
        continuity = engine.evaluate_task_continuity(
            user_input=user_input,
            session_id=session_id,
            context=ctx,
            workspace_id=workspace_id,
        )

        task_context = dict(ctx)
        if continuity.is_continuation and continuity.resource_target_id:
            task_context["target_id"] = continuity.resource_target_id

        # 2. Route turn through ModelRouter
        routing_result = engine.route_turn(
            user_input=user_input,
            session_id=session_id,
            context=task_context,
            local_models_enabled=engine.router.config.local_models_enabled,
            shadow_mode_enabled=engine.router.config.shadow_mode_enabled,
        )

        # 3. Check for learned strategies, lessons, or failure patterns
        retrieval = engine.retrieve_relevant(
            user_input=user_input,
            agent_id=agent_id,
        )
        prompt_section = retrieval.to_prompt_section()

        # 4. Build bounded, sanitized structured advisory injection if eligible
        advisory = engine.build_advisory_for_turn(routing_result)

        if not prompt_section and (not advisory.eligible or not advisory.context_text):
            return None

        if advisory.eligible and advisory.context_text and prompt_section:
            # Combine both within the bounded <learning_context>
            clean_body = advisory.context_text.replace("</learning_context>", "")
            combined = (
                clean_body.rstrip()
                + "\n  <!-- Learned Strategies & Lessons -->\n"
                + "\n".join(f"  {line}" for line in prompt_section.splitlines())
                + "\n</learning_context>"
            )
            return {"prependContext": f"\n{combined}\n"}

        if advisory.eligible and advisory.context_text:
            return {"prependContext": f"\n{advisory.context_text}\n"}

        return {
            "prependContext": f"\n<learning_context>\n{prompt_section}\n</learning_context>\n",
        }
    except Exception as e:
        logger.exception("learning: before_prompt_build failed: %s", e)
        return None


async def on_before_agent_start(
    payload: Any = None, context: Any = None, **kwargs: Any
) -> dict[str, Any] | None:
    """Observe agent turn initiation."""
    global hook_events_received  # noqa: PLW0603
    hook_events_received += 1
    return None


async def on_before_tool_call(
    payload: Any = None, context: Any = None, **kwargs: Any
) -> dict[str, Any] | None:
    """Check proposed tool call against scoped failure patterns (observational only)."""
    global hook_events_received, routing_decisions_recorded  # noqa: PLW0603
    hook_events_received += 1

    try:
        ev, _ = _extract_event_and_context(payload, context)
        engine = get_engine()

        tool_name = str(ev.get("tool") or ev.get("toolName") or ev.get("tool_name") or "")
        tool_args = ev.get("args") or ev.get("params") or ev.get("tool_args") or {}

        if not tool_name:
            return None

        routing_decisions_recorded += 1
        patterns = engine.check_tool_against_patterns(
            tool_name, tool_args if isinstance(tool_args, dict) else {}
        )
        if patterns:
            top = patterns[0]
            logger.warning(
                "learning: tool %s matches failure pattern '%s' (confidence=%.2f). Preferred: %s",
                tool_name,
                top.pattern_name,
                top.confidence,
                top.preferred_action,
            )

        return None
    except Exception as e:
        logger.exception("learning: before_tool_call failed: %s", e)
        return None


async def on_after_tool_call(
    payload: Any = None, context: Any = None, **kwargs: Any
) -> dict[str, Any] | None:
    """Capture tool execution outcome with durable two-tier idempotency."""
    global hook_events_received, experience_records_created, duplicate_events_suppressed  # noqa: PLW0603
    hook_events_received += 1

    try:
        ev, ctx = _extract_event_and_context(payload, context)

        tool_name = str(ev.get("tool") or ev.get("toolName") or ev.get("tool_name") or "")
        if not tool_name:
            return None

        tool_args = ev.get("args") or ev.get("params") or ev.get("tool_args") or {}
        tool_result = ev.get("result") or ev.get("tool_result")
        if tool_result is None and ev.get("is_error") is not None:
            tool_result = {
                "is_error": ev.get("is_error"),
                "duration_ms": ev.get("duration_ms", 0.0),
            }

        tool_call_id = str(
            ev.get("call_id")
            or ev.get("toolCallId")
            or ev.get("tool_call_id")
            or ev.get("id")
            or ""
        )
        attempt_id = int(
            ev.get("attemptId")
            or ev.get("attempt_id")
            or ctx.get("attemptId")
            or ctx.get("attempt_id")
            or 1
        )

        # Build AgentContext
        agent_id = str(ctx.get("agentId") or ctx.get("agent_id") or "default")
        session_id = str(ctx.get("sessionId") or ctx.get("session_id") or "default")
        agent_ctx = AgentContext(
            task_id=str(ctx.get("taskId") or ctx.get("task_id") or "default"),
            session_id=session_id,
            run_id=str(ctx.get("runId") or ctx.get("run_id") or "default"),
            agent_id=agent_id,
            sequence_number=attempt_id,
            tool_call_id=tool_call_id or None,
        )

        # Durable idempotency: check L1 memory + L2 SQLite
        if tool_call_id:
            store = get_idempotency_store()
            event_dedup_id = f"{tool_call_id}:{attempt_id}"
            if store.is_duplicate_and_record(
                agent_id=agent_ctx.agent_id,
                event_id=event_dedup_id,
                event_type="tool_completed",
            ):
                duplicate_events_suppressed += 1
                logger.debug(
                    "learning: skipping duplicate tool call event agent=%s id=%s",
                    agent_ctx.agent_id,
                    event_dedup_id,
                )
                return None

        engine = get_engine()
        user_input = str(
            ctx.get("lastUserInput")
            or ctx.get("last_user_input")
            or ev.get("lastUserInput")
            or ev.get("user_input")
            or ""
        )
        claimed_outcome = str(ev.get("claimed_outcome") or ctx.get("claimed_outcome") or "")

        # Physical outcome verification
        v_outcome = None
        try:
            from src.agents.verification.execution_verifier import ExecutionVerifier

            if tool_name == "write":
                v_outcome = ExecutionVerifier.verify_filesystem_write(
                    tool_args.get("path", ""),
                    expected_bytes=len(str(tool_args.get("content", "")).encode("utf-8")),
                )
            elif tool_name == "edit":
                v_outcome = ExecutionVerifier.verify_filesystem_edit(tool_args.get("path", ""))
            elif tool_name in ("remove_path", "rm"):
                v_outcome = ExecutionVerifier.verify_filesystem_removal(tool_args.get("path", ""))
            elif tool_name in ("rename_path", "mv"):
                v_outcome = ExecutionVerifier.verify_filesystem_rename(
                    tool_args.get("old_path", ""), tool_args.get("new_path", "")
                )
            elif tool_name == "audio":
                v_outcome = ExecutionVerifier.verify_audio_action(
                    action=str(tool_args.get("action", "")),
                    expected_volume=tool_args.get("percent") or tool_args.get("volume"),
                    expected_mute=tool_args.get("mute"),
                )
            elif tool_name == "exec":
                exit_code = (
                    int(tool_result.get("exit_code", 0)) if isinstance(tool_result, dict) else 0
                )
                v_outcome = ExecutionVerifier.verify_process_execution(
                    exit_code=exit_code,
                    stdout=str(
                        tool_result.get("stdout", "")
                        if isinstance(tool_result, dict)
                        else tool_result
                    ),
                    stderr=str(
                        tool_result.get("stderr", "") if isinstance(tool_result, dict) else ""
                    ),
                )
            elif tool_name in ("desktop", "desktop_action"):
                v_outcome = ExecutionVerifier.verify_desktop_action(
                    action=str(tool_args.get("action", "")),
                    target_app=str(tool_args.get("app") or tool_args.get("target") or ""),
                    output_text=str(tool_result),
                )
            else:
                v_outcome = ExecutionVerifier.verify_generic_tool(
                    tool_name=tool_name,
                    output_text=str(tool_result),
                )
        except Exception as v_err:
            logger.debug("ExecutionVerifier readback skipped/failed: %s", v_err)

        truthful_outcome = engine.truthfulness_enforcer.evaluate_outcome(
            tool_name=tool_name,
            tool_args=tool_args if isinstance(tool_args, dict) else {},
            tool_result=tool_result,
            verifier_outcome=v_outcome,
        )

        # Update task continuity
        stage_name = str(ctx.get("task_stage") or tool_name)
        engine.continuity_tracker.record_stage_transition(
            session_id=agent_ctx.session_id,
            stage_name=stage_name,
            success=truthful_outcome.verified,
            tool_call_id=tool_call_id,
            verification_status=truthful_outcome.outcome_class.value,
        )

        engine.record_tool_execution(
            session_id=agent_ctx.session_id,
            agent_id=agent_ctx.agent_id,
            user_input=user_input,
            tool_name=tool_name,
            tool_args=tool_args if isinstance(tool_args, dict) else {},
            tool_result=tool_result,
            claimed_outcome=claimed_outcome,
        )
        experience_records_created += 1
        return None
    except Exception as e:
        logger.exception("learning: after_tool_call failed: %s", e)
        return None


async def on_agent_end(
    payload: Any = None, context: Any = None, **kwargs: Any
) -> dict[str, Any] | None:
    """Run debounced reflection at agent turn completion."""
    global hook_events_received  # noqa: PLW0603
    hook_events_received += 1

    try:
        _, ctx = _extract_event_and_context(payload, context)
        engine = get_engine()
        session_id = str(ctx.get("sessionId") or ctx.get("session_id") or "")
        if session_id:
            engine.reflect_debounced(session_id=session_id, min_batch_size=1)
        return None
    except Exception as e:
        logger.exception("learning: agent_end reflection failed: %s", e)
        return None


async def on_session_start(
    payload: Any = None, context: Any = None, **kwargs: Any
) -> dict[str, Any] | None:
    """Observe session start."""
    global hook_events_received  # noqa: PLW0603
    hook_events_received += 1
    return None


async def on_session_end(
    payload: Any = None, context: Any = None, **kwargs: Any
) -> dict[str, Any] | None:
    """Flush all learning state cleanly to SQLite at session termination."""
    global hook_events_received  # noqa: PLW0603
    hook_events_received += 1

    try:
        engine = get_engine()
        engine.flush()
        logger.info("learning engine flushed at session end")
        return None
    except Exception as e:
        logger.exception("learning: session_end flush failed: %s", e)
        return None


def get_metrics() -> dict[str, Any]:
    """Return plugin lifecycle and hook invocation counters."""
    return {
        "learning_plugin_loaded": learning_plugin_loaded,
        "hook_registration_successful": hook_registration_successful,
        "hook_events_received": hook_events_received,
        "strategy_retrieval_events": strategy_retrieval_events,
        "experience_records_created": experience_records_created,
        "tool_calls_recorded": experience_records_created,
        "routing_decisions_recorded": routing_decisions_recorded,
        "duplicate_events_suppressed": duplicate_events_suppressed,
    }


class LearningPlugin:
    """Plugin adapter providing class-based lifecycle and hook invocation."""

    def __init__(self, engine: LearningEngine | None = None) -> None:
        if engine is not None:
            global _engine, _idempotency_store, hook_events_received, strategy_retrieval_events, experience_records_created, routing_decisions_recorded, duplicate_events_suppressed  # noqa: PLW0603
            _engine = engine
            _idempotency_store = EventIdempotencyStore(db=engine.db)
            hook_events_received = 0
            strategy_retrieval_events = 0
            experience_records_created = 0
            routing_decisions_recorded = 0
            duplicate_events_suppressed = 0

    def register(self, api: Any) -> None:
        """Register all hook handlers with PluginApi."""
        register(api)

    def before_prompt_build(self, event: Any = None, context: Any = None, **kwargs: Any) -> Any:
        return asyncio.run(on_before_prompt_build(event, context, **kwargs))

    def before_agent_start(self, event: Any = None, context: Any = None, **kwargs: Any) -> Any:
        return asyncio.run(on_before_agent_start(event, context, **kwargs))

    def before_tool_call(self, event: Any = None, context: Any = None, **kwargs: Any) -> Any:
        return asyncio.run(on_before_tool_call(event, context, **kwargs))

    def tool_called(self, event: Any = None, context: Any = None, **kwargs: Any) -> Any:
        return asyncio.run(on_before_tool_call(event, context, **kwargs))

    def after_tool_call(self, event: Any = None, context: Any = None, **kwargs: Any) -> Any:
        return asyncio.run(on_after_tool_call(event, context, **kwargs))

    def tool_completed(self, event: Any = None, context: Any = None, **kwargs: Any) -> Any:
        return asyncio.run(on_after_tool_call(event, context, **kwargs))

    def agent_end(self, event: Any = None, context: Any = None, **kwargs: Any) -> Any:
        return asyncio.run(on_agent_end(event, context, **kwargs))

    def session_start(self, event: Any = None, context: Any = None, **kwargs: Any) -> Any:
        return asyncio.run(on_session_start(event, context, **kwargs))

    def session_end(self, event: Any = None, context: Any = None, **kwargs: Any) -> Any:
        return asyncio.run(on_session_end(event, context, **kwargs))

    def get_metrics(self) -> dict[str, Any]:
        return get_metrics()


# Explicit hook dispatch mappings covering both OpenClaw standards and runtime aliases
HOOK_HANDLERS: dict[str, Any] = {
    "before_prompt_build": on_before_prompt_build,
    "before_agent_start": on_before_agent_start,
    "before_tool_call": on_before_tool_call,
    "tool_called": on_before_tool_call,
    "after_tool_call": on_after_tool_call,
    "tool_completed": on_after_tool_call,
    "agent_end": on_agent_end,
    "session_start": on_session_start,
    "session_end": on_session_end,
}


def register(api: Any) -> None:
    """Canonical OpenClaw plugin registration entrypoint."""
    global hook_registration_successful  # noqa: PLW0603
    try:
        if hasattr(api, "register_hook"):
            for hook_name, handler in HOOK_HANDLERS.items():
                api.register_hook(hook_name, handler)
        hook_registration_successful = True
        logger.info("learning plugin registered successfully with HookBus via PluginApi")
    except Exception:
        hook_registration_successful = False
        logger.exception("failed to register learning hooks via PluginApi")
        raise


plugin = LearningPlugin()
entry = {"register": register, "plugin": plugin}
