"""Phase 8.1d tests — src/shared/ (10 small files)."""
from __future__ import annotations

import asyncio
import os
import sys
from typing import Any, Dict, List, Optional

import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from src.shared.avatar_policy import (  # noqa: E402
    AVATAR_MAX_BYTES,
    has_avatar_uri_scheme,
    is_avatar_data_url,
    is_avatar_http_url,
    is_path_within_root,
    is_supported_local_avatar_extension,
    is_windows_absolute_path,
    looks_like_avatar_path,
    resolve_avatar_mime,
)
from src.shared.balanced_json import (  # noqa: E402
    BalancedJsonFragment,
    extract_balanced_json_fragments,
    extract_balanced_json_prefix,
)
from src.shared.entry_status import (  # noqa: E402
    evaluate_entry_metadata_requirements,
    evaluate_entry_requirements_for_current_platform,
    set_evaluate_entry_metadata_requirements_hook,
    set_evaluate_entry_requirements_for_current_platform_hook,
)
from src.shared.fast_mode import (  # noqa: E402
    DEFAULT_FAST_MODE_AUTO_ON_SECONDS,
    format_fast_mode_auto_label,
    format_fast_mode_auto_progress_text,
    format_fast_mode_command_options,
    format_fast_mode_current_status,
    format_fast_mode_source_suffix,
    format_fast_mode_status_value,
    format_fast_mode_value,
    resolve_fast_mode_for_elapsed,
    resolve_fast_mode_model_auto_on_seconds,
    resolve_fast_mode_model_params,
)
from src.shared.frontmatter import (  # noqa: F401
    LEGACY_MANIFEST_KEYS,
    MANIFEST_KEY,
    apply_openclaw_manifest_install_common_fields,
    get_frontmatter_string,
    normalize_string_list,
    parse_frontmatter_bool,
    parse_openclaw_manifest_install_base,
    resolve_openclaw_manifest_block,
    resolve_openclaw_manifest_install,
    resolve_openclaw_manifest_os,
    resolve_openclaw_manifest_requires,
)
from src.shared.lazy_promise import (  # noqa: E402
    create_lazy_promise,
    create_lazy_promise_loader,
    get_or_create_promise,
)
from src.shared.operator_scope_compat import (  # noqa: E402
    OPERATOR_ADMIN_SCOPE,
    OPERATOR_READ_SCOPE,
    OPERATOR_ROLE,
    OPERATOR_SCOPE_PREFIX,
    OPERATOR_WRITE_SCOPE,
    resolve_missing_requested_scope,
    resolve_scope_outside_requested_roles,
    role_scopes_allow,
)
from src.shared.pid_alive import (  # noqa: E402
    get_file_lock_process_start_time,
    get_process_start_time,
    is_pid_alive,
    is_pid_definitely_dead,
)
from src.shared.scoped_expiring_id_cache import (  # noqa: E402
    create_scoped_expiring_id_cache,
)
from src.shared.thread_binding_lifecycle import (  # noqa: E402
    ThreadBindingLifecycleRecord,
    resolve_thread_binding_lifecycle,
)


# ============================================================================
# avatar_policy
# ============================================================================


class TestAvatarPolicy:
    def test_mime(self) -> None:
        assert resolve_avatar_mime("foo.png") == "image/png"
        assert resolve_avatar_mime("foo.JPG") == "image/jpeg"
        assert resolve_avatar_mime("foo.svg") == "image/svg+xml"
        assert resolve_avatar_mime("foo.unknown") == "application/octet-stream"

    def test_data_url(self) -> None:
        assert is_avatar_data_url("data:image/png;base64,xxx") is True
        assert is_avatar_data_url("https://x.com") is False
        assert is_avatar_data_url("/local/path") is False

    def test_http_url(self) -> None:
        assert is_avatar_http_url("https://x.com/img.png") is True
        assert is_avatar_http_url("http://x.com") is True
        assert is_avatar_http_url("file:///tmp") is False

    def test_uri_scheme(self) -> None:
        assert has_avatar_uri_scheme("ftp://x.com") is True
        assert has_avatar_uri_scheme("slack://avatar") is True
        # OpenClaw parity: Windows paths DO match the URI-scheme regex
        # because 'C:' fits [a-z][a-z0-9+.-]*: — callers pair this with
        # is_windows_absolute_path to disambiguate.
        assert has_avatar_uri_scheme("C:\\path") is True
        assert has_avatar_uri_scheme("/local/path") is False

    def test_windows_absolute(self) -> None:
        assert is_windows_absolute_path("C:\\path") is True
        assert is_windows_absolute_path("C:/path") is True
        assert is_windows_absolute_path("/unix/path") is False

    def test_path_within_root(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            inside = os.path.join(tmp, "inside.png")
            open(inside, "w").close()
            assert is_path_within_root(tmp, inside) is True
            assert is_path_within_root(tmp, "/nonexistent/path") is False

    def test_looks_like_path(self) -> None:
        assert looks_like_avatar_path("/x/y.png") is True
        assert looks_like_avatar_path("foo.png") is True
        assert looks_like_avatar_path("data:foo") is False

    def test_supported_extension(self) -> None:
        assert is_supported_local_avatar_extension("x.png") is True
        assert is_supported_local_avatar_extension("x.svg") is True
        assert is_supported_local_avatar_extension("x.bmp") is False
        assert is_supported_local_avatar_extension("x.tiff") is False

    def test_constant(self) -> None:
        assert AVATAR_MAX_BYTES == 5 * 1024 * 1024


# ============================================================================
# balanced_json
# ============================================================================


class TestBalancedJson:
    def test_object(self) -> None:
        out = extract_balanced_json_prefix('prefix {"a": 1, "b": [1, 2]} suffix')
        assert out is not None
        assert out.json == '{"a": 1, "b": [1, 2]}'
        assert out.start_index == 7
        # end_index is the position of the matching closing delimiter
        # in OpenClaw: 'prefix '=7 chars, then '{' at 7, closing '}' at 27.
        assert out.end_index == 27

    def test_array(self) -> None:
        out = extract_balanced_json_prefix('prefix [1, 2, [3, 4]] suffix')
        assert out is not None
        assert out.json == '[1, 2, [3, 4]]'

    def test_string_with_brace(self) -> None:
        out = extract_balanced_json_prefix('{"a": "hello {world}"}')
        assert out is not None
        assert out.json == '{"a": "hello {world}"}'

    def test_escaped_quote(self) -> None:
        out = extract_balanced_json_prefix(r'{"a": "say \"hi\""}')
        assert out is not None

    def test_no_json(self) -> None:
        assert extract_balanced_json_prefix("no json here") is None
        assert extract_balanced_json_prefix("") is None

    def test_openers_filter(self) -> None:
        # Only allow [ as opener
        out = extract_balanced_json_prefix('{"a":1} [1, 2]', openers=("[",))
        assert out is not None
        assert out.json.startswith("[")

    def test_fragments(self) -> None:
        out = extract_balanced_json_fragments('{"a":1} {"b":2}')
        assert len(out) == 2

    def test_invalid(self) -> None:
        assert extract_balanced_json_prefix(None) is None
        assert extract_balanced_json_fragments(None) == []


# ============================================================================
# entry_status
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_entry_status_hooks() -> None:
    set_evaluate_entry_metadata_requirements_hook(None)
    set_evaluate_entry_requirements_for_current_platform_hook(None)
    yield
    set_evaluate_entry_metadata_requirements_hook(None)
    set_evaluate_entry_requirements_for_current_platform_hook(None)


class TestEntryStatus:
    def test_basic(self) -> None:
        out = evaluate_entry_metadata_requirements(
            {
                "always": False,
                "metadata": {"emoji": "🦊", "homepage": "https://x.com"},
            }
        )
        assert out["emoji"] == "🦊"
        assert out["homepage"] == "https://x.com"
        assert out["requirementsSatisfied"] is True

    def test_with_hook(self) -> None:
        set_evaluate_entry_metadata_requirements_hook(lambda _p: {"hooked": True})
        out = evaluate_entry_metadata_requirements({})
        assert out == {"hooked": True}

    def test_for_current_platform(self) -> None:
        out = evaluate_entry_requirements_for_current_platform({"always": True})
        assert out is not None
        assert out["requirementsSatisfied"] is True

    def test_for_current_platform_hook(self) -> None:
        set_evaluate_entry_requirements_for_current_platform_hook(lambda _p: {"hooked": True})
        out = evaluate_entry_requirements_for_current_platform({})
        assert out == {"hooked": True}


# ============================================================================
# fast_mode
# ============================================================================


class TestFastMode:
    def test_constants(self) -> None:
        assert DEFAULT_FAST_MODE_AUTO_ON_SECONDS == 60

    def test_resolve_params(self) -> None:
        out = resolve_fast_mode_model_params(
            {
                "cfg": {
                    "agents": {
                        "defaults": {
                            "models": {
                                "openai/gpt-4o": {"params": {"temperature": 0.5}}
                            }
                        }
                    }
                },
                "provider": "openai",
                "model": "gpt-4o",
            }
        )
        assert out == {"temperature": 0.5}

    def test_resolve_params_no_match(self) -> None:
        out = resolve_fast_mode_model_params(
            {
                "cfg": {"agents": {"defaults": {"models": {}}}},
                "provider": "openai",
                "model": "gpt-4o",
            }
        )
        assert out is None

    def test_auto_on_seconds(self) -> None:
        out = resolve_fast_mode_model_auto_on_seconds(
            {
                "cfg": {
                    "agents": {
                        "defaults": {
                            "models": {
                                "openai/gpt-4o": {"params": {"fastAutoOnSeconds": 30}}
                            }
                        }
                    }
                },
                "provider": "openai",
                "model": "gpt-4o",
            }
        )
        assert out == 30

    def test_auto_on_seconds_default(self) -> None:
        out = resolve_fast_mode_model_auto_on_seconds(
            {"cfg": None, "provider": "openai", "model": "gpt-4o"}
        )
        assert out == 60

    def test_resolve_for_elapsed(self) -> None:
        out = resolve_fast_mode_for_elapsed(
            {"mode": "auto", "startedAtMs": 1000, "nowMs": 1000}
        )
        assert out["enabled"] is True

    def test_resolve_for_elapsed_expired(self) -> None:
        out = resolve_fast_mode_for_elapsed(
            {
                "mode": "auto",
                "startedAtMs": 0,
                "nowMs": 120_000,  # 2 min elapsed
            }
        )
        assert out["enabled"] is False

    def test_format_auto_on(self) -> None:
        out = format_fast_mode_auto_progress_text({"enabled": True, "elapsedSeconds": 5})
        assert "auto-on" in out

    def test_format_auto_off(self) -> None:
        out = format_fast_mode_auto_progress_text(
            {"enabled": False, "elapsedSeconds": 70, "fastAutoOnSeconds": 60}
        )
        assert "auto-off" in out

    def test_format_value(self) -> None:
        assert format_fast_mode_value("auto") == "auto"
        assert format_fast_mode_value(True) == "on"
        assert format_fast_mode_value(False) == "off"
        assert format_fast_mode_value(None) == "off"

    def test_format_auto_label(self) -> None:
        assert "sec" in format_fast_mode_auto_label()

    def test_format_command_options(self) -> None:
        out = format_fast_mode_command_options()
        assert "on" in out
        assert "off" in out

    def test_format_source_suffix(self) -> None:
        assert "session" in format_fast_mode_source_suffix("session")
        assert format_fast_mode_source_suffix(None) == ""

    def test_format_current_status(self) -> None:
        out = format_fast_mode_current_status({"mode": "auto"})
        assert "Current fast mode" in out


# ============================================================================
# frontmatter
# ============================================================================


class TestFrontmatter:
    def test_normalize_string_list_string(self) -> None:
        assert normalize_string_list("a, b, c") == ["a", "b", "c"]

    def test_normalize_string_list_array(self) -> None:
        assert normalize_string_list(["a", "b"]) == ["a", "b"]

    def test_normalize_string_list_none(self) -> None:
        assert normalize_string_list(None) == []

    def test_normalize_string_list_drops_empty(self) -> None:
        assert normalize_string_list("a, , b, ") == ["a", "b"]

    def test_get_string(self) -> None:
        assert get_frontmatter_string({"key": "value"}, "key") == "value"
        assert get_frontmatter_string({"key": ""}, "key") is None
        assert get_frontmatter_string({"key": 123}, "key") is None
        assert get_frontmatter_string({}, "key") is None

    def test_parse_bool(self) -> None:
        assert parse_frontmatter_bool("true", False) is True
        assert parse_frontmatter_bool("false", True) is False
        assert parse_frontmatter_bool("yes", False) is True
        assert parse_frontmatter_bool("no", True) is False
        assert parse_frontmatter_bool(None, True) is True
        assert parse_frontmatter_bool("garbage", False) is False

    def test_manifest_block(self) -> None:
        block = resolve_openclaw_manifest_block(
            {
                "frontmatter": {
                    "metadata": '{"openclaw": {"foo": "bar"}}',
                }
            }
        )
        assert block == {"foo": "bar"}

    def test_manifest_block_legacy(self) -> None:
        block = resolve_openclaw_manifest_block(
            {"frontmatter": {"metadata": '{"jarvis": {"x": 1}}'}}
        )
        assert block == {"x": 1}

    def test_manifest_block_invalid(self) -> None:
        assert resolve_openclaw_manifest_block({"frontmatter": {}}) is None
        assert resolve_openclaw_manifest_block({}) is None

    def test_requires(self) -> None:
        out = resolve_openclaw_manifest_requires(
            {
                "requires": {
                    "bins": ["node", "git"],
                    "env": ["OPENAI_API_KEY"],
                }
            }
        )
        assert out is not None
        assert "node" in out["bins"]
        assert "OPENAI_API_KEY" in out["env"]

    def test_install(self) -> None:
        entries = resolve_openclaw_manifest_install(
            {
                "install": [
                    {"kind": "npm", "package": "foo"},
                    "not-a-dict",
                ]
            },
            lambda e: e if isinstance(e, dict) and e.get("kind") == "npm" else None,
        )
        assert len(entries) == 1
        assert entries[0]["package"] == "foo"

    def test_os(self) -> None:
        assert resolve_openclaw_manifest_os({"os": ["darwin", "linux"]}) == ["darwin", "linux"]

    def test_install_base(self) -> None:
        out = parse_openclaw_manifest_install_base(
            {"kind": "npm", "id": "x", "label": "L", "bins": ["npx"]},
            ["npm"],
        )
        assert out is not None
        assert out["kind"] == "npm"
        assert out["id"] == "x"

    def test_install_base_invalid_kind(self) -> None:
        assert parse_openclaw_manifest_install_base({"kind": "bogus"}, ["npm"]) is None

    def test_install_common_fields(self) -> None:
        spec = {"existing": "value"}
        apply_openclaw_manifest_install_common_fields(spec, {"id": "x", "label": "L", "bins": ["npx"]})
        assert spec["id"] == "x"
        assert spec["label"] == "L"
        assert spec["bins"] == ["npx"]
        assert spec["existing"] == "value"

    def test_constants(self) -> None:
        assert MANIFEST_KEY == "openclaw"
        assert "jarvis" in LEGACY_MANIFEST_KEYS


# ============================================================================
# lazy_promise
# ============================================================================


class TestLazyPromise:
    def test_get_or_create(self) -> None:
        cache: dict = {}
        calls = {"n": 0}

        def _create():
            calls["n"] += 1
            return "value"

        out1 = get_or_create_promise(cache, "k", _create)
        out2 = get_or_create_promise(cache, "k", _create)
        assert out1 == out2 == "value"
        assert calls["n"] == 1

    def test_loader_basic(self) -> None:
        async def _load():
            return "async-value"

        loader = create_lazy_promise_loader(_load)
        # First call returns a coroutine (no running loop in sync test);
        # asyncio.run drives it to completion.
        promise = loader.load()
        assert asyncio.run(promise) == "async-value"

    def test_loader_peek_clear(self) -> None:
        async def _load():
            return "value"

        loader = create_lazy_promise_loader(_load)
        promise = loader.load()
        assert loader.peek() is promise
        loader.clear()
        assert loader.peek() is None
        # New load after clear
        promise2 = loader.load()
        assert promise2 is not promise

    def test_create_lazy_promise(self) -> None:
        async def _load():
            return "v"

        fn = create_lazy_promise(_load)
        promise = fn()
        assert asyncio.run(promise) == "v"


# ============================================================================
# operator_scope_compat
# ============================================================================


class TestOperatorScopeCompat:
    def test_constants(self) -> None:
        assert OPERATOR_ROLE == "operator"
        assert OPERATOR_ADMIN_SCOPE == "operator.admin"
        assert OPERATOR_READ_SCOPE == "operator.read"
        assert OPERATOR_WRITE_SCOPE == "operator.write"

    def test_admin_grants_everything(self) -> None:
        assert role_scopes_allow(
            {
                "role": "operator",
                "requestedScopes": ["operator.admin", "operator.read"],
                "allowedScopes": ["operator.admin"],
            }
        ) is True

    def test_read_grants_read_and_write(self) -> None:
        # operator.read grant satisfies operator.read request
        assert role_scopes_allow(
            {
                "role": "operator",
                "requestedScopes": ["operator.read"],
                "allowedScopes": ["operator.read"],
            }
        ) is True
        # operator.write grant satisfies operator.read request (OpenClaw behavior)
        assert role_scopes_allow(
            {
                "role": "operator",
                "requestedScopes": ["operator.read"],
                "allowedScopes": ["operator.write"],
            }
        ) is True
        # operator.read does NOT satisfy operator.write
        assert role_scopes_allow(
            {
                "role": "operator",
                "requestedScopes": ["operator.write"],
                "allowedScopes": ["operator.read"],
            }
        ) is False

    def test_non_operator_role(self) -> None:
        # A non-operator role only matches its own scope prefix
        assert role_scopes_allow(
            {
                "role": "viewer",
                "requestedScopes": ["viewer.read"],
                "allowedScopes": ["viewer.read"],
            }
        ) is True
        assert role_scopes_allow(
            {
                "role": "viewer",
                "requestedScopes": ["viewer.read"],
                "allowedScopes": ["editor.read"],
            }
        ) is False

    def test_no_requested_scopes(self) -> None:
        assert role_scopes_allow(
            {"role": "x", "requestedScopes": [], "allowedScopes": []}
        ) is True

    def test_no_allowed_scopes(self) -> None:
        assert role_scopes_allow(
            {
                "role": "x",
                "requestedScopes": ["x.read"],
                "allowedScopes": [],
            }
        ) is False

    def test_resolve_missing(self) -> None:
        out = resolve_missing_requested_scope(
            {
                "role": "operator",
                "requestedScopes": ["operator.read", "operator.admin"],
                "allowedScopes": ["operator.read"],
            }
        )
        assert out == "operator.admin"

    def test_resolve_outside(self) -> None:
        out = resolve_scope_outside_requested_roles(
            {
                "requestedRoles": ["viewer"],
                "requestedScopes": ["viewer.read", "editor.write"],
            }
        )
        assert out == "editor.write"


# ============================================================================
# pid_alive
# ============================================================================


class TestPidAlive:
    def test_invalid(self) -> None:
        assert is_pid_alive(0) is False
        assert is_pid_alive(-1) is False
        assert is_pid_definitely_dead(0) is True
        assert is_pid_definitely_dead(-1) is True

    def test_get_start_time_invalid(self) -> None:
        assert get_process_start_time(0) is None
        assert get_process_start_time(-1) is None
        assert get_file_lock_process_start_time(0) is None

    def test_alive_self(self) -> None:
        # The current process should be alive
        import os
        pid = os.getpid()
        assert is_pid_alive(pid) is True


# ============================================================================
# scoped_expiring_id_cache
# ============================================================================


class TestScopedExpiringIdCache:
    def test_record_and_has(self) -> None:
        store: dict = {}
        cache = create_scoped_expiring_id_cache(
            {"store": store, "ttlMs": 60_000, "cleanupThreshold": 5}
        )
        cache.record("scope1", "id1", now=1000)
        assert cache.has("scope1", "id1", now=2000) is True
        # After TTL expires
        assert cache.has("scope1", "id1", now=70_000) is False

    def test_clear(self) -> None:
        store: dict = {}
        cache = create_scoped_expiring_id_cache(
            {"store": store, "ttlMs": 1000, "cleanupThreshold": 1}
        )
        cache.record("a", "1", now=0)
        cache.record("b", "1", now=0)
        assert cache.has("a", "1", now=0) is True
        cache.clear()
        assert cache.has("a", "1", now=0) is False

    def test_opportunistic_cleanup(self) -> None:
        store: dict = {}
        cache = create_scoped_expiring_id_cache(
            {"store": store, "ttlMs": 100, "cleanupThreshold": 2}
        )
        cache.record("s", "1", now=0)
        cache.record("s", "2", now=0)
        cache.record("s", "3", now=200)  # Triggers cleanup; 1+2 are now expired
        assert cache.has("s", "3", now=200) is True


# ============================================================================
# thread_binding_lifecycle
# ============================================================================


class TestThreadBindingLifecycle:
    def test_constants(self) -> None:
        rec = ThreadBindingLifecycleRecord(bound_at=1000, last_activity_at=1500)
        assert rec.bound_at == 1000
        assert rec.last_activity_at == 1500
        d = rec.to_dict()
        assert d["boundAt"] == 1000

    def test_idle_expires(self) -> None:
        out = resolve_thread_binding_lifecycle(
            {
                "record": {
                    "boundAt": 1000,
                    "lastActivityAt": 2000,
                },
                "defaultIdleTimeoutMs": 1000,
                "defaultMaxAgeMs": 0,
            }
        )
        # 2000 + 1000 = 3000 (idle-expired)
        assert out["expiresAt"] == 3000
        assert out["reason"] == "idle-expired"

    def test_max_age_expires(self) -> None:
        out = resolve_thread_binding_lifecycle(
            {
                "record": {
                    "boundAt": 1000,
                    "lastActivityAt": 2000,
                },
                "defaultIdleTimeoutMs": 0,
                "defaultMaxAgeMs": 5000,
            }
        )
        assert out["expiresAt"] == 6000
        assert out["reason"] == "max-age-expired"

    def test_no_expiry(self) -> None:
        out = resolve_thread_binding_lifecycle(
            {
                "record": {
                    "boundAt": 1000,
                    "lastActivityAt": 2000,
                },
                "defaultIdleTimeoutMs": 0,
                "defaultMaxAgeMs": 0,
            }
        )
        assert out == {}

    def test_overrides(self) -> None:
        out = resolve_thread_binding_lifecycle(
            {
                "record": {
                    "boundAt": 1000,
                    "lastActivityAt": 2000,
                    "idleTimeoutMs": 5000,
                },
                "defaultIdleTimeoutMs": 1000,
                "defaultMaxAgeMs": 0,
            }
        )
        assert out["expiresAt"] == 7000  # 2000 + 5000
