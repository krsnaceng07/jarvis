"""Phase 6.12h — agent_session main entry tests.

Verifies the public surface of
:class:`AgentSession` (the main entry
class):

- The constructor wires up agent
  event subscription, installs tool
  hooks (STUB), and builds the
  runtime.
- Inherits from
  :class:`AgentSessionTree`.
- The initial active tool names +
  includeAllExtensionTools options
  are passed to ``build_runtime``.
"""
from __future__ import annotations

import tempfile
from typing import Any

import pytest

from src.agents.sessions.agent_session import AgentSession
from src.agents.sessions.agent_session_tree import AgentSessionTree
from src.agents.sessions.extensions.runner import ExtensionRunner


# ============================================================================
# Fakes
# ============================================================================


class _NS:
    def __init__(self, **kw: Any) -> None:
        self.__dict__.update(kw)


class FakeAgent:
    def __init__(self) -> None:
        self.state: Any = _NS(
            model=None,
            messages=[],
            thinkingLevel="medium",
            systemPrompt="",
            steeringMode="one-at-a-time",
            followUpMode="one-at-a-time",
            activeTools=[],
        )
        self.steeringMode = "one-at-a-time"
        self.followUpMode = "one-at-a-time"
        self.signal: Any = None
        self.queued: int = 0
        self.subscribed: list = []

    def has_queued_messages(self) -> bool:
        return self.queued > 0

    async def wait_for_idle(self) -> None:
        return None

    def subscribe_events(self, handler: Any) -> Any:
        self.subscribed.append(handler)
        return lambda: None

    def continue_run(self) -> None:
        pass

    def clear_all_queues(self) -> None:
        self.queued = 0

    def abort(self, _reason: Any = None) -> None:
        pass


class FakeRegistry:
    def has_configured_auth(self, model: Any) -> bool:
        return True

    def get_available(self) -> list:
        return []

    def refresh(self) -> None:
        pass


class FakeSettingsManager:
    def get_retry_enabled(self) -> bool:
        return True

    def get_retry_max_attempts(self) -> int:
        return 3

    def get_retry_base_delay_ms(self) -> int:
        return 1000

    def get_retry_settings(self) -> dict:
        return {
            "enabled": True,
            "maxRetries": 3,
            "baseDelayMs": 1000,
        }

    def set_retry_enabled(self, _enabled: bool) -> None:
        pass

    def get_default_thinking_level(self) -> str:
        return "medium"

    def get_shell_path(self) -> str | None:
        return None

    def get_shell_command_prefix(self) -> str | None:
        return None

    def get_steering_mode(self) -> str:
        return "all"

    def get_follow_up_mode(self) -> str:
        return "all"

    def reload(self) -> _NS:
        async def _do_reload() -> None:
            return None
        return _do_reload()


class FakeSessionManager:
    def __init__(self) -> None:
        self.session_id: str = "sess-1"
        self.session_name: str | None = None
        self.session_file: str | None = "/tmp/sess.jsonl"
        self.cwd: str = "/tmp/proj"
        self.leaf_id: str = "leaf-x"

    def get_leaf_id(self) -> str:
        return self.leaf_id

    def get_session_id(self) -> str:
        return self.session_id

    def get_session_name(self) -> str | None:
        return self.session_name

    def get_session_file(self) -> str | None:
        return self.session_file

    def get_cwd(self) -> str:
        return self.cwd


class FakeResourceLoader:
    def __init__(self) -> None:
        self.extensions: list = []
        self.runtime: Any = _NS(
            flagValues={},
            pendingProviderRegistrations=[],
        )

    def get_extensions(self) -> _NS:
        return _NS(
            extensions=list(self.extensions),
            runtime=self.runtime,
            errors=[],
        )

    def get_skills(self) -> dict:
        return {"skills": [], "diagnostics": []}

    def get_prompts(self) -> dict:
        return {"prompts": [], "diagnostics": []}

    def get_themes(self) -> dict:
        return {"themes": [], "diagnostics": []}

    def get_system_prompt(self) -> str | None:
        return None

    def get_append_system_prompt(self) -> list:
        return []

    def get_agents_files(self) -> dict:
        return {"agentsFiles": [], "diagnostics": []}

    def extend_resources(self, _paths: dict) -> None:
        pass

    def reload(self) -> _NS:
        async def _do_reload() -> None:
            return None
        return _do_reload()


def _make_config(
    *,
    initial_active_tool_names: list[str] | None = None,
) -> _NS:
    return _NS(
        agent=FakeAgent(),
        session_manager=FakeSessionManager(),
        settings_manager=FakeSettingsManager(),
        scoped_models=[],
        custom_tools=[],
        cwd=tempfile.mkdtemp(),
        resource_loader=FakeResourceLoader(),
        model_registry=FakeRegistry(),
        extension_runner_ref=None,
        initial_active_tool_names=initial_active_tool_names,
        allowed_tool_names=None,
        disable_built_in_tools=False,
        base_tools_override=None,
        session_start_event=None,
        with_session_write_lock=None,
    )


# ============================================================================
# Constructor
# ============================================================================


class TestConstructor:
    def test_inherits_tree(self) -> None:
        session = AgentSession(_make_config())
        assert isinstance(session, AgentSessionTree)

    def test_subscribes_to_agent(self) -> None:
        config = _make_config()
        session = AgentSession(config)
        # The agent received the
        # subscription.
        assert len(config.agent.subscribed) == 1

    def test_builds_runtime(self) -> None:
        session = AgentSession(_make_config())
        # The extension runner was
        # created.
        assert isinstance(
            session.current_extension_runner, ExtensionRunner
        )

    def test_default_active_tool_names(self) -> None:
        session = AgentSession(_make_config())
        # No initial active tool names
        # → default "read", "bash",
        # "edit", "write".
        active = session.get_active_tool_names()
        assert "read" in active
        assert "bash" in active
        assert "edit" in active
        assert "write" in active

    def test_initial_active_tool_names(self) -> None:
        config = _make_config(
            initial_active_tool_names=["read"]
        )
        session = AgentSession(config)
        active = session.get_active_tool_names()
        assert "read" in active
        # Override → no default
        # bash / edit / write.
        assert "bash" not in active
        assert "edit" not in active
        assert "write" not in active

    def test_emits_session_start_via_subclass(self) -> None:
        # The OpenClaw source's
        # :class:`AgentSession` does
        # NOT emit ``session_start``
        # itself — that's the job of
        # :meth:`bindExtensions` (Phase
        # 6.12f). The Python port
        # follows the same shape: the
        # constructor builds the
        # runtime; ``bind_extensions``
        # is called by the
        # factory.
        config = _make_config()
        session = AgentSession(config)
        # No events on the listener (the
        # constructor didn't bind
        # extensions).
        events: list = []
        session.subscribe(events.append)
        # Just verify the session
        # exists + has the expected
        # state.
        assert session.current_extension_runner is not None
