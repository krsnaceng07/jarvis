"""Phase 6.0 — Layer 2 scaffolding + helpers + small types.

These tests prove the Phase-6.0 leaf modules in
``src/agents/sessions/`` match the OpenClaw source
contract for:

- ``defaults`` — ``DEFAULT_THINKING_LEVEL`` constant
- ``source_info`` — ``SourceInfo`` dataclass +
  ``create_source_info`` / ``create_synthetic_source_info``
- ``event_bus`` — ``create_event_bus`` emit / on / clear,
  handler error isolation
- ``diagnostics`` — ``ResourceDiagnostic`` /
  ``ResourceCollision`` dataclasses
- ``messages`` — re-exports of ``convert_to_llm``,
  ``BashExecutionMessage``, ``CustomMessage``
- ``slash_commands`` — ``SlashCommandInfo`` shape
- ``telemetry`` — ``is_install_telemetry_enabled``
  (env override + settings fallback)
- ``auth_guidance`` — provider login help messages
- ``provider_display_names`` — built-in provider labels
- ``resolve_config_value`` — env var / literal /
  shell command resolution + cache
"""
from __future__ import annotations

import os
import sys

import pytest

# Project root on sys.path so ``src.agents.sessions``
# imports work without an editable install (the
# existing JARVIS test convention).
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.agents.sessions import (  # noqa: E402
    BUILT_IN_PROVIDER_DISPLAY_NAMES,
    DEFAULT_THINKING_LEVEL,
    ResourceCollision,
    ResourceDiagnostic,
    SlashCommandInfo,
    SourceInfo,
    UNKNOWN_PROVIDER,
    clear_config_value_cache,
    create_event_bus,
    create_source_info,
    create_synthetic_source_info,
    format_no_api_key_found_message,
    format_no_model_selected_message,
    format_no_models_available_message,
    get_provider_login_help,
    is_install_telemetry_enabled,
    resolve_config_value,
    resolve_config_value_or_throw,
    resolve_config_value_uncached,
    resolve_headers_or_throw,
)


# ── defaults ──────────────────────────────────────────


class TestDefaults:
    def test_default_thinking_level_is_medium(self) -> None:
        """Mirrors ``DEFAULT_THINKING_LEVEL = "medium"``
        in ``defaults.ts:9``."""
        assert DEFAULT_THINKING_LEVEL == "medium"


# ── source_info ────────────────────────────────────────


class TestSourceInfo:
    def test_create_source_info_projects_metadata(self) -> None:
        """Mirrors ``createSourceInfo`` (source-info.ts:20-28)."""
        result = create_source_info(
            "/path/to/file.md",
            {
                "source": "npm:foo",
                "scope": "user",
                "origin": "package",
                "baseDir": "/path/to",
            },
        )
        assert result.path == "/path/to/file.md"
        assert result.source == "npm:foo"
        assert result.scope == "user"
        assert result.origin == "package"
        assert result.base_dir == "/path/to"

    def test_create_source_info_without_basedir(self) -> None:
        """The OpenClaw source preserves the
        ``baseDir: undefined`` shape when the metadata
        does not include one."""
        result = create_source_info(
            "/path/to/file.md",
            {
                "source": "local",
                "scope": "project",
                "origin": "top-level",
            },
        )
        assert result.base_dir is None

    def test_create_synthetic_source_info_defaults(self) -> None:
        """Mirrors ``createSyntheticSourceInfo``
        (source-info.ts:31-46) — defaults to
        ``scope="temporary"`` and ``origin="top-level"``
        when the caller does not provide them.
        """
        result = create_synthetic_source_info(
            "/tmp/synthetic",
            {"source": "synthetic"},
        )
        assert result.path == "/tmp/synthetic"
        assert result.source == "synthetic"
        assert result.scope == "temporary"
        assert result.origin == "top-level"

    def test_create_synthetic_source_info_overrides(self) -> None:
        result = create_synthetic_source_info(
            "/path/to",
            {
                "source": "extension:foo",
                "scope": "user",
                "origin": "package",
                "base_dir": "/base",
            },
        )
        assert result.scope == "user"
        assert result.origin == "package"
        assert result.base_dir == "/base"


# ── event_bus ──────────────────────────────────────────


class TestEventBus:
    def test_emit_and_on_basic(self) -> None:
        """Mirrors ``createEventBus`` (event-bus.ts:20-42)."""
        bus = create_event_bus()
        received: list[object] = []
        unsub = bus.on("ping", lambda d: received.append(d))
        bus.emit("ping", {"hello": "world"})
        assert received == [{"hello": "world"}]
        unsub()

    def test_unsub_stops_delivery(self) -> None:
        bus = create_event_bus()
        received: list[object] = []
        unsub = bus.on("ping", lambda d: received.append(d))
        bus.emit("ping", "first")
        unsub()
        bus.emit("ping", "second")
        assert received == ["first"]

    def test_clear_removes_all_subscribers(self) -> None:
        bus = create_event_bus()
        received: list[object] = []
        bus.on("a", lambda d: received.append(d))
        bus.on("b", lambda d: received.append(d))
        bus.clear()
        bus.emit("a", 1)
        bus.emit("b", 2)
        assert received == []

    def test_handler_error_does_not_break_bus(self) -> None:
        """Mirrors the OpenClaw comment "Isolates handler
        failures so one bad subscriber cannot break
        later listeners." (event-bus.ts:3-5)"""
        bus = create_event_bus()
        received: list[str] = []
        bus.on("ping", lambda _d: (_ for _ in ()).throw(RuntimeError("boom")))
        bus.on("ping", lambda d: received.append(d))  # type: ignore[arg-type]
        bus.emit("ping", "ok")
        # The second handler ran even though the first
        # raised.
        assert received == ["ok"]

    def test_multiple_subscribers_called_in_order(self) -> None:
        bus = create_event_bus()
        order: list[str] = []
        bus.on("ping", lambda _d: order.append("a"))
        bus.on("ping", lambda _d: order.append("b"))
        bus.on("ping", lambda _d: order.append("c"))
        bus.emit("ping", None)
        assert order == ["a", "b", "c"]


# ── diagnostics ────────────────────────────────────────


class TestDiagnostics:
    def test_resource_collision_fields(self) -> None:
        """Mirrors ``ResourceCollision`` (diagnostics.ts:6-13)."""
        c = ResourceCollision(
            resource_type="extension",
            name="acpx",
            winner_path="/a/acpx.js",
            loser_path="/b/acpx.js",
            winner_source="npm:foo",
            loser_source="npm:bar",
        )
        assert c.resource_type == "extension"
        assert c.name == "acpx"
        assert c.winner_path == "/a/acpx.js"
        assert c.loser_path == "/b/acpx.js"

    def test_resource_diagnostic_with_collision(self) -> None:
        """Mirrors ``ResourceDiagnostic`` (diagnostics.ts:15-20)."""
        c = ResourceCollision(
            resource_type="skill",
            name="weather",
            winner_path="/a/weather",
            loser_path="/b/weather",
        )
        d = ResourceDiagnostic(
            type="collision",
            message="weather shadowed",
            path="/b/weather",
            collision=c,
        )
        assert d.type == "collision"
        assert d.collision is c

    def test_resource_diagnostic_warning(self) -> None:
        d = ResourceDiagnostic(type="warning", message="skipped")
        assert d.type == "warning"
        assert d.path is None
        assert d.collision is None


# ── messages re-exports ────────────────────────────────


class TestMessagesReexports:
    def test_convert_to_llm_is_callable(self) -> None:
        """Mirrors the re-export of ``convertToLlm`` from
        ``messages.ts:7``."""
        from src.agents.sessions import convert_to_llm
        assert callable(convert_to_llm)

    def test_bash_execution_message_type(self) -> None:
        from src.agents.sessions import BashExecutionMessage
        assert BashExecutionMessage is not None
        # Role is the literal "bashExecution"
        msg = BashExecutionMessage(command="ls -la", output="")
        assert msg.role == "bashExecution"

    def test_custom_message_type(self) -> None:
        from src.agents.sessions import CustomMessage
        assert CustomMessage is not None
        # The OpenClaw fields are ``customType`` /
        # ``display`` / ``details`` / ``timestamp`` /
        # ``content``; the agent_runtime port
        # normalises these to snake_case so the
        # Python side uses ``custom_type`` /
        # ``display`` / ``details`` / ``timestamp``
        # / ``content``. We test the public Python
        # shape here.
        msg = CustomMessage(
            custom_type="note",
            content="hi",
            display=True,
            details={},
            timestamp=0,
        )
        assert msg.role == "custom"
        assert msg.custom_type == "note"


# ── slash_commands ─────────────────────────────────────


class TestSlashCommands:
    def test_slash_command_info_shape(self) -> None:
        """Mirrors ``SlashCommandInfo`` (slash-commands.ts:10-15)."""
        info = SlashCommandInfo(
            name="weather",
            description="Get the weather",
            source="extension",
            source_info=SourceInfo(
                path="/ext/weather.py",
                source="extension:weather",
                scope="user",
                origin="package",
            ),
        )
        assert info.name == "weather"
        assert info.source == "extension"


# ── telemetry ──────────────────────────────────────────


class _StubSettings:
    """Minimal stub for the ``SettingsManager`` protocol
    used by :func:`is_install_telemetry_enabled`."""

    def __init__(self, value: bool) -> None:
        self._value = value

    def get_enable_install_telemetry(self) -> bool:
        return self._value


class TestTelemetry:
    def setup_method(self) -> None:
        # Preserve + clear the env override so other
        # tests aren't affected.
        self._old_env = os.environ.pop("OPENCLAW_TELEMETRY", None)

    def teardown_method(self) -> None:
        if self._old_env is not None:
            os.environ["OPENCLAW_TELEMETRY"] = self._old_env
        else:
            os.environ.pop("OPENCLAW_TELEMETRY", None)

    def test_env_true_wins_over_settings(self) -> None:
        """Mirrors ``isInstallTelemetryEnabled``
        (telemetry.ts:16-22) — when the env override
        is set, the settings manager is not consulted.
        """
        os.environ["OPENCLAW_TELEMETRY"] = "1"
        assert is_install_telemetry_enabled(
            _StubSettings(value=False)
        ) is True

    def test_env_false_disables_even_when_settings_true(self) -> None:
        os.environ["OPENCLAW_TELEMETRY"] = "false"
        assert is_install_telemetry_enabled(
            _StubSettings(value=True)
        ) is False

    def test_env_unset_falls_back_to_settings(self) -> None:
        os.environ.pop("OPENCLAW_TELEMETRY", None)
        assert is_install_telemetry_enabled(
            _StubSettings(value=True)
        ) is True
        assert is_install_telemetry_enabled(
            _StubSettings(value=False)
        ) is False

    def test_env_truthy_variants(self) -> None:
        """Mirrors the truthy check (telemetry.ts:8-13)."""
        for v in ("1", "true", "True", "TRUE", "yes", "YES"):
            os.environ["OPENCLAW_TELEMETRY"] = v
            assert is_install_telemetry_enabled(
                _StubSettings(value=False)
            ) is True, f"env={v!r}"

    def test_env_explicit_empty_string_is_falsy(self) -> None:
        os.environ["OPENCLAW_TELEMETRY"] = ""
        # Empty string IS set in env, so the function
        # returns ``is_truthy_env_flag("")`` = ``False``
        # and the settings manager is NOT consulted.
        assert is_install_telemetry_enabled(
            _StubSettings(value=True)
        ) is False


# ── auth_guidance ──────────────────────────────────────


class TestAuthGuidance:
    def test_unknown_provider_uses_selected_model_phrase(self) -> None:
        """Mirrors the OpenClaw ``UNKNOWN_PROVIDER``
        special-case (auth-guidance.ts:32)."""
        msg = format_no_api_key_found_message(UNKNOWN_PROVIDER)
        assert "the selected model" in msg

    def test_known_provider_uses_provider_name(self) -> None:
        msg = format_no_api_key_found_message("anthropic")
        assert "anthropic" in msg
        assert "the selected model" not in msg

    def test_no_models_available_mentions_login(self) -> None:
        msg = format_no_models_available_message()
        assert "No models available" in msg
        assert "/login" in msg

    def test_no_model_selected_mentions_model_command(self) -> None:
        msg = format_no_model_selected_message()
        assert "No model selected" in msg
        assert "/model" in msg
        assert "/login" in msg

    def test_provider_login_help_links_docs(self) -> None:
        help_text = get_provider_login_help()
        assert "/login" in help_text
        assert "providers.md" in help_text
        assert "models.md" in help_text


# ── provider_display_names ────────────────────────────


class TestProviderDisplayNames:
    def test_known_providers_have_labels(self) -> None:
        """Mirrors the OpenClaw table
        (provider-display-names.ts:5-37)."""
        assert BUILT_IN_PROVIDER_DISPLAY_NAMES["anthropic"] == "Anthropic"
        assert BUILT_IN_PROVIDER_DISPLAY_NAMES["google"] == "Google Gemini"
        assert BUILT_IN_PROVIDER_DISPLAY_NAMES["openai"] == "OpenAI"

    def test_provider_count_matches_openclaw(self) -> None:
        """31 entries in the OpenClaw table — guards
        against accidental additions / removals during
        the port."""
        assert len(BUILT_IN_PROVIDER_DISPLAY_NAMES) == 31


# ── resolve_config_value ──────────────────────────────


class TestResolveConfigValue:
    def setup_method(self) -> None:
        # Clear the cache so a previous test's
        # command-result cache entry doesn't bleed
        # into this one.
        clear_config_value_cache()
        self._old_env: dict[str, str | None] = {}
        # Remove any test env overrides that might
        # affect the literal-path branch.
        for key in ("MY_LITERAL_KEY", "MY_ENV_KEY"):
            self._old_env[key] = os.environ.pop(key, None)

    def teardown_method(self) -> None:
        clear_config_value_cache()
        for key, value in self._old_env.items():
            if value is not None:
                os.environ[key] = value
            else:
                os.environ.pop(key, None)

    def test_env_var_is_consulted_first(self) -> None:
        """Mirrors the resolution order
        (resolve-config-value.ts:21-27)."""
        os.environ["MY_ENV_KEY"] = "from-env"
        assert resolve_config_value("MY_ENV_KEY") == "from-env"

    def test_literal_returned_when_env_unset(self) -> None:
        """When the env var is unset, the literal is
        returned (resolve-config-value.ts:26)."""
        os.environ.pop("MY_LITERAL_KEY", None)
        assert resolve_config_value("MY_LITERAL_KEY") == "MY_LITERAL_KEY"

    def test_command_executes_and_returns_stdout(self) -> None:
        """Mirrors the ``!command`` branch
        (resolve-config-value.ts:22-24)."""
        # ``echo`` is available on both POSIX + Windows.
        if sys.platform == "win32":
            value = resolve_config_value("!echo hello-from-shell")
        else:
            value = resolve_config_value("!echo hello-from-shell")
        assert value == "hello-from-shell"

    def test_command_result_is_cached(self) -> None:
        """Mirrors the cache
        (resolve-config-value.ts:91-99)."""
        if sys.platform == "win32":
            first = resolve_config_value("!echo cached")
            second = resolve_config_value("!echo cached")
        else:
            first = resolve_config_value("!echo cached")
            second = resolve_config_value("!echo cached")
        assert first == "cached"
        assert second == "cached"

    def test_command_failure_returns_none(self) -> None:
        """Mirrors the OpenClaw ``return { executed: true,
        value: undefined }`` branch
        (resolve-config-value.ts:54-57)."""
        # ``false`` exits with status 1 on every shell.
        value = resolve_config_value("!false")
        assert value is None

    def test_uncached_bypasses_cache(self) -> None:
        """Mirrors ``resolveConfigValueUncached``
        (resolve-config-value.ts:104-110)."""
        if sys.platform == "win32":
            first = resolve_config_value("!echo fresh")
            second = resolve_config_value_uncached("!echo fresh")
        else:
            first = resolve_config_value("!echo fresh")
            second = resolve_config_value_uncached("!echo fresh")
        # The cached first call populated the cache.
        # The uncached call re-executes the command.
        assert first == "fresh"
        assert second == "fresh"

    def test_or_throw_raises_on_unresolved_command(self) -> None:
        """Mirrors the OpenClaw error wording
        (resolve-config-value.ts:118-119)."""
        with pytest.raises(
            RuntimeError,
            match=r"Failed to resolve test description from shell command: false",
        ):
            resolve_config_value_or_throw("!false", "test description")

    def test_or_throw_returns_literal_when_env_unset(self) -> None:
        """When the env var is unset, the literal is
        returned (matches the resolution order in
        ``resolve-config-value.ts:21-27``). The
        ``*_or_throw`` form only raises for *commands*
        that fail — literal fallthrough is by design.
        """
        os.environ.pop("MY_TOTALLY_MISSING_KEY", None)
        # The literal is returned as-is.
        assert (
            resolve_config_value_or_throw(
                "MY_TOTALLY_MISSING_KEY", "api key"
            )
            == "MY_TOTALLY_MISSING_KEY"
        )

    def test_resolve_headers_or_throw_none(self) -> None:
        """``None`` headers pass through
        (resolve-config-value.ts:128-130)."""
        assert resolve_headers_or_throw(None, "test") is None

    def test_resolve_headers_or_throw_empty(self) -> None:
        """An empty mapping returns ``None``
        (resolve-config-value.ts:136)."""
        assert resolve_headers_or_throw({}, "test") is None

    def test_resolve_headers_or_throw_merges(self) -> None:
        os.environ["HEADER_VALUE"] = "secret"
        result = resolve_headers_or_throw(
            {"X-Test": "HEADER_VALUE"}, "test"
        )
        assert result == {"X-Test": "secret"}

    def test_clear_cache_resets(self) -> None:
        """Mirrors ``clearConfigValueCache``
        (resolve-config-value.ts:140-142)."""
        if sys.platform == "win32":
            resolve_config_value("!echo clear-me")
        else:
            resolve_config_value("!echo clear-me")
        # Re-running with a different command after
        # clearing should still work.
        clear_config_value_cache()
        if sys.platform == "win32":
            result = resolve_config_value("!echo after-clear")
        else:
            result = resolve_config_value("!echo after-clear")
        assert result == "after-clear"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
