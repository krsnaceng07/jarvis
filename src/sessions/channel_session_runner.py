"""Channel session runner — runs a full agent turn for a channel message.

Mirrors OpenClaw's ``src/agents/sessions/channel-session-runner.ts`` +
``src/channels/session-dispatch.ts``.

The ``ChannelSessionRunner`` is the W2 replacement for the ad-hoc
``_wire_channel_agent`` closure in the desktop app. It:

  1. Accepts an ``InboundMessage`` from a channel (via ``BindingRouter``).
  2. Builds a ``PluginContext`` / ``AgentContext`` for the current session.
  3. Runs tool calls through ``ToolDispatcher`` for each LLM tool_call batch.
  4. Collects the agent's text reply across all turns.
  5. Returns the reply as a string (or None if nothing was produced).
  6. Emits a ``TerminalOutcome`` for the host to log / project.

Phase W2: the runner is synchronous (no async event loop crossing). Wave 3
adds streaming and live partial-send. Agent turns are produced by calling
the LLM directly via ``jarvis_llm`` rather than going through the Gemini
Live WebSocket — giving us a consistent tool-call + reply loop.

Integration:
  BindingRouter calls ``agent_fn(session_key, text) -> str | None``.
  The host wires this by doing:
      runner = ChannelSessionRunner(dispatcher, llm_client, system_prompt)
      router = BindingRouter(..., agent_fn=runner.run)
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from jarvis_agent.terminal_outcome import TerminalOutcome, normalize_outcome
from src.hooks.lifecycle import LifecycleHooks
from src.tools.dispatch import ToolDispatcher

_log = logging.getLogger("jarvis.sessions.channel_runner")


# ── Simple LLM call contract ───────────────────────────────────────────


# A synchronous LLM fn: (messages, tools, system) -> (reply_text, tool_calls)
# This is the minimal surface the runner needs. The host injects the real
# implementation from jarvis_llm or the Gemini SDK. Tool_calls is a list of
# dicts: [{"name": str, "args": dict, "id": str}].
LlmCallFn = Callable[
    [list[dict[str, Any]], list[dict[str, Any]], str],
    tuple[str | None, list[dict[str, Any]]],
]


# ── Message history ────────────────────────────────────────────────────


class _ConversationHistory:
    """Minimal per-session message history.

    Adapter that wraps ``ConversationHistoryStore`` when one is provided,
    or keeps an in-memory list when running without persistence.

    W2: in-memory only. W5: ``history_store`` arg enables SQLite persistence.
    """

    def __init__(
        self,
        system_prompt: str = "",
        *,
        session_key: str = "",
        store: Any = None,
    ) -> None:
        self._system = system_prompt
        self._session_key = session_key
        self._store = store  # ConversationHistoryStore | None
        # In-memory fallback used when store is None.
        self._messages: list[dict[str, Any]] = []

    @property
    def system_prompt(self) -> str:
        return self._system

    def add_user(self, text: str) -> None:
        if self._store is not None:
            self._store.append_user(self._session_key, text)
        else:
            self._messages.append({"role": "user", "content": text})

    def add_assistant(self, text: str) -> None:
        if self._store is not None:
            self._store.append_assistant(self._session_key, text)
        else:
            self._messages.append({"role": "assistant", "content": text})

    def add_tool_result(self, tool_name: str, call_id: str, content: str) -> None:
        if self._store is not None:
            self._store.append_tool_result(self._session_key, tool_name, call_id, content)
        else:
            self._messages.append(
                {
                    "role": "tool",
                    "tool_name": tool_name,
                    "call_id": call_id,
                    "content": content,
                }
            )

    def all(self) -> list[dict[str, Any]]:
        if self._store is not None:
            return self._store.get_turns(self._session_key)
        return list(self._messages)

    def length(self) -> int:
        if self._store is not None:
            return self._store.turn_count(self._session_key)
        return len(self._messages)


# ── Channel session runner ─────────────────────────────────────────────


class ChannelSessionRunner:
    """Runs a full agent turn for one channel message.

    Mirrors OpenClaw's ``ChannelSessionRunner`` from
    ``src/agents/sessions/channel-session-runner.ts``.

    Parameters
    ----------
    dispatcher : ToolDispatcher
        Executes tool_calls returned by the LLM.
    llm_fn : LlmCallFn
        Sync LLM call: (messages, tool_schemas, system) -> (text, tool_calls).
    system_prompt : str
        The agent's system instruction (includes skills, persona, etc.).
    tool_schemas : list[dict]
        JSON schema descriptions of tools available to the LLM.
    max_tool_rounds : int
        Safety limit on tool_call → result → LLM rounds per message.
        Prevents infinite tool loops. Default: 10.
    timeout_sec : float
        Wall-clock timeout per message in seconds. Default: 60.
    """

    def __init__(
        self,
        dispatcher: ToolDispatcher,
        llm_fn: LlmCallFn,
        *,
        system_prompt: str = "",
        tool_schemas: list[dict[str, Any]] | None = None,
        max_tool_rounds: int = 10,
        timeout_sec: float = 60.0,
        history_store: Any = None,
        lifecycle: LifecycleHooks | None = None,  # W11.3: optional hook bus
    ) -> None:
        self._dispatcher = dispatcher
        self._llm_fn = llm_fn
        self._system_prompt = system_prompt
        self._tool_schemas = tool_schemas or []
        self._max_tool_rounds = max_tool_rounds
        self._timeout_sec = timeout_sec
        # W5: optional SQLite-backed history; falls back to in-memory dict.
        self._history_store = history_store  # ConversationHistoryStore | None
        # In-memory registry for history_store=None path.
        self._histories: dict[str, _ConversationHistory] = {}
        # W11.3: lifecycle hooks — None means no-op (no bus wired).
        self._lifecycle = lifecycle or LifecycleHooks(None)

    def _get_history(self, session_key: str) -> _ConversationHistory:
        if session_key not in self._histories:
            self._histories[session_key] = _ConversationHistory(
                self._system_prompt,
                session_key=session_key,
                store=self._history_store,
            )
        return self._histories[session_key]

    def run(self, session_key: str, text: str) -> str | None:
        """Run one agent turn for ``text`` in ``session_key``.

        This is the ``agent_fn`` that ``BindingRouter`` calls.
        Returns the final reply text, or None on timeout/error.

        The turn loop:
          1. Add user message to history.
          2. Call LLM → get text reply + tool_calls.
          3. If tool_calls: execute all via ToolDispatcher, add results,
             loop back to step 2. Repeat up to max_tool_rounds.
          4. When no more tool_calls: return accumulated text reply.
        """
        # W11.3: fire message_received at turn start (fire-and-forget).
        self._lifecycle.on_message_received({"session_key": session_key, "text": text})

        start_ms = time.monotonic()
        deadline = start_ms + self._timeout_sec
        history = self._get_history(session_key)
        history.add_user(text)

        reply_parts: list[str] = []
        outcome: TerminalOutcome | None = None

        try:
            for _round in range(self._max_tool_rounds + 1):
                elapsed_ms = int((time.monotonic() - start_ms) * 1000)

                # Timeout check.
                if time.monotonic() > deadline:
                    outcome = normalize_outcome(
                        timed_out=True,
                        duration_ms=elapsed_ms,
                        session_key=session_key,
                    )
                    _log.warning(
                        "channel_runner: session %s timed out after %dms",
                        session_key,
                        elapsed_ms,
                    )
                    break

                # Call LLM.
                try:
                    reply_text, tool_calls = self._llm_fn(
                        history.all(),
                        self._tool_schemas,
                        self._system_prompt,
                    )
                except Exception as llm_exc:  # noqa: BLE001
                    outcome = normalize_outcome(
                        exc=llm_exc,
                        duration_ms=elapsed_ms,
                        session_key=session_key,
                    )
                    _log.warning(
                        "channel_runner: session %s LLM error: %s",
                        session_key,
                        llm_exc,
                    )
                    break

                # Collect text.
                if reply_text:
                    reply_parts.append(reply_text)
                    history.add_assistant(reply_text)

                # If no tool_calls, turn is done.
                if not tool_calls:
                    outcome = normalize_outcome(
                        duration_ms=int((time.monotonic() - start_ms) * 1000),
                        session_key=session_key,
                    )
                    break

                # Execute tool_calls.
                if _round >= self._max_tool_rounds:
                    _log.warning(
                        "channel_runner: session %s hit max_tool_rounds=%d",
                        session_key,
                        self._max_tool_rounds,
                    )
                    outcome = normalize_outcome(
                        exc=RuntimeError("max tool rounds exceeded"),
                        duration_ms=int((time.monotonic() - start_ms) * 1000),
                        session_key=session_key,
                    )
                    break

                results = self._dispatcher.execute_batch(tool_calls)
                for res in results:
                    history.add_tool_result(res.tool_name, res.call_id, res.content)
                    if res.is_error:
                        _log.debug(
                            "channel_runner: tool %s error: %s",
                            res.tool_name,
                            res.content[:120],
                        )

            else:
                # for-else: loop exhausted without break
                outcome = normalize_outcome(
                    exc=RuntimeError("tool round limit exceeded"),
                    session_key=session_key,
                )

        except Exception as exc:  # noqa: BLE001
            elapsed_ms = int((time.monotonic() - start_ms) * 1000)
            outcome = normalize_outcome(exc=exc, duration_ms=elapsed_ms, session_key=session_key)
            _log.exception("channel_runner: unexpected error in session %s", session_key)

        if outcome is not None and not outcome.is_success:
            _log.info(
                "channel_runner: session %s ended with %s (%s)",
                session_key,
                outcome.kind.value,
                outcome.display_message,
            )

        reply = " ".join(reply_parts) if reply_parts else None

        # W11.3: fire lifecycle hooks at turn end.
        if reply:
            self._lifecycle.on_message_sent({"session_key": session_key, "reply": reply})
        self._lifecycle.on_agent_end(outcome)

        return reply

    def clear_history(self, session_key: str) -> None:
        """Discard conversation history for ``session_key``.

        For SQLite-backed stores, also deletes the persisted turns.
        """
        self._histories.pop(session_key, None)
        if self._history_store is not None:
            self._history_store.clear_session(session_key)

    def session_count(self) -> int:
        """Number of active in-memory session handles."""
        return len(self._histories)


__all__ = ["ChannelSessionRunner", "LlmCallFn"]
