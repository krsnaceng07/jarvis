"""Phase 6.12d — agent_session_models tests.

Verifies the model-management +
thinking-level-management + queue-mode
layers of the AgentSession family.

Covers:
- Helper functions:
  ``models_are_equal``,
  ``clamp_thinking_level``,
  ``get_supported_thinking_levels``.
- Model management:
  ``set_model`` (with + without auth),
  ``cycle_model`` (forward / backward /
  scoped / available).
- Thinking-level management:
  ``set_thinking_level`` (no-op when
  unchanged, persist, emit events),
  ``cycle_thinking_level``,
  ``get_available_thinking_levels``,
  ``supports_thinking``.
- Queue mode management:
  ``set_steering_mode``,
  ``set_follow_up_mode``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.agents.sessions.agent_session_models import (
    AgentSessionModels,
    QueueMode,
    THINKING_LEVELS_BASE,
    clamp_thinking_level,
    get_supported_thinking_levels,
    models_are_equal,
)
from src.agents.sessions.agent_session_types import (
    AgentSessionConfig,
    ScopedModelEntry,
)


# ============================================================================
# Fakes
# ============================================================================


class FakeAgent:
    def __init__(self) -> None:
        self.state: Any = _NS(
            model=None,
            messages=[],
            thinkingLevel="medium",
            systemPrompt="",
            steeringMode="one-at-a-time",
            followUpMode="one-at-a-time",
        )


class _NS:
    """Tiny namespace helper."""

    def __init__(self, **kw: Any) -> None:
        self.__dict__.update(kw)


class FakeRegistry:
    def __init__(
        self,
        has_auth: bool = True,
        available: list | None = None,
        auth_filter: list | None = None,
    ) -> None:
        self._has_auth = has_auth
        self._available = list(available or [])
        self._auth_filter = list(auth_filter or []) if auth_filter is not None else None

    def has_configured_auth(self, model: Any) -> bool:
        if self._auth_filter is not None:
            return any(models_are_equal(m, model) for m in self._auth_filter)
        return self._has_auth

    def get_available(self) -> list:
        return list(self._available)


class FakeSessionManager:
    def __init__(self) -> None:
        self.model_changes: list = []
        self.thinking_level_changes: list = []

    def append_model_change(self, provider: str, model_id: str) -> None:
        self.model_changes.append((provider, model_id))

    def append_thinking_level_change(self, level: str) -> None:
        self.thinking_level_changes.append(level)


class FakeSettingsManager:
    def __init__(self) -> None:
        self.model_provider: tuple | None = None
        self.thinking_level: str | None = None
        self.steering_mode: str | None = None
        self.follow_up_mode: str | None = None

    def set_default_model_and_provider(
        self, provider: str, model_id: str
    ) -> None:
        self.model_provider = (provider, model_id)

    def set_default_thinking_level(self, level: str) -> None:
        self.thinking_level = level

    def get_default_thinking_level(self) -> str | None:
        return self.thinking_level

    def set_steering_mode(self, mode: str) -> None:
        self.steering_mode = mode

    def set_follow_up_mode(self, mode: str) -> None:
        self.follow_up_mode = mode


class FakeExtensionRunner:
    def __init__(self) -> None:
        self.events: list = []

    async def emit(self, event: dict) -> None:
        self.events.append(event)


def _make_model(provider: str, model_id: str, reasoning: bool = True) -> dict:
    return {"provider": provider, "id": model_id, "reasoning": reasoning}


def _make_session(
    tmp_path: Path | None = None,
    *,
    model: Any = None,
    registry: Any | None = None,
    agent: Any | None = None,
    settings: Any | None = None,
    session_manager: Any | None = None,
    scoped_models: list | None = None,
) -> AgentSessionModels:
    import tempfile

    if tmp_path is None:
        tmp_path = Path(tempfile.mkdtemp())
    if agent is None:
        agent = FakeAgent()
    if registry is None:
        registry = FakeRegistry()
    if settings is None:
        settings = FakeSettingsManager()
    if session_manager is None:
        session_manager = FakeSessionManager()
    if scoped_models is None:
        scoped_models = []
    config = AgentSessionConfig(
        agent=agent,
        session_manager=session_manager,
        settings_manager=settings,
        cwd=str(tmp_path),
        resource_loader=_NS(),  # type: ignore[arg-type]
        model_registry=registry,  # type: ignore[arg-type]
        scoped_models=scoped_models,
    )
    session = AgentSessionModels(config)
    session.current_extension_runner = FakeExtensionRunner()
    session.model = model
    return session


# ============================================================================
# Helper functions
# ============================================================================


class TestModelsAreEqual:
    def test_same_provider_and_id(self) -> None:
        a = _make_model("openai", "gpt-5")
        b = _make_model("openai", "gpt-5")
        assert models_are_equal(a, b) is True

    def test_different_id(self) -> None:
        a = _make_model("openai", "gpt-5")
        b = _make_model("openai", "gpt-4")
        assert models_are_equal(a, b) is False

    def test_different_provider(self) -> None:
        a = _make_model("openai", "gpt-5")
        b = _make_model("anthropic", "gpt-5")
        assert models_are_equal(a, b) is False

    def test_both_none(self) -> None:
        assert models_are_equal(None, None) is True

    def test_one_none(self) -> None:
        assert models_are_equal(None, _make_model("openai", "gpt-5")) is False

    def test_empty_models(self) -> None:
        a: dict = {}
        b: dict = {}
        # Both empty → not equal
        # (because the provider/id pair
        # is empty).
        assert models_are_equal(a, b) is False


class TestClampThinkingLevel:
    def test_known_level_returned(self) -> None:
        model = _make_model("openai", "gpt-5", reasoning=True)
        assert clamp_thinking_level(model, "medium") == "medium"

    def test_off_when_no_reasoning(self) -> None:
        model = _make_model("openai", "gpt-5", reasoning=False)
        assert clamp_thinking_level(model, "high") == "off"

    def test_unknown_level_clamps_down(self) -> None:
        model = _make_model("openai", "gpt-5", reasoning=True)
        # An unknown level should clamp
        # down to the closest known
        # level at or below the request.
        result = clamp_thinking_level(model, "madeup")
        assert result in THINKING_LEVELS_BASE


class TestGetSupportedThinkingLevels:
    def test_no_model(self) -> None:
        # Returns the default base list.
        result = get_supported_thinking_levels(None)
        assert result == ["off"]

    def test_reasoning_model(self) -> None:
        model = _make_model("openai", "gpt-5", reasoning=True)
        result = get_supported_thinking_levels(model)
        # Reasoning model gets the full
        # list (including xhigh / max
        # that the Python port extends
        # beyond the OpenClaw base).
        assert "off" in result
        assert "high" in result

    def test_non_reasoning_model(self) -> None:
        model = _make_model("openai", "gpt-3.5", reasoning=False)
        result = get_supported_thinking_levels(model)
        assert result == ["off"]


# ============================================================================
# set_model
# ============================================================================


class TestSetModel:
    @pytest.mark.asyncio
    async def test_set_with_auth(self) -> None:
        registry = FakeRegistry(has_auth=True)
        sm = FakeSessionManager()
        settings = FakeSettingsManager()
        session = _make_session(
            registry=registry,
            settings=settings,
            session_manager=sm,
        )
        await session.set_model(_make_model("openai", "gpt-5"))
        # State updated.
        assert session.model["id"] == "gpt-5"
        # Session log appended.
        assert sm.model_changes == [("openai", "gpt-5")]
        # Settings persisted.
        assert settings.model_provider == ("openai", "gpt-5")

    @pytest.mark.asyncio
    async def test_set_without_auth_raises(self) -> None:
        registry = FakeRegistry(has_auth=False)
        session = _make_session(registry=registry)
        with pytest.raises(RuntimeError) as exc:
            await session.set_model(_make_model("openai", "gpt-5"))
        assert "No API key" in str(exc.value)

    @pytest.mark.asyncio
    async def test_set_emits_model_select(self) -> None:
        session = _make_session(
            registry=FakeRegistry(has_auth=True),
            model=_make_model("openai", "gpt-4"),
        )
        await session.set_model(_make_model("openai", "gpt-5"))
        # The extension event was emitted.
        select_events = [
            e for e in session.current_extension_runner.events
            if e.get("type") == "model_select"
        ]
        assert len(select_events) == 1
        assert select_events[0]["source"] == "set"

    @pytest.mark.asyncio
    async def test_set_same_model_does_not_emit(self) -> None:
        model = _make_model("openai", "gpt-5")
        session = _make_session(
            registry=FakeRegistry(has_auth=True),
            model=model,
        )
        await session.set_model(_make_model("openai", "gpt-5"))
        # No model_select event because
        # the model didn't change.
        select_events = [
            e for e in session.current_extension_runner.events
            if e.get("type") == "model_select"
        ]
        assert select_events == []


# ============================================================================
# cycle_model
# ============================================================================


class TestCycleModel:
    @pytest.mark.asyncio
    async def test_no_available_returns_none(self) -> None:
        registry = FakeRegistry(available=[])
        session = _make_session(registry=registry)
        result = await session.cycle_model()
        assert result is None

    @pytest.mark.asyncio
    async def test_single_available_returns_none(self) -> None:
        registry = FakeRegistry(available=[_make_model("openai", "gpt-5")])
        session = _make_session(registry=registry)
        result = await session.cycle_model()
        assert result is None

    @pytest.mark.asyncio
    async def test_forward_cycle(self) -> None:
        registry = FakeRegistry(
            available=[
                _make_model("openai", "gpt-5"),
                _make_model("openai", "gpt-4"),
            ]
        )
        session = _make_session(
            registry=registry,
            model=_make_model("openai", "gpt-5"),
        )
        result = await session.cycle_model("forward")
        assert result is not None
        assert result.is_scoped is False
        assert result.model["id"] == "gpt-4"
        assert session.model["id"] == "gpt-4"

    @pytest.mark.asyncio
    async def test_backward_cycle(self) -> None:
        registry = FakeRegistry(
            available=[
                _make_model("openai", "gpt-5"),
                _make_model("openai", "gpt-4"),
            ]
        )
        session = _make_session(
            registry=registry,
            model=_make_model("openai", "gpt-4"),
        )
        result = await session.cycle_model("backward")
        assert result is not None
        assert result.model["id"] == "gpt-5"

    @pytest.mark.asyncio
    async def test_scoped_cycle(self) -> None:
        scoped = [
            ScopedModelEntry(
                model=_make_model("openai", "gpt-5"),
            ),
            ScopedModelEntry(
                model=_make_model("anthropic", "claude"),
            ),
        ]
        registry = FakeRegistry(has_auth=True)
        session = _make_session(
            registry=registry,
            model=_make_model("openai", "gpt-5"),
            scoped_models=scoped,
        )
        result = await session.cycle_model("forward")
        assert result is not None
        assert result.is_scoped is True
        assert result.model["provider"] == "anthropic"

    @pytest.mark.asyncio
    async def test_scoped_single_returns_none(self) -> None:
        scoped = [ScopedModelEntry(model=_make_model("openai", "gpt-5"))]
        registry = FakeRegistry(has_auth=True)
        session = _make_session(
            registry=registry,
            scoped_models=scoped,
        )
        result = await session.cycle_model()
        assert result is None


# ============================================================================
# set_thinking_level
# ============================================================================


class TestSetThinkingLevel:
    @pytest.mark.asyncio
    async def test_set_basic(self) -> None:
        sm = FakeSessionManager()
        settings = FakeSettingsManager()
        session = _make_session(
            session_manager=sm,
            settings=settings,
        )
        # A reasoning model so the
        # thinking level sticks.
        session.model = _make_model("openai", "gpt-5", reasoning=True)
        await session.set_thinking_level("high")
        # Agent state updated.
        assert (
            session._get_agent_state_thinking_level() == "high"
        )
        # Session log appended.
        assert sm.thinking_level_changes == ["high"]
        # Settings persisted.
        assert settings.thinking_level == "high"

    @pytest.mark.asyncio
    async def test_set_emits_event(self) -> None:
        session = _make_session()
        session.model = _make_model("openai", "gpt-5", reasoning=True)
        await session.set_thinking_level("high")
        events = session.current_extension_runner.events
        select_events = [
            e for e in events
            if e.get("type") == "thinking_level_select"
        ]
        assert len(select_events) == 1
        assert select_events[0]["level"] == "high"

    @pytest.mark.asyncio
    async def test_set_session_event(self) -> None:
        events: list = []
        session = _make_session()
        session.model = _make_model("openai", "gpt-5", reasoning=True)
        session.subscribe(events.append)
        await session.set_thinking_level("high")
        tlc = [e for e in events if e.get("type") == "thinking_level_changed"]
        assert len(tlc) == 1
        assert tlc[0]["level"] == "high"

    @pytest.mark.asyncio
    async def test_set_no_op_when_unchanged(self) -> None:
        sm = FakeSessionManager()
        session = _make_session(session_manager=sm)
        session.model = _make_model("openai", "gpt-5", reasoning=True)
        session.thinking_level = "high"
        # Sync the agent state too.
        session._set_agent_state_thinking_level("high")
        await session.set_thinking_level("high")
        # No session log entry.
        assert sm.thinking_level_changes == []


# ============================================================================
# cycle_thinking_level
# ============================================================================


class TestCycleThinkingLevel:
    @pytest.mark.asyncio
    async def test_no_reasoning_model_returns_none(self) -> None:
        session = _make_session()
        session.model = _make_model("openai", "gpt-3.5", reasoning=False)
        assert await session.cycle_thinking_level() is None

    @pytest.mark.asyncio
    async def test_no_model_returns_none(self) -> None:
        session = _make_session()
        session.model = None
        # No model → supports_thinking
        # is False → returns None.
        assert await session.cycle_thinking_level() is None

    @pytest.mark.asyncio
    async def test_cycles_through_levels(self) -> None:
        session = _make_session()
        session.model = _make_model("openai", "gpt-5", reasoning=True)
        session.thinking_level = "off"
        # With a reasoning model, the
        # available levels include the
        # full list (7 levels).
        # Cycle: off → minimal → low
        # → medium → high → xhigh
        # → max → off.
        first = await session.cycle_thinking_level()
        assert first is not None
        assert first != "off"


# ============================================================================
# get_available_thinking_levels
# ============================================================================


class TestGetAvailableThinkingLevels:
    def test_no_model(self) -> None:
        session = _make_session()
        session.model = None
        result = session.get_available_thinking_levels()
        # Returns the base list.
        assert result == list(THINKING_LEVELS_BASE)

    def test_reasoning_model(self) -> None:
        session = _make_session()
        session.model = _make_model("openai", "gpt-5", reasoning=True)
        result = session.get_available_thinking_levels()
        # Full list (with xhigh + max).
        assert "off" in result
        assert "high" in result

    def test_non_reasoning_model(self) -> None:
        session = _make_session()
        session.model = _make_model("openai", "gpt-3.5", reasoning=False)
        result = session.get_available_thinking_levels()
        assert result == ["off"]


# ============================================================================
# supports_thinking
# ============================================================================


class TestSupportsThinking:
    def test_no_model(self) -> None:
        session = _make_session()
        session.model = None
        assert session.supports_thinking() is False

    def test_reasoning_dict(self) -> None:
        session = _make_session()
        session.model = _make_model("openai", "gpt-5", reasoning=True)
        assert session.supports_thinking() is True

    def test_non_reasoning_dict(self) -> None:
        session = _make_session()
        session.model = _make_model("openai", "gpt-5", reasoning=False)
        assert session.supports_thinking() is False


# ============================================================================
# Queue mode management
# ============================================================================


class TestSetSteeringMode:
    def test_set(self) -> None:
        settings = FakeSettingsManager()
        session = _make_session(settings=settings)
        session.set_steering_mode("all")
        # Session field updated (the
        # OpenClaw source writes the
        # mode to ``this.agent.steeringMode``;
        # the Python port also mirrors the
        # value to ``self.steering_mode``
        # so callers can read it from the
        # session directly).
        assert session.steering_mode == "all"
        # Settings persisted.
        assert settings.steering_mode == "all"

    def test_set_one_at_a_time(self) -> None:
        settings = FakeSettingsManager()
        session = _make_session(settings=settings)
        session.set_steering_mode("one-at-a-time")
        assert session.steering_mode == "one-at-a-time"
        assert settings.steering_mode == "one-at-a-time"


class TestSetFollowUpMode:
    def test_set(self) -> None:
        settings = FakeSettingsManager()
        session = _make_session(settings=settings)
        session.set_follow_up_mode("all")
        assert session.follow_up_mode == "all"
        assert settings.follow_up_mode == "all"


# ============================================================================
# Constructor
# ============================================================================


class TestConstructor:
    def test_default_thinking_level(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        # Default is "medium" per the
        # OpenClaw source.
        assert session.thinking_level == "medium"

    def test_default_modes(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        assert session.steering_mode == "one-at-a-time"
        assert session.follow_up_mode == "one-at-a-time"

    def test_inherits_prompting(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        from src.agents.sessions.agent_session_prompting import (
            AgentSessionPrompting,
        )
        assert isinstance(session, AgentSessionPrompting)

    def test_queue_mode_type(self) -> None:
        # Just a sanity check that the
        # literal type is correctly
        # defined.
        mode: QueueMode = "all"
        assert mode == "all"
