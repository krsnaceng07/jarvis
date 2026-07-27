"""jarvis_agent.turn_interruption — interrupted-turn plumbing.

OpenClaw parity: ``packages/agent-core/src/turn-interruption.ts`` (88 lines).

Deliberately **not** exported from the package ``__init__``: upstream keeps
these helpers out of the package barrel on purpose ("internal loop/harness
plumbing, not public agent-core API surface"), and this port preserves that
boundary. The loop and the harness import from this module directly.

Two easy-to-miss contracts
==========================

``create_failure_message`` here is not ``jarvis_llm.stream.create_failure_message``
    The stream-level helper builds ``content=[]`` and attaches diagnostics.
    This one is the *turn-interruption* shape from the TS source: exactly one
    empty text block and a fully zeroed usage including the nested cost.
    Session renderers distinguish "run produced nothing" from "run failed
    mid-provider-call" by that shape, so the two must not be unified.

Turn-handoff aborts skip the guidance
    A yield-style tool aborts the run *deliberately* to hand the turn to
    another runtime. Appending "tools may have partially executed" after
    such a clean stop would mislead the next turn, so
    :func:`is_turn_handoff_abort` gates the guidance.
"""

from __future__ import annotations

import inspect
from typing import Any, Callable, Union

from jarvis_llm.abort import AbortSignal, TurnHandoffAbort
from jarvis_llm.types import (
    AssistantMessage,
    Cost,
    Model,
    TextContent,
    Usage,
    UserMessage,
    now_ms,
)

from .types import AgentEvent, AgentMessage, CustomMessage
from .types import AgentEventMessageEnd, AgentEventMessageStart

#: Parity: ``INTERRUPTED_TURN_GUIDANCE`` — module-private constant in the TS,
#: replayed into model context (as a user message, via
#: :func:`normalize_core_context_messages`) after an interrupted turn.
INTERRUPTED_TURN_GUIDANCE = (
    "<turn_aborted>\n"
    "The previous turn was interrupted. Any running background processes may "
    "still be active. If any tools or commands were aborted, they may have "
    "partially executed.\n"
    "</turn_aborted>"
)

#: Parity: ``customType: "openclaw:turn-aborted"`` — the discriminator both
#: :func:`create_interrupted_turn_message` writes and
#: :func:`normalize_core_context_messages` matches on. One constant so the
#: two can never drift apart.
TURN_ABORTED_CUSTOM_TYPE = "openclaw:turn-aborted"


def create_failure_message(
    model: Model,
    error: object,
    aborted: bool,
) -> AssistantMessage:
    """Canonical empty aborted/error assistant recorded when a run ends
    without output. Parity: ``createFailureMessage`` in turn-interruption.ts.

    Shape contract (load-bearing, see module docstring): ``content`` is one
    empty text block — not an empty list — and ``usage`` is all zeros
    including the nested cost.
    """
    return AssistantMessage(
        api=model.api,
        provider=model.provider,
        model=model.id,
        content=[TextContent(text="")],
        usage=Usage(
            input=0,
            output=0,
            cache_read=0,
            cache_write=0,
            total_tokens=0,
            cost=Cost(input=0, output=0, cache_read=0, cache_write=0, total=0),
        ),
        stop_reason="aborted" if aborted else "error",
        # TS: `error instanceof Error ? error.message : String(error)`.
        # In Python str() covers both branches: str(exc) is the message.
        error_message=str(error),
        timestamp=now_ms(),
    )


def is_turn_handoff_abort(signal: AbortSignal | None) -> bool:
    """Whether an abort is an intentional turn handoff.

    Parity: ``isTurnHandoffAbort(signal)``. TS checks
    ``signal.reason.turnHandoff === true`` on an object reason. Python abort
    reasons are exceptions (:mod:`jarvis_llm.abort`), so the primary check is
    the :class:`TurnHandoffAbort` type; a ``turn_handoff`` attribute set to
    ``True`` on any other reason object is honoured for structural parity
    with the TS duck-check.
    """
    if signal is None or not signal.aborted:
        return False
    reason = signal.reason
    if isinstance(reason, TurnHandoffAbort):
        return True
    return getattr(reason, "turn_handoff", None) is True


def create_interrupted_turn_message() -> CustomMessage:
    """Parity: ``createInterruptedTurnMessage`` — hidden custom message
    carrying the interruption guidance."""
    return CustomMessage(
        custom_type=TURN_ABORTED_CUSTOM_TYPE,
        content=INTERRUPTED_TURN_GUIDANCE,
        display=False,
        timestamp=now_ms(),
    )


async def append_interrupted_turn_message(
    messages: list[AgentMessage],
    emit: Callable[[AgentEvent], Union[Any, None]],
) -> None:
    """Append the guidance message and emit its start/end events.

    Parity: ``appendInterruptedTurnMessage(messages, emit)``. ``emit`` may be
    sync or return an awaitable, matching ``Promise<void> | void``.
    """
    interruption = create_interrupted_turn_message()
    messages.append(interruption)
    await _maybe_await(emit(AgentEventMessageStart(message=interruption)))
    await _maybe_await(emit(AgentEventMessageEnd(message=interruption)))


def normalize_core_context_messages(
    messages: list[AgentMessage],
) -> list[AgentMessage]:
    """Rewrite turn-aborted custom messages into plain user messages.

    Parity: ``normalizeCoreContextMessages``. Providers never see the
    ``custom`` role; the guidance must reach the model as user content. Any
    other message passes through unchanged (same object, not a copy).
    """
    normalized: list[AgentMessage] = []
    for message in messages:
        if (
            getattr(message, "role", None) != "custom"
            or getattr(message, "custom_type", None) != TURN_ABORTED_CUSTOM_TYPE
        ):
            normalized.append(message)
            continue
        content = message.content
        normalized.append(
            UserMessage(
                content=[TextContent(text=content)] if isinstance(content, str) else content,
                timestamp=message.timestamp,
            )
        )
    return normalized


async def _maybe_await(value: object) -> None:
    """Settle ``Promise<void> | void`` results from an emit callback."""
    if inspect.isawaitable(value):
        await value


__all__ = [
    "INTERRUPTED_TURN_GUIDANCE",
    "TURN_ABORTED_CUSTOM_TYPE",
    "append_interrupted_turn_message",
    "create_failure_message",
    "create_interrupted_turn_message",
    "is_turn_handoff_abort",
    "normalize_core_context_messages",
]
