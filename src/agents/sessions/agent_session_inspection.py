"""jarvis.agents.sessions.agent_session_inspection — inspection layer.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/agent-session-inspection.ts``.

Adds the inspection / observability
layer on top of the models chain:

- :meth:`AgentSessionInspection.set_session_name` —
  set the display name of the current
  session.
- :meth:`AgentSessionInspection.get_session_stats` —
  per-session statistics (token usage,
  cost, message counts).
- :meth:`AgentSessionInspection.get_context_usage` —
  context-window usage (tokens +
  percent).
- :meth:`AgentSessionInspection.export_to_jsonl` —
  export the current session branch to
  a JSONL file.
- :meth:`AgentSessionInspection.get_last_assistant_text` —
  get the text of the last assistant
  message (for the ``/copy`` command).

Phase 6.12e — focused port.

Adaptations
-----------
- The OpenClaw source's
  :func:`calculateContextTokens` +
  :func:`estimateContextTokens` come
  from ``@openclaw/ai/internal/runtime``.
  The Python port uses
  :func:`estimate_messages_from_content`
  from :mod:`jarvis.agents.sessions.agent_session_utils`
  + a simple ``len / 4`` fallback for
  the per-message estimate.
- The OpenClaw source's
  :data:`CURRENT_SESSION_VERSION`
  constant is mirrored as a local
  ``"1"`` default; the real version
  comes from the session-manager
  codec module in 6.13+.
- The OpenClaw source's
  :func:`getLatestCompactionEntry` lives
  in ``session-manager.js``; the
  Python port ships a defensive
  fallback that returns ``None`` when
  the session manager doesn't expose
  the helper.
"""
from __future__ import annotations

import json
import os
from typing import (
    TYPE_CHECKING,
    Any,
    Optional,
)

from .agent_session_models import AgentSessionModels
from .agent_session_types import (
    SessionStats,
    SessionTokenUsage,
)
from .agent_session_utils import (
    estimate_messages_from_content,
    extract_text_content,
    has_persisted_assistant_content,
)
from .extensions.types import ContextUsage


if TYPE_CHECKING:
    from packages.jarvis_agent_runtime.src.jarvis_agent.types import (  # type: ignore[import-not-found]
        AgentMessage,
        AssistantMessage,
    )
else:
    AgentMessage = Any
    AssistantMessage = Any


#: The current session-file format
#: version. Mirrors the OpenClaw
#: source's ``CURRENT_SESSION_VERSION``
#: (the real value lives in the
#: session-manager codec module —
#: Phase 6.13+).
CURRENT_SESSION_VERSION: str = "1"


#: The SessionHeader shape used by
#: :meth:`AgentSessionInspection.export_to_jsonl`.
SessionHeader = dict


class AgentSessionInspection(AgentSessionModels):
    """The inspection layer of the
    :class:`AgentSession` family. Mirrors
    :class:`AgentSessionInspection`
    (``agent-session-inspection.ts:15-202``).

    Phase 6.12e port.
    """

    # ------------------------------------------------------------------
    # Session Management
    # ------------------------------------------------------------------

    def set_session_name(self, name: str) -> None:
        """Set the display name of the
        current session. Mirrors
        :meth:`setSessionName`
        (``agent-session-inspection.ts:23-26``)."""
        append_session_info = getattr(
            self.session_manager, "append_session_info", None
        )
        if callable(append_session_info):
            append_session_info(name)
        # Emit the session-info-changed
        # event with the new name.
        self.emit({
            "type": "session_info_changed",
            "name": self.session_name,
        })

    def get_session_stats(self) -> SessionStats:
        """Get per-session statistics.
        Mirrors :meth:`getSessionStats`
        (``agent-session-inspection.ts:31-74``)."""
        state = self.state
        if isinstance(state, dict):
            messages = state.get("messages", [])
        else:
            messages = getattr(state, "messages", []) or []
        user_messages = sum(1 for m in messages if _role(m) == "user")
        assistant_messages = sum(
            1 for m in messages if _role(m) == "assistant"
        )
        tool_results = sum(1 for m in messages if _role(m) == "toolResult")
        tool_calls = 0
        total_input = 0
        total_output = 0
        total_cache_read = 0
        total_cache_write = 0
        total_cost = 0.0
        for message in messages:
            if _role(message) != "assistant":
                continue
            content = _get_field(message, "content")
            if isinstance(content, list):
                tool_calls += sum(
                    1
                    for c in content
                    if isinstance(c, dict) and c.get("type") == "toolCall"
                )
            usage = _get_field(message, "usage") or {}
            if isinstance(usage, dict):
                total_input += int(usage.get("input", 0) or 0)
                total_output += int(usage.get("output", 0) or 0)
                total_cache_read += int(usage.get("cacheRead", 0) or 0)
                total_cache_write += int(usage.get("cacheWrite", 0) or 0)
                cost = usage.get("cost", {}) or {}
                if isinstance(cost, dict):
                    total_cost += float(cost.get("total", 0) or 0)
        return SessionStats(
            session_file=self.session_file,
            session_id=self.session_id,
            user_messages=user_messages,
            assistant_messages=assistant_messages,
            tool_calls=tool_calls,
            tool_results=tool_results,
            total_messages=len(messages),
            tokens=SessionTokenUsage(
                input_tokens=total_input,
                output_tokens=total_output,
                cache_read_tokens=total_cache_read,
                cache_write_tokens=total_cache_write,
                total_tokens=(
                    total_input
                    + total_output
                    + total_cache_read
                    + total_cache_write
                ),
            ),
            cost=total_cost,
            context_usage=self.get_context_usage(),
        )

    def get_context_usage(self) -> Optional[ContextUsage]:
        """Get context-window usage. Mirrors
        :meth:`getContextUsage`
        (``agent-session-inspection.ts:76-131``).

        Returns
        -------
        ContextUsage | None
            ``{"tokens", "contextWindow",
            "percent"}`` when a model is
            selected + has a context window
            of > 0; ``None`` otherwise.
        """
        if not self.model:
            return None
        if isinstance(self.model, dict):
            context_window = (
                self.model.get("contextWindow") or 0
            )
        else:
            context_window = (
                getattr(self.model, "context_window", 0) or 0
            )
        if context_window <= 0:
            return None
        # Check for the latest compaction
        # (so we don't read pre-compaction
        # context usage). The session
        # manager's ``getBranch`` +
        # ``getLatestCompactionEntry`` are
        # optional helpers; if not
        # available, fall back to the
        # content-based estimate.
        get_branch = getattr(
            self.session_manager, "get_branch", None
        )
        get_latest = getattr(
            self.session_manager, "get_latest_compaction_entry", None
        )
        if callable(get_branch) and callable(get_latest):
            try:
                branch = get_branch()
            except Exception:
                branch = None
            if branch is not None:
                latest = get_latest(branch)
            else:
                latest = None
        else:
            latest = None
        estimate_from_content = False
        if latest is not None:
            # Check for a valid assistant
            # usage after the compaction
            # boundary. Defensive — the
            # Python port doesn't ship a
            # full session codec yet.
            try:
                compaction_index = branch.index(latest)  # type: ignore
            except ValueError:
                compaction_index = -1
            has_post_compaction = False
            if compaction_index >= 0:
                for entry in reversed(branch[compaction_index + 1:]):  # type: ignore
                    if not _is_message_entry(entry):
                        continue
                    msg = _get_message(entry)
                    if _role(msg) != "assistant":
                        continue
                    stop_reason = _get_field(msg, "stopReason", "stop_reason")
                    if stop_reason in ("aborted", "error"):
                        continue
                    usage = _get_field(msg, "usage") or {}
                    context_usage_state = (
                        usage.get("contextUsage", {}).get("state")
                        if isinstance(usage, dict)
                        else None
                    )
                    if context_usage_state == "unavailable":
                        estimate_from_content = True
                        continue
                    context_tokens = _calculate_context_tokens(usage)
                    if context_tokens > 0:
                        has_post_compaction = True
                        estimate_from_content = False
                        break
            if not has_post_compaction and not estimate_from_content:
                return ContextUsage(
                    tokens=None,
                    contextWindow=context_window,
                    percent=None,
                )
        tokens = (
            estimate_messages_from_content(list(self.messages))
            if estimate_from_content
            else _estimate_context_tokens(list(self.messages)).get(
                "tokens", 0
            )
        )
        percent = (tokens / context_window) * 100 if context_window else 0
        return ContextUsage(
            tokens=tokens,
            contextWindow=context_window,
            percent=percent,
        )

    def export_to_jsonl(self, output_path: Optional[str] = None) -> str:
        """Export the current session
        branch to a JSONL file. Mirrors
        :meth:`exportToJsonl`
        (``agent-session-inspection.ts:139-169``).

        Returns the resolved output path.
        """
        from datetime import datetime

        if output_path is None:
            ts = datetime.now().isoformat().replace(":", "-").replace(".", "-")
            output_path = os.path.join(self.cwd, f"session-{ts}.jsonl")
        # Resolve + create the parent
        # directory.
        file_path = os.path.realpath(output_path)
        parent = os.path.dirname(file_path)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)
        header: SessionHeader = {
            "type": "session",
            "version": CURRENT_SESSION_VERSION,
            "id": self.session_id,
            "timestamp": datetime.now().isoformat(),
            "cwd": _get_cwd(self),
        }
        # Read the branch entries.
        get_branch = getattr(self.session_manager, "get_branch", None)  # type: ignore[assignment]
        if callable(get_branch):
            try:
                branch_entries = list(get_branch())  # type: ignore[arg-type]
            except Exception:
                branch_entries = []
        else:
            branch_entries = []
        lines = [json.dumps(header)]
        prev_id: Optional[str] = None
        for entry in branch_entries:
            entry_id = (
                entry.get("id") if isinstance(entry, dict) else None
            )
            linear = dict(entry) if isinstance(entry, dict) else {}
            linear["parentId"] = prev_id
            lines.append(json.dumps(linear))
            if entry_id is not None:
                prev_id = entry_id
        with open(file_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        return file_path

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def get_last_assistant_text(self) -> Optional[str]:
        """Get the text content of the
        last assistant message (for the
        ``/copy`` command). Mirrors
        :meth:`getLastAssistantText`
        (``agent-session-inspection.ts:180-201``)."""
        for message in reversed(list(self.messages)):
            if _role(message) != "assistant":
                continue
            stop_reason = _get_field(message, "stopReason", "stop_reason")
            content = _get_field(message, "content")
            if stop_reason == "aborted" and not has_persisted_assistant_content(
                content
            ):
                continue
            text = extract_text_content(content).strip()
            return text or None
        return None


# ============================================================================
# Module-level helpers
# ============================================================================


def _role(message: Any) -> Optional[str]:
    """Read the ``role`` field from a
    message (dict or object)."""
    if isinstance(message, dict):
        return message.get("role")
    return getattr(message, "role", None)


def _get_field(message: Any, *names: str) -> Any:
    """Read the first matching field
    from a message (dict or object)."""
    for name in names:
        if isinstance(message, dict):
            if name in message:
                return message.get(name)
            continue
        value = getattr(message, name, None)
        if value is not None:
            return value
    return None


def _is_message_entry(entry: Any) -> bool:
    """Whether a branch entry is a
    message entry (vs a session-info
    entry, etc.)."""
    if not isinstance(entry, dict):
        return False
    return entry.get("type") == "message"


def _get_message(entry: Any) -> Any:
    """Return the embedded ``message``
    payload from a branch entry, or
    the entry itself when it's not a
    typed wrapper."""
    if isinstance(entry, dict) and "message" in entry:
        return entry.get("message")
    return entry


def _calculate_context_tokens(usage: Any) -> int:
    """Sum the input / cacheRead /
    cacheWrite / output token counts
    from a usage record. Mirrors the
    OpenClaw source's
    ``calculateContextTokens`` helper.
    """
    if not isinstance(usage, dict):
        return 0
    total = 0
    for field in ("input", "cacheRead", "cacheWrite", "output"):
        value = usage.get(field, 0) or 0
        try:
            total += int(value)
        except (TypeError, ValueError):
            continue
    return total


def _estimate_context_tokens(messages: list) -> dict:
    """Lightweight estimate of context
    tokens from a message list. Mirrors
    the OpenClaw source's
    ``estimateContextTokens`` helper.

    Phase 6.12e — STUB. The OpenClaw
    source's per-provider / per-message
    estimator lands in 6.13+. The
    Python port uses the
    :func:`estimate_messages_from_content`
    helper (a 4-chars-per-token fallback).
    """
    return {"tokens": estimate_messages_from_content(messages)}


def _get_cwd(session: AgentSessionInspection) -> str:
    """Read the session cwd from the
    session manager."""
    get_cwd = getattr(session.session_manager, "get_cwd", None)
    if callable(get_cwd):
        try:
            return str(get_cwd())
        except Exception:
            pass
    return session.cwd


__all__ = [
    "AgentSessionInspection",
    "CURRENT_SESSION_VERSION",
    "SessionHeader",
]
