"""Phase 6.8b — Layer 2 settings manager typed setters.

Tests for every typed ``getX`` / ``setX``
method on
:class:`jarvis.agents.sessions.settings_manager.SettingsManager`.

- Last changelog version
- Default provider / model
- Steering mode + follow-up mode
- Theme
- Default thinking level
- Transport
- Compaction (enabled / reserve tokens / keep
  recent tokens / full settings)
- Branch summary (reserve tokens + skip prompt)
- Retry (enabled / settings / provider retry)
- HTTP idle timeout
- Hide thinking block
- Shell path / quiet startup / shell command
  prefix / npm command
- Collapse changelog / install telemetry
- Packages (global + project)
- Extension / skill / prompt / theme paths
  (global + project)
- Enable skill commands
- Thinking budgets
- Show images / image width / clear on
  shrink / show terminal progress
- Image auto-resize / block images
- Enabled models
- Double escape action / tree filter mode
- Show hardware cursor
- Editor padding X / autocomplete max visible
- Code block indent
- Warnings
"""
from __future__ import annotations

import json
import os
import sys

import pytest

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.agents.sessions import (  # noqa: E402
    SettingsManager,
)


# ── lastChangelogVersion ─────────────────────────────────────


class TestLastChangelogVersion:
    def test_get_set(self) -> None:
        sm = SettingsManager.in_memory()
        assert sm.get_last_changelog_version() is None
        sm.set_last_changelog_version("1.2.3")
        assert sm.get_last_changelog_version() == "1.2.3"


# ── Default provider / model ─────────────────────────────────


class TestDefaultProviderModel:
    def test_get_set(self) -> None:
        sm = SettingsManager.in_memory()
        assert sm.get_default_provider() is None
        assert sm.get_default_model() is None
        sm.set_default_provider("anthropic")
        sm.set_default_model("claude-3-5-sonnet")
        assert sm.get_default_provider() == "anthropic"
        assert sm.get_default_model() == "claude-3-5-sonnet"

    def test_set_both(self) -> None:
        sm = SettingsManager.in_memory()
        sm.set_default_model_and_provider("openai", "gpt-4")
        assert sm.get_default_provider() == "openai"
        assert sm.get_default_model() == "gpt-4"


# ── Steering mode + follow-up mode ───────────────────────────


class TestSteeringFollowUpMode:
    def test_steering_mode_default(self) -> None:
        sm = SettingsManager.in_memory()
        assert sm.get_steering_mode() == "one-at-a-time"

    def test_steering_mode_set(self) -> None:
        sm = SettingsManager.in_memory()
        sm.set_steering_mode("all")
        assert sm.get_steering_mode() == "all"

    def test_follow_up_mode_default(self) -> None:
        sm = SettingsManager.in_memory()
        assert sm.get_follow_up_mode() == "one-at-a-time"

    def test_follow_up_mode_set(self) -> None:
        sm = SettingsManager.in_memory()
        sm.set_follow_up_mode("all")
        assert sm.get_follow_up_mode() == "all"


# ── Theme ────────────────────────────────────────────────────


class TestTheme:
    def test_get_set(self) -> None:
        sm = SettingsManager.in_memory()
        assert sm.get_theme() is None
        sm.set_theme("dark")
        assert sm.get_theme() == "dark"


# ── Default thinking level ──────────────────────────────────


class TestDefaultThinkingLevel:
    def test_get_set(self) -> None:
        sm = SettingsManager.in_memory()
        assert sm.get_default_thinking_level() is None
        sm.set_default_thinking_level("high")
        assert sm.get_default_thinking_level() == "high"


# ── Transport ──────────────────────────────────────────────


class TestTransport:
    def test_get_default(self) -> None:
        sm = SettingsManager.in_memory()
        assert sm.get_transport() == "auto"

    def test_set(self) -> None:
        sm = SettingsManager.in_memory()
        sm.set_transport("websocket")
        assert sm.get_transport() == "websocket"


# ── Compaction ──────────────────────────────────────────────


class TestCompaction:
    def test_get_default_enabled(self) -> None:
        sm = SettingsManager.in_memory()
        assert sm.get_compaction_enabled() is True

    def test_set_enabled(self) -> None:
        sm = SettingsManager.in_memory()
        sm.set_compaction_enabled(False)
        assert sm.get_compaction_enabled() is False

    def test_reserve_tokens_default(self) -> None:
        sm = SettingsManager.in_memory()
        assert sm.get_compaction_reserve_tokens() == 16384

    def test_keep_recent_tokens_default(self) -> None:
        sm = SettingsManager.in_memory()
        assert sm.get_compaction_keep_recent_tokens() == 20000

    def test_get_settings(self) -> None:
        sm = SettingsManager.in_memory()
        settings = sm.get_compaction_settings()
        assert settings["enabled"] is True
        assert settings["reserveTokens"] == 16384
        assert settings["keepRecentTokens"] == 20000


# ── Branch summary ─────────────────────────────────────────


class TestBranchSummary:
    def test_defaults(self) -> None:
        sm = SettingsManager.in_memory()
        settings = sm.get_branch_summary_settings()
        assert settings["reserveTokens"] == 16384
        assert settings["skipPrompt"] is False

    def test_skip_prompt(self) -> None:
        sm = SettingsManager.in_memory()
        assert sm.get_branch_summary_skip_prompt() is False


# ── Retry ───────────────────────────────────────────────────


class TestRetry:
    def test_get_enabled_default(self) -> None:
        sm = SettingsManager.in_memory()
        assert sm.get_retry_enabled() is True

    def test_set_enabled(self) -> None:
        sm = SettingsManager.in_memory()
        sm.set_retry_enabled(False)
        assert sm.get_retry_enabled() is False

    def test_get_settings(self) -> None:
        sm = SettingsManager.in_memory()
        settings = sm.get_retry_settings()
        assert settings["enabled"] is True
        assert settings["maxRetries"] == 3
        assert settings["baseDelayMs"] == 2000

    def test_provider_retry_settings(self) -> None:
        sm = SettingsManager.in_memory()
        settings = sm.get_provider_retry_settings()
        assert settings["maxRetryDelayMs"] == 60000
        assert settings["timeoutMs"] is None
        assert settings["maxRetries"] is None


# ── HTTP idle timeout ───────────────────────────────────────


class TestHttpIdleTimeout:
    def test_default(self) -> None:
        sm = SettingsManager.in_memory()
        # The default is the LLM-side default
        # (300s).
        from src.agents.sessions import DEFAULT_HTTP_IDLE_TIMEOUT_MS
        assert sm.get_http_idle_timeout_ms() == DEFAULT_HTTP_IDLE_TIMEOUT_MS

    def test_set(self) -> None:
        sm = SettingsManager.in_memory()
        sm.set_http_idle_timeout_ms(30000)
        assert sm.get_http_idle_timeout_ms() == 30000

    def test_set_invalid_raises(self) -> None:
        sm = SettingsManager.in_memory()
        with pytest.raises(RuntimeError, match="Invalid"):
            sm.set_http_idle_timeout_ms(-1)


# ── Hide thinking block ────────────────────────────────────


class TestHideThinkingBlock:
    def test_get_set(self) -> None:
        sm = SettingsManager.in_memory()
        assert sm.get_hide_thinking_block() is False
        sm.set_hide_thinking_block(True)
        assert sm.get_hide_thinking_block() is True


# ── Shell path + quiet startup + command prefix ─────────────


class TestShell:
    def test_shell_path(self) -> None:
        sm = SettingsManager.in_memory()
        assert sm.get_shell_path() is None
        sm.set_shell_path("/bin/bash")
        assert sm.get_shell_path() == "/bin/bash"

    def test_quiet_startup(self) -> None:
        sm = SettingsManager.in_memory()
        assert sm.get_quiet_startup() is False
        sm.set_quiet_startup(True)
        assert sm.get_quiet_startup() is True

    def test_shell_command_prefix(self) -> None:
        sm = SettingsManager.in_memory()
        assert sm.get_shell_command_prefix() is None
        sm.set_shell_command_prefix("shopt -s expand_aliases")
        assert (
            sm.get_shell_command_prefix() == "shopt -s expand_aliases"
        )


# ── NPM command ─────────────────────────────────────────────


class TestNpmCommand:
    def test_get_set(self) -> None:
        sm = SettingsManager.in_memory()
        assert sm.get_npm_command() is None
        sm.set_npm_command(["mise", "exec", "node@20", "--", "npm"])
        assert sm.get_npm_command() == [
            "mise",
            "exec",
            "node@20",
            "--",
            "npm",
        ]


# ── Collapse changelog + install telemetry ──────────────────


class TestChangelogAndTelemetry:
    def test_collapse_changelog(self) -> None:
        sm = SettingsManager.in_memory()
        assert sm.get_collapse_changelog() is False
        sm.set_collapse_changelog(True)
        assert sm.get_collapse_changelog() is True

    def test_install_telemetry_default(self) -> None:
        sm = SettingsManager.in_memory()
        assert sm.get_enable_install_telemetry() is True

    def test_install_telemetry_set(self) -> None:
        sm = SettingsManager.in_memory()
        sm.set_enable_install_telemetry(False)
        assert sm.get_enable_install_telemetry() is False


# ── Packages / extension / skill / prompt / theme paths ────


class TestResourcePaths:
    def test_packages_default(self) -> None:
        sm = SettingsManager.in_memory()
        assert sm.get_packages() == []

    def test_packages_set(self) -> None:
        sm = SettingsManager.in_memory()
        sm.set_packages(["npm:foo", "git:bar"])
        assert sm.get_packages() == ["npm:foo", "git:bar"]

    def test_extension_paths(self) -> None:
        sm = SettingsManager.in_memory()
        sm.set_extension_paths(["/path/a", "/path/b"])
        assert sm.get_extension_paths() == ["/path/a", "/path/b"]

    def test_skill_paths(self) -> None:
        sm = SettingsManager.in_memory()
        sm.set_skill_paths(["/skills/x"])
        assert sm.get_skill_paths() == ["/skills/x"]

    def test_prompt_template_paths(self) -> None:
        sm = SettingsManager.in_memory()
        sm.set_prompt_template_paths(["/prompts/x"])
        assert sm.get_prompt_template_paths() == ["/prompts/x"]

    def test_theme_paths(self) -> None:
        sm = SettingsManager.in_memory()
        sm.set_theme_paths(["/themes/x"])
        assert sm.get_theme_paths() == ["/themes/x"]


# ── Project-scope path setters ──────────────────────────────


class TestProjectPaths:
    def test_project_extension_paths(self) -> None:
        sm = SettingsManager.in_memory()
        sm.set_project_extension_paths(["/proj/ext"])
        assert sm.get_extension_paths() == ["/proj/ext"]

    def test_project_skill_paths(self) -> None:
        sm = SettingsManager.in_memory()
        sm.set_project_skill_paths(["/proj/skills"])
        assert sm.get_skill_paths() == ["/proj/skills"]


# ── Enable skill commands ───────────────────────────────────


class TestEnableSkillCommands:
    def test_default(self) -> None:
        sm = SettingsManager.in_memory()
        assert sm.get_enable_skill_commands() is True

    def test_set(self) -> None:
        sm = SettingsManager.in_memory()
        sm.set_enable_skill_commands(False)
        assert sm.get_enable_skill_commands() is False


# ── Thinking budgets ────────────────────────────────────────


class TestThinkingBudgets:
    def test_get_none(self) -> None:
        sm = SettingsManager.in_memory()
        assert sm.get_thinking_budgets() is None

    def test_get_set(self) -> None:
        sm = SettingsManager.in_memory()
        # The OpenClaw source has no
        # ``setThinkingBudgets`` setter; the
        # get-only accessor reads the merged
        # ``this.settings.thinkingBudgets``.
        # Write directly to ``global_settings``
        # and recompute the merged view (the
        # same path the typed setters trigger
        # via ``save()``).
        sm.global_settings["thinkingBudgets"] = {
            "low": 100,
            "medium": 200,
        }
        sm._recompute_settings()
        assert sm.get_thinking_budgets() == {"low": 100, "medium": 200}


# ── Show images / image width / clear on shrink / show terminal progress ─


class TestTerminal:
    def test_show_images_default(self) -> None:
        sm = SettingsManager.in_memory()
        assert sm.get_show_images() is True

    def test_show_images_set(self) -> None:
        sm = SettingsManager.in_memory()
        sm.set_show_images(False)
        assert sm.get_show_images() is False

    def test_image_width_cells_default(self) -> None:
        sm = SettingsManager.in_memory()
        assert sm.get_image_width_cells() == 60

    def test_image_width_cells_set(self) -> None:
        sm = SettingsManager.in_memory()
        sm.set_image_width_cells(80)
        assert sm.get_image_width_cells() == 80

    def test_clear_on_shrink_default(self) -> None:
        sm = SettingsManager.in_memory()
        assert sm.get_clear_on_shrink() is False

    def test_clear_on_shrink_set(self) -> None:
        sm = SettingsManager.in_memory()
        sm.set_clear_on_shrink(True)
        assert sm.get_clear_on_shrink() is True

    def test_show_terminal_progress_default(self) -> None:
        sm = SettingsManager.in_memory()
        assert sm.get_show_terminal_progress() is False

    def test_show_terminal_progress_set(self) -> None:
        sm = SettingsManager.in_memory()
        sm.set_show_terminal_progress(True)
        assert sm.get_show_terminal_progress() is True


# ── Image auto-resize / block images ────────────────────────


class TestImageSettings:
    def test_image_auto_resize_default(self) -> None:
        sm = SettingsManager.in_memory()
        assert sm.get_image_auto_resize() is True

    def test_image_auto_resize_set(self) -> None:
        sm = SettingsManager.in_memory()
        sm.set_image_auto_resize(False)
        assert sm.get_image_auto_resize() is False

    def test_block_images_default(self) -> None:
        sm = SettingsManager.in_memory()
        assert sm.get_block_images() is False

    def test_block_images_set(self) -> None:
        sm = SettingsManager.in_memory()
        sm.set_block_images(True)
        assert sm.get_block_images() is True


# ── Enabled models ──────────────────────────────────────────


class TestEnabledModels:
    def test_get_none(self) -> None:
        sm = SettingsManager.in_memory()
        assert sm.get_enabled_models() is None

    def test_set(self) -> None:
        sm = SettingsManager.in_memory()
        sm.set_enabled_models(["anthropic/*", "openai/gpt-4*"])
        assert sm.get_enabled_models() == [
            "anthropic/*",
            "openai/gpt-4*",
        ]


# ── Double escape action / tree filter mode ────────────────


class TestEditorActions:
    def test_double_escape_action_default(self) -> None:
        sm = SettingsManager.in_memory()
        assert sm.get_double_escape_action() == "tree"

    def test_double_escape_action_set(self) -> None:
        sm = SettingsManager.in_memory()
        sm.set_double_escape_action("fork")
        assert sm.get_double_escape_action() == "fork"

    def test_tree_filter_mode_default(self) -> None:
        sm = SettingsManager.in_memory()
        assert sm.get_tree_filter_mode() == "default"

    def test_tree_filter_mode_set(self) -> None:
        sm = SettingsManager.in_memory()
        sm.set_tree_filter_mode("user-only")
        assert sm.get_tree_filter_mode() == "user-only"

    def test_tree_filter_mode_invalid_falls_back(self) -> None:
        """An invalid ``treeFilterMode`` falls
        back to ``"default"``."""
        sm = SettingsManager.in_memory(
            settings={"treeFilterMode": "invalid"}
        )
        assert sm.get_tree_filter_mode() == "default"


# ── Show hardware cursor / editor padding / autocomplete ─


class TestEditorSettings:
    def test_show_hardware_cursor_default(self) -> None:
        sm = SettingsManager.in_memory()
        assert sm.get_show_hardware_cursor() is False

    def test_show_hardware_cursor_set(self) -> None:
        sm = SettingsManager.in_memory()
        sm.set_show_hardware_cursor(True)
        assert sm.get_show_hardware_cursor() is True

    def test_editor_padding_x_default(self) -> None:
        sm = SettingsManager.in_memory()
        assert sm.get_editor_padding_x() == 0

    def test_editor_padding_x_set(self) -> None:
        sm = SettingsManager.in_memory()
        sm.set_editor_padding_x(2)
        assert sm.get_editor_padding_x() == 2

    def test_editor_padding_x_clamped(self) -> None:
        sm = SettingsManager.in_memory()
        sm.set_editor_padding_x(99)
        # Clamped to 3.
        assert sm.get_editor_padding_x() == 3

    def test_autocomplete_max_visible_default(self) -> None:
        sm = SettingsManager.in_memory()
        assert sm.get_autocomplete_max_visible() == 5

    def test_autocomplete_max_visible_set(self) -> None:
        sm = SettingsManager.in_memory()
        sm.set_autocomplete_max_visible(10)
        assert sm.get_autocomplete_max_visible() == 10

    def test_autocomplete_max_visible_clamped(self) -> None:
        sm = SettingsManager.in_memory()
        sm.set_autocomplete_max_visible(99)
        # Clamped to 20.
        assert sm.get_autocomplete_max_visible() == 20

    def test_code_block_indent_default(self) -> None:
        sm = SettingsManager.in_memory()
        assert sm.get_code_block_indent() == "  "


# ── Warnings ────────────────────────────────────────────────


class TestWarnings:
    def test_get_empty(self) -> None:
        sm = SettingsManager.in_memory()
        assert sm.get_warnings() == {}

    def test_set(self) -> None:
        sm = SettingsManager.in_memory()
        sm.set_warnings({"anthropicExtraUsage": False})
        assert sm.get_warnings() == {"anthropicExtraUsage": False}


# ── Persistence: setters update the in-memory state ──────────


class TestPersistence:
    def test_setters_update_in_memory(self, tmp_path) -> None:
        """The typed setters update the
        ``globalSettings`` dict (in-memory)."""
        sm = SettingsManager.create(
            cwd=str(tmp_path), agent_dir=str(tmp_path / "agent")
        )
        sm.set_default_provider("anthropic")
        sm.set_default_model("claude-3-5-sonnet")
        # The in-memory state is updated.
        assert sm.get_settings()["defaultProvider"] == "anthropic"
        assert sm.get_settings()["defaultModel"] == "claude-3-5-sonnet"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
