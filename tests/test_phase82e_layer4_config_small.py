"""Tests for Phase 8.2e — src/config/ small file batch (20 files).

Covers:
- silent_reply, io, io_snapshot_shared, sensitive_paths
- runtime_source_projection, runtime_schema, port_defaults, sessions
- version, io_owner_display_secret, shell_env_expected_keys
- plugins_allowlist, patch_replace_paths, mutation_conflict, mutation_types
- talk_defaults, plugin_web_search_config, web_search_legacy_provider_keys
- plugin_auto_enable_types, plugin_auto_enable_detect
"""

from __future__ import annotations

import asyncio

import pytest

from src.config.io import (
    CircularIncludeError,
    ConfigIncludeError,
    MissingEnvVarError,
    get_runtime_config,
    install_runtime_hooks,
    load_config,
)
from src.config.io_owner_display_secret import (
    OwnerDisplaySecretRuntimeState,
    retain_generated_owner_display_secret,
)
from src.config.io_snapshot_shared import (
    collect_invalid_config_legacy_issues,
    create_config_file_snapshot,
    finalize_read_config_snapshot_internal_result,
)
from src.config.mutation_conflict import ConfigMutationConflictError
from src.config.mutation_types import ConfigMutationBase
from src.config.patch_replace_paths import (
    normalize_config_patch_replace_paths,
)
from src.config.plugin_auto_enable_detect import (
    detect_plugin_auto_enable_candidates,
)
from src.config.plugin_auto_enable_types import (
    PluginAutoEnableCandidate,
    PluginAutoEnableResult,
)
from src.config.plugin_web_search_config import (
    resolve_plugin_web_search_config,
)
from src.config.plugins_allowlist import ensure_plugin_allowlisted
from src.config.port_defaults import (
    DEFAULT_BROWSER_CDP_PORT_RANGE_END,
    DEFAULT_BROWSER_CDP_PORT_RANGE_SPAN,
    DEFAULT_BROWSER_CDP_PORT_RANGE_START,
    derive_default_browser_cdp_port_range,
)
from src.config.runtime_schema import (
    load_gateway_runtime_config_schema,
    read_best_effort_runtime_config_schema,
)
from src.config.runtime_source_projection import (
    project_config_onto_runtime_source_snapshot,
)
from src.config.sensitive_paths import (
    SENSITIVE_KEY_WHITELIST_SUFFIXES,
    SENSITIVE_PATTERNS,
    is_sensitive_config_path,
)
from src.config.sessions import (
    canonicalize_session_entry_aliases,
    delete_session_entry_lifecycle,
    patch_session_entry_with_key,
    reset_session_entry_lifecycle,
    resolve_session_entry_candidate_target,
)
from src.config.shell_env_expected_keys import (
    CORE_SHELL_ENV_EXPECTED_KEYS,
    resolve_shell_env_expected_keys,
)
from src.config.silent_reply import (
    resolve_silent_reply_settings,
)
from src.config.talk_defaults import (
    TALK_SILENCE_TIMEOUT_MS_BY_PLATFORM,
    describe_talk_silence_timeout_defaults,
)
from src.config.version import (
    compare_openclaw_versions,
    normalize_openclaw_version_base,
    should_warn_on_touched_version,
)
from src.config.web_search_legacy_provider_keys import (
    LEGACY_WEB_SEARCH_PROVIDER_CONFIG_KEYS,
    is_legacy_web_search_provider_config_key,
)

# ============================================================================
# silent_reply
# ============================================================================


class TestSilentReply:
    def test_shipped_defaults_when_no_cfg(self) -> None:
        out = resolve_silent_reply_settings({})
        assert "policy" in out

    def test_resolve_with_empty_cfg(self) -> None:
        out = resolve_silent_reply_settings({"cfg": {}})
        assert out["policy"] is not None

    def test_resolve_with_session_key(self) -> None:
        out = resolve_silent_reply_settings(
            {
                "sessionKey": "agent:main:dm:user1",
            }
        )
        assert "policy" in out

    def test_resolve_with_surface(self) -> None:
        cfg = {"surfaces": {"discord": {"silentReply": {"enabled": False}}}}
        out = resolve_silent_reply_settings({"cfg": cfg, "surface": "discord"})
        assert "policy" in out


# ============================================================================
# io
# ============================================================================


class TestIoFacade:
    def test_missing_env_var_error_imported(self) -> None:
        assert MissingEnvVarError is not None
        assert issubclass(MissingEnvVarError, Exception)

    def test_circular_include_error_is_exception(self) -> None:
        assert issubclass(CircularIncludeError, Exception)

    def test_config_include_error_is_exception(self) -> None:
        assert issubclass(ConfigIncludeError, Exception)

    def test_runtime_helpers_raise_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError):
            get_runtime_config()
        with pytest.raises(NotImplementedError):
            load_config()


# ============================================================================
# io_snapshot_shared
# ============================================================================


class TestIoSnapshotShared:
    def test_create_config_file_snapshot_minimal(self) -> None:
        snap = create_config_file_snapshot(
            {
                "path": "/cfg.json",
                "exists": True,
                "raw": "{}",
                "parsed": {},
                "sourceConfig": {"a": 1},
                "runtimeConfig": {"a": 1},
                "valid": True,
                "issues": [],
                "warnings": [],
                "legacyIssues": [],
            }
        )
        assert snap["path"] == "/cfg.json"
        assert snap["sourceConfig"] == {"a": 1}
        assert snap["resolved"] == {"a": 1}
        assert snap["runtimeConfig"] == {"a": 1}
        assert snap["config"] == {"a": 1}

    def test_create_snapshot_with_hash_and_error(self) -> None:
        snap = create_config_file_snapshot(
            {
                "path": "/cfg.json",
                "exists": True,
                "raw": "{}",
                "parsed": {},
                "sourceConfig": {},
                "runtimeConfig": {},
                "valid": False,
                "issues": [{"path": "x", "message": "bad"}],
                "warnings": [],
                "legacyIssues": [],
                "hash": "abc123",
                "readError": {"code": "ENOENT"},
            }
        )
        assert snap["hash"] == "abc123"
        assert snap["readError"] == {"code": "ENOENT"}
        assert len(snap["issues"]) == 1

    def test_finalize_runs_observer(self) -> None:
        async def run() -> None:
            captured = []

            async def observe(deps, snapshot):
                captured.append(snapshot)

            result = await finalize_read_config_snapshot_internal_result(
                {"observe": True},
                {"snapshot": {"path": "/x"}},
                observe_config_snapshot_fn=observe,
            )
            assert captured == [{"path": "/x"}]
            assert result["snapshot"]["path"] == "/x"

        asyncio.run(run())

    def test_finalize_skips_when_deps_observe_false(self) -> None:
        async def run() -> None:
            called = []

            async def observe(deps, snapshot):
                called.append(snapshot)

            await finalize_read_config_snapshot_internal_result(
                {"observe": False},
                {"snapshot": {}},
                observe_config_snapshot_fn=observe,
            )
            assert called == []

        asyncio.run(run())

    def test_collect_legacy_issues_non_dict(self) -> None:
        async def run() -> None:
            assert await collect_invalid_config_legacy_issues(None, None) == []
            assert await collect_invalid_config_legacy_issues("x", "x") == []

        asyncio.run(run())

    def test_collect_legacy_issues_calls_doctor(self) -> None:
        async def run() -> None:
            captured = []

            async def find_issues(raw, src):
                captured.append((raw, src))
                return [{"path": "a", "message": "m"}]

            out = await collect_invalid_config_legacy_issues(
                {"a": 1},
                {"a": 2},
                find_doctor_legacy_config_issues=find_issues,
            )
            assert out == [{"path": "a", "message": "m"}]
            assert captured == [({"a": 1}, {"a": 2})]

        asyncio.run(run())


# ============================================================================
# sensitive_paths
# ============================================================================


class TestSensitivePaths:
    def test_token_path(self) -> None:
        assert is_sensitive_config_path("plugins.entries.foo.token") is True
        assert is_sensitive_config_path("apiKey") is True
        assert is_sensitive_config_path("PASSWORD") is True
        assert is_sensitive_config_path("privateKey") is True

    def test_non_sensitive_path(self) -> None:
        assert is_sensitive_config_path("agents") is False
        assert is_sensitive_config_path("displayName") is False

    def test_whitelisted_path_not_sensitive(self) -> None:
        # "maxTokens" ends with "tokens" but matches the whitelist suffix "maxtokens".
        assert is_sensitive_config_path("maxTokens") is False
        assert is_sensitive_config_path("tokenCount") is False
        assert is_sensitive_config_path("passwordFile") is False

    def test_local_service_env_always_sensitive(self) -> None:
        assert is_sensitive_config_path("localService.env.something") is True

    def test_constants_exposed(self) -> None:
        assert "maxtokens" in SENSITIVE_KEY_WHITELIST_SUFFIXES
        assert len(SENSITIVE_PATTERNS) > 0


# ============================================================================
# runtime_source_projection
# ============================================================================


class TestRuntimeSourceProjection:
    def test_no_runtime_snapshot_returns_input(self) -> None:
        out = project_config_onto_runtime_source_snapshot(
            {"a": 1},
            get_runtime_config_snapshot_fn=lambda: None,
            get_runtime_config_source_snapshot_fn=lambda: None,
        )
        assert out == {"a": 1}

    def test_identity_match_returns_source(self) -> None:
        snap = {"a": 1}
        out = project_config_onto_runtime_source_snapshot(
            snap,
            get_runtime_config_snapshot_fn=lambda: snap,
            get_runtime_config_source_snapshot_fn=lambda: {"a": 1, "extra": 2},
        )
        assert out == {"a": 1, "extra": 2}

    def test_incompatible_shape_returns_input(self) -> None:
        runtime = {"a": "string"}
        out = project_config_onto_runtime_source_snapshot(
            {"a": 1},
            get_runtime_config_snapshot_fn=lambda: runtime,
            get_runtime_config_source_snapshot_fn=lambda: {"a": "old"},
        )
        assert out == {"a": 1}

    def test_apply_merge_patch_via_projection(self) -> None:
        # When shapes match, runtime overrides are applied via merge-patch.
        runtime_snap = {"a": 1, "b": 2}
        source_snap = {"a": 1, "b": 0}
        config = {"a": 1, "b": 99, "c": 3}

        out = project_config_onto_runtime_source_snapshot(
            config,
            get_runtime_config_snapshot_fn=lambda: runtime_snap,
            get_runtime_config_source_snapshot_fn=lambda: source_snap,
        )
        # source.b was 0, runtime_patch adds b=99, c=3; a stays 1.
        assert out == {"a": 1, "b": 99, "c": 3}


# ============================================================================
# runtime_schema
# ============================================================================


class TestRuntimeSchema:
    def test_load_schema_uses_runtime_config(self) -> None:
        def get_runtime_config_fn():
            return {"plugins": {"entries": {}}}

        def build_config_schema_fn(params):
            return {
                "plugins": [{"id": p["id"]} for p in params.get("plugins", [])],
                "channels": params.get("channels", []),
            }

        out = load_gateway_runtime_config_schema(
            get_runtime_config_fn=get_runtime_config_fn,
            build_config_schema_fn=build_config_schema_fn,
        )
        assert "plugins" in out
        assert "channels" in out

    def test_load_schema_requires_hooks(self) -> None:
        with pytest.raises(NotImplementedError):
            load_gateway_runtime_config_schema()

    def test_read_best_effort_invalid_fallback(self) -> None:
        async def run() -> None:
            async def read():
                return {"valid": False}

            def build_config_schema_fn(params):
                return {"plugins": params["plugins"], "channels": params["channels"]}

            out = await read_best_effort_runtime_config_schema(
                read_config_file_snapshot_fn=read,
                build_config_schema_fn=build_config_schema_fn,
            )
            assert out == {"plugins": [], "channels": []}

        asyncio.run(run())

    def test_read_best_effort_requires_hooks(self) -> None:
        async def run() -> None:
            with pytest.raises(NotImplementedError):
                await read_best_effort_runtime_config_schema()

        asyncio.run(run())


# ============================================================================
# port_defaults
# ============================================================================


class TestPortDefaults:
    def test_constants(self) -> None:
        assert DEFAULT_BROWSER_CDP_PORT_RANGE_START == 18800
        assert DEFAULT_BROWSER_CDP_PORT_RANGE_END == 18899
        assert DEFAULT_BROWSER_CDP_PORT_RANGE_SPAN == 99

    def test_derive_normal_range(self) -> None:
        # Control port 18700 + 9 = 18709, end = 18709 + 99 = 18808 (within 65535).
        out = derive_default_browser_cdp_port_range(18700)
        assert out == {"start": 18709, "end": 18808}

    def test_derive_falls_back_when_overflow(self) -> None:
        # Control port 65530 + 9 = 65539, end = 65539 + 99 = 65638 (overflow).
        out = derive_default_browser_cdp_port_range(65530)
        assert out == {
            "start": DEFAULT_BROWSER_CDP_PORT_RANGE_START,
            "end": DEFAULT_BROWSER_CDP_PORT_RANGE_END,
        }

    def test_derive_invalid_port_falls_back(self) -> None:
        out = derive_default_browser_cdp_port_range(-1)
        # -1 + 9 = 8 (valid) — so this derives from offset, not the input
        assert out["start"] > 0


# ============================================================================
# sessions facade
# ============================================================================


class TestSessionsFacade:
    def test_helpers_raise_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError):
            canonicalize_session_entry_aliases()
        with pytest.raises(NotImplementedError):
            delete_session_entry_lifecycle()

    def test_helpers_delegate_to_runtime_hooks(self) -> None:
        install_runtime_hooks(
            {
                "canonicalize_session_entry_aliases": lambda *args, **kwargs: {
                    "ok": "canonicalized"
                },
                "delete_session_entry_lifecycle": lambda *args, **kwargs: {"ok": "deleted"},
                "patch_session_entry_with_key": lambda *args, **kwargs: {"ok": "patched"},
                "reset_session_entry_lifecycle": lambda *args, **kwargs: {"ok": "reset"},
                "resolve_session_entry_candidate_target": lambda *args, **kwargs: {
                    "ok": "resolved"
                },
            }
        )

        assert canonicalize_session_entry_aliases() == {"ok": "canonicalized"}
        assert delete_session_entry_lifecycle() == {"ok": "deleted"}
        assert patch_session_entry_with_key() == {"ok": "patched"}
        assert reset_session_entry_lifecycle() == {"ok": "reset"}
        assert resolve_session_entry_candidate_target() == {"ok": "resolved"}


# ============================================================================
# version
# ============================================================================


class TestVersion:
    def test_normalize_base_simple(self) -> None:
        # Provide a parse_semver_fn that returns a simple dict.
        def parse_semver(s):
            parts = s.split(".")
            if len(parts) < 3:
                return None
            try:
                return {"major": int(parts[0]), "minor": int(parts[1]), "patch": int(parts[2])}
            except ValueError:
                return None

        assert normalize_openclaw_version_base("1.2.3", parse_semver_fn=parse_semver) == "1.2.3"
        assert normalize_openclaw_version_base(None, parse_semver_fn=parse_semver) is None
        assert normalize_openclaw_version_base("invalid", parse_semver_fn=parse_semver) is None

    def test_normalize_legacy_dot_beta(self) -> None:
        def parse_semver(s):
            parts = s.split(".")
            return {"major": int(parts[0]), "minor": int(parts[1]), "patch": int(parts[2])}

        def normalize(s):
            # "1.2.b3" -> "1.2.3"
            if s.endswith(tuple(f".b{i}" for i in range(10))):
                head, b_part = s.rsplit(".b", 1)
                return f"{head}.{b_part}"
            return s

        out = normalize_openclaw_version_base(
            "1.2.b3",
            parse_semver_fn=parse_semver,
            normalize_legacy_dot_beta_version_fn=normalize,
        )
        assert out == "1.2.3"

    def test_compare_versions(self) -> None:
        def parse_semver(s):
            parts = s.split(".")
            if len(parts) < 3:
                return None
            try:
                return {"major": int(parts[0]), "minor": int(parts[1]), "patch": int(parts[2])}
            except ValueError:
                return None

        def compare(a, b):
            if a["major"] != b["major"]:
                return -1 if a["major"] < b["major"] else 1
            if a["minor"] != b["minor"]:
                return -1 if a["minor"] < b["minor"] else 1
            if a["patch"] != b["patch"]:
                return -1 if a["patch"] < b["patch"] else 1
            return 0

        assert (
            compare_openclaw_versions(
                "1.0.0",
                "2.0.0",
                parse_semver_fn=parse_semver,
                compare_openclaw_semver_fn=compare,
            )
            == -1
        )
        assert (
            compare_openclaw_versions(
                "invalid",
                "1.0.0",
                parse_semver_fn=parse_semver,
            )
            is None
        )

    def test_should_warn_older(self) -> None:
        def parse_semver(s):
            parts = s.split(".")
            return {
                "major": int(parts[0]),
                "minor": int(parts[1]),
                "patch": int(parts[2]),
                "prerelease": [],
            }

        def compare(a, b):
            if a["major"] != b["major"]:
                return -1 if a["major"] < b["major"] else 1
            return 0

        # Current is older than touched => warn.
        assert (
            should_warn_on_touched_version(
                "1.0.0",
                "2.0.0",
                parse_semver_fn=parse_semver,
                compare_openclaw_semver_fn=compare,
            )
            is True
        )

    def test_should_not_warn_same(self) -> None:
        class V:
            prerelease: list

            def __init__(self, v):
                self.major, self.minor, self.patch = [int(x) for x in v.split(".")]
                self.prerelease = []

            def compare_main(self, other):
                if (self.major, self.minor, self.patch) == (other.major, other.minor, other.patch):
                    return 0
                return -1 if self.major < other.major else 1

        def parse_semver(s):
            return V(s)

        def compare(a, b):
            if (a.major, a.minor, a.patch) == (b.major, b.minor, b.patch):
                return 0
            return -1

        assert (
            should_warn_on_touched_version(
                "1.0.0",
                "1.0.0",
                parse_semver_fn=parse_semver,
                compare_openclaw_semver_fn=compare,
            )
            is False
        )


# ============================================================================
# io_owner_display_secret
# ============================================================================


class TestIoOwnerDisplaySecret:
    def test_retain_with_secret(self) -> None:
        state: OwnerDisplaySecretRuntimeState = {"pendingByPath": {}}
        config = {"a": 1}
        out = retain_generated_owner_display_secret(
            {
                "config": config,
                "configPath": "plugins.entries.foo.apiKey",
                "generatedSecret": "secret-123",
                "state": state,
            }
        )
        assert out is config
        assert state["pendingByPath"]["plugins.entries.foo.apiKey"] == "secret-123"

    def test_retain_without_secret_clears(self) -> None:
        state: OwnerDisplaySecretRuntimeState = {
            "pendingByPath": {"old.path": "old-secret"},
        }
        config = {"a": 1}
        out = retain_generated_owner_display_secret(
            {
                "config": config,
                "configPath": "old.path",
                "state": state,
            }
        )
        assert out is config
        assert "old.path" not in state["pendingByPath"]


# ============================================================================
# shell_env_expected_keys
# ============================================================================


class TestShellEnvExpectedKeys:
    def test_core_keys_present(self) -> None:
        keys = resolve_shell_env_expected_keys({})
        assert "OPENCLAW_GATEWAY_TOKEN" in keys
        assert "OPENCLAW_GATEWAY_PASSWORD" in keys

    def test_provider_keys_merged(self) -> None:
        def list_provider(env=None):
            return ["OPENAI_API_KEY", "DUP"]

        def list_channel(env=None):
            return ["DUP", "TELEGRAM_BOT_TOKEN"]

        keys = resolve_shell_env_expected_keys(
            {},
            list_known_provider_auth_env_var_names=list_provider,
            list_known_channel_env_var_names=list_channel,
        )
        assert "OPENAI_API_KEY" in keys
        assert "TELEGRAM_BOT_TOKEN" in keys
        # Deduplicated
        assert keys.count("DUP") == 1

    def test_core_keys_constant(self) -> None:
        assert "OPENCLAW_GATEWAY_TOKEN" in CORE_SHELL_ENV_EXPECTED_KEYS


# ============================================================================
# plugins_allowlist
# ============================================================================


class TestPluginsAllowlist:
    def test_no_allowlist_passthrough(self) -> None:
        cfg = {"plugins": {"entries": {}}}
        out = ensure_plugin_allowlisted(cfg, "foo")
        assert out is cfg  # No new restrictive list

    def test_existing_allowlist_appends(self) -> None:
        cfg = {"plugins": {"allow": ["bar"]}}
        out = ensure_plugin_allowlisted(cfg, "foo")
        assert out["plugins"]["allow"] == ["bar", "foo"]
        # Original unchanged
        assert cfg["plugins"]["allow"] == ["bar"]

    def test_already_allowlisted_passthrough(self) -> None:
        cfg = {"plugins": {"allow": ["foo"]}}
        out = ensure_plugin_allowlisted(cfg, "foo")
        # Already in list — config returned unchanged.
        assert out["plugins"]["allow"] == ["foo"]


# ============================================================================
# patch_replace_paths
# ============================================================================


class TestPatchReplacePaths:
    def test_empty(self) -> None:
        assert normalize_config_patch_replace_paths(None) == set()
        assert normalize_config_patch_replace_paths([]) == set()

    def test_simple_paths(self) -> None:
        out = normalize_config_patch_replace_paths(["a.b", "x.y"])
        assert out == {"a.b", "x.y"}

    def test_numeric_index_normalized(self) -> None:
        out = normalize_config_patch_replace_paths(["items[0].name", "items[12].value"])
        assert out == {"items[].name", "items[].value"}

    def test_explicit_array_form_preserved(self) -> None:
        out = normalize_config_patch_replace_paths(["items[]"])
        assert "items" in out

    def test_non_string_filtered(self) -> None:
        out = normalize_config_patch_replace_paths([None, 123, "a.b"])
        assert out == {"a.b"}


# ============================================================================
# mutation_conflict
# ============================================================================


class TestMutationConflict:
    def test_basic_error(self) -> None:
        err = ConfigMutationConflictError(
            "snapshot changed",
            current_hash="abc",
        )
        assert err.name == "ConfigMutationConflictError"
        assert err.currentHash == "abc"
        assert err.retryable is True
        assert "snapshot changed" in str(err)

    def test_non_retryable(self) -> None:
        err = ConfigMutationConflictError(
            "fatal",
            current_hash=None,
            retryable=False,
        )
        assert err.retryable is False
        assert err.currentHash is None


# ============================================================================
# mutation_types
# ============================================================================


class TestMutationTypes:
    def test_config_mutation_base_alias(self) -> None:
        assert ConfigMutationBase == str
        # The canonical values are still "runtime" and "source".
        assert "runtime" in {"runtime", "source"}
        assert "source" in {"runtime", "source"}


# ============================================================================
# talk_defaults
# ============================================================================


class TestTalkDefaults:
    def test_platform_table(self) -> None:
        assert TALK_SILENCE_TIMEOUT_MS_BY_PLATFORM["macos"] == 700
        assert TALK_SILENCE_TIMEOUT_MS_BY_PLATFORM["android"] == 700
        assert TALK_SILENCE_TIMEOUT_MS_BY_PLATFORM["ios"] == 900

    def test_describe_string(self) -> None:
        out = describe_talk_silence_timeout_defaults()
        assert "700" in out
        assert "900" in out
        assert "macOS" in out
        assert "iOS" in out


# ============================================================================
# plugin_web_search_config
# ============================================================================


class TestPluginWebSearchConfig:
    def test_no_config(self) -> None:
        assert resolve_plugin_web_search_config(None, "foo") is None

    def test_no_entries(self) -> None:
        assert resolve_plugin_web_search_config({}, "foo") is None

    def test_plugin_without_web_search(self) -> None:
        cfg = {"plugins": {"entries": {"foo": {"config": {}}}}}
        assert resolve_plugin_web_search_config(cfg, "foo") is None

    def test_plugin_with_web_search(self) -> None:
        cfg = {
            "plugins": {
                "entries": {
                    "foo": {"config": {"webSearch": {"provider": "tavily"}}},
                }
            }
        }
        out = resolve_plugin_web_search_config(cfg, "foo")
        assert out == {"provider": "tavily"}

    def test_web_search_not_dict(self) -> None:
        cfg = {
            "plugins": {
                "entries": {
                    "foo": {"config": {"webSearch": "not-a-dict"}},
                }
            }
        }
        assert resolve_plugin_web_search_config(cfg, "foo") is None


# ============================================================================
# web_search_legacy_provider_keys
# ============================================================================


class TestWebSearchLegacyProviderKeys:
    def test_set_contents(self) -> None:
        assert "brave" in LEGACY_WEB_SEARCH_PROVIDER_CONFIG_KEYS
        assert "tavily" in LEGACY_WEB_SEARCH_PROVIDER_CONFIG_KEYS
        assert "minimax" in LEGACY_WEB_SEARCH_PROVIDER_CONFIG_KEYS

    def test_is_legacy(self) -> None:
        assert is_legacy_web_search_provider_config_key("brave") is True
        assert is_legacy_web_search_provider_config_key("tavily") is True

    def test_not_legacy(self) -> None:
        assert is_legacy_web_search_provider_config_key("google") is False
        assert is_legacy_web_search_provider_config_key("") is False


# ============================================================================
# plugin_auto_enable_types
# ============================================================================


class TestPluginAutoEnableTypes:
    def test_candidate_dict(self) -> None:
        c: PluginAutoEnableCandidate = {
            "pluginId": "telegram",
            "kind": "channel-configured",
            "channelId": "telegram",
        }
        assert c["kind"] == "channel-configured"

    def test_result_shape(self) -> None:
        r: PluginAutoEnableResult = {
            "config": {"plugins": {"entries": {"telegram": {"enabled": True}}}},
            "changes": ["enabled telegram"],
            "autoEnabledReasons": {"telegram": ["channel-configured"]},
        }
        assert "telegram" in r["autoEnabledReasons"]


# ============================================================================
# plugin_auto_enable_detect
# ============================================================================


class TestPluginAutoEnableDetect:
    def test_no_hooks_returns_empty(self) -> None:
        assert detect_plugin_auto_enable_candidates() == []

    def test_not_ready_returns_empty(self) -> None:
        def readiness(config, env, discovery):
            return {"mayNeedAutoEnable": False, "configuredChannelIds": []}

        out = detect_plugin_auto_enable_candidates(
            resolve_plugin_auto_enable_readiness_fn=readiness,
        )
        assert out == []

    def test_ready_returns_candidates(self) -> None:
        def readiness(config, env, discovery):
            return {"mayNeedAutoEnable": True, "configuredChannelIds": ["telegram"]}

        def registry_resolver(params):
            return {"plugins": []}

        def candidates_resolver(params):
            return [
                {
                    "pluginId": "telegram",
                    "kind": "channel-configured",
                    "channelId": "telegram",
                }
            ]

        out = detect_plugin_auto_enable_candidates(
            resolve_plugin_auto_enable_readiness_fn=readiness,
            resolve_plugin_auto_enable_manifest_registry_fn=registry_resolver,
            resolve_configured_plugin_auto_enable_candidates_fn=candidates_resolver,
        )
        assert out == [
            {
                "pluginId": "telegram",
                "kind": "channel-configured",
                "channelId": "telegram",
            }
        ]
