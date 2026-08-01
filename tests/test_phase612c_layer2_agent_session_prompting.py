"""Phase 6.12c — agent_session_prompting tests.

Verifies the public surface of
:class:`AgentSessionPrompting`:

- :meth:`prompt` — the main entry point
  (extension command handling, input
  event emission, model validation,
  auth validation, expansion, queue).
- :meth:`steer` / :meth:`follow_up` —
  queueing during streaming.
- :meth:`send_custom_message` /
  :meth:`send_user_message` — the
  convenience message-injection APIs.
- :meth:`clear_queue` — drop the queues.
- :meth:`abort` — abort the current
  run.
- Public getters: ``pending_message_count``,
  ``get_steering_messages``,
  ``get_follow_up_messages``,
  ``resource_loader``.

The test uses lightweight fakes for the
Layer 1 ``Agent`` + the extension
runner + the resource loader + the
model registry, so the prompting logic
can be exercised without standing up
the full agent runtime.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from src.agents.sessions.agent_session_prompting import AgentSessionPrompting
from src.agents.sessions.agent_session_types import (
    AgentSessionConfig,
    PromptOptions,
)


# ============================================================================
# Fakes
# ============================================================================


class FakeAgent:
    """Minimal Layer 1 ``Agent`` fake for
    the prompting tests."""

    def __init__(self) -> None:
        self.state: Any = SimpleNamespace(
            messages=[],
            systemPrompt="",
        )
        self.steered: list = []
        self.follow_ups: list = []
        self.continued: int = 0
        self.prompted: list = []
        self.aborted_with: Any = None
        self._idle_event = asyncio.Event()
        self._idle_event.set()

    async def prompt(self, messages: Any) -> None:
        self.prompted.append(messages)

    async def continue_run(self) -> None:  # Python disallows ``continue`` as a method name.
        self.continued += 1

    def steer(self, message: Any) -> None:
        self.steered.append(message)

    def follow_up(self, message: Any) -> None:
        self.follow_ups.append(message)

    def clear_all_queues(self) -> None:
        self.steered.clear()
        self.follow_ups.clear()

    def has_queued_messages(self) -> bool:
        return bool(self.steered) or bool(self.follow_ups)

    def abort(self, reason: Any = None) -> None:
        self.aborted_with = reason

    async def wait_for_idle(self) -> None:
        await self._idle_event.wait()


class SimpleNamespace:
    """Tiny stand-in for types.SimpleNamespace
    to avoid an extra import."""

    def __init__(self, **kwargs: Any) -> None:
        self.__dict__.update(kwargs)


class FakeRegistry:
    """Minimal model registry fake."""

    def __init__(self, has_auth: bool = True, oauth: bool = False) -> None:
        self._has_auth = has_auth
        self._oauth = oauth

    def has_configured_auth(self, model: Any) -> bool:
        return self._has_auth

    def is_using_oauth(self, model: Any) -> bool:
        return self._oauth


class FakeExtensionRunner:
    """Minimal extension runner fake."""

    def __init__(self) -> None:
        self.handlers: set = set()
        self.commands: dict = {}
        self.errors: list = []
        self.events: list = []

    def has_handlers(self, event: str) -> bool:
        return event in self.handlers

    def get_command(self, name: str) -> Any:
        return self.commands.get(name)

    def create_command_context(self) -> Any:
        return SimpleNamespace()

    def emit_error(self, payload: dict) -> None:
        self.errors.append(payload)

    async def emit(self, event: dict) -> None:
        self.events.append(event)

    async def emit_input(
        self, text: str, images: Any, source: str
    ) -> dict:
        return {"action": "passthrough", "text": text, "images": images}

    async def emit_before_agent_start(
        self,
        text: str,
        images: Any,
        base_system_prompt: str,
        base_system_prompt_options: Any,
    ) -> dict:
        return {}

    async def emit_settled(self) -> None:
        return None


class FakeResourceLoader:
    """Minimal resource loader fake."""

    def __init__(self) -> None:
        self._skills: list = []

    def get_skills(self) -> dict:
        return {"skills": self._skills, "diagnostics": []}


# ============================================================================
# Helpers
# ============================================================================


def _make_session(
    tmp_path: Path | None = None,
    *,
    model: Any = "openai/gpt-5",
    registry: Any = None,
    runner: Any | None = None,
    agent: Any | None = None,
) -> AgentSessionPrompting:
    """Build an AgentSessionPrompting
    with sensible fakes for the tests."""
    if agent is None:
        agent = FakeAgent()
    if registry is None:
        registry = FakeRegistry()
    if runner is None:
        runner = FakeExtensionRunner()
    if tmp_path is None:
        import tempfile

        tmp_path = Path(tempfile.mkdtemp())
    resource_loader = FakeResourceLoader()
    config = AgentSessionConfig(
        agent=agent,
        session_manager=SimpleNamespace(),  # type: ignore[arg-type]
        settings_manager=SimpleNamespace(),  # type: ignore[arg-type]
        cwd=str(tmp_path),
        resource_loader=resource_loader,  # type: ignore[arg-type]
        model_registry=registry,  # type: ignore[arg-type]
    )
    session = AgentSessionPrompting(config)
    session.current_extension_runner = runner
    session.model = model
    session.base_system_prompt = "you are jarvis"
    return session


# ============================================================================
# Constructor
# ============================================================================


class TestConstructor:
    def test_inherits_base(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        assert isinstance(session, AgentSessionPrompting)
        # Inherited from base.
        assert session.cwd == str(tmp_path)
        assert session.pending_message_count == 0
        assert session.steering_messages == []
        assert session.follow_up_messages == []


# ============================================================================
# Public API: prompt
# ============================================================================


class TestPrompt:
    @pytest.mark.asyncio
    async def test_basic_prompt(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        await session.prompt("hello")
        assert len(session.agent.prompted) == 1
        messages = session.agent.prompted[0]
        # The user message is the only
        # one (no pending next-turn
        # messages).
        assert len(messages) == 1
        assert messages[0]["role"] == "user"

    @pytest.mark.asyncio
    async def test_extension_command_handled(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        runner = session.current_extension_runner
        handled: list = []

        async def handler(args: str, ctx: Any) -> None:
            handled.append(args)

        runner.commands["test"] = {"handler": handler}
        await session.prompt("/test arg1 arg2")
        assert handled == ["arg1 arg2"]
        # The agent should not have been
        # prompted — the extension command
        # took over.
        assert session.agent.prompted == []

    @pytest.mark.asyncio
    async def test_extension_command_does_not_expand_templates(
        self, tmp_path: Path
    ) -> None:
        session = _make_session(tmp_path)
        runner = session.current_extension_runner
        runner.commands["foo"] = {"handler": lambda args, ctx: None}
        await session.prompt(
            "/foo",
            PromptOptions(expand_prompt_templates=False),
        )
        # With expand disabled, the
        # extension command check is
        # skipped — the agent gets the
        # raw text.
        assert session.agent.prompted != []

    @pytest.mark.asyncio
    async def test_streaming_requires_behavior(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        session.is_streaming = True
        with pytest.raises(RuntimeError) as exc:
            await session.prompt("hello")
        assert "streamingBehavior" in str(exc.value)

    @pytest.mark.asyncio
    async def test_streaming_steer(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        session.is_streaming = True
        await session.prompt(
            "steer this",
            PromptOptions(streaming_behavior="steer"),
        )
        assert session.steering_messages == ["steer this"]
        assert session.agent.steered != []
        assert session.agent.follow_ups == []

    @pytest.mark.asyncio
    async def test_streaming_follow_up(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        session.is_streaming = True
        await session.prompt(
            "queue this",
            PromptOptions(streaming_behavior="followUp"),
        )
        assert session.follow_up_messages == ["queue this"]
        assert session.agent.follow_ups != []
        assert session.steering_messages == []

    @pytest.mark.asyncio
    async def test_no_model_raises(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path, model=None)
        with pytest.raises(RuntimeError) as exc:
            await session.prompt("hello")
        assert "No model selected" in str(exc.value)

    @pytest.mark.asyncio
    async def test_no_api_key_raises(self, tmp_path: Path) -> None:
        registry = FakeRegistry(has_auth=False, oauth=False)
        session = _make_session(tmp_path, registry=registry)
        with pytest.raises(RuntimeError) as exc:
            await session.prompt("hello")
        assert "No API key" in str(exc.value)

    @pytest.mark.asyncio
    async def test_oauth_expired_raises(self, tmp_path: Path) -> None:
        registry = FakeRegistry(has_auth=False, oauth=True)
        session = _make_session(tmp_path, registry=registry)
        with pytest.raises(RuntimeError) as exc:
            await session.prompt("hello")
        assert "Authentication failed" in str(exc.value)
        assert "/login" in str(exc.value)

    @pytest.mark.asyncio
    async def test_preflight_callback_called_on_success(
        self, tmp_path: Path
    ) -> None:
        session = _make_session(tmp_path)
        calls: list = []
        await session.prompt(
            "hello", PromptOptions(preflight_result=calls.append)
        )
        assert calls == [True]

    @pytest.mark.asyncio
    async def test_preflight_callback_called_on_error(
        self, tmp_path: Path
    ) -> None:
        session = _make_session(tmp_path, model=None)
        calls: list = []
        with pytest.raises(RuntimeError):
            await session.prompt(
                "hello", PromptOptions(preflight_result=calls.append)
            )
        assert calls == [False]

    @pytest.mark.asyncio
    async def test_preflight_skipped_when_extension_command_handled(
        self, tmp_path: Path
    ) -> None:
        session = _make_session(tmp_path)
        runner = session.current_extension_runner
        runner.commands["test"] = {"handler": lambda args, ctx: None}
        calls: list = []
        await session.prompt(
            "/test",
            PromptOptions(preflight_result=calls.append),
        )
        # Extension command handled +
        # preflight=True.
        assert calls == [True]


# ============================================================================
# Public API: steer
# ============================================================================


class TestSteer:
    @pytest.mark.asyncio
    async def test_basic_steer(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        await session.steer("hi")
        assert session.steering_messages == ["hi"]
        assert session.agent.steered != []

    @pytest.mark.asyncio
    async def test_steer_rejects_extension_command(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        runner = session.current_extension_runner
        runner.commands["test"] = {"handler": lambda args, ctx: None}
        with pytest.raises(RuntimeError) as exc:
            await session.steer("/test")
        assert "cannot be queued" in str(exc.value)


# ============================================================================
# Public API: follow_up
# ============================================================================


class TestFollowUp:
    @pytest.mark.asyncio
    async def test_basic_follow_up(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        await session.follow_up("later")
        assert session.follow_up_messages == ["later"]
        assert session.agent.follow_ups != []

    @pytest.mark.asyncio
    async def test_follow_up_rejects_extension_command(
        self, tmp_path: Path
    ) -> None:
        session = _make_session(tmp_path)
        runner = session.current_extension_runner
        runner.commands["test"] = {"handler": lambda args, ctx: None}
        with pytest.raises(RuntimeError) as exc:
            await session.follow_up("/test")
        assert "cannot be queued" in str(exc.value)


# ============================================================================
# Public API: send_custom_message
# ============================================================================


class TestSendCustomMessage:
    @pytest.mark.asyncio
    async def test_next_turn(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        await session.send_custom_message(
            {"customType": "x", "content": "y"},
            {"deliverAs": "nextTurn"},
        )
        assert len(session.pending_next_turn_messages) == 1

    @pytest.mark.asyncio
    async def test_streaming_steer(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        session.is_streaming = True
        await session.send_custom_message(
            {"customType": "x", "content": "y"},
            {"deliverAs": "steer"},
        )
        assert session.agent.steered != []

    @pytest.mark.asyncio
    async def test_streaming_follow_up(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        session.is_streaming = True
        await session.send_custom_message(
            {"customType": "x", "content": "y"},
            {"deliverAs": "followUp"},
        )
        assert session.agent.follow_ups != []

    @pytest.mark.asyncio
    async def test_trigger_turn_runs_prompt(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        await session.send_custom_message(
            {"customType": "x", "content": "y"},
            {"triggerTurn": True},
        )
        assert session.agent.prompted != []

    @pytest.mark.asyncio
    async def test_no_trigger_appends(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        await session.send_custom_message(
            {"customType": "x", "content": "y"},
        )
        # The message is appended to the
        # agent state.
        assert len(session.agent.state.messages) == 1


# ============================================================================
# Public API: send_user_message
# ============================================================================


class TestSendUserMessage:
    @pytest.mark.asyncio
    async def test_string_content(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        await session.send_user_message("hello world")
        assert session.agent.prompted != []
        msgs = session.agent.prompted[0]
        assert msgs[0]["role"] == "user"

    @pytest.mark.asyncio
    async def test_content_array(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        await session.send_user_message(
            [
                {"type": "text", "text": "hi"},
                {"type": "image", "data": "..."},
            ]
        )
        msgs = session.agent.prompted[0]
        # Text + image content blocks.
        content = msgs[0]["content"]
        assert content[0] == {"type": "text", "text": "hi"}

    @pytest.mark.asyncio
    async def test_with_deliver_as(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        session.is_streaming = True
        await session.send_user_message(
            "queued", {"deliverAs": "followUp"}
        )
        assert session.follow_up_messages == ["queued"]


# ============================================================================
# Public API: clear_queue
# ============================================================================


class TestClearQueue:
    def test_clear_both(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        session.steering_messages = ["a", "b"]
        session.follow_up_messages = ["c"]
        # Mirror the underlying agent
        # state.
        session.agent.steer({"role": "user", "content": []})
        session.agent.follow_up({"role": "user", "content": []})
        result = session.clear_queue()
        assert result["steering"] == ["a", "b"]
        assert result["followUp"] == ["c"]
        assert session.steering_messages == []
        assert session.follow_up_messages == []
        assert session.agent.steered == []
        assert session.agent.follow_ups == []


# ============================================================================
# Public API: abort
# ============================================================================


class TestAbort:
    @pytest.mark.asyncio
    async def test_abort_calls_agent(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        await session.abort()
        assert session.agent.aborted_with is None

    @pytest.mark.asyncio
    async def test_abort_passes_reason(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        await session.abort("user-cancelled")
        assert session.agent.aborted_with == "user-cancelled"


# ============================================================================
# Public API: getters
# ============================================================================


class TestGetters:
    def test_pending_message_count(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        assert session.pending_message_count == 0
        session.steering_messages = ["a"]
        assert session.pending_message_count == 1
        session.follow_up_messages = ["b", "c"]
        assert session.pending_message_count == 3

    def test_get_steering_messages(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        session.steering_messages = ["a", "b"]
        assert session.get_steering_messages() == ["a", "b"]

    def test_get_follow_up_messages(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        session.follow_up_messages = ["c"]
        assert session.get_follow_up_messages() == ["c"]

    def test_resource_loader(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        assert session.resource_loader is session.session_resource_loader


# ============================================================================
# Private helpers
# ============================================================================


class TestCreateUserContent:
    def test_text_only(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        content = session._create_user_content("hi")
        assert content == [{"type": "text", "text": "hi"}]

    def test_text_with_images(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        content = session._create_user_content(
            "hi", [{"type": "image", "data": "x"}]
        )
        assert content[0] == {"type": "text", "text": "hi"}
        assert content[1] == {"type": "image", "data": "x"}


class TestExpandSkillCommand:
    def test_no_skill_prefix(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        assert session._expand_skill_command("hello") == "hello"

    def test_unknown_skill(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        assert session._expand_skill_command("/skill:unknown") == "/skill:unknown"

    def test_known_skill(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        skill_md = tmp_path / "my_skill" / "SKILL.md"
        skill_md.parent.mkdir(parents=True)
        skill_md.write_text("# My skill\nbody\n")
        session.session_resource_loader._skills = [
            SimpleNamespace(
                name="my_skill",
                file_path=str(skill_md),
                base_dir=str(skill_md.parent),
            )
        ]
        result = session._expand_skill_command("/skill:my_skill")
        assert "References are relative to" in result
        assert "body" in result

    def test_skill_with_args(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        skill_md = tmp_path / "my_skill" / "SKILL.md"
        skill_md.parent.mkdir(parents=True)
        skill_md.write_text("body\n")
        session.session_resource_loader._skills = [
            SimpleNamespace(
                name="my_skill",
                file_path=str(skill_md),
                base_dir=str(skill_md.parent),
            )
        ]
        result = session._expand_skill_command(
            "/skill:my_skill some args"
        )
        assert "some args" in result


class TestThrowIfExtensionCommand:
    def test_no_command(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        # Should not raise when no
        # command matches.
        session._throw_if_extension_command("/unknown")

    def test_known_command_raises(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        runner = session.current_extension_runner
        runner.commands["test"] = {"handler": lambda args, ctx: None}
        with pytest.raises(RuntimeError) as exc:
            session._throw_if_extension_command("/test arg")
        assert "cannot be queued" in str(exc.value)


class TestHandlePostAgentRun:
    @pytest.mark.asyncio
    async def test_no_message_returns_settled(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        # ``lastAssistantMessage`` is
        # ``None`` → settled.
        result = await session._handle_post_agent_run()
        assert result == "settled"

    @pytest.mark.asyncio
    async def test_handoff_returns_handoff(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        session.last_run_ended_for_turn_handoff = True
        result = await session._handle_post_agent_run()
        assert result == "handoff"
        # Flag consumed.
        assert session.last_run_ended_for_turn_handoff is False
