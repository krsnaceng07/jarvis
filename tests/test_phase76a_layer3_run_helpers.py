"""Phase 7.6a tests — run/ small files (params + types + helpers + payloads + images)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from src.agents.embedded_agent_runner.run.helpers import (
    ANTHROPIC_MAGIC_STRING_REPLACEMENT,
    ANTHROPIC_MAGIC_STRING_TRIGGER_REFUSAL,
    DEFAULT_MAX_OVERLOAD_PROFILE_ROTATIONS,
    DEFAULT_MAX_RATE_LIMIT_PROFILE_ROTATIONS,
    DEFAULT_OVERLOAD_FAILOVER_BACKOFF_MS,
    MAX_SAME_MODEL_RATE_LIMIT_RETRIES,
    RUNTIME_AUTH_REFRESH_MARGIN_MS,
    RUNTIME_AUTH_REFRESH_MIN_DELAY_MS,
    RUNTIME_AUTH_REFRESH_RETRY_MS,
    SAME_MODEL_RATE_LIMIT_BACKOFF_STEP_MS,
    SAME_MODEL_RATE_LIMIT_MAX_BACKOFF_MS,
    resolve_next_same_model_rate_limit_retry_count,
    resolve_overload_failover_backoff_ms,
    resolve_overload_profile_rotation_limit,
    resolve_rate_limit_profile_rotation_limit,
    resolve_same_model_rate_limit_retry_delay_ms,
    scrub_anthropic_refusal_magic,
)
from src.agents.embedded_agent_runner.run.images import (
    IMAGE_EXTENSIONS,
    IMAGE_EXTENSION_NAMES,
    MEDIA_URI_REGEX,
    detect_image_references,
    is_image_extension,
    merge_prompt_attachment_images,
)
from src.agents.embedded_agent_runner.run.payloads import (
    RECOVERABLE_TOOL_ERROR_KEYWORDS,
    build_embedded_run_payloads,
    is_recoverable_tool_error,
    set_build_embedded_run_payloads_hook,
    set_build_source_reply_payload_state_hook,
    set_format_tool_aggregate_hook,
    set_format_user_facing_assistant_error_text_hook,
    set_sanitize_assistant_visible_stream_text_hook,
)
from src.agents.embedded_agent_runner.run.params import (
    CurrentInboundPromptContext,
    EmbeddedRunTrigger,
    RunEmbeddedAgentParams,
    get_run_param_keys,
)
from src.agents.embedded_agent_runner.run.types import (
    EmbeddedRunAttemptBase,
    EmbeddedRunAttemptParams,
    EmbeddedRunFastModeParam,
)


# ============================================================================
# params
# ============================================================================


class TestParamsTypedDicts:
    def test_embedded_run_trigger(self) -> None:
        # EmbeddedRunTrigger is a string literal.
        assert EmbeddedRunTrigger == str
        # Common values.
        assert EmbeddedRunTrigger("cron") == "cron"
        assert EmbeddedRunTrigger("manual") == "manual"

    def test_current_inbound_prompt_context(self) -> None:
        ctx: CurrentInboundPromptContext = {
            "text": "hello",
            "resumableText": "world",
            "promptJoiner": "\n\n",
        }
        assert ctx["text"] == "hello"
        assert ctx["resumableText"] == "world"
        assert ctx["promptJoiner"] == "\n\n"

    def test_run_embedded_agent_params(self) -> None:
        params: RunEmbeddedAgentParams = {
            "sessionId": "s1",
            "sessionKey": "k1",
            "trigger": "manual",
        }
        assert params["sessionId"] == "s1"
        assert params["trigger"] == "manual"

    def test_get_run_param_keys(self) -> None:
        keys = get_run_param_keys()
        assert "sessionId" in keys
        assert "sessionKey" in keys
        assert "agentId" in keys
        assert "trigger" in keys
        assert "abortSignal" in keys


# ============================================================================
# types
# ============================================================================


class TestTypesTypedDicts:
    def test_fast_mode_param_bool(self) -> None:
        value: EmbeddedRunFastModeParam = True
        assert value is True

    def test_fast_mode_param_callable(self) -> None:
        def resolver() -> Optional[bool]:
            return False

        value: EmbeddedRunFastModeParam = resolver
        assert value() is False

    def test_attempt_base(self) -> None:
        base: EmbeddedRunAttemptBase = {
            "sessionId": "s1",
            "sessionKey": "k1",
            "agentId": "a1",
        }
        assert base["sessionId"] == "s1"

    def test_attempt_params(self) -> None:
        params: EmbeddedRunAttemptParams = {
            "sessionId": "s1",
            "sessionFile": "/tmp/s.jsonl",
        }
        assert params["sessionFile"] == "/tmp/s.jsonl"


# ============================================================================
# helpers
# ============================================================================


class TestHelpersConstants:
    def test_constants(self) -> None:
        assert RUNTIME_AUTH_REFRESH_MARGIN_MS == 5 * 60 * 1000
        assert RUNTIME_AUTH_REFRESH_RETRY_MS == 60 * 1000
        assert RUNTIME_AUTH_REFRESH_MIN_DELAY_MS == 5 * 1000
        assert MAX_SAME_MODEL_RATE_LIMIT_RETRIES == 3
        assert SAME_MODEL_RATE_LIMIT_BACKOFF_STEP_MS == 10_000
        assert SAME_MODEL_RATE_LIMIT_MAX_BACKOFF_MS == 60_000
        assert DEFAULT_OVERLOAD_FAILOVER_BACKOFF_MS == 0
        assert DEFAULT_MAX_OVERLOAD_PROFILE_ROTATIONS == 1
        assert DEFAULT_MAX_RATE_LIMIT_PROFILE_ROTATIONS == 1
        assert (
            ANTHROPIC_MAGIC_STRING_TRIGGER_REFUSAL
            == "ANTHROPIC_MAGIC_STRING_TRIGGER_REFUSAL"
        )
        assert ANTHROPIC_MAGIC_STRING_REPLACEMENT.startswith("ANTHROPIC MAGIC STRING")


class TestResolveOverloadFailoverBackoffMs:
    def test_default(self) -> None:
        assert (
            resolve_overload_failover_backoff_ms() == DEFAULT_OVERLOAD_FAILOVER_BACKOFF_MS
        )

    def test_configured(self) -> None:
        config = {"auth": {"cooldowns": {"overloadedBackoffMs": 1234}}}
        assert resolve_overload_failover_backoff_ms(config) == 1234

    def test_missing_cooldowns(self) -> None:
        assert (
            resolve_overload_failover_backoff_ms({"auth": {}})
            == DEFAULT_OVERLOAD_FAILOVER_BACKOFF_MS
        )


class TestResolveOverloadProfileRotationLimit:
    def test_default(self) -> None:
        assert (
            resolve_overload_profile_rotation_limit()
            == DEFAULT_MAX_OVERLOAD_PROFILE_ROTATIONS
        )

    def test_configured(self) -> None:
        config = {
            "auth": {"cooldowns": {"overloadedProfileRotations": 5}}
        }
        assert resolve_overload_profile_rotation_limit(config) == 5


class TestResolveRateLimitProfileRotationLimit:
    def test_default(self) -> None:
        assert (
            resolve_rate_limit_profile_rotation_limit()
            == DEFAULT_MAX_RATE_LIMIT_PROFILE_ROTATIONS
        )

    def test_configured(self) -> None:
        config = {
            "auth": {"cooldowns": {"rateLimitedProfileRotations": 3}}
        }
        assert resolve_rate_limit_profile_rotation_limit(config) == 3


class TestResolveSameModelRateLimitRetryDelayMs:
    def test_first_retry(self) -> None:
        # retriesSoFar=0 -> 10_000 * 1 = 10_000
        assert (
            resolve_same_model_rate_limit_retry_delay_ms(retries_so_far=0)
            == 10_000
        )

    def test_second_retry(self) -> None:
        # retriesSoFar=1 -> 10_000 * 2 = 20_000
        assert (
            resolve_same_model_rate_limit_retry_delay_ms(retries_so_far=1)
            == 20_000
        )

    def test_third_retry(self) -> None:
        # retriesSoFar=2 -> 10_000 * 3 = 30_000
        assert (
            resolve_same_model_rate_limit_retry_delay_ms(retries_so_far=2)
            == 30_000
        )

    def test_max_backoff(self) -> None:
        # retriesSoFar=10 -> 10_000 * 11 = 110_000, capped at 60_000.
        assert (
            resolve_same_model_rate_limit_retry_delay_ms(retries_so_far=10)
            == 60_000
        )

    def test_retry_after_larger(self) -> None:
        # retry_after=120s -> 120_000 ms, > max -> 60_000
        assert (
            resolve_same_model_rate_limit_retry_delay_ms(
                retries_so_far=0, retry_after_seconds=120
            )
            == 60_000
        )

    def test_retry_after_smaller(self) -> None:
        # retry_after=2s -> 2_000 ms, < backoff (10_000) -> 10_000
        assert (
            resolve_same_model_rate_limit_retry_delay_ms(
                retries_so_far=0, retry_after_seconds=2
            )
            == 10_000
        )

    def test_negative_retries_so_far(self) -> None:
        # Treats as 0 -> 10_000
        assert (
            resolve_same_model_rate_limit_retry_delay_ms(retries_so_far=-5)
            == 10_000
        )


class TestResolveNextSameModelRateLimitRetryCount:
    def test_not_retried(self) -> None:
        assert (
            resolve_next_same_model_rate_limit_retry_count(
                retries_so_far=2, retried_same_model_rate_limit=False
            )
            == 0
        )

    def test_retried(self) -> None:
        assert (
            resolve_next_same_model_rate_limit_retry_count(
                retries_so_far=2, retried_same_model_rate_limit=True
            )
            == 3
        )

    def test_retried_zero(self) -> None:
        assert (
            resolve_next_same_model_rate_limit_retry_count(
                retries_so_far=0, retried_same_model_rate_limit=True
            )
            == 1
        )


class TestScrubAnthropicRefusalMagic:
    def test_no_magic(self) -> None:
        prompt = "hello world"
        assert scrub_anthropic_refusal_magic(prompt) == prompt

    def test_magic_replaced(self) -> None:
        prompt = f"hello {ANTHROPIC_MAGIC_STRING_TRIGGER_REFUSAL} world"
        result = scrub_anthropic_refusal_magic(prompt)
        assert ANTHROPIC_MAGIC_STRING_TRIGGER_REFUSAL not in result
        assert ANTHROPIC_MAGIC_STRING_REPLACEMENT in result

    def test_non_string(self) -> None:
        assert scrub_anthropic_refusal_magic(None) is None  # type: ignore[arg-type]

    def test_multiple(self) -> None:
        prompt = (
            f"first {ANTHROPIC_MAGIC_STRING_TRIGGER_REFUSAL} "
            f"second {ANTHROPIC_MAGIC_STRING_TRIGGER_REFUSAL} end"
        )
        result = scrub_anthropic_refusal_magic(prompt)
        assert ANTHROPIC_MAGIC_STRING_TRIGGER_REFUSAL not in result


# ============================================================================
# payloads
# ============================================================================


class TestPayloads:
    def setup_method(self) -> None:
        # Reset all hooks to defaults.
        set_build_embedded_run_payloads_hook(lambda _p: [])
        set_sanitize_assistant_visible_stream_text_hook(lambda t: t)
        set_build_source_reply_payload_state_hook(
            lambda _p: {
                "replyItems": [],
                "hasSourceReplyPayload": False,
                "deliveredSourceReplyViaMessageTool": False,
                "explicitFinalSourceReply": None,
                "completedSourceReplyViaMessageTool": False,
            }
        )
        set_format_tool_aggregate_hook(lambda _e: "")
        set_format_user_facing_assistant_error_text_hook(
            lambda _a, _o: None
        )

    def test_default_returns_empty(self) -> None:
        result = build_embedded_run_payloads({"sessionKey": "k1"})
        assert result == []

    def test_custom_handler(self) -> None:
        called: List[Dict[str, Any]] = []

        def handler(params: Dict[str, Any]) -> List[Dict[str, Any]]:
            called.append(params)
            return [{"text": "ok"}]

        set_build_embedded_run_payloads_hook(handler)
        result = build_embedded_run_payloads({"sessionKey": "k1"})
        assert result == [{"text": "ok"}]
        assert called == [{"sessionKey": "k1"}]

    def test_recoverable_keywords(self) -> None:
        assert "required" in RECOVERABLE_TOOL_ERROR_KEYWORDS
        assert "missing" in RECOVERABLE_TOOL_ERROR_KEYWORDS
        assert "invalid" in RECOVERABLE_TOOL_ERROR_KEYWORDS
        assert "must be" in RECOVERABLE_TOOL_ERROR_KEYWORDS

    def test_is_recoverable_tool_error(self) -> None:
        assert is_recoverable_tool_error("Argument is required")
        assert is_recoverable_tool_error("Missing field")
        assert is_recoverable_tool_error("Invalid value")
        assert is_recoverable_tool_error("Must be a string")
        assert not is_recoverable_tool_error("Unknown error")
        assert not is_recoverable_tool_error("")


# ============================================================================
# images
# ============================================================================


class TestImageExtensions:
    def test_extensions_set(self) -> None:
        assert ".png" in IMAGE_EXTENSIONS
        assert ".jpg" in IMAGE_EXTENSIONS
        assert ".jpeg" in IMAGE_EXTENSIONS
        assert ".webp" in IMAGE_EXTENSIONS

    def test_image_extension_names(self) -> None:
        assert "png" in IMAGE_EXTENSION_NAMES
        assert "gif" in IMAGE_EXTENSION_NAMES
        assert "heic" in IMAGE_EXTENSION_NAMES

    def test_is_image_extension(self) -> None:
        assert is_image_extension("/tmp/photo.png") is True
        assert is_image_extension("C:/img/test.jpg") is True
        assert is_image_extension("foo.webp") is True
        assert is_image_extension("/tmp/file.txt") is False
        assert is_image_extension("") is False
        assert is_image_extension(None) is False  # type: ignore[arg-type]

    def test_is_image_extension_case_insensitive(self) -> None:
        assert is_image_extension("/tmp/FOO.PNG") is True
        assert is_image_extension("bar.JpG") is True


class TestMediaUriRegex:
    def test_simple_match(self) -> None:
        match = MEDIA_URI_REGEX.search("[Image: source: media://inbound/abc123.png]")
        assert match is not None
        assert match.group(1) == "abc123.png"

    def test_unicode_id(self) -> None:
        match = MEDIA_URI_REGEX.search("media://inbound/图片.png")
        assert match is not None
        assert match.group(1) == "图片.png"

    def test_dash_underscore(self) -> None:
        match = MEDIA_URI_REGEX.search("media://inbound/photo_123-abc.png")
        assert match is not None
        assert match.group(1) == "photo_123-abc.png"

    def test_no_match(self) -> None:
        assert MEDIA_URI_REGEX.search("not a media uri") is None


class TestDetectImageReferences:
    def test_empty(self) -> None:
        assert detect_image_references("") == []
        assert detect_image_references(None) == []  # type: ignore[arg-type]

    def test_media_uri(self) -> None:
        refs = detect_image_references("see media://inbound/abc.png please")
        assert len(refs) == 1
        assert refs[0]["type"] == "media-uri"
        assert refs[0]["id"] == "abc.png"

    def test_path(self) -> None:
        refs = detect_image_references("see /tmp/photo.png")
        assert any(r["type"] == "path" for r in refs)

    def test_windows_path(self) -> None:
        refs = detect_image_references("see C:/img/test.jpg")
        assert any(r["type"] == "path" for r in refs)

    def test_message_image(self) -> None:
        prompt = "[Image: source: /tmp/photo.png]"
        refs = detect_image_references(prompt)
        assert any(r["type"] == "path" for r in refs)

    def test_file_url(self) -> None:
        refs = detect_image_references("see file:///tmp/img.png")
        assert any(r["type"] == "path" for r in refs)

    def test_dedup(self) -> None:
        refs = detect_image_references(
            "media://inbound/abc.png and media://inbound/abc.png"
        )
        assert len(refs) == 1

    def test_non_image_path_filtered(self) -> None:
        refs = detect_image_references("see /tmp/file.txt")
        # The .txt path is not in IMAGE_EXTENSIONS, so it should be
        # filtered out. But the path regex doesn't validate
        # extension, only IMAGE_EXTENSION regexes do.
        # Looking at the source: the path regex includes the
        # image extension, so .txt won't match.
        # Actually our path_regex uses (?:" + "|".join(IMAGE_EXTENSION_NAMES) + r")
        # so only image extensions are captured.
        assert refs == []


class TestMergePromptAttachmentImages:
    def test_no_order(self) -> None:
        result = merge_prompt_attachment_images(
            existing_images=[{"a": 1}],
            offloaded_images=[{"b": 2}],
            prompt_ref_images=[{"c": 3}],
        )
        assert len(result) == 3

    def test_with_order(self) -> None:
        result = merge_prompt_attachment_images(
            image_order=["inline", "offloaded", "inline"],
            existing_images=[{"a": 1}, {"a": 2}],
            offloaded_images=[{"b": 1}],
            prompt_ref_images=[{"c": 1}],
        )
        # inline-0: a=1, offloaded-0: b=1, inline-1: a=2, then no more,
        # then prompt_ref c=1.
        assert result == [{"a": 1}, {"b": 1}, {"a": 2}, {"c": 1}]

    def test_with_order_skips_null(self) -> None:
        result = merge_prompt_attachment_images(
            image_order=["offloaded", "offloaded"],
            offloaded_images=[None, {"b": 2}],
        )
        assert result == [{"b": 2}]

    def test_no_images(self) -> None:
        result = merge_prompt_attachment_images()
        assert result == []
