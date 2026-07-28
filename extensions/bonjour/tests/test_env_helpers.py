"""Tests for ``extensions/bonjour/src/env_helpers.py``.

Mirrors OpenClaw's ``extensions/bonjour/src/advertiser.test.ts``
for the env-detection helpers.
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

import pytest

from extensions.bonjour.src.env_helpers import (
    is_container_environment,
    is_disabled_by_env,
    is_truthy_env_value,
    prettify_instance_name,
    read_bonjour_disable_override,
    resolve_system_mdns_hostname,
    safe_service_name,
    truncate_to_dns_label,
)


class TestIsTruthyEnvValue:
    def test_truthy_strings(self) -> None:
        assert is_truthy_env_value("1") is True
        assert is_truthy_env_value("on") is True
        assert is_truthy_env_value("true") is True
        assert is_truthy_env_value("yes") is True
        assert is_truthy_env_value("YES") is True
        assert is_truthy_env_value(" True ") is True

    def test_falsy_strings(self) -> None:
        assert is_truthy_env_value("0") is False
        assert is_truthy_env_value("false") is False
        assert is_truthy_env_value("no") is False
        assert is_truthy_env_value("off") is False
        assert is_truthy_env_value("") is False
        assert is_truthy_env_value("maybe") is False

    def test_non_string_values(self) -> None:
        assert is_truthy_env_value(None) is False
        assert is_truthy_env_value(1) is False
        assert is_truthy_env_value(True) is False


class TestReadBonjourDisableOverride:
    def test_unset_returns_none(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            assert read_bonjour_disable_override() is None

    def test_truthy_returns_true(self) -> None:
        for v in ["1", "on", "true", "yes"]:
            with mock.patch.dict(os.environ, {"OPENCLAW_DISABLE_BONJOUR": v}):
                assert read_bonjour_disable_override() is True

    def test_falsy_returns_false(self) -> None:
        for v in ["0", "false", "no", "off"]:
            with mock.patch.dict(os.environ, {"OPENCLAW_DISABLE_BONJOUR": v}):
                assert read_bonjour_disable_override() is False

    def test_unrecognized_returns_none(self) -> None:
        with mock.patch.dict(os.environ, {"OPENCLAW_DISABLE_BONJOUR": "maybe"}):
            assert read_bonjour_disable_override() is None

    def test_blank_returns_none(self) -> None:
        with mock.patch.dict(os.environ, {"OPENCLAW_DISABLE_BONJOUR": "   "}):
            assert read_bonjour_disable_override() is None


class TestIsContainerEnvironment:
    def test_fly_env(self) -> None:
        with mock.patch.dict(
            os.environ, {"FLY_MACHINE_ID": "abc", "FLY_APP_NAME": "demo"}, clear=True
        ):
            assert is_container_environment() is True

    def test_sentinel_file(self, tmp_path: Path) -> None:
        sentinel = tmp_path / "dockerenv"
        sentinel.touch()
        with mock.patch(
            "extensions.bonjour.src.env_helpers.CONTAINER_SENTINEL_PATHS",
            (str(sentinel),),
        ):
            assert is_container_environment() is True

    def test_no_sentinel_no_fly(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            # No fly env, no sentinel files (on Windows those
            # POSIX paths won't exist), no /proc/1/cgroup readable.
            assert is_container_environment() is False


class TestIsDisabledByEnv:
    def test_node_env_test_disables(self) -> None:
        with mock.patch.dict(os.environ, {"NODE_ENV": "test"}, clear=True):
            assert is_disabled_by_env() is True

    def test_vitest_disables(self) -> None:
        with mock.patch.dict(os.environ, {"VITEST": "1"}, clear=True):
            assert is_disabled_by_env() is True

    def test_explicit_disable_override(self) -> None:
        with mock.patch.dict(
            os.environ, {"OPENCLAW_DISABLE_BONJOUR": "true"}, clear=True
        ):
            assert is_disabled_by_env() is True

    def test_explicit_enable_override(self) -> None:
        with mock.patch.dict(
            os.environ, {"OPENCLAW_DISABLE_BONJOUR": "false"}, clear=True
        ):
            assert is_disabled_by_env() is False

    def test_container_disables(self) -> None:
        with mock.patch(
            "extensions.bonjour.src.env_helpers.is_container_environment",
            return_value=True,
        ):
            with mock.patch.dict(os.environ, {}, clear=True):
                assert is_disabled_by_env() is True

    def test_no_override_no_container(self) -> None:
        with mock.patch(
            "extensions.bonjour.src.env_helpers.is_container_environment",
            return_value=False,
        ):
            with mock.patch.dict(os.environ, {}, clear=True):
                assert is_disabled_by_env() is False


class TestResolveSystemMdnsHostname:
    def test_returns_first_label_of_local(self) -> None:
        with mock.patch(
            "extensions.bonjour.src.env_helpers.socket.gethostname",
            return_value="myhost.local",
        ):
            assert resolve_system_mdns_hostname() == "myhost"

    def test_returns_first_label_of_fqdn(self) -> None:
        with mock.patch(
            "extensions.bonjour.src.env_helpers.socket.gethostname",
            return_value="myhost.example.com",
        ):
            assert resolve_system_mdns_hostname() == "myhost"

    def test_rejects_invalid_label(self) -> None:
        with mock.patch(
            "extensions.bonjour.src.env_helpers.socket.gethostname",
            return_value="-invalid-",
        ):
            assert resolve_system_mdns_hostname() is None

    def test_rejects_empty(self) -> None:
        with mock.patch(
            "extensions.bonjour.src.env_helpers.socket.gethostname",
            return_value="",
        ):
            assert resolve_system_mdns_hostname() is None


class TestTruncateToDnsLabel:
    def test_short_name_unchanged(self) -> None:
        assert truncate_to_dns_label("hello") == "hello"

    def test_truncates_at_63_bytes(self) -> None:
        long_name = "a" * 200
        result = truncate_to_dns_label(long_name)
        assert len(result.encode("utf-8")) <= 63
        assert result.startswith("a" * 50)  # most of the 'a' prefix preserved

    def test_truncates_on_utf8_boundary(self) -> None:
        # 60 ASCII chars + 1 four-byte char = 64 bytes total.
        # The function should truncate to 63 bytes (within the
        # last multi-byte char), backing off to 60 to land on a
        # UTF-8 boundary. The result must be valid UTF-8.
        name = "a" * 60 + "🦀"  # 🦀 is 4 bytes in UTF-8
        result = truncate_to_dns_label(name)
        # Result should be valid UTF-8 (no partial decode) and
        # within 63 bytes.
        assert isinstance(result, str)
        assert len(result.encode("utf-8")) <= 63
        # Trailing-hyphen stripping shouldn't have run (no hyphens).
        assert "a" in result

    def test_returns_short_input_unchanged(self) -> None:
        # Inputs under 63 bytes pass through unchanged (the
        # UTF-8 boundary logic only kicks in for over-long
        # inputs).
        assert truncate_to_dns_label("---") == "---"
        assert truncate_to_dns_label("a") == "a"

    def test_empty_string_returns_empty(self) -> None:
        # Empty strings return empty (TS port preserves the
        # ``return name`` for short inputs; the fallback only
        # applies when truncation strips everything to empty).
        assert truncate_to_dns_label("") == ""


class TestSafeServiceName:
    def test_trimmed_name_passes_through(self) -> None:
        assert safe_service_name("hello") == "hello"

    def test_blank_falls_back(self) -> None:
        assert safe_service_name("") == "openclaw"
        assert safe_service_name("   ") == "openclaw"

    def test_truncates_long_names(self) -> None:
        long_name = "z" * 200
        result = safe_service_name(long_name)
        assert len(result.encode("utf-8")) <= 63


class TestPrettifyInstanceName:
    def test_strips_openclaw_suffix(self) -> None:
        assert prettify_instance_name("MyHost (OpenClaw)") == "MyHost"

    def test_keeps_non_openclaw_suffix(self) -> None:
        assert prettify_instance_name("MyHost (Other)") == "MyHost (Other)"

    def test_collapses_whitespace(self) -> None:
        assert prettify_instance_name("  My   Host  ") == "My Host"

    def test_case_insensitive_suffix(self) -> None:
        assert prettify_instance_name("MyHost (openclaw)") == "MyHost"
        assert prettify_instance_name("MyHost (OPENCLAW)") == "MyHost"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
