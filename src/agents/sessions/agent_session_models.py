"""jarvis.agents.sessions.agent_session_models — model + thinking-level layer.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/agent-session-models.ts``.

Adds three layers on top of
:class:`AgentSessionPrompting`:

- **Model management** — set a model
  directly, cycle through the scoped
  model list (``--models`` flag) or
  the registry's available models.
- **Thinking-level management** —
  set / cycle the per-session thinking
  level; clamp to the model's
  capabilities; persist to session +
  settings.
- **Queue mode management** — set
  the steering / follow-up queue
  modes (``"all"`` vs
  ``"one-at-a-time"``).

Public surface (matches the OpenClaw
source):

- :meth:`AgentSessionModels.set_model` —
  set the model directly.
- :meth:`AgentSessionModels.cycle_model` —
  cycle to the next / previous model.
- :meth:`AgentSessionModels.set_thinking_level` —
  set the thinking level.
- :meth:`AgentSessionModels.cycle_thinking_level` —
  cycle to the next thinking level.
- :meth:`AgentSessionModels.get_available_thinking_levels` —
  list the levels the current model
  supports.
- :meth:`AgentSessionModels.supports_thinking` —
  whether the model supports reasoning.
- :meth:`AgentSessionModels.set_steering_mode` —
  set the steering queue mode.
- :meth:`AgentSessionModels.set_follow_up_mode` —
  set the follow-up queue mode.

Phase 6.12d — focused port.

Adaptations
-----------
- The OpenClaw source imports
  :func:`modelsAreEqual`,
  :func:`clampThinkingLevel`, +
  :func:`getSupportedThinkingLevels`
  from ``@openclaw/ai/internal/runtime``.
  The Python port ships its own minimal
  implementations of those three
  helpers in this module (mirroring
  the OpenClaw semantics) so the
  module has no workspace-internal
  dependency.
- TypedDict / interface types are
  plain ``dict`` at runtime; the
  Python port uses ``.get(...)`` to
  read model fields (``provider``,
  ``id``, ``reasoning``).
- The OpenClaw source's
  ``modelsAreEqual`` is a small
  provider + id equality check; the
  Python port follows the same shape.
"""
from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    Optional,
)

from .agent_session_prompting import AgentSessionPrompting
from .agent_session_types import ModelCycleResult
from .defaults import DEFAULT_THINKING_LEVEL, THINKING_LEVELS


if TYPE_CHECKING:
    from packages.jarvis_agent_runtime.src.jarvis_agent.types import (  # type: ignore[import-not-found]
        ThinkingLevel,
    )
    from packages.jarvis_llm_client.src.jarvis_llm.types import (  # type: ignore[import-not-found]
        Model,
    )
else:
    ThinkingLevel = str
    Model = Any


#: The base thinking-level list. Mirrors
#: the OpenClaw source's local
#: ``THINKING_LEVELS`` constant in
#: ``agent-session-models.ts:12``.
#: The Python port uses the full
#: ``THINKING_LEVELS`` from
#: :mod:`jarvis.agents.sessions.defaults`
#: (which extends the OpenClaw list with
#: ``"xhigh"`` + ``"max"``).
THINKING_LEVELS_BASE: tuple[str, ...] = ("off", "minimal", "low", "medium", "high")


#: The agent's queue mode literal. Mirrors
#: the OpenClaw source's union
#: ``"all" | "one-at-a-time"``.
QueueMode = Literal["all", "one-at-a-time"]


# ============================================================================
# Helper functions (OpenClaw imports these from @openclaw/ai/internal/runtime)
# ============================================================================


def _model_id(model: Any) -> tuple[str, str]:
    """Return the ``(provider, id)`` tuple
    for a model. Mirrors the OpenClaw
    source's
    ``model.provider`` / ``model.id``
    access pattern."""
    if isinstance(model, dict):
        return (model.get("provider", ""), model.get("id", ""))
    return (
        getattr(model, "provider", ""),
        getattr(model, "id", ""),
    )


def models_are_equal(a: Any, b: Any) -> bool:
    """Whether two models are equal.
    Mirrors ``modelsAreEqual``
    (``@openclaw/ai/internal/runtime``).

    Two models are equal when both their
    ``provider`` + ``id`` match.
    """
    if a is None or b is None:
        return a is b
    a_id = _model_id(a)
    b_id = _model_id(b)
    return a_id == b_id and a_id != ("", "")


def clamp_thinking_level(model: Any, level: str) -> str:
    """Clamp ``level`` to a level the
    ``model`` supports. Mirrors
    :func:`clampThinkingLevel`
    (``@openclaw/ai/internal/runtime``).

    The OpenClaw source's provider is
    responsible for the actual clamp; the
    Python port preserves the same
    semantics:

    - If the model has ``reasoning=False``,
      return ``"off"``.
    - If the level is in the
      :data:`THINKING_LEVELS_BASE` (the
      OpenClaw 5-level list), return it
      unchanged.
    - If the level is unknown, clamp down
      to the max of the base list
      (``"high"``).

    Phase 6.12d — STUB. The OpenClaw
    source delegates to a per-provider
    implementation. The Python port
    ships the conservative ordering-based
    fallback. The per-provider impl
    lands in Phase 6.13+.
    """
    if not getattr(model, "reasoning", False) and not (
        isinstance(model, dict) and model.get("reasoning", False)
    ):
        return "off"
    if level in THINKING_LEVELS_BASE:
        return level
    # Unknown level — clamp down to
    # the max of the base list.
    return THINKING_LEVELS_BASE[-1]


def get_supported_thinking_levels(model: Any) -> list[str]:
    """Return the list of thinking levels
    the model supports. Mirrors
    :func:`getSupportedThinkingLevels`
    (``@openclaw/ai/internal/runtime``).

    Phase 6.12d — STUB. The OpenClaw
    source delegates to a per-provider
    implementation. The Python port
    returns the conservative default:
    models without ``reasoning`` get the
    ``["off"]`` list; reasoning-capable
    models get the full
    ``THINKING_LEVELS`` list.
    """
    reasoning = getattr(model, "reasoning", False) or (
        isinstance(model, dict) and model.get("reasoning", False)
    )
    if not reasoning:
        return ["off"]
    return list(THINKING_LEVELS)


def _thinking_level_rank(level: str) -> int:
    """Return the position of ``level``
    in the THINKING_LEVELS ordering."""
    try:
        return THINKING_LEVELS.index(level)  # type: ignore[arg-type]
    except ValueError:
        # Unknown level — return the max
        # rank so the conservative fallback
        # picks the highest known level.
        return len(THINKING_LEVELS) - 1


# ============================================================================
# AgentSessionModels
# ============================================================================


class AgentSessionModels(AgentSessionPrompting):
    """The model + thinking-level + queue
    mode layer of the
    :class:`AgentSession` family. Mirrors
    :class:`AgentSessionModels`
    (``agent-session-models.ts:14-245``).

    Phase 6.12d port.
    """

    # ------------------------------------------------------------------
    # Model Management
    # ------------------------------------------------------------------

    async def _emit_model_select(
        self,
        next_model: Model,
        previous_model: Optional[Model],
        source: str,
    ) -> None:
        """Emit the ``model_select`` event
        when the model changes. Mirrors
        :meth:`emitModelSelect`
        (``agent-session-models.ts:19-33``)."""
        if models_are_equal(previous_model, next_model):
            return
        runner = self.current_extension_runner
        if runner is None:
            return
        await runner.emit({
            "type": "model_select",
            "model": next_model,
            "previousModel": previous_model,
            "source": source,
        })

    async def _apply_model_switch(
        self,
        model: Model,
        thinking_level: str,
        source: str,
    ) -> None:
        """Apply a model switch: update
        agent state, append to the session
        log, set the default in settings,
        apply the new thinking level, emit
        the ``model_select`` event. Mirrors
        :meth:`applyModelSwitch`
        (``agent-session-models.ts:35-46``)."""
        previous_model = self.model
        # Update the local ``model``
        # field (the OpenClaw source's
        # ``this.model`` is a getter that
        # reads from ``agent.state.model``;
        # the Python port uses a stored
        # field, so we update both).
        self.model = model
        if hasattr(self.agent.state, "model"):
            self.agent.state.model = model
        elif isinstance(self.agent.state, dict):
            self.agent.state["model"] = model
        # Append the model-change entry to
        # the session log.
        provider = _model_id(model)[0]
        model_id = _model_id(model)[1]
        append_model_change = getattr(
            self.session_manager, "append_model_change", None
        )
        if callable(append_model_change):
            append_model_change(provider, model_id)
        # Persist the new default in
        # settings.
        setter = getattr(
            self.settings_manager, "set_default_model_and_provider", None
        )
        if callable(setter):
            setter(provider, model_id)
        # Apply the new thinking level.
        await self.set_thinking_level(thinking_level)
        # Emit the model-select event.
        await self._emit_model_select(model, previous_model, source)

    async def set_model(self, model: Model) -> None:
        """Set the model directly. Validates
        that auth is configured; raises
        when no API key is available. Mirrors
        :meth:`setModel`
        (``agent-session-models.ts:53-60``)."""
        if not self.session_model_registry.has_configured_auth(model):
            provider = _model_id(model)[0]
            model_id = _model_id(model)[1]
            raise RuntimeError(f"No API key for {provider}/{model_id}")
        thinking_level = self._get_thinking_level_for_model_switch()
        await self._apply_model_switch(model, thinking_level, "set")

    async def cycle_model(
        self, direction: str = "forward"
    ) -> Optional[ModelCycleResult]:
        """Cycle to the next / previous
        model. Uses the scoped model list
        (from ``--models``) when available;
        otherwise falls back to the registry's
        available models. Mirrors
        :meth:`cycleModel`
        (``agent-session-models.ts:68-75``)."""
        if self.scoped_model_entries:
            return await self._cycle_scoped_model(direction)
        return await self._cycle_available_model(direction)

    async def _cycle_scoped_model(
        self, direction: str
    ) -> Optional[ModelCycleResult]:
        """Cycle through the scoped model
        list (from ``--models``). Mirrors
        :meth:`cycleScopedModel`
        (``agent-session-models.ts:77-109``)."""
        scoped = [
            entry
            for entry in self.scoped_model_entries
            if self.session_model_registry.has_configured_auth(
                entry.get("model")  # type: ignore[arg-type]
            )
        ]
        if len(scoped) <= 1:
            return None
        current_model = self.model
        current_index = next(
            (
                i
                for i, sm in enumerate(scoped)
                if models_are_equal(sm.get("model"), current_model)
            ),
            0,
        )
        length = len(scoped)
        if direction == "forward":
            next_index = (current_index + 1) % length
        else:
            next_index = (current_index - 1 + length) % length
        nxt = scoped[next_index]
        if nxt is None:
            raise RuntimeError("Scoped model cycle produced an invalid index")
        thinking_level = self._get_thinking_level_for_model_switch(
            nxt.get("thinkingLevel")
        )
        await self._apply_model_switch(
            nxt["model"], thinking_level, "cycle"
        )
        return ModelCycleResult(
            model=nxt["model"],
            thinking_level=self.thinking_level,
            is_scoped=True,
        )

    async def _cycle_available_model(
        self, direction: str
    ) -> Optional[ModelCycleResult]:
        """Cycle through the registry's
        available models. Mirrors
        :meth:`cycleAvailableModel`
        (``agent-session-models.ts:111-137``)."""
        get_available = getattr(
            self.session_model_registry, "get_available", None
        )
        available_models: list = (
            list(get_available())  # type: ignore[arg-type]
            if callable(get_available)
            else []
        )
        if len(available_models) <= 1:
            return None
        current_model = self.model
        current_index = next(
            (
                i
                for i, m in enumerate(available_models)
                if models_are_equal(m, current_model)
            ),
            0,
        )
        length = len(available_models)
        if direction == "forward":
            next_index = (current_index + 1) % length
        else:
            next_index = (current_index - 1 + length) % length
        next_model = available_models[next_index]
        if next_model is None:
            raise RuntimeError(
                "Available model cycle produced an invalid index"
            )
        thinking_level = self._get_thinking_level_for_model_switch()
        await self._apply_model_switch(next_model, thinking_level, "cycle")
        return ModelCycleResult(
            model=next_model,
            thinking_level=self.thinking_level,
            is_scoped=False,
        )

    # ------------------------------------------------------------------
    # Thinking Level Management
    # ------------------------------------------------------------------

    async def set_thinking_level(self, level: str) -> None:
        """Set the thinking level. Clamps
        to the model's capabilities;
        persists to session + settings
        only when the level actually
        changes. Mirrors
        :meth:`setThinkingLevel`
        (``agent-session-models.ts:148-170``)."""
        available_levels = self.get_available_thinking_levels()
        if level in available_levels:
            effective = level
        else:
            effective = self._clamp_thinking_level(level)
        previous_level = self._get_agent_state_thinking_level()
        is_changing = effective != previous_level
        # Update agent state.
        self._set_agent_state_thinking_level(effective)
        if not is_changing:
            return
        # Append the thinking-level change
        # to the session log.
        append_tlc = getattr(
            self.session_manager, "append_thinking_level_change", None
        )
        if callable(append_tlc):
            append_tlc(effective)
        # Persist the new default in
        # settings (unless the model
        # doesn't support thinking AND the
        # new level is "off" — that's a
        # no-op).
        if self.supports_thinking() or effective != "off":
            setter = getattr(
                self.settings_manager,
                "set_default_thinking_level",
                None,
            )
            if callable(setter):
                setter(effective)
        # Emit the session event.
        self.emit({"type": "thinking_level_changed", "level": effective})
        # Emit the extension event.
        runner = self.current_extension_runner
        if runner is not None:
            await runner.emit({
                "type": "thinking_level_select",
                "level": effective,
                "previousLevel": previous_level,
            })

    async def cycle_thinking_level(self) -> Optional[str]:
        """Cycle to the next thinking level.
        Returns the new level, or ``None``
        when the model doesn't support
        thinking. Mirrors
        :meth:`cycleThinkingLevel`
        (``agent-session-models.ts:176-191``)."""
        if not self.supports_thinking():
            return None
        levels = self.get_available_thinking_levels()
        try:
            current_index = levels.index(self.thinking_level)
        except ValueError:
            current_index = 0
        next_index = (current_index + 1) % len(levels)
        next_level = levels[next_index]
        if next_level is None:
            return None
        await self.set_thinking_level(next_level)
        return next_level

    def get_available_thinking_levels(self) -> list[str]:
        """Return the list of thinking
        levels the current model supports.
        Mirrors
        :meth:`getAvailableThinkingLevels`
        (``agent-session-models.ts:197-202``)."""
        if not self.model:
            return list(THINKING_LEVELS_BASE)
        return get_supported_thinking_levels(self.model)

    def supports_thinking(self) -> bool:
        """Whether the current model
        supports thinking / reasoning.
        Mirrors :meth:`supportsThinking`
        (``agent-session-models.ts:207-209``)."""
        model = self.model
        if isinstance(model, dict):
            return bool(model.get("reasoning", False))
        return bool(getattr(model, "reasoning", False))

    def _get_thinking_level_for_model_switch(
        self, explicit_level: Optional[str] = None
    ) -> str:
        """Pick the right thinking level
        for a model switch. Mirrors
        :meth:`getThinkingLevelForModelSwitch`
        (``agent-session-models.ts:211-219``).

        Rules:
        - Explicit level wins.
        - Non-reasoning models inherit the
          default thinking level.
        - Reasoning models inherit the
          current session thinking level.
        """
        if explicit_level is not None:
            return explicit_level
        if not self.supports_thinking():
            getter = getattr(
                self.settings_manager,
                "get_default_thinking_level",
                None,
            )
            if callable(getter):
                value = getter()
                if value is not None:
                    return str(value)
            return DEFAULT_THINKING_LEVEL
        return self.thinking_level

    def _clamp_thinking_level(self, level: str) -> str:
        """Clamp ``level`` to the closest
        level at or below. Mirrors
        :meth:`clampThinkingLevel`
        (``agent-session-models.ts:221-223``)."""
        if not self.model:
            return "off"
        return clamp_thinking_level(self.model, level)

    # ------------------------------------------------------------------
    # Internal helpers — agent-state
    # field access (dict or namespace)
    # ------------------------------------------------------------------

    def _get_agent_state_thinking_level(self) -> str:
        """Read the agent state's thinking
        level. The OpenClaw source uses a
        discriminated union; the Python
        port reads the field defensively
        (works for both dict + namespace
        state)."""
        state = self.agent.state
        if isinstance(state, dict):
            return state.get("thinkingLevel", DEFAULT_THINKING_LEVEL)
        return getattr(state, "thinking_level", DEFAULT_THINKING_LEVEL)

    def _set_agent_state_thinking_level(self, level: str) -> None:
        """Write the agent state's thinking
        level. Mirrors the
        ``this.agent.state.thinkingLevel = ...``
        assignment in the OpenClaw source.
        """
        state = self.agent.state
        if isinstance(state, dict):
            state["thinkingLevel"] = level
        else:
            setattr(state, "thinking_level", level)

    # ------------------------------------------------------------------
    # Queue Mode Management
    # ------------------------------------------------------------------

    def set_steering_mode(self, mode: str) -> None:
        """Set the steering message mode
        (``"all"`` or
        ``"one-at-a-time"``). Mirrors
        :meth:`setSteeringMode`
        (``agent-session-models.ts:233-236``).

        The OpenClaw source writes
        ``this.agent.steeringMode = mode``
        (on the agent itself, not on the
        agent state).
        """
        # The OpenClaw source writes the
        # mode on the agent object itself
        # (not on the agent's state).
        self.steering_mode = mode
        setter = getattr(self.settings_manager, "set_steering_mode", None)
        if callable(setter):
            setter(mode)

    def set_follow_up_mode(self, mode: str) -> None:
        """Set the follow-up message mode
        (``"all"`` or
        ``"one-at-a-time"``). Mirrors
        :meth:`setFollowUpMode`
        (``agent-session-models.ts:242-245``)."""
        self.follow_up_mode = mode
        setter = getattr(self.settings_manager, "set_follow_up_mode", None)
        if callable(setter):
            setter(mode)


__all__ = [
    "AgentSessionModels",
    "QueueMode",
    "THINKING_LEVELS_BASE",
    "clamp_thinking_level",
    "get_supported_thinking_levels",
    "models_are_equal",
]
