"""Tests for memory_core.dreaming — Phase 4.4j.

Mirrors the TypeScript ``test_dreaming.test.ts`` patterns. Tests the
deterministic surface (cron job builders, config resolver, helper
classifiers) and the stubbed lifecycle functions.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace


from extensions.memory_core import dreaming as drm


# ── Cron constants ──────────────────────────────────────────────────


def test_constants_present() -> None:
    """All exported constants are present and have expected values."""
    assert drm.RUNTIME_CRON_RECONCILE_INTERVAL_MS == 60_000
    assert drm.STARTUP_CRON_RETRY_DELAY_MS == 5_000
    assert drm.STARTUP_CRON_RETRY_MAX_ATTEMPTS == 12
    assert drm.HEARTBEAT_ISOLATED_SESSION_SUFFIX == ":heartbeat"
    assert drm.MANAGED_DREAMING_CRON_NAME == "Memory Dreaming Promotion"
    assert drm.MANAGED_DREAMING_CRON_TAG.startswith("[managed-by=")
    assert drm.DREAMING_SYSTEM_EVENT_TEXT.startswith("__openclaw_")
    assert drm.LEGACY_LIGHT_SLEEP_CRON_NAME == "Memory Light Dreaming"
    assert drm.LEGACY_REM_SLEEP_CRON_NAME == "Memory REM Dreaming"
    assert drm.DEFAULT_MEMORY_DREAMING_MAX_PROMOTED_SNIPPET_TOKENS == 160
    assert drm.DEFAULT_MEMORY_DREAMING_RECENCY_HALF_LIFE_DAYS == 14


# ── Managed cron description + job builder ──────────────────────────


def test_resolve_managed_cron_description_basic() -> None:
    """Description includes tag + thresholds + recency window."""
    config: drm.ShortTermPromotionDreamingConfig = {
        "enabled": True,
        "cron": "0 3 * * *",
        "limit": 10,
        "minScore": 0.8,
        "minRecallCount": 3,
        "minUniqueQueries": 3,
    }
    description = drm.resolve_managed_cron_description(config)
    assert drm.MANAGED_DREAMING_CRON_TAG in description
    assert "limit=10" in description
    assert "minScore=0.800" in description
    assert "minRecallCount=3" in description
    assert "minUniqueQueries=3" in description
    assert "recencyHalfLifeDays=14" in description  # default
    assert "maxAgeDays=none" in description  # None → "none"


def test_resolve_managed_cron_description_with_max_age() -> None:
    """``maxAgeDays`` is rendered when present."""
    config: drm.ShortTermPromotionDreamingConfig = {
        "limit": 5,
        "minScore": 0.7,
        "minRecallCount": 2,
        "minUniqueQueries": 2,
        "maxAgeDays": 30,
    }
    description = drm.resolve_managed_cron_description(config)
    assert "maxAgeDays=30" in description


def test_build_managed_dreaming_cron_job_basic() -> None:
    """Job dict has all required fields."""
    config: drm.ShortTermPromotionDreamingConfig = {
        "cron": "0 3 * * *",
        "timezone": "UTC",
    }
    job = drm.build_managed_dreaming_cron_job(config)
    assert job["name"] == drm.MANAGED_DREAMING_CRON_NAME
    assert job["enabled"] is True
    assert job["sessionTarget"] == "isolated"
    assert job["wakeMode"] == "now"
    assert job["delivery"] == {"mode": "none"}
    schedule = job["schedule"]
    assert isinstance(schedule, dict)
    assert schedule["kind"] == "cron"
    assert schedule["expr"] == "0 3 * * *"
    assert schedule["tz"] == "UTC"
    payload = job["payload"]
    assert isinstance(payload, dict)
    assert payload["kind"] == "agentTurn"
    assert payload["message"] == drm.DREAMING_SYSTEM_EVENT_TEXT
    assert payload["lightContext"] is True


def test_build_managed_dreaming_cron_job_no_timezone() -> None:
    """Without timezone, the schedule omits the ``tz`` key."""
    config: drm.ShortTermPromotionDreamingConfig = {"cron": "0 3 * * *"}
    job = drm.build_managed_dreaming_cron_job(config)
    schedule = job["schedule"]
    assert isinstance(schedule, dict)
    assert "tz" not in schedule


# ── Payload token resolver ──────────────────────────────────────────


def test_resolve_managed_dreaming_payload_token_systemevent() -> None:
    """``systemEvent`` payload returns the trimmed text."""
    payload = {"kind": "systemEvent", "text": "  hello  "}
    assert drm.resolve_managed_dreaming_payload_token(payload) == "hello"


def test_resolve_managed_dreaming_payload_token_agentturn() -> None:
    """``agentTurn`` payload returns the trimmed message."""
    payload = {"kind": "agentTurn", "message": "wake up"}
    assert drm.resolve_managed_dreaming_payload_token(payload) == "wake up"


def test_resolve_managed_dreaming_payload_token_unknown_kind() -> None:
    """Unknown payload kinds return ``None``."""
    assert drm.resolve_managed_dreaming_payload_token({"kind": "unknown"}) is None
    assert drm.resolve_managed_dreaming_payload_token({}) is None
    assert drm.resolve_managed_dreaming_payload_token(None) is None


def test_resolve_managed_dreaming_payload_token_empty() -> None:
    """Empty text / message returns ``None``."""
    assert drm.resolve_managed_dreaming_payload_token({"kind": "systemEvent", "text": ""}) is None
    assert (
        drm.resolve_managed_dreaming_payload_token({"kind": "agentTurn", "message": "  "}) is None
    )


def test_resolve_managed_dreaming_payload_token_case_insensitive_kind() -> None:
    """``kind`` match is case-insensitive (matches OpenClaw's lowercased compare)."""
    payload = {"kind": "SystemEvent", "text": "hello"}
    assert drm.resolve_managed_dreaming_payload_token(payload) == "hello"


# ── Job classifiers ─────────────────────────────────────────────────


def test_is_managed_dreaming_job_by_name() -> None:
    """Job with the managed cron name is recognized."""
    job: drm.ManagedCronJobLike = {"name": drm.MANAGED_DREAMING_CRON_NAME}
    assert drm.is_managed_dreaming_job(job) is True


def test_is_managed_dreaming_job_by_tag() -> None:
    """Job with the managed cron tag in the description is recognized."""
    job: drm.ManagedCronJobLike = {"description": f"prefix {drm.MANAGED_DREAMING_CRON_TAG} suffix"}
    assert drm.is_managed_dreaming_job(job) is True


def test_is_managed_dreaming_job_unrelated() -> None:
    """Unrelated jobs return ``False``."""
    assert drm.is_managed_dreaming_job({"name": "Other Job"}) is False
    assert drm.is_managed_dreaming_job({}) is False
    assert drm.is_managed_dreaming_job(None) is False  # type: ignore[arg-type]


def test_is_legacy_phase_dreaming_job_light() -> None:
    """Legacy light dreaming job is recognized."""
    job: drm.ManagedCronJobLike = {"name": drm.LEGACY_LIGHT_SLEEP_CRON_NAME}
    assert drm.is_legacy_phase_dreaming_job(job) is True


def test_is_legacy_phase_dreaming_job_rem() -> None:
    """Legacy REM dreaming job is recognized."""
    job: drm.ManagedCronJobLike = {"name": drm.LEGACY_REM_SLEEP_CRON_NAME}
    assert drm.is_legacy_phase_dreaming_job(job) is True


def test_is_legacy_phase_dreaming_job_unrelated() -> None:
    """Unrelated jobs return ``False``."""
    assert drm.is_legacy_phase_dreaming_job({"name": "Other Job"}) is False
    assert drm.is_legacy_phase_dreaming_job({}) is False


# ── compare_optional_strings ────────────────────────────────────────


def test_compare_optional_strings_both_none() -> None:
    assert drm.compare_optional_strings(None, None) is True


def test_compare_optional_strings_one_none() -> None:
    assert drm.compare_optional_strings(None, "x") is False
    assert drm.compare_optional_strings("x", None) is False


def test_compare_optional_strings_equal() -> None:
    assert drm.compare_optional_strings("hello", "hello") is True
    assert drm.compare_optional_strings("HELLO", "hello") is True  # case-insensitive
    assert drm.compare_optional_strings("  hello  ", "hello") is True  # trim


def test_compare_optional_strings_different() -> None:
    assert drm.compare_optional_strings("hello", "world") is False


# ── Config resolver ─────────────────────────────────────────────────


def test_resolve_short_term_promotion_dreaming_config_defaults() -> None:
    """Empty config returns the documented defaults."""
    config = drm.resolve_short_term_promotion_dreaming_config({})
    assert config["enabled"] is False
    assert config["cron"] == "0 3 * * *"
    assert config["timezone"] is None
    assert config["limit"] == 10
    assert config["minScore"] == 0.8
    assert config["minRecallCount"] == 3
    assert config["minUniqueQueries"] == 3
    assert config["recencyHalfLifeDays"] == 14
    assert config["maxAgeDays"] is None
    assert config["maxPromotedSnippetTokens"] == 160
    assert config["verboseLogging"] is False


def test_resolve_short_term_promotion_dreaming_config_full() -> None:
    """All fields are resolved from the input."""
    plugin_config = {
        "dreaming": {
            "enabled": True,
            "frequency": "0 4 * * *",
            "timezone": "Asia/Kathmandu",
            "verboseLogging": True,
            "storage": {"mode": "both", "separateReports": True},
            "execution": {"model": "gpt-4"},
        },
        "deep": {
            "limit": 25,
            "minScore": 0.9,
            "minRecallCount": 5,
            "minUniqueQueries": 4,
            "recencyHalfLifeDays": 7,
            "maxAgeDays": 60,
            "maxPromotedSnippetTokens": 200,
        },
    }
    config = drm.resolve_short_term_promotion_dreaming_config(plugin_config)
    assert config["enabled"] is True
    assert config["cron"] == "0 4 * * *"
    assert config["timezone"] == "Asia/Kathmandu"
    assert config["limit"] == 25
    assert config["minScore"] == 0.9
    assert config["minRecallCount"] == 5
    assert config["minUniqueQueries"] == 4
    assert config["recencyHalfLifeDays"] == 7
    assert config["maxAgeDays"] == 60
    assert config["maxPromotedSnippetTokens"] == 200
    assert config["verboseLogging"] is True
    assert config["storage"] == {"mode": "both", "separateReports": True}
    assert config["execution"] == {"model": "gpt-4"}


def test_resolve_short_term_promotion_dreaming_config_no_plugin() -> None:
    """``None`` config returns the defaults."""
    config = drm.resolve_short_term_promotion_dreaming_config(None)
    assert config["enabled"] is False
    assert config["cron"] == "0 3 * * *"


# ── Cron service resolution ────────────────────────────────────────


def test_resolve_cron_service_from_candidate_object_attr() -> None:
    """``candidate.cron`` is used when present."""
    fake_cron = SimpleNamespace(list=lambda: None)
    candidate = SimpleNamespace(cron=fake_cron)
    assert drm._resolve_cron_service_from_candidate(candidate) is fake_cron


def test_resolve_cron_service_from_candidate_getter() -> None:
    """``candidate.getCron()`` / ``get_cron()`` are tried as fallbacks."""
    fake_cron = SimpleNamespace(list=lambda: None)
    candidate = SimpleNamespace(get_cron=lambda: fake_cron)
    assert drm._resolve_cron_service_from_candidate(candidate) is fake_cron


def test_resolve_cron_service_from_candidate_none() -> None:
    """No service when nothing is configured."""
    assert drm._resolve_cron_service_from_candidate(None) is None
    assert drm._resolve_cron_service_from_candidate({}) is None


def test_resolve_cron_service_from_gateway_context() -> None:
    """``context.getCron()`` returns the cron service."""
    fake_cron = SimpleNamespace(list=lambda: None)
    context = {"getCron": lambda: fake_cron}
    assert drm._resolve_cron_service_from_gateway_context(context) is fake_cron


def test_resolve_cron_service_from_gateway_context_invalid() -> None:
    """Non-dict / missing getter → ``None``."""
    assert drm._resolve_cron_service_from_gateway_context(None) is None
    assert drm._resolve_cron_service_from_gateway_context({}) is None


# ── Reconciliation + trigger (stubs) ─────────────────────────────────


def test_reconcile_returns_unavailable_without_cron() -> None:
    """No cron service → ``{status: "unavailable", removed: 0}``."""
    result = asyncio.run(drm.reconcile_short_term_dreaming_cron_job({}))
    assert result["status"] == "unavailable"
    assert result["removed"] == 0


def test_run_short_term_dreaming_promotion_if_triggered_stub() -> None:
    """Stub returns ``False`` (no sweep was triggered)."""
    result = asyncio.run(
        drm.run_short_term_dreaming_promotion_if_triggered(workspace_dir="/tmp/ws")
    )
    assert result is False


def test_register_short_term_promotion_dreaming_stub() -> None:
    """Stub logs warn + returns (no exception)."""
    calls: list[str] = []

    class _L:
        def info(self, m: str) -> None:
            pass

        def warn(self, m: str) -> None:
            calls.append(m)

        def error(self, m: str) -> None:
            pass

    api = SimpleNamespace(logger=_L())
    drm.register_short_term_promotion_dreaming(api)
    assert any("stub" in m for m in calls)


def test_register_short_term_promotion_dreaming_no_logger() -> None:
    """Stub tolerates a missing logger."""
    api = SimpleNamespace(logger=None)
    # No exception
    drm.register_short_term_promotion_dreaming(api)
