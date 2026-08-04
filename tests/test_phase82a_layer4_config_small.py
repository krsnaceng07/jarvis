"""Tests for Phase 8.2a — src/config/ small file batch (20 files)."""
from __future__ import annotations

import os
import sys
import tempfile

import pytest

from src.config.agent_dirs import (
    DEFAULT_AGENT_ID,
    DuplicateAgentDirError,
    find_duplicate_agent_dirs,
    format_duplicate_agent_dir_error,
    normalize_agent_id,
    resolve_effective_agent_dir,
)
from src.config.agent_limits import (
    DEFAULT_AGENT_MAX_CONCURRENT,
    DEFAULT_SUBAGENT_MAX_CONCURRENT,
    resolve_agent_max_concurrent,
    resolve_subagent_max_concurrent,
)
from src.config.allowed_values import (
    append_allowed_values_hint,
    summarize_allowed_values,
)
from src.config.backup_rotation import (
    CONFIG_BACKUP_COUNT,
    create_pre_update_config_snapshot,
    harden_backup_permissions,
    maintain_config_backups,
    rotate_config_backups,
)
from src.config.bindings import (
    is_acp_binding,
    is_route_binding,
    list_acp_bindings,
    list_configured_bindings,
    list_route_bindings,
)
from src.config.byte_size import (
    is_valid_non_negative_byte_size_string,
    parse_byte_size,
    parse_non_negative_byte_size,
)
from src.config.cache_utils import (
    ExpiringMapCache,
    get_file_stat_snapshot,
    is_cache_enabled,
    resolve_cache_ttl_ms,
)
from src.config.channel_capabilities import resolve_channel_capabilities
from src.config.channel_configured import (
    has_meaningful_channel_config_shallow,
    is_channel_configured,
    resolve_channel_config_record,
)
from src.config.commands import (
    is_native_commands_explicitly_disabled,
    resolve_native_commands_enabled,
    resolve_native_skills_enabled,
)
from src.config.commands_flags import (
    is_command_flag_enabled,
    is_restart_enabled,
)
from src.config.config_paths import (
    get_config_value_at_path,
    parse_config_path,
    set_config_value_at_path,
    unset_config_value_at_path,
)
from src.config.context_visibility import (
    resolve_channel_context_visibility_mode,
    resolve_default_context_visibility,
)
from src.config.control_ui_css import (
    is_valid_control_ui_chat_message_max_width,
    normalize_control_ui_chat_message_max_width,
)
from src.config.cron_limits import (
    DEFAULT_CRON_MAX_CONCURRENT_RUNS,
    DEFAULT_CRON_TRIGGER_MIN_INTERVAL_MS,
    resolve_cron_max_concurrent_runs,
    resolve_cron_trigger_min_interval_ms,
)
from src.config.dangerous_name_matching import (
    collect_provider_dangerous_name_matching_scopes,
    is_dangerous_name_matching_enabled,
    resolve_dangerous_name_matching_enabled,
)


# ============================================================================
# agent-dirs
# ============================================================================


class TestAgentDirs:
    def test_normalize_agent_id(self) -> None:
        assert normalize_agent_id("ALICE") == "alice"
        assert normalize_agent_id("  bob  ") == "bob"
        assert normalize_agent_id("") == DEFAULT_AGENT_ID
        assert normalize_agent_id(None) == DEFAULT_AGENT_ID  # type: ignore[arg-type]

    def test_resolve_effective_agent_dir_default(self) -> None:
        cfg: dict = {}
        out = resolve_effective_agent_dir(cfg, "main", env={}, homedir=lambda: "/home/test")
        assert out.endswith(os.path.join("agents", "main", "agent"))

    def test_resolve_effective_agent_dir_configured(self) -> None:
        cfg = {"agents": {"list": [{"id": "main", "agentDir": "/custom/dir"}]}}
        out = resolve_effective_agent_dir(cfg, "main", env={}, homedir=lambda: "/home/test")
        assert out == "/custom/dir"

    def test_find_duplicate_agent_dirs_none(self) -> None:
        cfg: dict = {}
        assert find_duplicate_agent_dirs(cfg, env={}, homedir=lambda: "/home/test") == []

    def test_find_duplicate_agent_dirs_found(self) -> None:
        cfg = {
            "agents": {
                "list": [
                    {"id": "a", "agentDir": "/shared"},
                    {"id": "b", "agentDir": "/shared"},
                ]
            }
        }
        dups = find_duplicate_agent_dirs(cfg, env={}, homedir=lambda: "/home/test")
        assert len(dups) == 1
        assert "a" in dups[0]["agentIds"]
        assert "b" in dups[0]["agentIds"]

    def test_format_duplicate_error(self) -> None:
        msg = format_duplicate_agent_dir_error([
            {"agentDir": "/shared", "agentIds": ["a", "b"]}
        ])
        assert "Duplicate" in msg
        assert '"a"' in msg
        assert '"b"' in msg

    def test_duplicate_error_class(self) -> None:
        err = DuplicateAgentDirError([{"agentDir": "/x", "agentIds": ["a", "b"]}])
        assert err.duplicates[0]["agentDir"] == "/x"
        assert "Duplicate" in str(err)


# ============================================================================
# agent-limits
# ============================================================================


class TestAgentLimits:
    def test_constants(self) -> None:
        assert DEFAULT_AGENT_MAX_CONCURRENT == 4
        assert DEFAULT_SUBAGENT_MAX_CONCURRENT == 8

    def test_resolve_default(self) -> None:
        assert resolve_agent_max_concurrent({}) == 4
        assert resolve_subagent_max_concurrent({}) == 8

    def test_resolve_explicit(self) -> None:
        cfg = {"agents": {"defaults": {"maxConcurrent": 16}}}
        assert resolve_agent_max_concurrent(cfg) == 16

    def test_resolve_floor(self) -> None:
        cfg = {"agents": {"defaults": {"maxConcurrent": 0}}}
        assert resolve_agent_max_concurrent(cfg) == 1


# ============================================================================
# allowed-values
# ============================================================================


class TestAllowedValues:
    def test_empty(self) -> None:
        assert summarize_allowed_values([]) is None

    def test_basic(self) -> None:
        out = summarize_allowed_values(["a", "b", "c"])
        assert out is not None
        assert out["values"] == ["a", "b", "c"]
        assert out["hiddenCount"] == 0

    def test_dedup(self) -> None:
        out = summarize_allowed_values(["a", "a", "b"])
        assert out["values"] == ["a", "b"]

    def test_hidden_count(self) -> None:
        out = summarize_allowed_values([f"v{i}" for i in range(20)])
        assert out["hiddenCount"] == 20 - 12

    def test_mixed_types(self) -> None:
        out = summarize_allowed_values([1, "1", None])
        # Numeric 1 and string "1" are distinct types, both kept.
        # Note: numeric values go through safeStringify in the value
        # field, so the `value` for the int 1 is the string "1".
        assert "1" in out["values"]  # both the int 1 and the string "1" serialize to "1"
        assert "" in out["values"]  # None serializes to ""

    def test_append_hint(self) -> None:
        s = summarize_allowed_values(["a", "b"])
        msg = append_allowed_values_hint("Bad value", s)
        assert "Bad value" in msg
        assert "allowed:" in msg

    def test_append_skipped_when_present(self) -> None:
        s = summarize_allowed_values(["a"])
        msg = append_allowed_values_hint("Bad (allowed: x)", s)
        assert msg == "Bad (allowed: x)"


# ============================================================================
# backup-rotation
# ============================================================================


class _FakeFs:
    def __init__(self) -> None:
        self.files: dict = {}
        self.calls: list = []

    async def unlink(self, path: str) -> None:
        self.calls.append(("unlink", path))
        self.files.pop(path, None)

    async def rename(self, src: str, dst: str) -> None:
        self.calls.append(("rename", src, dst))
        if src in self.files:
            self.files[dst] = self.files.pop(src)

    async def copy_file(self, src: str, dst: str) -> None:
        self.calls.append(("copy", src, dst))
        self.files[dst] = self.files.get(src, "")

    async def chmod(self, path: str, mode: int) -> None:
        self.calls.append(("chmod", path, mode))

    async def readdir(self, path: str) -> list:
        return [os.path.basename(p) for p in self.files.keys() if os.path.dirname(p) == path]


class TestBackupRotation:
    def test_constants(self) -> None:
        assert CONFIG_BACKUP_COUNT == 5

    @pytest.mark.asyncio
    async def test_rotate(self) -> None:
        fs = _FakeFs()
        # Pre-populate the .bak ring AND the primary .bak so rotation can
        # move .bak → .bak.1.
        fs.files["/cfg.json.bak"] = "primary"
        fs.files["/cfg.json.bak.1"] = "a"
        fs.files["/cfg.json.bak.2"] = "b"
        await rotate_config_backups("/cfg.json", fs)
        # b→3, a→2, primary→1, slot 4 deleted (or never existed).
        assert "/cfg.json.bak.3" in fs.files  # b shifted to 3
        assert "/cfg.json.bak.2" in fs.files  # a shifted to 2
        assert "/cfg.json.bak.1" in fs.files  # primary shifted to 1
        assert fs.files["/cfg.json.bak.1"] == "primary"

    @pytest.mark.asyncio
    async def test_maintain_full(self) -> None:
        fs = _FakeFs()
        fs.files["/cfg.json"] = "primary"
        await maintain_config_backups("/cfg.json", fs)
        assert fs.files["/cfg.json.bak"] == "primary"

    @pytest.mark.asyncio
    async def test_harden_permissions(self) -> None:
        fs = _FakeFs()
        fs.files["/cfg.json.bak"] = "x"
        await harden_backup_permissions("/cfg.json", fs)
        chmod_calls = [c for c in fs.calls if c[0] == "chmod"]
        assert any(c[1] == "/cfg.json.bak" and c[2] == 0o600 for c in chmod_calls)

    @pytest.mark.asyncio
    async def test_pre_update_snapshot(self) -> None:
        # The snapshot function needs a sync exists_sync and async read_file/write_file.
        class _SnapshotFs:
            def __init__(self):
                self.files = {"/cfg.json": "original"}

            def exists_sync(self, path):
                return path in self.files

            async def read_file(self, path, encoding):
                return self.files[path]

            async def write_file(self, path, content, **kwargs):
                self.files[path] = content

        fs = _SnapshotFs()
        await create_pre_update_config_snapshot({"configPath": "/cfg.json", "fs": fs})
        assert "/cfg.json.pre-update" in fs.files
        assert fs.files["/cfg.json.pre-update"] == "original"


# ============================================================================
# bindings
# ============================================================================


class TestBindings:
    def test_list_empty(self) -> None:
        assert list_configured_bindings({}) == []
        assert list_route_bindings({}) == []
        assert list_acp_bindings({}) == []

    def test_list_filtered(self) -> None:
        cfg = {
            "bindings": [
                {"agentId": "a", "match": {}},
                {"type": "acp", "agentId": "b", "cursor": {}},
                {"agentId": "c", "match": {}},
            ]
        }
        assert len(list_configured_bindings(cfg)) == 3
        assert len(list_route_bindings(cfg)) == 2
        assert len(list_acp_bindings(cfg)) == 1

    def test_route_type_default(self) -> None:
        assert is_route_binding({"agentId": "a", "match": {}}) is True
        assert is_acp_binding({"agentId": "a", "match": {}}) is False

    def test_acp_type(self) -> None:
        assert is_acp_binding({"type": "acp", "agentId": "b"}) is True
        assert is_route_binding({"type": "acp", "agentId": "b"}) is False


# ============================================================================
# byte-size
# ============================================================================


class TestByteSize:
    def test_parse_bytes(self) -> None:
        assert parse_byte_size("100") == 100
        assert parse_byte_size("100b") == 100

    def test_parse_kb_mb(self) -> None:
        assert parse_byte_size("2kb") == 2048
        assert parse_byte_size("2mb") == 2 * 1024 * 1024
        assert parse_byte_size("1.5mb") == int(1.5 * 1024 * 1024)

    def test_parse_gb(self) -> None:
        assert parse_byte_size("1gb") == 1024 * 1024 * 1024

    def test_invalid(self) -> None:
        with pytest.raises(ValueError):
            parse_byte_size("abc")

    def test_parse_non_negative_number(self) -> None:
        assert parse_non_negative_byte_size(1024) == 1024
        assert parse_non_negative_byte_size(0) == 0
        assert parse_non_negative_byte_size(-1) is None
        assert parse_non_negative_byte_size("invalid") is None
        assert parse_non_negative_byte_size(None) is None

    def test_parse_non_negative_string(self) -> None:
        assert parse_non_negative_byte_size("1mb") == 1024 * 1024
        assert parse_non_negative_byte_size("") is None

    def test_is_valid(self) -> None:
        assert is_valid_non_negative_byte_size_string("1mb") is True
        assert is_valid_non_negative_byte_size_string("garbage") is False


# ============================================================================
# cache-utils
# ============================================================================


class TestCacheUtils:
    def test_resolve_ttl_env(self) -> None:
        assert resolve_cache_ttl_ms(env_value="5000", default_ttl_ms=1000) == 5000
        assert resolve_cache_ttl_ms(env_value="garbage", default_ttl_ms=1000) == 1000
        assert resolve_cache_ttl_ms(env_value=None, default_ttl_ms=1000) == 1000

    def test_is_cache_enabled(self) -> None:
        assert is_cache_enabled(0) is False
        assert is_cache_enabled(1) is True
        assert is_cache_enabled(-1) is False

    def test_expiring_map_cache_basic(self) -> None:
        clock = [1000]
        cache = ExpiringMapCache[str, int](ttl_ms=100, clock=lambda: clock[0])
        cache.set("a", 1)
        assert cache.get("a") == 1
        # OpenClaw uses strict > so equal-difference is still alive.
        clock[0] = 1100  # 100ms past TTL exactly
        assert cache.get("a") == 1
        clock[0] = 1101  # 101ms past TTL — expired
        assert cache.get("a") is None

    def test_expiring_map_cache_size(self) -> None:
        cache = ExpiringMapCache[str, int](ttl_ms=1000, clock=lambda: 0)
        cache.set("a", 1)
        cache.set("b", 2)
        assert cache.size() == 2
        assert set(cache.keys()) == {"a", "b"}

    def test_expiring_map_cache_clear(self) -> None:
        cache = ExpiringMapCache[str, int](ttl_ms=1000, clock=lambda: 0)
        cache.set("a", 1)
        cache.clear()
        assert cache.get("a") is None
        assert cache.size() == 0

    def test_expiring_map_cache_disabled(self) -> None:
        cache = ExpiringMapCache[str, int](ttl_ms=0, clock=lambda: 0)
        cache.set("a", 1)
        assert cache.get("a") is None

    def test_file_stat_snapshot(self) -> None:
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"x" * 100)
            path = f.name
        try:
            snap = get_file_stat_snapshot(path)
            assert snap is not None
            assert snap["size_bytes"] == 100
        finally:
            os.unlink(path)

    def test_file_stat_missing(self) -> None:
        assert get_file_stat_snapshot("/nonexistent/abc/xyz") is None


# ============================================================================
# channel-capabilities
# ============================================================================


class TestChannelCapabilities:
    def test_missing_channel(self) -> None:
        assert resolve_channel_capabilities({"cfg": {}, "channel": None}) is None

    def test_string_array(self) -> None:
        cfg = {"channels": {"telegram": {"capabilities": ["inline_buttons", "threads"]}}}
        out = resolve_channel_capabilities({"cfg": cfg, "channel": "telegram"})
        assert out == ["inline_buttons", "threads"]

    def test_object_capabilities_returns_none(self) -> None:
        # OpenClaw falls back to per-channel handler for object-format capabilities.
        cfg = {"channels": {"telegram": {"capabilities": {"inlineButtons": "dm"}}}}
        out = resolve_channel_capabilities({"cfg": cfg, "channel": "telegram"})
        assert out is None

    def test_account_override(self) -> None:
        cfg = {
            "channels": {
                "telegram": {
                    "capabilities": ["a"],
                    "accounts": {
                        "work": {"capabilities": ["b"]}
                    }
                }
            }
        }
        out = resolve_channel_capabilities({"cfg": cfg, "channel": "telegram", "accountId": "work"})
        assert out == ["b"]


# ============================================================================
# channel-configured
# ============================================================================


class TestChannelConfigured:
    def test_resolve_config_record(self) -> None:
        cfg = {"channels": {"telegram": {"botToken": "x"}}}
        assert resolve_channel_config_record(cfg, "telegram") == {"botToken": "x"}

    def test_resolve_config_record_missing(self) -> None:
        assert resolve_channel_config_record({}, "telegram") == {}

    def test_meaningful_empty(self) -> None:
        assert has_meaningful_channel_config_shallow({}) is False

    def test_meaningful_only_enabled_false(self) -> None:
        assert has_meaningful_channel_config_shallow({"enabled": False}) is False

    def test_meaningful_only_enabled_true(self) -> None:
        assert has_meaningful_channel_config_shallow({"enabled": True}) is True

    def test_meaningful_other_keys(self) -> None:
        assert has_meaningful_channel_config_shallow({"botToken": "x"}) is True

    def test_is_channel_configured(self) -> None:
        cfg = {"channels": {"telegram": {"botToken": "x"}}}
        assert is_channel_configured(cfg, "telegram") is True
        assert is_channel_configured(cfg, "discord") is False


# ============================================================================
# commands
# ============================================================================


class TestCommands:
    def test_explicitly_disabled(self) -> None:
        assert is_native_commands_explicitly_disabled({"providerSetting": False}) is True
        assert is_native_commands_explicitly_disabled({"providerSetting": True}) is False

    def test_explicitly_disabled_inherited(self) -> None:
        assert is_native_commands_explicitly_disabled({"globalSetting": False}) is True
        assert is_native_commands_explicitly_disabled({"globalSetting": True}) is False

    def test_explicitly_disabled_provider_unset(self) -> None:
        # providerSetting is undefined → fall back to global
        assert is_native_commands_explicitly_disabled({
            "providerSetting": None,
            "globalSetting": False,
        }) is True
        assert is_native_commands_explicitly_disabled({
            "providerSetting": None,
            "globalSetting": True,
        }) is False

    def test_resolve_explicit_true(self) -> None:
        out = resolve_native_commands_enabled({"providerId": "x", "providerSetting": True})
        assert out is True

    def test_resolve_explicit_false(self) -> None:
        out = resolve_native_commands_enabled({"providerId": "x", "providerSetting": False})
        assert out is False

    def test_resolve_no_provider_id(self) -> None:
        # When providerId is None, OpenClaw's autoDefault fallback returns False;
        # when globalSetting=True is the resolved setting, it returns True.
        out = resolve_native_skills_enabled({"providerId": None, "globalSetting": True})
        assert out is True

    def test_resolve_no_provider_id_no_setting(self) -> None:
        out = resolve_native_skills_enabled({"providerId": None})
        # No global setting and no provider id → auto default returns False.
        assert out is False

    def test_resolve_kind_dispatch(self) -> None:
        # Same args should produce different kind markers
        kwargs = {"providerId": "x", "providerSetting": True}
        assert resolve_native_commands_enabled(kwargs) is True
        assert resolve_native_skills_enabled(kwargs) is True


# ============================================================================
# commands.flags
# ============================================================================


class TestCommandsFlags:
    def test_is_enabled_true(self) -> None:
        assert is_command_flag_enabled({"commands": {"restart": True}}, "restart") is True

    def test_is_enabled_false(self) -> None:
        assert is_command_flag_enabled({"commands": {"restart": False}}, "restart") is False

    def test_is_enabled_missing(self) -> None:
        assert is_command_flag_enabled({}, "restart") is False
        assert is_command_flag_enabled(None, "restart") is False

    def test_is_restart_default(self) -> None:
        # restart defaults on; only disabled by explicit false.
        assert is_restart_enabled({}) is True
        assert is_restart_enabled(None) is True
        assert is_restart_enabled({"commands": {"restart": True}}) is True
        assert is_restart_enabled({"commands": {"restart": False}}) is False


# ============================================================================
# config-paths
# ============================================================================


class TestConfigPaths:
    def test_parse_valid(self) -> None:
        out = parse_config_path("a.b.c")
        assert out["ok"] is True
        assert out["path"] == ["a", "b", "c"]

    def test_parse_invalid(self) -> None:
        assert parse_config_path("")["ok"] is False
        assert parse_config_path("a..b")["ok"] is False
        assert parse_config_path("a.__proto__.x")["ok"] is False

    def test_set_and_get(self) -> None:
        root: dict = {}
        set_config_value_at_path(root, ["a", "b", "c"], 42)
        assert get_config_value_at_path(root, ["a", "b", "c"]) == 42

    def test_set_existing(self) -> None:
        root = {"a": {"b": 1}}
        set_config_value_at_path(root, ["a", "b"], 2)
        assert root["a"]["b"] == 2

    def test_unset(self) -> None:
        root = {"a": {"b": 1}}
        assert unset_config_value_at_path(root, ["a", "b"]) is True
        # a becomes empty and is pruned
        assert "a" not in root

    def test_unset_keeps_non_empty_parents(self) -> None:
        root = {"a": {"b": 1, "c": 2}}
        assert unset_config_value_at_path(root, ["a", "b"]) is True
        assert root == {"a": {"c": 2}}

    def test_unset_missing(self) -> None:
        assert unset_config_value_at_path({}, ["a", "b"]) is False


# ============================================================================
# context-visibility
# ============================================================================


class TestContextVisibility:
    def test_default(self) -> None:
        assert resolve_default_context_visibility({}) is None
        cfg = {"channels": {"defaults": {"contextVisibility": "tag"}}}
        assert resolve_default_context_visibility(cfg) == "tag"

    def test_mode(self) -> None:
        out = resolve_channel_context_visibility_mode({"channel": "telegram", "cfg": {}})
        assert out == "all"

    def test_channel_override(self) -> None:
        cfg = {"channels": {"telegram": {"contextVisibility": "tag"}}}
        out = resolve_channel_context_visibility_mode({"channel": "telegram", "cfg": cfg})
        assert out == "tag"

    def test_account_override(self) -> None:
        cfg = {
            "channels": {
                "telegram": {
                    "contextVisibility": "tag",
                    "accounts": {"work": {"contextVisibility": "none"}},
                }
            }
        }
        out = resolve_channel_context_visibility_mode({
            "channel": "telegram", "accountId": "work", "cfg": cfg,
        })
        assert out == "none"

    def test_configured_overrides(self) -> None:
        out = resolve_channel_context_visibility_mode({
            "channel": "telegram", "cfg": {},
            "configuredContextVisibility": "none",
        })
        assert out == "none"


# ============================================================================
# control-ui-css
# ============================================================================


class TestControlUiCss:
    def test_normalize(self) -> None:
        assert normalize_control_ui_chat_message_max_width("  100px  ") == "100px"

    def test_keyword_none(self) -> None:
        assert is_valid_control_ui_chat_message_max_width("none") is True

    def test_keyword_min_content(self) -> None:
        assert is_valid_control_ui_chat_message_max_width("min-content") is True

    def test_simple_px(self) -> None:
        assert is_valid_control_ui_chat_message_max_width("100px") is True
        # Bare "100" without a unit does not match CSS_WIDTH_SIMPLE_RE
        # (which requires a unit suffix).
        assert is_valid_control_ui_chat_message_max_width("100") is False
        assert is_valid_control_ui_chat_message_max_width("100rem") is True
        assert is_valid_control_ui_chat_message_max_width("100%") is True

    def test_calc(self) -> None:
        assert is_valid_control_ui_chat_message_max_width("calc(100% - 20px)") is True

    def test_clamp(self) -> None:
        assert is_valid_control_ui_chat_message_max_width("clamp(100px, 50%, 200px)") is True

    def test_invalid(self) -> None:
        assert is_valid_control_ui_chat_message_max_width("") is False
        assert is_valid_control_ui_chat_message_max_width("garbage") is False
        # Too long
        assert is_valid_control_ui_chat_message_max_width("a" * 200) is False
        # Disallowed characters
        assert is_valid_control_ui_chat_message_max_width("100;") is False


# ============================================================================
# cron-limits
# ============================================================================


class TestCronLimits:
    def test_constants(self) -> None:
        assert DEFAULT_CRON_MAX_CONCURRENT_RUNS == 8
        assert DEFAULT_CRON_TRIGGER_MIN_INTERVAL_MS == 30_000

    def test_default(self) -> None:
        assert resolve_cron_max_concurrent_runs() == 8
        assert resolve_cron_trigger_min_interval_ms() == 30_000

    def test_explicit(self) -> None:
        assert resolve_cron_max_concurrent_runs({"maxConcurrentRuns": 16}) == 16
        assert resolve_cron_trigger_min_interval_ms({"triggers": {"minIntervalMs": 60_000}}) == 60_000

    def test_floor(self) -> None:
        assert resolve_cron_max_concurrent_runs({"maxConcurrentRuns": 0}) == 1


# ============================================================================
# dangerous-name-matching
# ============================================================================


class TestDangerousNameMatching:
    def test_enabled(self) -> None:
        assert is_dangerous_name_matching_enabled({"dangerouslyAllowNameMatching": True}) is True
        assert is_dangerous_name_matching_enabled({}) is False
        assert is_dangerous_name_matching_enabled(None) is False  # type: ignore[arg-type]

    def test_resolve_account_overrides(self) -> None:
        out = resolve_dangerous_name_matching_enabled({
            "providerConfig": {"dangerouslyAllowNameMatching": True},
            "accountConfig": {"dangerouslyAllowNameMatching": False},
        })
        assert out is False

    def test_resolve_provider_inherited(self) -> None:
        out = resolve_dangerous_name_matching_enabled({
            "providerConfig": {"dangerouslyAllowNameMatching": True},
            "accountConfig": {},
        })
        assert out is True

    def test_resolve_both_unset(self) -> None:
        out = resolve_dangerous_name_matching_enabled({
            "providerConfig": {},
            "accountConfig": {},
        })
        assert out is False

    def test_collect_scopes(self) -> None:
        cfg = {
            "channels": {
                "telegram": {
                    "dangerouslyAllowNameMatching": True,
                    "accounts": {
                        "work": {"dangerouslyAllowNameMatching": False},
                    },
                }
            }
        }
        scopes = collect_provider_dangerous_name_matching_scopes(cfg, "telegram")
        assert len(scopes) == 2
        assert scopes[0]["prefix"] == "channels.telegram"
        assert scopes[0]["dangerousNameMatchingEnabled"] is True
        assert scopes[1]["prefix"] == "channels.telegram.accounts.work"
        assert scopes[1]["dangerousNameMatchingEnabled"] is False

    def test_collect_no_channels(self) -> None:
        assert collect_provider_dangerous_name_matching_scopes({}, "telegram") == []
