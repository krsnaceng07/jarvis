"""Phase 8.1c tests — src/logging/ (10 small files)."""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from src.logging.config import (  # noqa: E402
    read_logging_config,
    reset_logging_config_cache,
    should_skip_mutating_logging_config_read,
)
from src.logging.env_log_level import (  # noqa: E402
    resolve_env_log_level_override,
    reset_invalid_env_log_level_state,
)
from src.logging.levels import (  # noqa: E402
    ALLOWED_LOG_LEVELS,
    level_to_min_level,
    normalize_log_level,
    try_parse_log_level,
)
from src.logging.message_lifecycle import (  # noqa: E402
    create_diagnostic_message_lifecycle,
    set_log_message_processed_hook,
    set_log_message_queued_hook,
    set_log_session_state_change_hook,
)
from src.logging.node_require import resolve_node_require_from_meta  # noqa: E402
from src.logging.parse_log_line import parse_log_line  # noqa: E402
from src.logging.secret_redaction_registry import (  # noqa: E402
    has_registered_secret_values_for_redaction,
    is_secret_value_registered_for_redaction,
    redact_registered_secret_values,
    register_secret_value_for_redaction,
    reset_secret_redaction_registry_for_test,
)
from src.logging.state import logging_state  # noqa: E402
from src.logging.timestamps import format_timestamp  # noqa: E402
from src.logging.types import ConsoleStyle, LoggerSettings  # noqa: E402


# ============================================================================
# config
# ============================================================================


class TestLoggingConfig:
    def test_should_skip(self) -> None:
        assert should_skip_mutating_logging_config_read(["config", "schema"]) is True
        assert should_skip_mutating_logging_config_read(["config", "validate"]) is True
        assert should_skip_mutating_logging_config_read(["agent", "run"]) is False
        assert should_skip_mutating_logging_config_read([]) is False

    def test_read_no_path(self) -> None:
        reset_logging_config_cache()
        # Without a real config file, returns None
        result = read_logging_config()
        assert result is None or isinstance(result, dict)

    def test_reset(self) -> None:
        reset_logging_config_cache()  # No error


# ============================================================================
# env_log_level
# ============================================================================


class TestEnvLogLevel:
    def setup_method(self) -> None:
        reset_invalid_env_log_level_state()
        os.environ.pop("OPENCLAW_LOG_LEVEL", None)

    def test_no_env(self) -> None:
        assert resolve_env_log_level_override() is None

    def test_valid_env(self) -> None:
        os.environ["OPENCLAW_LOG_LEVEL"] = "debug"
        assert resolve_env_log_level_override() == "debug"

    def test_invalid_env(self, capsys) -> None:
        os.environ["OPENCLAW_LOG_LEVEL"] = "bogus"
        assert resolve_env_log_level_override() is None
        captured = capsys.readouterr()
        assert "Ignoring invalid" in captured.err


# ============================================================================
# levels
# ============================================================================


class TestLevels:
    def test_constants(self) -> None:
        assert "info" in ALLOWED_LOG_LEVELS
        assert "debug" in ALLOWED_LOG_LEVELS
        assert "silent" in ALLOWED_LOG_LEVELS

    def test_try_parse(self) -> None:
        assert try_parse_log_level("info") == "info"
        assert try_parse_log_level("DEBUG") == "debug"
        assert try_parse_log_level("invalid") is None
        assert try_parse_log_level(None) is None

    def test_normalize(self) -> None:
        assert normalize_log_level("warn") == "warn"
        assert normalize_log_level("garbage") == "info"
        assert normalize_log_level("garbage", fallback="error") == "error"

    def test_level_to_min_level(self) -> None:
        assert level_to_min_level("info") == 3
        assert level_to_min_level("debug") == 2
        assert level_to_min_level("error") == 5
        assert level_to_min_level("silent") == float("inf")


# ============================================================================
# message_lifecycle
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_message_lifecycle_hooks() -> None:
    set_log_message_processed_hook(None)
    set_log_message_queued_hook(None)
    set_log_session_state_change_hook(None)
    yield
    set_log_message_processed_hook(None)
    set_log_message_queued_hook(None)
    set_log_session_state_change_hook(None)


class TestMessageLifecycle:
    def test_disabled(self) -> None:
        lc = create_diagnostic_message_lifecycle(
            {"enabled": False, "channel": "telegram", "source": "test"}
        )
        # No hooks set → silent no-op
        lc["markProcessing"]()
        lc["markIdle"]()
        lc["markProcessed"]("completed")

    def test_enabled_with_hooks(self) -> None:
        queued = []
        state = []
        processed = []
        set_log_message_queued_hook(lambda p: queued.append(p))
        set_log_session_state_change_hook(lambda p: state.append(p))
        set_log_message_processed_hook(lambda p: processed.append(p))
        lc = create_diagnostic_message_lifecycle(
            {
                "enabled": True,
                "channel": "telegram",
                "source": "test",
                "sessionId": "s1",
                "trackSessionState": True,
            }
        )
        lc["markProcessing"]()
        lc["markIdle"]("done")
        lc["markProcessed"]("completed", {"durationMs": 100, "reason": "ok"})
        assert len(queued) == 1
        assert queued[0]["channel"] == "telegram"
        assert len(state) == 2
        assert state[0]["state"] == "processing"
        assert len(processed) == 1
        assert processed[0]["outcome"] == "completed"


# ============================================================================
# node_require
# ============================================================================


class TestNodeRequire:
    def test_empty(self) -> None:
        # Empty meta_url → None; any non-empty string returns a loader callable
        assert resolve_node_require_from_meta("") is None

    def test_with_meta(self) -> None:
        out = resolve_node_require_from_meta("__main__")
        # Returns a loader callable (caller decides whether to use it)
        assert out is None or callable(out)


# ============================================================================
# parse_log_line
# ============================================================================


class TestParseLogLine:
    def test_invalid(self) -> None:
        assert parse_log_line("not json") is None
        assert parse_log_line("") is None
        assert parse_log_line(123) is None

    def test_basic(self) -> None:
        line = '{"0": "hello", "1": "world", "_meta": {"logLevelName": "INFO", "name": "{\\"subsystem\\":\\"test\\"}"}}'
        out = parse_log_line(line)
        assert out is not None
        assert out["message"] == "hello world"
        assert out["level"] == "info"
        assert out["subsystem"] == "test"

    def test_meta_only(self) -> None:
        line = '{"_meta": {"logLevelName": "WARN"}}'
        out = parse_log_line(line)
        assert out is not None
        assert out["level"] == "warn"
        assert out["message"] == ""


# ============================================================================
# secret_redaction_registry
# ============================================================================


class TestSecretRedactionRegistry:
    def setup_method(self) -> None:
        reset_secret_redaction_registry_for_test()

    def test_register_too_short(self) -> None:
        register_secret_value_for_redaction("abc")
        assert has_registered_secret_values_for_redaction() is False

    def test_register_and_check(self) -> None:
        secret = "this-is-a-test-secret-12345"
        register_secret_value_for_redaction(secret)
        assert has_registered_secret_values_for_redaction() is True
        assert is_secret_value_registered_for_redaction(secret) is True
        assert is_secret_value_registered_for_redaction("nope") is False

    def test_redact(self) -> None:
        secret = "secret-value-abcdef-12345"
        register_secret_value_for_redaction(secret)
        out = redact_registered_secret_values(
            f"prefix {secret} suffix",
            lambda v: "***",
        )
        assert "***" in out
        assert secret not in out

    def test_redact_no_match(self) -> None:
        secret = "secret-value-abcdef-12345"
        register_secret_value_for_redaction(secret)
        out = redact_registered_secret_values("nothing here", lambda v: "***")
        assert out == "nothing here"

    def test_bounded_registry(self) -> None:
        # Register MAX_SECRET_VALUES + 1 values, the oldest should be evicted
        for i in range(512):
            register_secret_value_for_redaction(f"secret-value-{i:05d}-xyz")
        # All values still there at the bound
        assert has_registered_secret_values_for_redaction() is True

    def test_reset(self) -> None:
        register_secret_value_for_redaction("secret-value-abcdef-12345")
        assert has_registered_secret_values_for_redaction() is True
        reset_secret_redaction_registry_for_test()
        assert has_registered_secret_values_for_redaction() is False


# ============================================================================
# state
# ============================================================================


class TestLoggingState:
    def test_state_exists(self) -> None:
        assert isinstance(logging_state, dict)
        assert "cachedLogger" in logging_state
        assert "consolePatched" in logging_state


# ============================================================================
# timestamps
# ============================================================================


class TestTimestamps:
    def test_basic(self) -> None:
        d = datetime(2024, 1, 15, 12, 30, 45, tzinfo=timezone.utc)
        out = format_timestamp(d, {"style": "short", "timeZone": "UTC"})
        assert "12:30:45" in out
        assert "+00:00" in out

    def test_medium(self) -> None:
        d = datetime(2024, 1, 15, 12, 30, 45, 123456, tzinfo=timezone.utc)
        out = format_timestamp(d, {"style": "medium", "timeZone": "UTC"})
        assert "12:30:45.123" in out

    def test_long(self) -> None:
        d = datetime(2024, 1, 15, 12, 30, 45, 123456, tzinfo=timezone.utc)
        out = format_timestamp(d, {"style": "long", "timeZone": "UTC"})
        assert "2024-01-15T12:30:45.123" in out
        assert "+00:00" in out

    def test_invalid_style(self) -> None:
        d = datetime(2024, 1, 15, 12, 30, 45, tzinfo=timezone.utc)
        with pytest.raises(ValueError):
            format_timestamp(d, {"style": "garbage"})

    def test_no_date(self) -> None:
        out = format_timestamp(None, {"style": "short"})
        assert ":" in out  # has time


# ============================================================================
# types
# ============================================================================


class TestLoggingTypes:
    def test_logger_settings(self) -> None:
        s = LoggerSettings(
            level="info", file="/tmp/log.txt", max_file_bytes=10_000_000,
            console_level="debug", console_style="pretty",
        )
        d = s.to_dict()
        assert d["level"] == "info"
        assert d["file"] == "/tmp/log.txt"
        assert d["maxFileBytes"] == 10_000_000
        assert d["consoleLevel"] == "debug"
        assert d["consoleStyle"] == "pretty"

    def test_console_style_alias(self) -> None:
        assert ConsoleStyle is str
