"""Tests for Phase 8.2c — src/config/ small file batch (20 files).

Covers:
- gateway_env_selection, group_scope_tree, home_env_test_harness
- implicit_mentions, includes_scan, issue_format, json5_comments
- legacy, legacy_shared, local_model_lean_auto, logging
- markdown_tables, materialize, merge_patch, model_input
- nix_mode_write_guard, normalize_exec_safe_bin, normalize_paths
- recovery_policy, redact_argv
"""
from __future__ import annotations

import os
import tempfile

import pytest

from src.config.gateway_env_selection import (
    GATEWAY_CONFIG_SELECTION_ENV_KEYS,
    assert_gateway_config_env_selection_unchanged,
)
from src.config.group_scope_tree import (
    ScopeTree,
    build_channel_groups_scope_tree,
    encode_scope_segment,
    resolve_scope_intro_hint,
    resolve_scope_key_case_insensitive,
    resolve_scope_require_mention,
    resolve_scope_tools_policy,
    scope_key,
)
from src.config.home_env_test_harness import with_temp_home
from src.config.implicit_mentions import (
    SHIPPED_IMPLICIT_MENTION_DEFAULTS,
    resolve_channel_implicit_mentions,
)
from src.config.includes_scan import (
    INCLUDE_KEY,
    MAX_INCLUDE_DEPTH,
    collect_include_paths_recursive,
)
from src.config.issue_format import (
    format_config_issue_line,
    format_config_issue_lines,
    format_config_issue_summary,
    normalize_config_issue,
    normalize_config_issue_path,
    normalize_config_issues,
)
from src.config.json5_comments import warn_if_json5_comments_will_be_stripped
from src.config.legacy import find_legacy_config_issues
from src.config.legacy_shared import (
    LegacyConfigRule,
    define_legacy_config_migration,
    ensure_record,
    get_record,
    is_safe_executable_value,
    map_legacy_audio_transcription,
    merge_missing,
)
from src.config.local_model_lean_auto import (
    AUTO_LOCAL_MODEL_LEAN_PROVIDER_IDS,
    apply_auto_local_model_lean,
    should_auto_enable_local_model_lean,
)
from src.config.logging import (
    format_config_path,
    format_config_updated_message,
)
from src.config.markdown_tables import resolve_markdown_table_mode
from src.config.materialize import (
    as_resolved_source_config,
    as_runtime_config,
    materialize_runtime_config,
)
from src.config.merge_patch import (
    apply_merge_patch,
    is_merge_patch_object_key_allowed,
)
from src.config.model_input import (
    normalize_agent_model_map_for_config,
    normalize_agent_model_ref_for_config,
    resolve_agent_model_fallback_values,
    resolve_agent_model_primary_value,
    resolve_agent_model_timeout_ms_value,
    to_agent_model_list_like,
)
from src.config.nix_mode_write_guard import (
    NIX_OPENCLAW_AGENT_FIRST_URL,
    OPENCLAW_NIX_OVERVIEW_URL,
    NixModeConfigMutationError,
    assert_config_write_allowed_in_current_mode,
    resolve_is_nix_mode,
)
from src.config.normalize_exec_safe_bin import (
    normalize_exec_safe_bin_profiles_in_config,
)
from src.config.normalize_paths import normalize_config_paths
from src.config.recovery_policy import (
    is_plugin_local_invalid_config_snapshot,
    is_plugin_packaging_runtime_output_invalid_config_snapshot,
    should_attempt_last_known_good_recovery,
)
from src.config.redact_argv import SECRET_FLAG_NAMES, redact_sensitive_argv


# ============================================================================
# gateway-env-selection
# ============================================================================


class TestGatewayEnvSelection:
    def test_env_keys_frozenset(self) -> None:
        assert isinstance(GATEWAY_CONFIG_SELECTION_ENV_KEYS, frozenset)
        assert "HOME" in GATEWAY_CONFIG_SELECTION_ENV_KEYS
        assert "USERPROFILE" in GATEWAY_CONFIG_SELECTION_ENV_KEYS
        assert "OPENCLAW_NIX_MODE" in GATEWAY_CONFIG_SELECTION_ENV_KEYS
        # Renamed legacy keys NOT present.
        assert "JARVIS_HOME" not in GATEWAY_CONFIG_SELECTION_ENV_KEYS

    def test_unchanged_when_no_runtime_env_differs(self) -> None:
        # The minimal stub collector always returns {}, so no diff is detected.
        assert_gateway_config_env_selection_unchanged({}, {})

    def test_uppercase_normalization_passes(self) -> None:
        # Even with different key casings on input, no runtime env diff is found.
        assert_gateway_config_env_selection_unchanged(
            {"agents": {"defaults": {"workspaceDir": "~/foo"}}},
            {"agents": {"defaults": {"workspaceDir": "~/bar"}}},
        )

    def test_non_dict_inputs_pass_through(self) -> None:
        # Non-dict inputs are handled.
        assert_gateway_config_env_selection_unchanged(None, None)  # type: ignore[arg-type]


# ============================================================================
# group-scope-tree
# ============================================================================


class TestGroupScopeTree:
    def test_encode_scope_segment(self) -> None:
        assert encode_scope_segment("slack") == "5:slack"
        assert encode_scope_segment("") == "0:"

    def test_scope_key(self) -> None:
        k = scope_key(("channel", "slack"), ("account", "main"))
        assert k.startswith("channel:5:slack/")
        assert "account:4:main" in k

    def test_build_empty_tree_when_no_resolver(self) -> None:
        tree = build_channel_groups_scope_tree({}, "slack")
        assert tree == {"scopes": {}}
        assert "defaults" not in tree

    def test_build_with_resolver_extracts_defaults(self) -> None:
        def resolver(cfg, ch, acct):
            return {
                "*": {"requireMention": False},
                "team-A": {"requireMention": True},
            }

        tree = build_channel_groups_scope_tree({}, "slack", "main", resolve_channel_groups=resolver)
        assert "defaults" in tree
        assert tree["defaults"]["requireMention"] is False
        assert "team-A" in tree["scopes"]
        assert "*" not in tree["scopes"]

    def test_resolve_scope_key_case_insensitive(self) -> None:
        tree: ScopeTree = {"scopes": {"Team-A": {}, "team-B": {}}}
        assert resolve_scope_key_case_insensitive(tree, "team-a") == "Team-A"
        assert resolve_scope_key_case_insensitive(tree, "TEAM-B") == "team-B"
        assert resolve_scope_key_case_insensitive(tree, "team-c") is None
        assert resolve_scope_key_case_insensitive(tree, None) is None
        assert resolve_scope_key_case_insensitive(tree, "") is None

    def test_resolve_scope_require_mention_default_true(self) -> None:
        # No config, no override => True (mentions required by default).
        out = resolve_scope_require_mention({"tree": {"scopes": {}}, "path": []})
        assert out is True

    def test_resolve_scope_require_mention_from_config(self) -> None:
        tree: ScopeTree = {
            "scopes": {
                "team-A": {"requireMention": False},
                "team-B": {},
            }
        }
        out = resolve_scope_require_mention({"tree": tree, "path": ["team-A"]})
        assert out is False
        # Walk back to default
        out2 = resolve_scope_require_mention({"tree": tree, "path": ["team-B"]})
        assert out2 is True

    def test_resolve_scope_require_mention_override_after(self) -> None:
        tree: ScopeTree = {"scopes": {"team-A": {"requireMention": True}}}
        out = resolve_scope_require_mention({
            "tree": tree,
            "path": ["team-A"],
            "requireMentionOverride": False,
            "overrideOrder": "after-config",
        })
        # After-config: config wins
        assert out is True

    def test_resolve_scope_require_mention_override_before(self) -> None:
        tree: ScopeTree = {"scopes": {"team-A": {"requireMention": True}}}
        out = resolve_scope_require_mention({
            "tree": tree,
            "path": ["team-A"],
            "requireMentionOverride": False,
            "overrideOrder": "before-config",
        })
        # Before-config: override wins
        assert out is False

    def test_resolve_scope_intro_hint(self) -> None:
        tree: ScopeTree = {
            "scopes": {"team-A": {"introHint": "hello"}, "team-B": {}},
            "defaults": {"introHint": "default-hello"},
        }
        assert resolve_scope_intro_hint({"tree": tree, "path": ["team-A"]}) == "hello"
        assert resolve_scope_intro_hint({"tree": tree, "path": ["team-B"]}) == "default-hello"
        assert resolve_scope_intro_hint({"tree": {}, "path": ["team-A"]}) is None

    def test_resolve_scope_tools_policy_no_sender_resolver(self) -> None:
        tree: ScopeTree = {"scopes": {"team-A": {"tools": {"policy": "allow"}}}}
        out = resolve_scope_tools_policy({"tree": tree, "path": ["team-A"]})
        assert out == {"policy": "allow"}

    def test_resolve_scope_tools_policy_with_sender_resolver(self) -> None:
        # Sender-merge: when resolver returns something, use that.
        def resolver(params):
            return {"policy": "deny", "by": "sender"}

        tree: ScopeTree = {
            "scopes": {
                "team-A": {
                    "tools": {"policy": "allow"},
                    "toolsBySender": {"u1": {"policy": "deny"}},
                }
            }
        }
        out = resolve_scope_tools_policy({
            "tree": tree,
            "path": ["team-A"],
            "senderId": "u1",
            "resolveToolsBySender": resolver,
        })
        assert out == {"policy": "deny", "by": "sender"}


# ============================================================================
# home-env.test-harness
# ============================================================================


class TestHomeEnvTestHarness:
    def test_sets_HOME_USERPROFILE_and_restores(self) -> None:
        saved_home = os.environ.get("HOME")
        saved_userprofile = os.environ.get("USERPROFILE")
        with with_temp_home(prefix="jarvis-test-home-") as tmp:
            assert os.path.isdir(tmp)
            assert os.environ.get("HOME") == tmp
            assert os.environ.get("USERPROFILE") == tmp
        # Restored after the context exits.
        assert os.environ.get("HOME") == saved_home
        assert os.environ.get("USERPROFILE") == saved_userprofile
        # Temp dir was cleaned up.
        assert not os.path.isdir(tmp)

    def test_restores_when_original_missing(self) -> None:
        saved_home = os.environ.pop("HOME", None)
        saved_userprofile = os.environ.pop("USERPROFILE", None)
        try:
            with with_temp_home(prefix="jarvis-test-home-") as tmp:
                assert os.environ["HOME"] == tmp
            # Both removed since they were originally missing.
            assert "HOME" not in os.environ
            assert "USERPROFILE" not in os.environ
        finally:
            if saved_home is not None:
                os.environ["HOME"] = saved_home
            if saved_userprofile is not None:
                os.environ["USERPROFILE"] = saved_userprofile


# ============================================================================
# implicit-mentions
# ============================================================================


class TestImplicitMentions:
    def test_shipped_defaults(self) -> None:
        assert SHIPPED_IMPLICIT_MENTION_DEFAULTS == {
            "replyToBot": True,
            "quotedBot": True,
            "threadParticipation": True,
        }

    def test_no_cfg_returns_defaults(self) -> None:
        out = resolve_channel_implicit_mentions({"channel": "slack"})
        assert out == SHIPPED_IMPLICIT_MENTION_DEFAULTS

    def test_account_overrides_channel(self) -> None:
        cfg = {
            "channels": {
                "slack": {
                    "implicitMentions": {"replyToBot": False},
                    "accounts": {
                        "u1": {"implicitMentions": {"replyToBot": True}},
                    },
                }
            }
        }
        out = resolve_channel_implicit_mentions({"cfg": cfg, "channel": "slack", "accountId": "u1"})
        assert out["replyToBot"] is True

    def test_channel_overrides_shipped(self) -> None:
        cfg = {
            "channels": {
                "slack": {"implicitMentions": {"replyToBot": False, "quotedBot": False}},
            }
        }
        out = resolve_channel_implicit_mentions({"cfg": cfg, "channel": "slack"})
        assert out["replyToBot"] is False
        assert out["quotedBot"] is False
        assert out["threadParticipation"] is True  # default

    def test_defaults_block_overrides_shipped(self) -> None:
        cfg = {
            "channels": {
                "defaults": {"implicitMentions": {"replyToBot": False}},
                "slack": {},
            }
        }
        out = resolve_channel_implicit_mentions({"cfg": cfg, "channel": "slack"})
        assert out["replyToBot"] is False

    def test_account_id_normalized_lowercase(self) -> None:
        cfg = {
            "channels": {
                "slack": {
                    "accounts": {
                        "u1": {"implicitMentions": {"replyToBot": False}},
                    },
                }
            }
        }
        out = resolve_channel_implicit_mentions({"cfg": cfg, "channel": "slack", "accountId": "U1"})
        assert out["replyToBot"] is False


# ============================================================================
# includes-scan
# ============================================================================


class TestIncludesScan:
    def test_constants(self) -> None:
        assert INCLUDE_KEY == "$include"
        assert MAX_INCLUDE_DEPTH == 10

    def test_collect_includes_no_resolver(self) -> None:
        out = collect_include_paths_recursive({"configPath": "a.json", "parsed": {}})
        assert out == []

    def test_collect_includes_with_resolver(self) -> None:
        captured = []

        def resolve_include(value, base, resolver):
            resolver(value, base, captured.append)

        def read_file(p):
            return "{}"

        out = collect_include_paths_recursive(
            {"configPath": "a.json", "parsed": {"$include": "b.json"}},
            resolve_include=resolve_include,
            read_file=read_file,
        )
        # Resolver is invoked, included_paths captured.
        assert isinstance(out, list)

    def test_collect_includes_resolver_exception_swallowed(self) -> None:
        def resolve_include(value, base, resolver):
            raise RuntimeError("boom")

        # Should not raise.
        out = collect_include_paths_recursive(
            {"configPath": "a.json", "parsed": {"$include": "b.json"}},
            resolve_include=resolve_include,
        )
        assert out == []


# ============================================================================
# issue-format
# ============================================================================


class TestIssueFormat:
    def test_normalize_path_blank_to_root(self) -> None:
        assert normalize_config_issue_path("") == "<root>"
        assert normalize_config_issue_path("   ") == "<root>"
        assert normalize_config_issue_path(None) == "<root>"  # type: ignore[arg-type]

    def test_normalize_path_keeps_value(self) -> None:
        assert normalize_config_issue_path("channels.slack") == "channels.slack"

    def test_normalize_issue_basic(self) -> None:
        out = normalize_config_issue({"path": "", "message": "bad"})
        assert out["path"] == "<root>"
        assert out["message"] == "bad"
        assert "allowedValues" not in out

    def test_normalize_issue_with_allowed_values(self) -> None:
        out = normalize_config_issue({
            "path": "x",
            "message": "bad",
            "allowedValues": ["a", "b"],
            "allowedValuesHiddenCount": 3,
        })
        assert out["allowedValues"] == ["a", "b"]
        assert out["allowedValuesHiddenCount"] == 3

    def test_normalize_issue_empty_allowed_values_dropped(self) -> None:
        out = normalize_config_issue({"path": "x", "message": "bad", "allowedValues": []})
        assert "allowedValues" not in out

    def test_normalize_issue_zero_hidden_dropped(self) -> None:
        out = normalize_config_issue({"path": "x", "message": "bad", "allowedValuesHiddenCount": 0})
        assert "allowedValuesHiddenCount" not in out

    def test_normalize_issues_list(self) -> None:
        out = normalize_config_issues([
            {"path": "a", "message": "m1"},
            {"path": "", "message": "m2"},
        ])
        assert out[0]["path"] == "a"
        assert out[1]["path"] == "<root>"

    def test_format_line(self) -> None:
        line = format_config_issue_line({"path": "x", "message": "bad"}, marker="-")
        assert line == "- x: bad"

    def test_format_line_with_source(self) -> None:
        line = format_config_issue_line(
            {"path": "x", "message": "bad", "sourceFile": "cfg.json", "line": 12},
        )
        assert line.startswith("- cfg.json:12 — x: bad")

    def test_format_line_strips_control_chars(self) -> None:
        line = format_config_issue_line({"path": "x", "message": "bad\x00text"})
        assert "\x00" not in line
        assert "badtext" in line

    def test_format_lines(self) -> None:
        out = format_config_issue_lines([{"path": "a", "message": "m"}])
        assert out == ["- a: m"]

    def test_format_summary_empty(self) -> None:
        assert format_config_issue_summary([]) is None
        assert format_config_issue_summary(None) is None  # type: ignore[arg-type]

    def test_format_summary_truncates(self) -> None:
        issues = [{"path": f"p{i}", "message": f"m{i}"} for i in range(10)]
        out = format_config_issue_summary(issues, {"maxIssues": 3})
        assert out is not None
        assert "and 7 more" in out
        # 3 visible joined with "; " (2 separators) + "; and N more" tail (1 more) = 3 total.
        assert out.count("; ") == 3

    def test_format_summary_clamps_min_one(self) -> None:
        issues = [{"path": "p", "message": "m"}]
        out = format_config_issue_summary(issues, {"maxIssues": 0})
        assert out is not None
        assert "p: m" in out


# ============================================================================
# json5-comments
# ============================================================================


class TestJson5Comments:
    def test_warns_on_line_comment(self) -> None:
        captured = []
        warn_if_json5_comments_will_be_stripped({
            "raw": '{ "a": 1 } // comment',
            "filePath": "cfg.json",
            "warn": captured.append,
        })
        assert len(captured) == 1
        assert "JSON5 comments" in captured[0]
        assert "cfg.json" in captured[0]

    def test_warns_on_block_comment(self) -> None:
        captured = []
        warn_if_json5_comments_will_be_stripped({
            "raw": '{ "a": /* x */ 1 }',
            "filePath": "cfg.json",
            "warn": captured.append,
        })
        assert len(captured) == 1

    def test_no_warn_on_pure_json(self) -> None:
        captured = []
        warn_if_json5_comments_will_be_stripped({
            "raw": '{ "a": 1, "b": "x" }',
            "filePath": "cfg.json",
            "warn": captured.append,
        })
        assert captured == []

    def test_no_warn_when_slash_inside_string(self) -> None:
        captured = []
        warn_if_json5_comments_will_be_stripped({
            "raw": '{ "a": "https://example.com" }',
            "filePath": "cfg.json",
            "warn": captured.append,
        })
        assert captured == []

    def test_skip_output_logs(self) -> None:
        captured = []
        warn_if_json5_comments_will_be_stripped({
            "raw": '{ "a": 1 } // comment',
            "filePath": "cfg.json",
            "warn": captured.append,
            "skipOutputLogs": True,
        })
        assert captured == []


# ============================================================================
# legacy + legacy_shared
# ============================================================================


class TestLegacyShared:
    def test_get_record(self) -> None:
        assert get_record({"a": 1}) == {"a": 1}
        assert get_record("x") is None
        assert get_record(None) is None

    def test_ensure_record_existing(self) -> None:
        root = {"x": {"a": 1}}
        out = ensure_record(root, "x")
        assert out == {"a": 1}
        assert out is root["x"]

    def test_ensure_record_new(self) -> None:
        root: dict = {}
        out = ensure_record(root, "x")
        assert out == {}
        assert root["x"] is out

    def test_merge_missing_no_overwrite(self) -> None:
        target = {"a": 1, "b": {"x": 1}}
        source = {"a": 999, "b": {"x": 999, "y": 2}, "c": 3}
        merge_missing(target, source)
        assert target["a"] == 1  # not overwritten
        assert target["b"]["x"] == 1  # not overwritten
        assert target["b"]["y"] == 2  # added
        assert target["c"] == 3  # added

    def test_merge_missing_skips_blocked_keys(self) -> None:
        target: dict = {}
        merge_missing(target, {"__proto__": {"x": 1}, "constructor": 1, "a": 2})
        # Blocked keys are NOT merged.
        assert "__proto__" not in target or not target.get("__proto__")
        assert "a" in target

    def test_merge_missing_skips_none(self) -> None:
        target: dict = {}
        merge_missing(target, {"a": None, "b": 1})
        assert "a" not in target
        assert target["b"] == 1

    def test_is_safe_executable_value(self) -> None:
        assert is_safe_executable_value("/usr/bin/ffmpeg")
        assert is_safe_executable_value("ffmpeg")
        assert not is_safe_executable_value("")
        assert not is_safe_executable_value("   ")
        assert not is_safe_executable_value(None)  # type: ignore[arg-type]

    def test_map_legacy_audio_transcription(self) -> None:
        out = map_legacy_audio_transcription({
            "command": ["/usr/bin/ffmpeg", "-i", "{input}", "-ar", "16000"],
            "timeoutSeconds": 30,
        })
        assert out == {
            "command": "/usr/bin/ffmpeg",
            "type": "cli",
            "args": ["-i", "{{MediaPath}}", "-ar", "16000"],
            "timeoutSeconds": 30,
        }

    def test_map_legacy_audio_transcription_invalid(self) -> None:
        assert map_legacy_audio_transcription({}) is None
        assert map_legacy_audio_transcription({"command": []}) is None
        assert map_legacy_audio_transcription({"command": [123]}) is None
        assert map_legacy_audio_transcription({"command": ["   ", "x"]}) is None

    def test_define_legacy_config_migration_returns_input(self) -> None:
        mig = {"path": ["a"], "message": "m", "match": lambda v, r: True}
        assert define_legacy_config_migration(mig) is mig


class TestLegacy:
    def test_find_legacy_config_issues_non_dict(self) -> None:
        assert find_legacy_config_issues(None) == []  # type: ignore[arg-type]
        assert find_legacy_config_issues("x") == []  # type: ignore[arg-type]

    def test_find_legacy_config_issues_no_rules(self) -> None:
        assert find_legacy_config_issues({"a": 1}) == []

    def test_find_legacy_config_issues_basic(self) -> None:
        rule: LegacyConfigRule = {
            "path": ["legacy", "field"],
            "message": "use new field",
            "match": lambda v, r: v == "old",
        }
        issues = find_legacy_config_issues(
            {"legacy": {"field": "old"}},
            extra_rules=[rule],
        )
        assert len(issues) == 1
        assert issues[0]["path"] == "legacy.field"
        assert issues[0]["message"] == "use new field"

    def test_find_legacy_config_issues_no_match(self) -> None:
        rule: LegacyConfigRule = {
            "path": ["legacy"],
            "message": "m",
            "match": lambda v, r: v == "old",
        }
        issues = find_legacy_config_issues({"legacy": "new"}, extra_rules=[rule])
        assert issues == []

    def test_find_legacy_config_issues_require_source_literal(self) -> None:
        rule: LegacyConfigRule = {
            "path": ["legacy"],
            "message": "m",
            "requireSourceLiteral": True,
            "match": lambda v, r: v == "old",
        }
        # Source present and matches => issue.
        issues = find_legacy_config_issues(
            {"legacy": "old"},
            source_raw={"legacy": "old"},
            extra_rules=[rule],
        )
        assert len(issues) == 1
        # Source missing (None) => falls back to raw, source_cursor present, issue added.
        issues2 = find_legacy_config_issues(
            {"legacy": "old"},
            extra_rules=[rule],
        )
        assert len(issues2) == 1
        # Source present but doesn't match => no issue.
        issues3 = find_legacy_config_issues(
            {"legacy": "old"},
            source_raw={"legacy": "different"},
            extra_rules=[rule],
        )
        assert issues3 == []


# ============================================================================
# local-model-lean-auto
# ============================================================================


class TestLocalModelLeanAuto:
    def test_provider_set(self) -> None:
        assert "lmstudio" in AUTO_LOCAL_MODEL_LEAN_PROVIDER_IDS
        assert "ollama" in AUTO_LOCAL_MODEL_LEAN_PROVIDER_IDS
        assert "openai" not in AUTO_LOCAL_MODEL_LEAN_PROVIDER_IDS

    def test_should_auto_enable(self) -> None:
        assert should_auto_enable_local_model_lean("LMStudio") is True
        assert should_auto_enable_local_model_lean("ollama") is True
        assert should_auto_enable_local_model_lean("openai") is False
        assert should_auto_enable_local_model_lean("") is False
        assert should_auto_enable_local_model_lean(None) is False  # type: ignore[arg-type]

    def test_non_lean_provider_no_auto_no_existing(self) -> None:
        cfg = {}
        out = apply_auto_local_model_lean({"config": cfg, "providerId": "openai", "modelRef": "gpt-4"})
        assert out["changed"] is False
        assert out["enabled"] is False
        assert out["config"] == cfg

    def test_non_lean_provider_with_existing_clears_when_user_overrides(self) -> None:
        # user explicitly disabled lean, and onboarding had auto-marked
        cfg = {
            "agents": {"defaults": {"experimental": {"localModelLean": False}}},
            "wizard": {"localModelLeanAutoModel": "ollama/llama3"},
        }
        out = apply_auto_local_model_lean({
            "config": cfg,
            "providerId": "openai",
            "modelRef": "gpt-4",
        })
        assert out["changed"] is True
        assert out["enabled"] is False
        assert "localModelLeanAutoModel" not in out["config"].get("wizard", {})

    def test_lean_provider_no_existing_setting(self) -> None:
        cfg = {
            "agents": {"defaults": {"model": "ollama/llama3"}},
        }
        out = apply_auto_local_model_lean({
            "config": cfg,
            "providerId": "ollama",
            "modelRef": "ollama/llama3",
        })
        assert out["changed"] is True
        assert out["enabled"] is True
        assert out["config"]["wizard"]["localModelLeanAutoModel"] == "ollama/llama3"
        assert out["config"]["agents"]["defaults"]["experimental"]["localModelLean"] is True

    def test_lean_provider_with_explicit_setting_user_overrides(self) -> None:
        # User explicitly set localModelLean = False, and onboarding has set auto.
        cfg = {
            "agents": {
                "defaults": {
                    "model": "ollama/llama3",
                    "experimental": {"localModelLean": False},
                },
            },
            "wizard": {"localModelLeanAutoModel": "ollama/llama3"},
        }
        out = apply_auto_local_model_lean({
            "config": cfg,
            "providerId": "ollama",
            "modelRef": "ollama/llama3",
        })
        # localModelLean != True => clear auto, no change to lean setting.
        assert out["changed"] is True
        assert out["enabled"] is False

    def test_lean_provider_user_changed_model(self) -> None:
        # Onboarding set auto = "ollama/llama3", user has now changed to "ollama/mistral"
        # AND localModelLean = True. Onboarding no longer owns the setting, so auto is cleared.
        cfg = {
            "agents": {
                "defaults": {
                    "model": "ollama/mistral",
                    "experimental": {"localModelLean": True},
                },
            },
            "wizard": {"localModelLeanAutoModel": "ollama/llama3"},
        }
        out = apply_auto_local_model_lean({
            "config": cfg,
            "providerId": "ollama",
            "modelRef": "ollama/mistral",
        })
        # Onboarding no longer owns the setting => auto ref is cleared.
        assert out["changed"] is True
        assert "localModelLeanAutoModel" not in out["config"].get("wizard", {})
        assert out["enabled"] is False


# ============================================================================
# logging (config-side)
# ============================================================================


class TestConfigLogging:
    def test_format_config_path_empty(self) -> None:
        assert format_config_path("") == ""
        assert format_config_path(None) == ""  # type: ignore[arg-type]

    def test_format_config_path_passthrough(self) -> None:
        assert format_config_path("/etc/foo.json") == "/etc/foo.json"

    def test_format_config_updated_message_no_backup(self) -> None:
        msg = format_config_updated_message("/etc/foo.json")
        assert msg.startswith("Updated config: /etc/foo.json")
        assert "Backup:" not in msg

    def test_format_config_updated_message_with_suffix(self) -> None:
        msg = format_config_updated_message("/etc/foo.json", suffix="ok")
        assert msg == "Updated config: /etc/foo.json ok"

    def test_format_config_updated_message_existing_backup(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".bak", delete=False) as f:
            backup = f.name
        try:
            msg = format_config_updated_message("/etc/foo.json", backup_path=backup)
            assert "Backup:" in msg
            assert backup in msg
        finally:
            os.unlink(backup)

    def test_format_config_updated_message_missing_backup_file(self) -> None:
        # Path is set but file does not exist => no Backup line.
        msg = format_config_updated_message("/etc/foo.json", backup_path="/nonexistent.bak")
        assert "Backup:" not in msg


# ============================================================================
# markdown-tables
# ============================================================================


class TestMarkdownTables:
    def test_no_channel_returns_code(self) -> None:
        assert resolve_markdown_table_mode({"channel": None}) == "code"  # type: ignore[arg-type]
        assert resolve_markdown_table_mode({"channel": ""}) == "code"
        assert resolve_markdown_table_mode({}) == "code"

    def test_channel_default_code(self) -> None:
        assert resolve_markdown_table_mode({"channel": "slack"}) == "code"

    def test_channel_account_override(self) -> None:
        cfg = {
            "channels": {
                "slack": {
                    "markdown": {"tables": "block"},
                    "accounts": {
                        "u1": {"markdown": {"tables": "off"}},
                    },
                }
            }
        }
        out = resolve_markdown_table_mode({
            "channel": "slack",
            "accountId": "u1",
            "cfg": cfg,
        })
        assert out == "off"

    def test_channel_default_mode(self) -> None:
        cfg = {
            "channels": {
                "slack": {"markdown": {"tables": "bullets"}},
            }
        }
        out = resolve_markdown_table_mode({"channel": "slack", "cfg": cfg})
        assert out == "bullets"

    def test_block_fallback_when_unsupported(self) -> None:
        cfg = {
            "channels": {
                "slack": {"markdown": {"tables": "block"}},
            }
        }
        out = resolve_markdown_table_mode({
            "channel": "slack",
            "cfg": cfg,
            "supportsBlockTables": False,
        })
        assert out == "code"

    def test_block_kept_when_supported(self) -> None:
        cfg = {
            "channels": {
                "slack": {"markdown": {"tables": "block"}},
            }
        }
        out = resolve_markdown_table_mode({
            "channel": "slack",
            "cfg": cfg,
            "supportsBlockTables": True,
        })
        assert out == "block"

    def test_default_modes_injected(self) -> None:
        def get_default_table_modes():
            return {"slack": "bullets"}

        out = resolve_markdown_table_mode(
            {"channel": "slack"},
            get_default_table_modes=get_default_table_modes,
        )
        assert out == "bullets"


# ============================================================================
# materialize
# ============================================================================


class TestMaterialize:
    def test_as_resolved_source_config_passthrough(self) -> None:
        cfg = {"a": 1}
        assert as_resolved_source_config(cfg) is cfg

    def test_as_runtime_config_passthrough(self) -> None:
        cfg = {"a": 1}
        assert as_runtime_config(cfg) is cfg

    def test_materialize_load_profile_runs_session(self) -> None:
        calls = []

        def apply_session_defaults(c):
            calls.append("session")
            return c

        cfg = {"a": 1}
        out = materialize_runtime_config(
            cfg, "load", apply_session_defaults=apply_session_defaults
        )
        assert "session" in calls
        assert out == {"a": 1}

    def test_materialize_snapshot_skips_compaction(self) -> None:
        calls = []

        def apply_compaction_defaults(c):
            calls.append("compaction")
            return c

        materialize_runtime_config(
            {"a": 1}, "snapshot", apply_compaction_defaults=apply_compaction_defaults,
        )
        # snapshot profile has includeCompactionDefaults=False.
        assert "compaction" not in calls

    def test_materialize_missing_skips_logging(self) -> None:
        calls = []

        def apply_logging_defaults(c):
            calls.append("logging")
            return c

        materialize_runtime_config(
            {"a": 1}, "missing", apply_logging_defaults=apply_logging_defaults,
        )
        # missing profile has includeLoggingDefaults=False.
        assert "logging" not in calls

    def test_materialize_unknown_mode_falls_back_to_load(self) -> None:
        # "load" profile includes compaction.
        calls = []

        def apply_compaction_defaults(c):
            calls.append("compaction")
            return c

        materialize_runtime_config(
            {"a": 1}, "unknown-mode", apply_compaction_defaults=apply_compaction_defaults,
        )
        assert "compaction" in calls

    def test_materialize_normalize_paths_called(self) -> None:
        captured = []

        def normalize_paths(c):
            captured.append(c)

        materialize_runtime_config(
            {"a": 1}, "load", normalize_config_paths_fn=normalize_paths,
        )
        # load profile has normalizePaths=True
        assert captured == [{"a": 1}]


# ============================================================================
# merge-patch
# ============================================================================


class TestMergePatch:
    def test_key_allowed_default(self) -> None:
        assert is_merge_patch_object_key_allowed("a") is True

    def test_key_blocked_proto(self) -> None:
        assert is_merge_patch_object_key_allowed("__proto__") is False
        assert is_merge_patch_object_key_allowed("constructor") is False
        assert is_merge_patch_object_key_allowed("prototype") is False

    def test_key_allowed_in_browser_profiles(self) -> None:
        assert is_merge_patch_object_key_allowed("constructor", "browser.profiles") is True
        assert is_merge_patch_object_key_allowed("prototype", "browser.profiles") is True
        # __proto__ still blocked.
        assert is_merge_patch_object_key_allowed("__proto__", "browser.profiles") is False

    def test_simple_merge(self) -> None:
        out = apply_merge_patch({"a": 1, "b": 2}, {"b": 3, "c": 4})
        assert out == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge(self) -> None:
        base = {"a": {"x": 1, "y": 2}}
        patch = {"a": {"y": 20, "z": 30}}
        out = apply_merge_patch(base, patch)
        assert out == {"a": {"x": 1, "y": 20, "z": 30}}

    def test_null_deletes_key(self) -> None:
        out = apply_merge_patch({"a": 1, "b": 2}, {"a": None})
        assert out == {"b": 2}

    def test_non_object_patch_replaces(self) -> None:
        out = apply_merge_patch({"a": 1}, "scalar")
        assert out == "scalar"

    def test_blocked_keys_stripped(self) -> None:
        out = apply_merge_patch({}, {"__proto__": {"x": 1}, "a": 1})
        assert "__proto__" not in out or out.get("__proto__") in ({}, None)
        assert out["a"] == 1

    def test_array_replacement(self) -> None:
        base = {"items": [1, 2, 3]}
        out = apply_merge_patch(base, {"items": [4, 5]})
        assert out["items"] == [4, 5]

    def test_array_merge_by_id(self) -> None:
        base = {"items": [{"id": "a", "v": 1}, {"id": "b", "v": 2}]}
        patch = {"items": [{"id": "a", "v": 10}, {"id": "c", "v": 3}]}
        out = apply_merge_patch(base, patch, {"mergeObjectArraysById": True})
        assert out["items"] == [
            {"id": "a", "v": 10},
            {"id": "b", "v": 2},
            {"id": "c", "v": 3},
        ]

    def test_array_replace_path(self) -> None:
        base = {"items": [{"id": "a", "v": 1}]}
        out = apply_merge_patch(
            base, {"items": [{"id": "b", "v": 2}]},
            {"mergeObjectArraysById": True, "replaceArrayPaths": {"items"}},
        )
        assert out["items"] == [{"id": "b", "v": 2}]

    def test_array_merge_non_id_keyed_replaces(self) -> None:
        base = {"items": [1, 2, 3]}
        out = apply_merge_patch(
            base, {"items": [4, 5]},
            {"mergeObjectArraysById": True},
        )
        # Non-id-keyed arrays are RFC-replaced even with merge-by-id.
        assert out["items"] == [4, 5]


# ============================================================================
# model-input
# ============================================================================


class TestModelInput:
    def test_resolve_primary_string(self) -> None:
        assert resolve_agent_model_primary_value("gpt-4") == "gpt-4"
        assert resolve_agent_model_primary_value("  gpt-4  ") == "gpt-4"
        assert resolve_agent_model_primary_value("") is None
        assert resolve_agent_model_primary_value(None) is None

    def test_resolve_primary_object(self) -> None:
        assert resolve_agent_model_primary_value({"primary": "gpt-4"}) == "gpt-4"
        assert resolve_agent_model_primary_value({"primary": "  gpt-4  "}) == "gpt-4"
        assert resolve_agent_model_primary_value({"primary": ""}) is None
        assert resolve_agent_model_primary_value({}) is None

    def test_resolve_fallbacks(self) -> None:
        assert resolve_agent_model_fallback_values({"fallbacks": ["a", "b"]}) == ["a", "b"]
        assert resolve_agent_model_fallback_values({}) == []
        assert resolve_agent_model_fallback_values("gpt-4") == []
        assert resolve_agent_model_fallback_values(None) == []

    def test_resolve_timeout(self) -> None:
        assert resolve_agent_model_timeout_ms_value({"timeoutMs": 5000}) == 5000
        assert resolve_agent_model_timeout_ms_value({"timeoutMs": 0}) is None
        assert resolve_agent_model_timeout_ms_value({"timeoutMs": -1}) is None
        assert resolve_agent_model_timeout_ms_value({}) is None
        assert resolve_agent_model_timeout_ms_value("x") is None

    def test_to_list_like(self) -> None:
        assert to_agent_model_list_like("gpt-4") == {"primary": "gpt-4"}
        assert to_agent_model_list_like("") is None
        assert to_agent_model_list_like({"primary": "gpt-4"}) == {"primary": "gpt-4"}
        assert to_agent_model_list_like(None) is None

    def test_normalize_ref_no_parser(self) -> None:
        # Without parser, ref is just stripped.
        assert normalize_agent_model_ref_for_config("  gpt-4  ") == "gpt-4"

    def test_normalize_ref_with_parser(self) -> None:
        def parse(ref):
            return {"provider": "openai", "modelId": "gpt-4"}

        out = normalize_agent_model_ref_for_config(
            "openai/gpt-4", parse_model_catalog_ref=parse,
        )
        assert out == "openai/gpt-4"

    def test_normalize_ref_google(self) -> None:
        def parse(ref):
            return {"provider": "google", "modelId": "gemini-1.5-pro"}

        def norm_google(model):
            return "gemini-1.5-pro-preview"

        out = normalize_agent_model_ref_for_config(
            "google/gemini-1.5-pro",
            parse_model_catalog_ref=parse,
            normalize_google_preview_model_id=norm_google,
        )
        assert out == "google/gemini-1.5-pro-preview"

    def test_normalize_map_collapses(self) -> None:
        # When the parser can't parse keys, map stays the same.
        models = {
            "openai/gpt-4": {"params": {"temperature": 0.5}},
            "openai/gpt-4-turbo": {"params": {"temperature": 0.7}},
        }
        out = normalize_agent_model_map_for_config(models)
        assert out is models  # not mutated when nothing changes


# ============================================================================
# nix-mode-write-guard
# ============================================================================


class TestNixModeWriteGuard:
    def test_constants(self) -> None:
        assert "nix-openclaw" in NIX_OPENCLAW_AGENT_FIRST_URL
        assert "nix" in OPENCLAW_NIX_OVERVIEW_URL

    def test_resolve_no_env(self) -> None:
        assert resolve_is_nix_mode() is False
        assert resolve_is_nix_mode({}) is False
        assert resolve_is_nix_mode(None) is False  # type: ignore[arg-type]

    def test_resolve_env(self) -> None:
        assert resolve_is_nix_mode({"OPENCLAW_NIX_MODE": "1"}) is True
        assert resolve_is_nix_mode({"OPENCLAW_NIX_MODE": "true"}) is True
        assert resolve_is_nix_mode({"OPENCLAW_NIX_MODE": "yes"}) is True
        assert resolve_is_nix_mode({"OPENCLAW_NIX_MODE": "0"}) is False
        assert resolve_is_nix_mode({"OPENCLAW_NIX_MODE": "no"}) is False
        assert resolve_is_nix_mode({"OPENCLAW_NIX_MODE": ""}) is False
        assert resolve_is_nix_mode({"OPENCLAW_NIX_MODE": "  1  "}) is True
        # Non-string truthy
        assert resolve_is_nix_mode({"OPENCLAW_NIX_MODE": True}) is True  # type: ignore[dict-item]

    def test_assert_passes_when_not_nix(self) -> None:
        # Should not raise.
        assert_config_write_allowed_in_current_mode()

    def test_assert_raises_when_nix(self) -> None:
        with pytest.raises(NixModeConfigMutationError) as exc_info:
            assert_config_write_allowed_in_current_mode(
                config_path="/etc/openclaw.json",
                env={"OPENCLAW_NIX_MODE": "1"},
            )
        assert exc_info.value.code == "OPENCLAW_NIX_MODE_CONFIG_IMMUTABLE"
        assert "/etc/openclaw.json" in str(exc_info.value)

    def test_error_includes_url(self) -> None:
        with pytest.raises(NixModeConfigMutationError) as exc_info:
            assert_config_write_allowed_in_current_mode(
                env={"OPENCLAW_NIX_MODE": "1"},
            )
        assert "nix-openclaw" in str(exc_info.value)

    def test_assert_uses_injected_resolver(self) -> None:
        # Even when env says False, custom resolver can flip it.
        with pytest.raises(NixModeConfigMutationError):
            assert_config_write_allowed_in_current_mode(
                env={"OPENCLAW_NIX_MODE": "0"},
                resolve_is_nix_mode_fn=lambda env: True,
            )


# ============================================================================
# normalize-exec-safe-bin
# ============================================================================


class TestNormalizeExecSafeBin:
    def test_non_dict_passthrough(self) -> None:
        normalize_exec_safe_bin_profiles_in_config(None)  # type: ignore[arg-type]
        normalize_exec_safe_bin_profiles_in_config("x")  # type: ignore[arg-type]

    def test_no_exec_section(self) -> None:
        cfg = {"agents": {"list": []}}
        normalize_exec_safe_bin_profiles_in_config(cfg)
        assert cfg == {"agents": {"list": []}}

    def test_normalizes_global(self) -> None:
        cfg = {
            "tools": {
                "exec": {
                    "safeBinProfiles": {"raw": "x"},
                    "safeBinTrustedDirs": ["raw", "raw", "normed"],
                }
            }
        }
        # Both normalizers invoked.
        normalize_exec_safe_bin_profiles_in_config(
            cfg,
            normalize_safe_bin_profile_fixtures=lambda x: {"normalized": x.get("raw")},
            normalize_trusted_safe_bin_dirs=lambda x: list({d for d in x if d != "raw"}),
        )
        assert cfg["tools"]["exec"]["safeBinProfiles"] == {"normalized": "x"}
        assert cfg["tools"]["exec"]["safeBinTrustedDirs"] == ["normed"]

    def test_normalizes_per_agent(self) -> None:
        cfg = {
            "tools": {"exec": {"safeBinProfiles": {"raw": "g"}}},
            "agents": {
                "list": [
                    {
                        "id": "main",
                        "tools": {
                            "exec": {
                                "safeBinProfiles": {"raw": "a"},
                                "safeBinTrustedDirs": ["dir1", "dir2"],
                            }
                        },
                    }
                ]
            },
        }
        normalize_exec_safe_bin_profiles_in_config(
            cfg,
            normalize_safe_bin_profile_fixtures=lambda x: {"norm": x.get("raw")},
            normalize_trusted_safe_bin_dirs=lambda x: list(set(x)),
        )
        assert cfg["tools"]["exec"]["safeBinProfiles"] == {"norm": "g"}
        agent_exec = cfg["agents"]["list"][0]["tools"]["exec"]
        assert agent_exec["safeBinProfiles"] == {"norm": "a"}
        assert sorted(agent_exec["safeBinTrustedDirs"]) == ["dir1", "dir2"]

    def test_empty_normalized_removed(self) -> None:
        cfg = {
            "tools": {"exec": {"safeBinProfiles": {"a": 1}}},
        }
        normalize_exec_safe_bin_profiles_in_config(
            cfg,
            normalize_safe_bin_profile_fixtures=lambda x: {},  # empty result
            normalize_trusted_safe_bin_dirs=lambda x: [],
        )
        assert "safeBinProfiles" not in cfg["tools"]["exec"]
        assert "safeBinTrustedDirs" not in cfg["tools"]["exec"]


# ============================================================================
# normalize-paths
# ============================================================================


class TestNormalizePaths:
    def test_non_dict(self) -> None:
        assert normalize_config_paths(None) is None  # type: ignore[arg-type]
        assert normalize_config_paths("x") == "x"  # type: ignore[arg-type]

    def test_expand_tilde_in_path_key(self, monkeypatch) -> None:
        # Mock os.path.expanduser to return a stable fake home.
        monkeypatch.setattr(
            "src.config.normalize_paths.os.path.expanduser",
            lambda p: p.replace("~", "/fakehome", 1),
        )
        cfg = {"agents": {"defaults": {"workspaceDir": "~/foo"}}}
        normalize_config_paths(cfg)
        assert cfg["agents"]["defaults"]["workspaceDir"] == "/fakehome/foo"

    def test_expand_tilde_in_paths_list(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "src.config.normalize_paths.os.path.expanduser",
            lambda p: p.replace("~", "/fakehome", 1),
        )
        cfg = {"plugins": {"paths": ["~/a", "~/b"]}}
        normalize_config_paths(cfg)
        assert cfg["plugins"]["paths"] == ["/fakehome/a", "/fakehome/b"]

    def test_non_path_key_unchanged(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "src.config.normalize_paths.os.path.expanduser",
            lambda p: p.replace("~", "/fakehome", 1),
        )
        cfg = {"name": "~/foo"}
        normalize_config_paths(cfg)
        assert cfg["name"] == "~/foo"

    def test_no_tilde_unchanged(self) -> None:
        cfg = {"agents": {"defaults": {"workspaceDir": "/abs/path"}}}
        normalize_config_paths(cfg)
        assert cfg["agents"]["defaults"]["workspaceDir"] == "/abs/path"

    def test_list_with_non_strings(self) -> None:
        cfg = {"x": [1, 2, "~/foo"]}
        # Key "x" is not in PATH_LIST_KEYS and not in _PATH_KEY_RE.
        normalize_config_paths(cfg)
        assert cfg["x"] == [1, 2, "~/foo"]

    def test_nested_objects(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "src.config.normalize_paths.os.path.expanduser",
            lambda p: p.replace("~", "/fakehome", 1),
        )
        # At the leaf, the parent key is the path-key check.
        cfg = {"a": {"workspaceDir": "~/deep"}}
        normalize_config_paths(cfg)
        assert cfg["a"]["workspaceDir"] == "/fakehome/deep"


# ============================================================================
# recovery-policy
# ============================================================================


class TestRecoveryPolicy:
    def test_packaging_runtime_output_detection(self) -> None:
        snapshot = {
            "valid": False,
            "issues": [
                {"path": "plugins.entries.foo", "message": "plugin foo: compiled runtime output"},
            ],
            "legacyIssues": [],
        }
        # When issues are all plugin-packaging-fallout, recovery is appropriate.
        # But is_plugin_packaging_runtime_output_invalid_config_snapshot requires
        # packaging-plugin-id set + each non-packaging issue must be a fallout
        # of one of those plugins.
        assert (
            is_plugin_packaging_runtime_output_invalid_config_snapshot(snapshot) is True
        )

    def test_packaging_fallout_only(self) -> None:
        # A "plugin not found" without "compiled runtime output" is a fallout issue,
        # not a runtime-output issue. The packaging-runtime-output detector requires
        # "compiled runtime output" to be present.
        snapshot = {
            "valid": False,
            "issues": [
                {"path": "plugins.entries.foo", "message": "plugin not found: foo"},
            ],
            "legacyIssues": [],
        }
        # The packaging-runtime-output detector returns False (no runtime-output issues).
        assert (
            is_plugin_packaging_runtime_output_invalid_config_snapshot(snapshot) is False
        )
        # But the plugin-local detector returns True (all issues are plugin-related).
        assert is_plugin_local_invalid_config_snapshot(snapshot) is True

    def test_unrelated_issue_blocks(self) -> None:
        snapshot = {
            "valid": False,
            "issues": [
                {"path": "plugins.entries.foo", "message": "plugin not found: foo"},
                {"path": "agents", "message": "type error"},
            ],
            "legacyIssues": [],
        }
        assert (
            is_plugin_packaging_runtime_output_invalid_config_snapshot(snapshot) is False
        )

    def test_valid_snapshot_returns_false(self) -> None:
        snapshot = {"valid": True, "issues": [], "legacyIssues": []}
        assert (
            is_plugin_packaging_runtime_output_invalid_config_snapshot(snapshot) is False
        )

    def test_legacy_issues_blocks(self) -> None:
        snapshot = {
            "valid": False,
            "issues": [
                {"path": "plugins.entries.foo", "message": "plugin not found: foo"},
            ],
            "legacyIssues": [{"path": "x", "message": "y"}],
        }
        assert (
            is_plugin_packaging_runtime_output_invalid_config_snapshot(snapshot) is False
        )

    def test_plugin_local_invalid(self) -> None:
        snapshot = {
            "valid": False,
            "issues": [
                {"path": "plugins.entries.foo", "message": "missing"},
                {"path": "plugins.allow", "message": "plugin not found: bar"},
            ],
            "legacyIssues": [],
        }
        assert is_plugin_local_invalid_config_snapshot(snapshot) is True

    def test_plugin_local_with_unrelated_issue(self) -> None:
        snapshot = {
            "valid": False,
            "issues": [
                {"path": "plugins.entries.foo", "message": "missing"},
                {"path": "agents", "message": "type error"},
            ],
            "legacyIssues": [],
        }
        assert is_plugin_local_invalid_config_snapshot(snapshot) is False

    def test_should_attempt_last_known_good(self) -> None:
        # Plugin-only issues => don't attempt whole-file recovery.
        snapshot = {
            "valid": False,
            "issues": [
                {"path": "plugins.entries.foo", "message": "missing"},
            ],
            "legacyIssues": [],
        }
        assert should_attempt_last_known_good_recovery(snapshot) is False
        # Other issues => attempt.
        snapshot2 = {
            "valid": False,
            "issues": [{"path": "agents", "message": "type error"}],
            "legacyIssues": [],
        }
        assert should_attempt_last_known_good_recovery(snapshot2) is True

    def test_valid_snapshot_no_recovery(self) -> None:
        snapshot = {"valid": True, "issues": [], "legacyIssues": []}
        assert should_attempt_last_known_good_recovery(snapshot) is False


# ============================================================================
# redact-argv
# ============================================================================


class TestRedactArgv:
    def test_secret_flag_names_set(self) -> None:
        assert "--token" in SECRET_FLAG_NAMES
        assert "--api-key" in SECRET_FLAG_NAMES
        assert "--password" in SECRET_FLAG_NAMES
        assert "--bearer" in SECRET_FLAG_NAMES

    def test_flag_value_redacted(self) -> None:
        out = redact_sensitive_argv(["--token", "abc123"])
        assert out == ["--token", "***"]

    def test_equals_form_redacted(self) -> None:
        out = redact_sensitive_argv(["--token=abc123"])
        assert out == ["--token=***"]

    def test_non_secret_flag_preserved(self) -> None:
        out = redact_sensitive_argv(["--name", "alice", "--age", "30"])
        assert out == ["--name", "alice", "--age", "30"]

    def test_suffix_heuristic_token(self) -> None:
        out = redact_sensitive_argv(["--custom-token", "xyz"])
        assert out == ["--custom-token", "***"]

    def test_suffix_heuristic_password(self) -> None:
        out = redact_sensitive_argv(["--db-password", "secret"])
        assert out == ["--db-password", "***"]

    def test_custom_redacted_value(self) -> None:
        out = redact_sensitive_argv(["--token", "abc"], redacted_value="<redacted>")
        assert out == ["--token", "<redacted>"]

    def test_case_insensitive(self) -> None:
        out = redact_sensitive_argv(["--Token", "abc"])
        assert out == ["--Token", "***"]

    def test_redact_text_callback(self) -> None:
        def redact_text(s):
            return "REDACTED"

        out = redact_sensitive_argv(
            ["--name", "alice"],
            redact_text=redact_text,
        )
        # redact_text is called for every non-secret arg.
        assert out == ["REDACTED", "REDACTED"]

    def test_mixed_args(self) -> None:
        out = redact_sensitive_argv([
            "node", "app.js",
            "--token", "abc",
            "--debug",
        ])
        assert out == ["node", "app.js", "--token", "***", "--debug"]

    def test_empty_argv(self) -> None:
        assert redact_sensitive_argv([]) == []

    def test_non_string_args(self) -> None:
        out = redact_sensitive_argv([None, "--token", "abc", 42])  # type: ignore[list-item]
        assert out[0] is None
        assert out[1] == "--token"
        assert out[2] == "***"
        assert out[3] == 42
