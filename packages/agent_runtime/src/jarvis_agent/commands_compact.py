"""/compact command handler and manual compaction orchestration.

Port of ``src/auto-reply/reply/commands-compact.ts``.

Handles the user-initiated ``/compact [instructions]`` command.  Also
provides runtime helpers that the auto-compaction loop re-uses:
``resolve_manual_compact_context_token_budget``,
``format_compaction_reason``, and ``is_compaction_skip_reason``.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    pass  # heavy imports deferred to reduce cold-start cost

# ---------------------------------------------------------------------------
# Skip / reason classification
# ---------------------------------------------------------------------------

#: Compaction skip reasons — mirrors ``CompactionSkipReason`` in TS.
CompactionSkipReason = Literal[
    "already_small",
    "recently_compacted",
    "no_messages",
    "no_model",
    "disabled",
]

#: Reasons the caller should treat as benign no-ops (no error notice needed).
_BENIGN_SKIP_REASONS: frozenset[str] = frozenset(
    {
        "already_small",
        "recently_compacted",
        "no_messages",
    }
)


def is_compaction_skip_reason(reason: Any) -> bool:
    """Return True when *reason* is a recognised skip-reason literal.

    Parity: ``isCompactionSkipReason``.
    """
    return isinstance(reason, str) and reason in {
        "already_small",
        "recently_compacted",
        "no_messages",
        "no_model",
        "disabled",
    }


def format_compaction_reason(reason: Any) -> str:
    """Return a human-readable description for a compaction skip/error reason.

    Parity: ``formatCompactionReason``.
    """
    _MESSAGES: dict[str, str] = {
        "already_small": "Context is small enough; compaction not needed.",
        "recently_compacted": "Context was recently compacted; skipping.",
        "no_messages": "No messages to compact.",
        "no_model": "No model configured; cannot compact.",
        "disabled": "Compaction is disabled.",
    }
    if isinstance(reason, str) and reason in _MESSAGES:
        return _MESSAGES[reason]
    if isinstance(reason, str):
        return reason
    return "Compaction skipped."


def is_benign_skip(reason: Any) -> bool:
    """Return True for skip reasons that don't need an error notice.

    Parity: ``isBenignSkipReason`` (inline check in ``commands-compact.ts``).
    """
    return isinstance(reason, str) and reason in _BENIGN_SKIP_REASONS


# ---------------------------------------------------------------------------
# Instruction extraction
# ---------------------------------------------------------------------------

#: Regex to strip `/compact` (with optional @agent-name prefix) from body.
_COMPACT_CMD_RE = re.compile(r"^(?:@[\w-]+\s+)?/compact\s*", re.IGNORECASE)

#: Regex to strip leading group mentions like ``@agent-name`` from raw body.
_GROUP_MENTION_RE = re.compile(r"^@[\w-]+\s+", re.IGNORECASE)


def extract_compact_instructions(
    raw_body: str,
    *,
    is_group: bool = False,
) -> str | None:
    """Strip the ``/compact`` prefix and return the custom instruction text.

    Returns ``None`` when no custom instructions were provided.
    Parity: ``extractCompactInstructions``.

    Args:
        raw_body: The raw user message body (may start with ``/compact``).
        is_group: When True, also strip a leading ``@agent-name`` mention.
    """
    text = raw_body.strip()
    if is_group:
        text = _GROUP_MENTION_RE.sub("", text)
    text = _COMPACT_CMD_RE.sub("", text).strip()
    return text if text else None


# ---------------------------------------------------------------------------
# Context token budget resolution
# ---------------------------------------------------------------------------


def resolve_manual_compact_context_token_budget(
    session_context_window_tokens: int | None = None,
    config_context_window_tokens: int | None = None,
    model_context_window_tokens: int | None = None,
) -> int:
    """Resolve the effective context token budget for a manual /compact call.

    Parity: ``resolveManualCompactContextTokenBudget``.

    Priority order (first non-None positive int wins):
    1. Live session context window (from last assistant usage snapshot).
    2. Model context window from model metadata.
    3. Config-specified override.
    4. Hardcoded default (200 000).
    """
    _DEFAULT = 200_000
    candidates = [
        session_context_window_tokens,
        model_context_window_tokens,
        config_context_window_tokens,
    ]
    for c in candidates:
        if isinstance(c, (int, float)) and c > 0:
            return int(c)
    return _DEFAULT


# ---------------------------------------------------------------------------
# Full /compact handler
# ---------------------------------------------------------------------------


async def handle_compact_command(
    *,
    raw_body: str,
    session_messages: list[Any],
    model: Any | None = None,
    api_key: str | None = None,
    headers: dict[str, Any] | None = None,
    signal: Any | None = None,
    cfg: Any = None,
    agent_id: str | None = None,
    workspace_dir: str | None = None,
    current_message_id: str | None = None,
    is_group: bool = False,
    notify_user: bool = False,
    on_notice: Any | None = None,
    on_compaction_done: Any | None = None,
) -> dict[str, Any]:
    """Orchestrate a user-initiated /compact command.

    Parity: ``handleCompactCommand``.

    This is the integration point for all the Phase A/B helpers:
    - extracts custom instructions from the raw body
    - calls ``prepare_compaction`` → determines whether compaction is needed
    - emits start/end/skipped notices if ``notify_user``
    - calls ``compact`` to summarise
    - persists the result via ``on_compaction_done`` callback
    - injects post-compaction context from AGENTS.md
    - returns a result dict with ``outcome`` and optional ``notices``

    Args:
        raw_body: Full raw message body (``/compact [instructions]``).
        session_messages: Current ordered message list.
        model: LLM to use for summarisation.
        api_key: Provider API key.
        headers: Optional extra HTTP headers.
        signal: Optional cancellation signal.
        cfg: JARVIS config object or dict.
        agent_id: Current agent id.
        workspace_dir: Absolute path to the workspace root.
        current_message_id: Current turn message id for reply targeting.
        is_group: Whether this is a group-channel command.
        notify_user: Emit before/after notices in channel.
        on_notice: Async callback ``(payload: dict) -> None`` for notice delivery.
        on_compaction_done: Async callback ``(compaction_entry) -> None`` for persistence.

    Returns:
        ``{"outcome": "compacted" | "skipped" | "error", "reason": ..., "notices": [...]}``
    """
    from .compaction import compact, prepare_compaction
    from .compaction_notice import (
        create_compaction_notice_payload,
        should_notify_user_about_compaction,
    )

    notices: list[dict[str, Any]] = []

    effective_notify = notify_user or should_notify_user_about_compaction(cfg)

    async def _emit_notice(phase: str) -> None:
        payload = create_compaction_notice_payload(phase, current_message_id)  # type: ignore[arg-type]
        notices.append(payload)
        if on_notice is not None:
            try:
                await on_notice(payload)
            except Exception:
                pass

    # Extract custom instructions from the raw body.
    custom_instructions = extract_compact_instructions(raw_body, is_group=is_group)

    if not model:
        await _emit_notice("skipped")
        return {
            "outcome": "skipped",
            "reason": "no_model",
            "notices": notices,
        }

    if not session_messages:
        await _emit_notice("skipped")
        return {
            "outcome": "skipped",
            "reason": "no_messages",
            "notices": notices,
        }

    # Resolve context window for the manual call.
    session_ctx_tokens = None
    model_ctx_tokens = getattr(model, "context_tokens", None) or getattr(
        model, "context_window", None
    )
    effective_ctx_tokens = resolve_manual_compact_context_token_budget(
        session_context_window_tokens=session_ctx_tokens,
        model_context_window_tokens=model_ctx_tokens,
    )

    # Prepare compaction — determines the cut point.
    try:
        preparation = prepare_compaction(
            session_messages,
            effective_ctx_tokens,
        )
    except Exception as exc:
        return {
            "outcome": "error",
            "reason": str(exc),
            "notices": notices,
        }

    # Check for skip conditions from preparation.
    skip_reason = getattr(preparation, "skip_reason", None)
    if skip_reason is not None:
        if effective_notify:
            await _emit_notice("skipped")
        return {
            "outcome": "skipped",
            "reason": skip_reason,
            "notices": notices,
        }

    # Emit start notice.
    if effective_notify:
        await _emit_notice("start")

    # Run compaction.
    try:
        result = await compact(
            preparation,
            model,
            api_key,
            headers,
            signal,
            custom_instructions=custom_instructions,
        )
    except Exception as exc:
        if effective_notify:
            await _emit_notice("incomplete")
        return {
            "outcome": "error",
            "reason": str(exc),
            "notices": notices,
        }

    # Persist via callback.
    if on_compaction_done is not None:
        try:
            await on_compaction_done(result)
        except Exception:
            pass

    # Inject post-compaction AGENTS.md context if workspace is available.
    post_context: str | None = None
    if workspace_dir:
        try:
            from extensions.memory_core.post_compaction_context import (
                read_post_compaction_context,
            )

            post_context = read_post_compaction_context(
                workspace_dir=workspace_dir,
                cfg=cfg,
                agent_id=agent_id,
            )
        except Exception:
            pass

    # Emit end notice.
    if effective_notify:
        await _emit_notice("end")

    return {
        "outcome": "compacted",
        "result": result,
        "post_context": post_context,
        "notices": notices,
    }


__all__ = [
    "CompactionSkipReason",
    "extract_compact_instructions",
    "format_compaction_reason",
    "handle_compact_command",
    "is_benign_skip",
    "is_compaction_skip_reason",
    "resolve_manual_compact_context_token_budget",
]
