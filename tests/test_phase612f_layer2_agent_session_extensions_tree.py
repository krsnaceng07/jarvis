"""Phase 6.12f — agent_session_extensions + agent_session_tree tests.

Verifies the public surface of:

- :class:`AgentSessionExtensions` —
  extension runner binding, tool
  registry refresh, build_runtime +
  reload, core binding + action
  delegates (``_core_*``).
- :class:`AgentSessionTree` —
  session-tree navigation
  (``navigate_tree``) +
  ``get_user_messages_for_forking`` +
  ``create_replaced_session_context`` +
  ``has_extension_handlers`` +
  ``extension_runner`` property.
"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

import pytest

from src.agents.sessions.agent_session_execution import AgentSessionExecution
from src.agents.sessions.agent_session_extensions import (
    AgentSessionExtensions,
)
from src.agents.sessions.agent_session_models import AgentSessionModels
from src.agents.sessions.agent_session_tree import (
    AgentSessionTree,
    BranchSummaryEntry,
)
from src.agents.sessions.agent_session_types import (
    AgentSessionConfig,
    ExtensionBindings,
)
from src.agents.sessions.extensions.runner import ExtensionRunner
from src.agents.sessions.extensions.types import (
    Extension,
    ExtensionRuntime,
    ToolDefinition,
)


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


class FakeRegistry:
    def __init__(self) -> None:
        self.registered: list = []
        self.unregistered: list = []
        self.has_auth: bool = True

    def has_configured_auth(self, model: Any) -> bool:
        return self.has_auth

    def register_provider(self, name: str, config: Any) -> None:
        self.registered.append((name, config))

    def unregister_provider(self, name: str) -> None:
        self.unregistered.append(name)

    def find(self, provider: str, model_id: str) -> Any:
        return {"provider": provider, "id": model_id, "refreshed": True}

    def refresh(self) -> None:
        pass

    def get_available(self) -> list:
        return []


class FakeSettingsManager:
    def __init__(self) -> None:
        self.steering_mode: str = "all"
        self.follow_up_mode: str = "all"
        self.reload_called: int = 0

    def reload(self) -> None:  # async-coroutine-compatible
        self.reload_called += 1
        return _async_noop()

    def get_steering_mode(self) -> str:
        return self.steering_mode

    def get_follow_up_mode(self) -> str:
        return self.follow_up_mode

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

    def set_retry_enabled(self, enabled: bool) -> None:
        pass

    def get_default_thinking_level(self) -> str:
        return "medium"

    def get_shell_path(self) -> str | None:
        return None

    def get_shell_command_prefix(self) -> str | None:
        return None

    def get_image_auto_resize(self) -> bool:
        return True


async def _async_noop() -> None:
    return None


class FakeSessionManager:
    def __init__(self) -> None:
        self.appended: list = []
        self.session_id: str = "sess-1"
        self.session_name: str | None = None
        self.session_file: str | None = "/tmp/sess.jsonl"
        self.cwd: str = "/tmp/proj"
        self.leaf_id: str = "leaf-x"
        self.entries: list = []
        self.built_ctx: dict = {"messages": []}
        self._label_appends: list = []
        self._custom_appends: list = []
        self._branch_calls: list = []
        self._reset_called: int = 0

    def append_message(self, message: Any) -> None:
        self.appended.append(message)

    def append_session_info(self, name: str) -> None:
        self.session_name = name

    def set_session_name(self, name: str) -> None:
        self.session_name = name

    def get_session_id(self) -> str:
        return self.session_id

    def get_session_name(self) -> str | None:
        return self.session_name

    def get_session_file(self) -> str | None:
        return self.session_file

    def get_cwd(self) -> str:
        return self.cwd

    def get_leaf_id(self) -> str:
        return self.leaf_id

    def get_entry(self, entry_id: str) -> dict | None:
        for e in self.entries:
            if isinstance(e, dict) and e.get("id") == entry_id:
                return e
        return None

    def get_entries(self) -> list:
        return list(self.entries)

    def build_session_context(self) -> dict:
        return dict(self.built_ctx)

    def branch(self, leaf_id: str) -> None:
        self._branch_calls.append(leaf_id)
        self.leaf_id = leaf_id

    def reset_leaf(self) -> None:
        self._reset_called += 1
        self.leaf_id = ""

    def append_label_change(self, entry_id: str, label: str) -> None:
        self._label_appends.append((entry_id, label))

    def append_custom_entry(self, custom_type: str, data: Any) -> None:
        self._custom_appends.append((custom_type, data))

    def append_custom_message_entry(
        self,
        custom_type: str,
        content: Any,
        display: Any,
        details: Any,
    ) -> None:
        self._custom_appends.append((custom_type, content))


class FakeResourceLoader:
    def __init__(self) -> None:
        self.extensions: list = []
        self.runtime: ExtensionRuntime = _make_extension_runtime()
        self.reloaded: int = 0
        self.extended: list = []
        self.skills: list = []
        self.prompts: list = []
        self.themes: list = []

    def get_extensions(self) -> _NS:
        return _NS(
            extensions=list(self.extensions),
            runtime=self.runtime,
            errors=[],
        )

    def get_skills(self) -> dict:
        return {"skills": list(self.skills), "diagnostics": []}

    def get_prompts(self) -> dict:
        return {"prompts": list(self.prompts), "diagnostics": []}

    def get_themes(self) -> dict:
        return {"themes": list(self.themes), "diagnostics": []}

    def extend_resources(self, paths: dict) -> None:
        self.extended.append(paths)

    def reload(self) -> _NS:
        async def _do_reload() -> None:
            self.reloaded += 1

        return _do_reload()

    def get_system_prompt(self) -> str | None:
        return None

    def get_append_system_prompt(self) -> list:
        return []

    def get_agents_files(self) -> dict:
        return {"agentsFiles": [], "diagnostics": []}


def _make_extension_runtime() -> ExtensionRuntime:
    return ExtensionRuntime(
        flagValues={},
        pendingProviderRegistrations=[],
    )


def _make_extension(path: str = "<test:fake>") -> Extension:
    return Extension(
        path=path,
        resolvedPath=path,
        sourceInfo={"path": path, "source": "test"},
        handlers={},
        tools={},
        messageRenderers={},
        commands={},
        flags={},
        shortcuts={},
    )


def _make_extension_session(
    tmp_path: Path | None = None,
    *,
    resource_loader: Any | None = None,
    settings: Any | None = None,
    session_manager: Any | None = None,
    model_registry: Any | None = None,
    extension_runner: Any | None = None,
    cwd: str | None = None,
) -> AgentSessionExtensions:
    if tmp_path is None:
        tmp_path = Path(tempfile.mkdtemp())
    agent = FakeAgent()
    config = AgentSessionConfig(
        agent=agent,
        session_manager=session_manager or FakeSessionManager(),
        settings_manager=settings or FakeSettingsManager(),
        cwd=cwd or str(tmp_path),
        resource_loader=resource_loader or FakeResourceLoader(),
        model_registry=model_registry or FakeRegistry(),
    )
    session = AgentSessionExtensions(config)
    if extension_runner is not None:
        session.current_extension_runner = extension_runner
    return session


def _make_tree_session(
    tmp_path: Path | None = None,
    *,
    resource_loader: Any | None = None,
    session_manager: Any | None = None,
    extension_runner: Any | None = None,
    cwd: str | None = None,
) -> AgentSessionTree:
    if tmp_path is None:
        tmp_path = Path(tempfile.mkdtemp())
    agent = FakeAgent()
    config = AgentSessionConfig(
        agent=agent,
        session_manager=session_manager or FakeSessionManager(),
        settings_manager=FakeSettingsManager(),
        cwd=cwd or str(tmp_path),
        resource_loader=resource_loader or FakeResourceLoader(),
        model_registry=FakeRegistry(),
    )
    session = AgentSessionTree(config)
    if extension_runner is not None:
        session.current_extension_runner = extension_runner
    return session


# ============================================================================
# Real ExtensionRunner helpers (using a real instance so bind_core works)
# ============================================================================


def _make_real_runner(
    extensions: list[Extension] | None = None,
    resource_loader: Any | None = None,
) -> ExtensionRunner:
    """Build a real :class:`ExtensionRunner`
    for tests. Bound to a real
    :class:`ExtensionRuntime` so the
    ``bindCore`` contract works."""
    if extensions is None:
        extensions = [_make_extension()]
    if resource_loader is None:
        resource_loader = FakeResourceLoader()
    extensions_result = resource_loader.get_extensions()
    return ExtensionRunner(
        extensions=extensions_result.extensions,
        runtime=extensions_result.runtime,
        cwd="C:/work/proj",
        session_manager=FakeSessionManager(),
        model_registry=FakeRegistry(),
    )


# ============================================================================
# Constructor / inheritance
# ============================================================================


class TestConstructor:
    def test_extensions_inherits_execution(self, tmp_path: Path) -> None:
        session = _make_extension_session(tmp_path)
        assert isinstance(session, AgentSessionExecution)
        assert isinstance(session, AgentSessionModels)

    def test_tree_inherits_extensions(self, tmp_path: Path) -> None:
        session = _make_tree_session(tmp_path)
        assert isinstance(session, AgentSessionExtensions)
        assert isinstance(session, AgentSessionExecution)
        assert isinstance(session, AgentSessionModels)


# ============================================================================
# AgentSessionExtensions: get_active_tool_names / get_all_tools /
# set_active_tools_by_name
# ============================================================================


class TestActiveToolNames:
    def test_get_default(self, tmp_path: Path) -> None:
        session = _make_extension_session(tmp_path)
        assert session.get_active_tool_names() == []

    def test_get_existing(self, tmp_path: Path) -> None:
        session = _make_extension_session(tmp_path)
        session.agent.state.activeTools = ["read", "write"]
        assert session.get_active_tool_names() == ["read", "write"]

    def test_set(self, tmp_path: Path) -> None:
        session = _make_extension_session(tmp_path)
        session.set_active_tools_by_name(["read", "bash", "read"])
        # Dedup + write to state.
        assert session.agent.state.activeTools == ["read", "bash"]

    def test_set_empty(self, tmp_path: Path) -> None:
        session = _make_extension_session(tmp_path)
        session.agent.state.activeTools = ["old"]
        session.set_active_tools_by_name([])
        assert session.agent.state.activeTools == []


class TestGetAllTools:
    def test_empty(self, tmp_path: Path) -> None:
        session = _make_extension_session(tmp_path)
        session.tool_registry = {}
        assert session.get_all_tools() == []

    def test_populated(self, tmp_path: Path) -> None:
        session = _make_extension_session(tmp_path)
        session.tool_registry = {
            "read": _NS(name="read"),
            "write": _NS(name="write"),
        }
        assert sorted(session.get_all_tools()) == ["read", "write"]


# ============================================================================
# AgentSessionExtensions: _get_extension_source_label
# ============================================================================


class TestGetExtensionSourceLabel:
    def test_empty(self, tmp_path: Path) -> None:
        session = _make_extension_session(tmp_path)
        assert session._get_extension_source_label("") == "extension:unknown"

    def test_synthetic(self, tmp_path: Path) -> None:
        session = _make_extension_session(tmp_path)
        # <synthetic:name> → extension:name
        assert (
            session._get_extension_source_label("<synthetic:foo>")
            == "extension:synthetic:foo"
        )

    def test_real_path(self, tmp_path: Path) -> None:
        session = _make_extension_session(tmp_path)
        # No `.ts` / `.js` suffix in
        # extension source label (OpenClaw
        # strips both).
        assert (
            session._get_extension_source_label("C:/exts/myext.ts")
            == "extension:myext"
        )

    def test_real_path_js(self, tmp_path: Path) -> None:
        session = _make_extension_session(tmp_path)
        assert (
            session._get_extension_source_label("C:/exts/other.js")
            == "extension:other"
        )


# ============================================================================
# AgentSessionExtensions: _build_extension_resource_paths
# ============================================================================


class TestBuildExtensionResourcePaths:
    def test_empty(self, tmp_path: Path) -> None:
        session = _make_extension_session(tmp_path)
        assert session._build_extension_resource_paths([]) == []

    def test_real_path(self, tmp_path: Path) -> None:
        session = _make_extension_session(tmp_path)
        entries = [
            {
                "path": "/skill/test.md",
                "extensionPath": "C:/exts/myext.ts",
            }
        ]
        out = session._build_extension_resource_paths(entries)
        assert len(out) == 1
        assert out[0]["path"] == "/skill/test.md"
        meta = out[0]["metadata"]
        assert meta["source"] == "extension:myext"
        assert meta["scope"] == "temporary"
        assert meta["origin"] == "top-level"
        # Real path → baseDir = dirname.
        assert meta["baseDir"] == "C:/exts"

    def test_synthetic_path(self, tmp_path: Path) -> None:
        session = _make_extension_session(tmp_path)
        entries = [
            {
                "path": "/skill/x.md",
                "extensionPath": "<synthetic:myext>",
            }
        ]
        out = session._build_extension_resource_paths(entries)
        assert len(out) == 1
        meta = out[0]["metadata"]
        assert meta["source"] == "extension:synthetic:myext"
        # Synthetic → baseDir is None.
        assert meta["baseDir"] is None


# ============================================================================
# AgentSessionExtensions: _refresh_current_model_from_registry
# ============================================================================


class TestRefreshCurrentModelFromRegistry:
    def test_no_model(self, tmp_path: Path) -> None:
        registry = FakeRegistry()
        session = _make_extension_session(
            tmp_path, model_registry=registry
        )
        session.model = None
        # No-op when there's no current model.
        session._refresh_current_model_from_registry()

    def test_refreshed(self, tmp_path: Path) -> None:
        registry = FakeRegistry()
        session = _make_extension_session(
            tmp_path, model_registry=registry
        )
        session.model = {"provider": "anthropic", "id": "claude-3"}
        session._refresh_current_model_from_registry()
        # Refreshed to the registry's find()
        # result.
        assert session.model["refreshed"] is True
        assert session.agent.state.model["refreshed"] is True

    def test_registry_has_no_find(self, tmp_path: Path) -> None:
        # Registry without a ``find`` method →
        # no-op.
        class _NoFindRegistry:
            def has_configured_auth(self, _model: Any) -> bool:
                return True

            def get_available(self) -> list:
                return []

        session = _make_extension_session(
            tmp_path, model_registry=_NoFindRegistry()
        )
        session.model = {"provider": "x", "id": "y"}
        # Should not raise.
        session._refresh_current_model_from_registry()
        # Model unchanged.
        assert session.model == {"provider": "x", "id": "y"}


# ============================================================================
# AgentSessionExtensions: _bind_extension_core + _core_* delegates
# ============================================================================


class TestBindExtensionCore:
    def test_binds_core_actions_registration(
        self, tmp_path: Path
    ) -> None:
        runner = _make_real_runner()
        session = _make_extension_session(
            tmp_path, extension_runner=runner
        )
        # Trigger bind via the public build_runtime.
        # Just call the private helper
        # directly.
        session._bind_extension_core(runner)
        # The runtime stores the core
        # actions (the runner's
        # ``bindCore`` wires the dict
        # into the runtime).
        runtime = runner._runtime
        assert callable(runtime.sendMessage)
        assert callable(runtime.setModel)
        # The context actions are stored
        # on the runner itself (not the
        # runtime).
        assert callable(runner._get_model)
        assert callable(runner._is_idle)


class TestCoreGetCommands:
    def test_empty(self, tmp_path: Path) -> None:
        runner = _make_real_runner()
        session = _make_extension_session(
            tmp_path, extension_runner=runner
        )
        commands = session._core_get_commands()
        # No extensions, no templates, no
        # skills → empty list.
        assert commands == []

    def test_with_prompt_template(self, tmp_path: Path) -> None:
        runner = _make_real_runner()
        session = _make_extension_session(
            tmp_path, extension_runner=runner
        )
        session.prompt_templates = [
            {
                "name": "test-template",
                "description": "A test",
                "sourceInfo": {"path": "<test>"},
            }
        ]
        commands = session._core_get_commands()
        # 1 prompt template.
        assert len(commands) == 1
        assert commands[0]["name"] == "test-template"
        assert commands[0]["source"] == "prompt"

    def test_with_skill(self, tmp_path: Path) -> None:
        runner = _make_real_runner()
        skill = _NS(
            name="my-skill",
            description="My skill",
            source_info={"path": "<skill>"},
        )
        loader = FakeResourceLoader()
        loader.skills = [skill]
        session = _make_extension_session(
            tmp_path,
            extension_runner=runner,
            resource_loader=loader,
        )
        commands = session._core_get_commands()
        # 1 skill.
        assert len(commands) == 1
        assert commands[0]["name"] == "skill:my-skill"
        assert commands[0]["source"] == "skill"


class TestCoreSetModel:
    @pytest.mark.asyncio
    async def test_no_auth(self, tmp_path: Path) -> None:
        registry = FakeRegistry()
        registry.has_auth = False
        runner = _make_real_runner()
        session = _make_extension_session(
            tmp_path, model_registry=registry, extension_runner=runner
        )
        result = await session._core_set_model({"provider": "x", "id": "y"})
        assert result is False
        # model NOT set.
        assert session.model is None

    @pytest.mark.asyncio
    async def test_with_auth(self, tmp_path: Path) -> None:
        registry = FakeRegistry()
        registry.has_auth = True
        runner = _make_real_runner()
        session = _make_extension_session(
            tmp_path, model_registry=registry, extension_runner=runner
        )
        result = await session._core_set_model(
            {"provider": "anthropic", "id": "claude-3"}
        )
        assert result is True
        assert session.model == {
            "provider": "anthropic",
            "id": "claude-3",
        }


class TestCoreAbort:
    def test_uses_extension_handler(self, tmp_path: Path) -> None:
        runner = _make_real_runner()
        session = _make_extension_session(
            tmp_path, extension_runner=runner
        )

        called: list = []

        def _handler() -> None:
            called.append("abort")

        session.extension_abort_handler = _handler
        session._core_abort()
        assert called == ["abort"]

    @pytest.mark.asyncio
    async def test_falls_back_to_task(self, tmp_path: Path) -> None:
        runner = _make_real_runner()
        session = _make_extension_session(
            tmp_path, extension_runner=runner
        )
        # No handler → schedule abort task.
        # The ``abort`` method on the base
        # class is a no-op when there's no
        # in-flight prompt; verify no
        # exception is raised.
        session.extension_abort_handler = None
        session._core_abort()  # no error
        # Give the scheduled task a
        # chance to run.
        await asyncio.sleep(0)


class TestCoreShutdown:
    def test_uses_handler(self, tmp_path: Path) -> None:
        runner = _make_real_runner()
        session = _make_extension_session(
            tmp_path, extension_runner=runner
        )
        called: list = []

        def _handler() -> None:
            called.append("shutdown")

        session.extension_shutdown_handler = _handler
        session._core_shutdown()
        assert called == ["shutdown"]

    def test_no_handler(self, tmp_path: Path) -> None:
        runner = _make_real_runner()
        session = _make_extension_session(
            tmp_path, extension_runner=runner
        )
        session.extension_shutdown_handler = None
        # No-op.
        session._core_shutdown()


class TestCoreRegisterProvider:
    def test_register(self, tmp_path: Path) -> None:
        registry = FakeRegistry()
        runner = _make_real_runner()
        session = _make_extension_session(
            tmp_path, model_registry=registry, extension_runner=runner
        )
        session._core_register_provider("myprov", {"key": "value"})
        assert ("myprov", {"key": "value"}) in registry.registered

    def test_unregister(self, tmp_path: Path) -> None:
        registry = FakeRegistry()
        runner = _make_real_runner()
        session = _make_extension_session(
            tmp_path, model_registry=registry, extension_runner=runner
        )
        session._core_unregister_provider("myprov")
        assert "myprov" in registry.unregistered


# ============================================================================
# AgentSessionExtensions: build_runtime
# ============================================================================


class TestBuildRuntime:
    def test_creates_runner(self, tmp_path: Path) -> None:
        session = _make_extension_session(tmp_path)
        session.build_runtime()
        # The runner was created + bound.
        assert isinstance(
            session.current_extension_runner, ExtensionRunner
        )
        # Default active tools: read,
        # bash, edit, write.
        active = session.get_active_tool_names()
        assert "read" in active
        assert "bash" in active
        assert "edit" in active
        assert "write" in active

    def test_with_active_tool_names(self, tmp_path: Path) -> None:
        session = _make_extension_session(tmp_path)
        session.build_runtime(
            {"activeToolNames": ["read"], "includeAllExtensionTools": False}
        )
        active = session.get_active_tool_names()
        assert "read" in active
        # Bash / edit / write NOT in active
        # when overridden.
        assert "bash" not in active

    def test_with_flag_values(self, tmp_path: Path) -> None:
        session = _make_extension_session(tmp_path)
        session.build_runtime(
            {"flagValues": {"my-flag": True}}
        )
        # Flag is stored on the runtime.
        assert session.current_extension_runner.get_flag_values() == {
            "my-flag": True
        }

    def test_includes_all_extension_tools_when_allowed(
        self, tmp_path: Path
    ) -> None:
        loader = FakeResourceLoader()
        # Register one extension tool.
        ext = _make_extension("<test:myext>")
        tool_def: ToolDefinition = {
            "name": "my-custom",
            "description": "Custom",
        }
        ext.tools["my-custom"] = {
            "definition": tool_def,
            "sourceInfo": {"path": "<test:myext>"},
        }
        loader.extensions = [ext]
        session = _make_extension_session(
            tmp_path, resource_loader=loader
        )
        # Allow all tools.
        config = session.session_manager  # type: ignore[attr-defined]
        _ = config
        # allowed_tool_names is None →
        # default filter.
        session.build_runtime(
            {"activeToolNames": [], "includeAllExtensionTools": True}
        )
        # The extension tool is registered.
        assert "my-custom" in session.get_all_tools()

    def test_extension_runner_ref(self, tmp_path: Path) -> None:
        # extensionRunnerRef is a dict with
        # ``current`` key.
        ref: dict = {}
        agent = FakeAgent()
        config = AgentSessionConfig(
            agent=agent,
            session_manager=FakeSessionManager(),
            settings_manager=FakeSettingsManager(),
            cwd=str(tmp_path),
            resource_loader=FakeResourceLoader(),
            model_registry=FakeRegistry(),
            extension_runner_ref=ref,
        )
        session = AgentSessionExtensions(config)
        session.build_runtime()
        # The ref was updated.
        assert ref["current"] is session.current_extension_runner


# ============================================================================
# AgentSessionExtensions: bind_extensions
# ============================================================================


class TestBindExtensions:
    @pytest.mark.asyncio
    async def test_emits_session_start(self, tmp_path: Path) -> None:
        events: list = []

        class _Runner:
            def __init__(self) -> None:
                self.handlers: dict = {"session_start": [lambda _e: None]}

            def has_handlers(self, t: str) -> bool:
                return bool(self.handlers.get(t))

            async def emit(self, event: dict) -> None:
                events.append(event)

            def set_ui_context(self, _ctx: Any) -> None:
                pass

            def bind_command_context(self, _ctx: Any) -> None:
                pass

            def on_error(self, _listener: Any) -> Any:
                return lambda: None

            def get_flag_values(self) -> dict:
                return {}

        runner = _Runner()
        session = _make_extension_session(
            tmp_path, extension_runner=runner
        )
        await session.bind_extensions(ExtensionBindings())
        # Session start event emitted.
        session_start_events = [
            e for e in events if e.get("type") == "session_start"
        ]
        assert len(session_start_events) == 1
        assert session_start_events[0]["reason"] == "startup"

    @pytest.mark.asyncio
    async def test_applies_bindings(self, tmp_path: Path) -> None:
        ui_ctx = _NS()
        cc_actions: dict = {}
        abort_called: list = []
        shutdown_called: list = []
        error_listener = lambda _e: None

        class _Runner:
            def __init__(self) -> None:
                self.ui_ctx = None
                self.cc_actions = None
                self.error_listener = None

            def has_handlers(self, t: str) -> bool:
                return False

            async def emit(self, event: dict) -> None:
                pass

            def set_ui_context(self, ctx: Any) -> None:
                self.ui_ctx = ctx

            def bind_command_context(self, actions: Any) -> None:
                self.cc_actions = actions

            def on_error(self, listener: Any) -> Any:
                self.error_listener = listener
                return lambda: None

            def get_flag_values(self) -> dict:
                return {}

        runner = _Runner()
        session = _make_extension_session(
            tmp_path, extension_runner=runner
        )

        def _abort() -> None:
            abort_called.append("abort")

        def _shutdown() -> None:
            shutdown_called.append("shutdown")

        await session.bind_extensions(
            ExtensionBindings(
                ui_context=ui_ctx,
                command_context_actions=cc_actions,
                abort_handler=_abort,
                shutdown_handler=_shutdown,
                on_error=error_listener,
            )
        )
        # Bindings stored.
        assert runner.ui_ctx is ui_ctx
        assert runner.cc_actions is cc_actions
        assert runner.error_listener is error_listener
        assert session.extension_abort_handler is _abort
        assert session.extension_shutdown_handler is _shutdown


# ============================================================================
# AgentSessionExtensions: reload
# ============================================================================


class TestReload:
    @pytest.mark.asyncio
    async def test_emits_shutdown_then_rebuild(
        self, tmp_path: Path
    ) -> None:
        events: list = []

        class _Runner:
            def __init__(self) -> None:
                self.flag_values = {"kept": True}

            def has_handlers(self, t: str) -> bool:
                return t == "session_shutdown"

            async def emit(self, event: dict) -> None:
                events.append(event)

            def set_ui_context(self, _ctx: Any) -> None:
                pass

            def bind_command_context(self, _ctx: Any) -> None:
                pass

            def on_error(self, _listener: Any) -> Any:
                return lambda: None

            def get_flag_values(self) -> dict:
                return dict(self.flag_values)

        runner = _Runner()
        settings = FakeSettingsManager()
        sm = FakeSessionManager()
        loader = FakeResourceLoader()
        session = _make_extension_session(
            tmp_path,
            extension_runner=runner,
            settings=settings,
            session_manager=sm,
            resource_loader=loader,
        )
        # Add bindings so reload re-emits
        # the session_start event.
        session.extension_ui_context = _NS()
        await session.reload()
        # session_shutdown emitted.
        types = [e.get("type") for e in events]
        assert "session_shutdown" in types
        # The settings_manager was reloaded.
        assert settings.reload_called == 1
        # The resource loader was reloaded.
        assert loader.reloaded == 1
        # The new runner was created
        # (build_runtime replaced it).
        assert isinstance(
            session.current_extension_runner, ExtensionRunner
        )
        # The settings' steering / follow-up
        # modes were applied to the agent
        # (OpenClaw writes to
        # ``this.agent.steeringMode`` /
        # ``this.agent.followUpMode``).
        assert session.agent.steeringMode == "all"
        assert session.agent.followUpMode == "all"
        assert session.steering_mode == "all"
        assert session.follow_up_mode == "all"

    @pytest.mark.asyncio
    async def test_reload_without_bindings(self, tmp_path: Path) -> None:
        events: list = []

        class _Runner:
            def __init__(self) -> None:
                self.flag_values = {}

            def has_handlers(self, t: str) -> bool:
                return t == "session_shutdown"

            async def emit(self, event: dict) -> None:
                events.append(event)

            def set_ui_context(self, _ctx: Any) -> None:
                pass

            def bind_command_context(self, _ctx: Any) -> None:
                pass

            def on_error(self, _listener: Any) -> Any:
                return lambda: None

            def get_flag_values(self) -> dict:
                return {}

        runner = _Runner()
        settings = FakeSettingsManager()
        loader = FakeResourceLoader()
        session = _make_extension_session(
            tmp_path,
            extension_runner=runner,
            settings=settings,
            resource_loader=loader,
        )
        # No bindings.
        await session.reload()
        # session_shutdown emitted.
        types = [e.get("type") for e in events]
        assert "session_shutdown" in types
        # session_start NOT re-emitted (no
        # bindings present).
        assert "session_start" not in types


# ============================================================================
# AgentSessionTree: navigate_tree
# ============================================================================


class TestNavigateTree:
    @pytest.mark.asyncio
    async def test_no_op_at_same_leaf(self, tmp_path: Path) -> None:
        sm = FakeSessionManager()
        sm.leaf_id = "entry-1"
        session = _make_tree_session(
            tmp_path, session_manager=sm
        )
        # Stub the runner so it doesn't
        # crash on emit.
        session.current_extension_runner = _make_real_runner()
        result = await session.navigate_tree("entry-1")
        assert result["cancelled"] is False

    @pytest.mark.asyncio
    async def test_missing_entry(self, tmp_path: Path) -> None:
        sm = FakeSessionManager()
        sm.leaf_id = "leaf-old"
        sm.entries = []  # No entry.
        session = _make_tree_session(
            tmp_path, session_manager=sm
        )
        session.current_extension_runner = _make_real_runner()
        with pytest.raises(RuntimeError, match="not found"):
            await session.navigate_tree("missing-id")

    @pytest.mark.asyncio
    async def test_summarize_no_model(self, tmp_path: Path) -> None:
        sm = FakeSessionManager()
        sm.leaf_id = "leaf-old"
        sm.entries = [
            {"id": "target", "type": "message"},
        ]
        session = _make_tree_session(
            tmp_path, session_manager=sm
        )
        session.current_extension_runner = _make_real_runner()
        # summarize=True but no model →
        # error.
        with pytest.raises(RuntimeError, match="No model available"):
            await session.navigate_tree(
                "target", {"summarize": True}
            )

    @pytest.mark.asyncio
    async def test_user_message_target(self, tmp_path: Path) -> None:
        sm = FakeSessionManager()
        sm.leaf_id = "leaf-old"
        sm.entries = [
            {
                "id": "user-1",
                "type": "message",
                "parentId": "root",
                "message": {
                    "role": "user",
                    "content": "Hello there",
                },
            },
        ]
        events: list = []

        class _Runner:
            def __init__(self) -> None:
                self.handlers: dict = {}

            def has_handlers(self, t: str) -> bool:
                return bool(self.handlers.get(t))

            async def emit(self, event: dict) -> None:
                events.append(event)

            def set_ui_context(self, _ctx: Any) -> None:
                pass

            def bind_command_context(self, _ctx: Any) -> None:
                pass

            def on_error(self, _listener: Any) -> Any:
                return lambda: None

            def get_flag_values(self) -> dict:
                return {}

        runner = _Runner()
        session = _make_tree_session(
            tmp_path, session_manager=sm
        )
        session.current_extension_runner = runner
        result = await session.navigate_tree("user-1")
        # editor text is the user message.
        assert result["editorText"] == "Hello there"
        assert result["cancelled"] is False
        # Branch was called with parentId
        # ("root") — the new leaf.
        assert sm._branch_calls == ["root"]
        # session_tree event emitted.
        tree_events = [
            e for e in events if e.get("type") == "session_tree"
        ]
        assert len(tree_events) == 1

    @pytest.mark.asyncio
    async def test_custom_message_target(self, tmp_path: Path) -> None:
        sm = FakeSessionManager()
        sm.leaf_id = "leaf-old"
        sm.entries = [
            {
                "id": "custom-1",
                "type": "custom_message",
                "parentId": "root",
                "content": "Custom text",
            },
        ]
        session = _make_tree_session(
            tmp_path, session_manager=sm
        )
        session.current_extension_runner = _make_real_runner()
        result = await session.navigate_tree("custom-1")
        # editor text is the custom
        # message's content.
        assert result["editorText"] == "Custom text"
        assert result["cancelled"] is False
        # Branch was called with parentId.
        assert sm._branch_calls == ["root"]

    @pytest.mark.asyncio
    async def test_non_user_message_target(self, tmp_path: Path) -> None:
        sm = FakeSessionManager()
        sm.leaf_id = "leaf-old"
        sm.entries = [
            {
                "id": "assistant-1",
                "type": "message",
                "parentId": "user-1",
                "message": {
                    "role": "assistant",
                    "content": "hi",
                },
            },
        ]
        session = _make_tree_session(
            tmp_path, session_manager=sm
        )
        session.current_extension_runner = _make_real_runner()
        result = await session.navigate_tree("assistant-1")
        # Non-user → leaf = target_id.
        assert sm._branch_calls == ["assistant-1"]

    @pytest.mark.asyncio
    async def test_extension_cancel(self, tmp_path: Path) -> None:
        sm = FakeSessionManager()
        sm.leaf_id = "leaf-old"
        sm.entries = [
            {
                "id": "user-1",
                "type": "message",
                "parentId": "root",
                "message": {
                    "role": "user",
                    "content": "hi",
                },
            },
        ]

        class _Runner:
            def __init__(self) -> None:
                self.handlers: dict = {
                    "session_before_tree": [lambda _e: None]
                }

            def has_handlers(self, t: str) -> bool:
                return bool(self.handlers.get(t))

            async def emit(self, event: dict) -> None:
                if event.get("type") == "session_before_tree":
                    return {"cancel": True}
                return None

            def set_ui_context(self, _ctx: Any) -> None:
                pass

            def bind_command_context(self, _ctx: Any) -> None:
                pass

            def on_error(self, _listener: Any) -> Any:
                return lambda: None

            def get_flag_values(self) -> dict:
                return {}

        runner = _Runner()
        session = _make_tree_session(
            tmp_path, session_manager=sm
        )
        session.current_extension_runner = runner
        result = await session.navigate_tree("user-1")
        # Extension cancelled.
        assert result["cancelled"] is True
        # Branch NOT called.
        assert sm._branch_calls == []

    @pytest.mark.asyncio
    async def test_extension_label(self, tmp_path: Path) -> None:
        sm = FakeSessionManager()
        sm.leaf_id = "leaf-old"
        sm.entries = [
            {
                "id": "user-1",
                "type": "message",
                "parentId": "root",
                "message": {
                    "role": "user",
                    "content": "hi",
                },
            },
        ]
        session = _make_tree_session(
            tmp_path, session_manager=sm
        )
        session.current_extension_runner = _make_real_runner()
        await session.navigate_tree("user-1", {"label": "my-label"})
        # Label was appended.
        assert sm._label_appends == [("user-1", "my-label")]

    @pytest.mark.asyncio
    async def test_extension_override_instructions(
        self, tmp_path: Path) -> None:
        sm = FakeSessionManager()
        sm.leaf_id = "leaf-old"
        sm.entries = [
            {
                "id": "user-1",
                "type": "message",
                "parentId": "root",
                "message": {
                    "role": "user",
                    "content": "hi",
                },
            },
        ]
        # Extension that overrides label.
        class _Runner:
            def __init__(self) -> None:
                self.handlers: dict = {
                    "session_before_tree": [lambda _e: None]
                }

            def has_handlers(self, t: str) -> bool:
                return bool(self.handlers.get(t))

            async def emit(self, event: dict) -> None:
                if event.get("type") == "session_before_tree":
                    return {"label": "ext-label"}
                return None

            def set_ui_context(self, _ctx: Any) -> None:
                pass

            def bind_command_context(self, _ctx: Any) -> None:
                pass

            def on_error(self, _listener: Any) -> Any:
                return lambda: None

            def get_flag_values(self) -> dict:
                return {}

        runner = _Runner()
        session = _make_tree_session(
            tmp_path, session_manager=sm
        )
        session.current_extension_runner = runner
        await session.navigate_tree("user-1")
        # Extension label was used.
        assert sm._label_appends == [("user-1", "ext-label")]

    @pytest.mark.asyncio
    async def test_update_agent_state_messages(
        self, tmp_path: Path
    ) -> None:
        sm = FakeSessionManager()
        sm.leaf_id = "leaf-old"
        sm.entries = [
            {
                "id": "user-1",
                "type": "message",
                "parentId": "root",
                "message": {
                    "role": "user",
                    "content": "hi",
                },
            },
        ]
        # build_session_context returns
        # a fresh messages list.
        sm.built_ctx = {"messages": [{"role": "user", "content": "hi"}]}
        session = _make_tree_session(
            tmp_path, session_manager=sm
        )
        session.current_extension_runner = _make_real_runner()
        await session.navigate_tree("user-1")
        # agent.state.messages updated to
        # the session context's messages.
        assert session.agent.state.messages == [
            {"role": "user", "content": "hi"}
        ]


# ============================================================================
# AgentSessionTree: get_user_messages_for_forking
# ============================================================================


class TestGetUserMessagesForForking:
    def test_empty(self, tmp_path: Path) -> None:
        sm = FakeSessionManager()
        session = _make_tree_session(
            tmp_path, session_manager=sm
        )
        assert session.get_user_messages_for_forking() == []

    def test_filters_user(self, tmp_path: Path) -> None:
        sm = FakeSessionManager()
        sm.entries = [
            {
                "id": "u1",
                "type": "message",
                "message": {"role": "user", "content": "hi"},
            },
            {
                "id": "a1",
                "type": "message",
                "message": {"role": "assistant", "content": "ok"},
            },
            {
                "id": "u2",
                "type": "message",
                "message": {
                    "role": "user",
                    "content": "another",
                },
            },
        ]
        session = _make_tree_session(
            tmp_path, session_manager=sm
        )
        result = session.get_user_messages_for_forking()
        assert len(result) == 2
        assert result[0]["entryId"] == "u1"
        assert result[0]["text"] == "hi"
        assert result[1]["entryId"] == "u2"
        assert result[1]["text"] == "another"

    def test_skips_non_message(self, tmp_path: Path) -> None:
        sm = FakeSessionManager()
        sm.entries = [
            {"id": "c1", "type": "custom_message", "content": "x"},
            {
                "id": "u1",
                "type": "message",
                "message": {"role": "user", "content": "hi"},
            },
        ]
        session = _make_tree_session(
            tmp_path, session_manager=sm
        )
        result = session.get_user_messages_for_forking()
        # Only the user message.
        assert len(result) == 1
        assert result[0]["entryId"] == "u1"

    def test_skips_empty_text(self, tmp_path: Path) -> None:
        sm = FakeSessionManager()
        sm.entries = [
            {
                "id": "u1",
                "type": "message",
                "message": {"role": "user", "content": ""},
            },
            {
                "id": "u2",
                "type": "message",
                "message": {"role": "user", "content": "hi"},
            },
        ]
        session = _make_tree_session(
            tmp_path, session_manager=sm
        )
        result = session.get_user_messages_for_forking()
        assert len(result) == 1
        assert result[0]["entryId"] == "u2"


# ============================================================================
# AgentSessionTree: create_replaced_session_context
# ============================================================================


class TestCreateReplacedSessionContext:
    def test_returns_runner_command_context_with_overrides(
        self, tmp_path: Path
    ) -> None:
        # Real ExtensionRunner has
        # ``create_command_context``.
        runner = _make_real_runner()
        session = _make_tree_session(
            tmp_path, extension_runner=runner
        )
        ctx = session.create_replaced_session_context()
        # The Python port returns a
        # subclass of the
        # ``_CommandContextView`` that
        # overrides ``sendMessage`` +
        # ``sendUserMessage``.
        assert hasattr(ctx, "sendMessage")
        assert hasattr(ctx, "sendUserMessage")
        # Calling the overrides returns a
        # coroutine (they delegate to
        # ``send_custom_message`` /
        # ``send_user_message``).
        coro1 = ctx.sendMessage({"x": 1}, {"y": 2})
        assert asyncio.iscoroutine(coro1)
        coro1.close()
        coro2 = ctx.sendUserMessage("hello", {"z": 3})
        assert asyncio.iscoroutine(coro2)
        coro2.close()
        # Inherits the command-context
        # methods (e.g. ``newSession``).
        assert hasattr(ctx, "newSession")
        assert hasattr(ctx, "fork")
        assert hasattr(ctx, "navigateTree")


# ============================================================================
# AgentSessionTree: has_extension_handlers + extension_runner property
# ============================================================================


class TestHasExtensionHandlers:
    def test_delegates_to_runner(self, tmp_path: Path) -> None:
        class _Runner:
            def __init__(self) -> None:
                self.calls: list = []

            def has_handlers(self, t: str) -> bool:
                self.calls.append(t)
                return t == "session_start"

        runner = _Runner()
        session = _make_tree_session(
            tmp_path, extension_runner=runner
        )
        assert session.has_extension_handlers("session_start") is True
        assert session.has_extension_handlers("other") is False
        assert runner.calls == ["session_start", "other"]


class TestExtensionRunnerProperty:
    def test_returns_current_runner(self, tmp_path: Path) -> None:
        runner = _make_real_runner()
        session = _make_tree_session(
            tmp_path, extension_runner=runner
        )
        assert session.extension_runner is runner


# ============================================================================
# Re-exports
# ============================================================================


class TestReExports:
    def test_branch_summary_entry_alias(self) -> None:
        # BranchSummaryEntry is exposed as
        # a dict alias.
        assert BranchSummaryEntry is dict
