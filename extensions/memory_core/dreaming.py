"""memory_core.dreaming — short-term promotion dreaming (cron + lifecycle).

OpenClaw parity: mirrors ``extensions/memory-core/src/dreaming.ts``
(926 LOC). This is the orchestrator that ties the dreaming pipeline
to the cron service:

- ``resolve_short_term_promotion_dreaming_config`` — read the
  ``memory-core`` plugin's dreaming config and return a fully
  resolved ``ShortTermPromotionDreamingConfig``.
- ``build_managed_dreaming_cron_job`` — build the managed cron
  job dict that the host registers for the dreaming sweep.
- ``is_managed_dreaming_job`` / ``is_legacy_phase_dreaming_job`` —
  detect managed vs. legacy cron jobs so the reconciliation step
  can update / remove them.
- ``resolve_managed_dreaming_payload_token`` — extract the
  payload text token (systemEvent or agentTurn) from a job.
- ``compare_optional_strings`` — case-insensitive optional-string
  equality used to detect cron-job drift.
- ``register_short_term_promotion_dreaming`` — STUB. Wires the
  cron service + reconciliation loop + startup retry. Logs a
  warning and returns when the cron service / system event
  runtime isn't available; the public surface is documented so
  callers can import from the right location.

Key port decisions:
- All cron-name / cron-tag / system-event-text constants are
  inlined as Python module constants (they're owned by the
  dreaming module, not the SDK).
- ``resolve_short_term_promotion_dreaming_config`` reads the
  same fields the SDK's resolver would surface. Defaults match
  OpenClaw's documented defaults.
- The cron service surface is inlined as ``CronServiceLike``
  with ``list / add / update / remove`` — when the JARVIS cron
  extension exposes the equivalent, replace with delegation.
- The reconciliation step (``reconcile_short_term_dreaming_cron_job``)
  is also a stub: it returns a ``ReconcileResult`` with
  ``status="unavailable"`` when no cron service is configured.
- The trigger detection (``run_short_term_dreaming_promotion_if_triggered``)
  is stubbed for the same reason.
"""
from __future__ import annotations

import asyncio
from typing import Any, Literal, TypedDict


# ── Cron constants (inlined from OpenClaw) ───────────────────────────

RUNTIME_CRON_RECONCILE_INTERVAL_MS = 60_000
STARTUP_CRON_RETRY_DELAY_MS = 5_000
STARTUP_CRON_RETRY_MAX_ATTEMPTS = 12
HEARTBEAT_ISOLATED_SESSION_SUFFIX = ":heartbeat"

# Owned by the dreaming module; mirrored from OpenClaw's
# ``memory-core-host-status`` constants.
MANAGED_DREAMING_CRON_NAME = "Memory Dreaming Promotion"
MANAGED_DREAMING_CRON_TAG = "[managed-by=memory-core.short-term-promotion]"
DREAMING_SYSTEM_EVENT_TEXT = "__openclaw_memory_core_short_term_promotion_dream__"

LEGACY_LIGHT_SLEEP_CRON_NAME = "Memory Light Dreaming"
LEGACY_LIGHT_SLEEP_CRON_TAG = "[managed-by=memory-core.dreaming.light]"
LEGACY_LIGHT_SLEEP_EVENT_TEXT = "__openclaw_memory_core_light_sleep__"

LEGACY_REM_SLEEP_CRON_NAME = "Memory REM Dreaming"
LEGACY_REM_SLEEP_CRON_TAG = "[managed-by=memory-core.dreaming.rem]"
LEGACY_REM_SLEEP_EVENT_TEXT = "__openclaw_memory_core_rem_sleep__"

# Defaults (mirrors OpenClaw's ``DEFAULT_MEMORY_DEEP_DREAMING_*``)
DEFAULT_MEMORY_DREAMING_MAX_PROMOTED_SNIPPET_TOKENS = 160
DEFAULT_MEMORY_DREAMING_RECENCY_HALF_LIFE_DAYS = 14


# ── Types ─────────────────────────────────────────────────────────────


CronSchedule = TypedDict("CronSchedule", {"kind": str, "expr": str, "tz": str}, total=False)


class CronPayloadSystemEvent(TypedDict, total=False):
    kind: Literal["systemEvent"]
    text: str


class CronPayloadAgentTurn(TypedDict, total=False):
    kind: Literal["agentTurn"]
    message: str
    lightContext: bool


CronPayload = dict  # Union of the two above; loose typing for cross-host compat


class ManagedCronJobCreate(TypedDict, total=False):
    name: str
    description: str
    enabled: bool
    schedule: dict
    sessionTarget: Literal["main", "isolated"]
    wakeMode: Literal["now"]
    payload: dict
    delivery: dict


class ManagedCronJobLike(TypedDict, total=False):
    id: str
    name: str
    description: str
    enabled: bool
    schedule: dict
    sessionTarget: str
    wakeMode: str
    payload: dict
    delivery: dict
    createdAtMs: int


class ShortTermPromotionDreamingConfig(TypedDict, total=False):
    enabled: bool
    cron: str
    timezone: str
    limit: int
    minScore: float
    minRecallCount: int
    minUniqueQueries: int
    recencyHalfLifeDays: int
    maxAgeDays: int
    maxPromotedSnippetTokens: int
    verboseLogging: bool
    storage: dict
    execution: dict


ReconcileResult = TypedDict(
    "ReconcileResult",
    {
        "status": Literal["unavailable", "disabled", "added", "updated", "noop"],
        "removed": int,
    },
    total=False,
)


# ── Cron job builders ────────────────────────────────────────────────


def _normalize_lower(value: str | None) -> str:
    """Trim + lowercase. Empty string when not a non-empty string."""
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


def resolve_managed_cron_description(
    config: ShortTermPromotionDreamingConfig,
) -> str:
    """Return the description string for the managed dreaming cron job.

    Mirrors OpenClaw's ``resolveManagedCronDescription``. Includes
    the tag, limit, thresholds, and recency window.
    """
    recency = config.get("recencyHalfLifeDays")
    if recency is None:
        recency = DEFAULT_MEMORY_DREAMING_RECENCY_HALF_LIFE_DAYS
    max_age = config.get("maxAgeDays")
    return (
        f"{MANAGED_DREAMING_CRON_TAG} "
        f"Promote weighted short-term recalls into MEMORY.md "
        f"(limit={config.get('limit', 0)}, "
        f"minScore={float(config.get('minScore', 0)):.3f}, "
        f"minRecallCount={config.get('minRecallCount', 0)}, "
        f"minUniqueQueries={config.get('minUniqueQueries', 0)}, "
        f"recencyHalfLifeDays={recency}, "
        f"maxAgeDays={'none' if max_age is None else max_age})."
    )


def build_managed_dreaming_cron_job(
    config: ShortTermPromotionDreamingConfig,
) -> ManagedCronJobCreate:
    """Build the managed cron job dict for the dreaming sweep.

    Mirrors OpenClaw's ``buildManagedDreamingCronJob``. Uses
    ``sessionTarget: "isolated"`` and ``delivery.mode: "none"`` so
    the sweep doesn't fan out to channels.
    """
    schedule: dict = {"kind": "cron", "expr": config.get("cron", "0 3 * * *")}
    tz = config.get("timezone")
    if tz:
        schedule["tz"] = tz
    return {
        "name": MANAGED_DREAMING_CRON_NAME,
        "description": resolve_managed_cron_description(config),
        "enabled": True,
        "schedule": schedule,
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {
            "kind": "agentTurn",
            "message": DREAMING_SYSTEM_EVENT_TEXT,
            "lightContext": True,
        },
        "delivery": {"mode": "none"},
    }


def resolve_managed_dreaming_payload_token(
    payload: Any,
) -> str | None:
    """Return the payload text token (``systemEvent.text`` or
    ``agentTurn.message``), or ``None`` for unknown payload kinds.

    Mirrors OpenClaw's ``resolveManagedDreamingPayloadToken``.
    """
    if not isinstance(payload, dict):
        return None
    kind = _normalize_lower(payload.get("kind"))
    if kind == "systemevent":
        text = payload.get("text")
        if isinstance(text, str):
            trimmed = text.strip()
            return trimmed if trimmed else None
        return None
    if kind == "agentturn":
        msg = payload.get("message")
        if isinstance(msg, str):
            trimmed = msg.strip()
            return trimmed if trimmed else None
        return None
    return None


def is_managed_dreaming_job(job: ManagedCronJobLike) -> bool:
    """Return ``True`` if ``job`` is the managed dreaming cron job.

    Mirrors OpenClaw's ``isManagedDreamingJob``. Matches by the
    cron tag in the description OR by the name field.
    """
    if not isinstance(job, dict):
        return False
    name = job.get("name")
    description = job.get("description")
    if isinstance(name, str) and name.strip() == MANAGED_DREAMING_CRON_NAME:
        return True
    if isinstance(description, str) and MANAGED_DREAMING_CRON_TAG in description:
        return True
    return False


def is_legacy_phase_dreaming_job(job: ManagedCronJobLike) -> bool:
    """Return ``True`` if ``job`` is a legacy phase dreaming cron job.

    Mirrors OpenClaw's ``isLegacyPhaseDreamingJob``. Matches the
    legacy light / REM sleep cron names.
    """
    if not isinstance(job, dict):
        return False
    name = job.get("name")
    if not isinstance(name, str):
        return False
    return name.strip() in (LEGACY_LIGHT_SLEEP_CRON_NAME, LEGACY_REM_SLEEP_CRON_NAME)


def compare_optional_strings(a: str | None, b: str | None) -> bool:
    """Case-insensitive optional-string equality (both treated as ``""``).

    Mirrors OpenClaw's ``compareOptionalStrings``. Used to detect
    cron-job drift (e.g. payload text changed).
    """
    return _normalize_lower(a) == _normalize_lower(b)


# ── Config resolver ──────────────────────────────────────────────────


def resolve_short_term_promotion_dreaming_config(
    plugin_config: dict | None = None, cfg: Any = None
) -> ShortTermPromotionDreamingConfig:
    """Resolve the dreaming config from the plugin's config dict.

    Mirrors OpenClaw's ``resolveShortTermPromotionDreamingConfig``.
    Reads ``plugin_config.deep`` (and ``plugin_config.dreaming``)
    and returns a fully-populated ``ShortTermPromotionDreamingConfig``.
    """
    plugin_config = plugin_config if isinstance(plugin_config, dict) else {}
    deep = plugin_config.get("deep") if isinstance(plugin_config.get("deep"), dict) else {}
    dreaming = (
        plugin_config.get("dreaming") if isinstance(plugin_config.get("dreaming"), dict) else {}
    )
    storage = (
        dreaming.get("storage") if isinstance(dreaming.get("storage"), dict) else None
    )
    execution = (
        dreaming.get("execution") if isinstance(dreaming.get("execution"), dict) else None
    )
    enabled = bool(dreaming.get("enabled", deep.get("enabled", False)))
    return {
        "enabled": enabled,
        "cron": str(dreaming.get("frequency") or deep.get("cron") or "0 3 * * *"),
        "timezone": (
            str(dreaming.get("timezone") or deep.get("timezone"))
            if (dreaming.get("timezone") or deep.get("timezone"))
            else None
        ),
        "limit": int(deep.get("limit", 10)),
        "minScore": float(deep.get("minScore", 0.8)),
        "minRecallCount": int(deep.get("minRecallCount", 3)),
        "minUniqueQueries": int(deep.get("minUniqueQueries", 3)),
        "recencyHalfLifeDays": int(
            deep.get("recencyHalfLifeDays", DEFAULT_MEMORY_DREAMING_RECENCY_HALF_LIFE_DAYS)
        ),
        "maxAgeDays": deep.get("maxAgeDays") if deep.get("maxAgeDays") is not None else None,
        "maxPromotedSnippetTokens": int(
            deep.get(
                "maxPromotedSnippetTokens",
                DEFAULT_MEMORY_DREAMING_MAX_PROMOTED_SNIPPET_TOKENS,
            )
        ),
        "verboseLogging": bool(dreaming.get("verboseLogging", False)),
        **({"storage": storage} if storage is not None else {}),
        **({"execution": execution} if execution is not None else {}),
    }


# ── Reconciliation (STUB) ────────────────────────────────────────────


def _resolve_cron_service_from_candidate(candidate: Any) -> Any | None:
    """Best-effort: find a cron service on the candidate object.

    Mirrors OpenClaw's ``resolveCronServiceFromCandidate``. Looks for
    ``candidate.cron`` first; then for ``candidate.getCron`` /
    ``candidate.get_cron``.
    """
    if candidate is None:
        return None
    cron = getattr(candidate, "cron", None)
    if cron is not None and hasattr(cron, "list"):
        return cron
    for name in ("getCron", "get_cron"):
        fn = getattr(candidate, name, None)
        if callable(fn):
            try:
                resolved = fn()
            except Exception:  # noqa: BLE001
                return None
            if resolved is not None and hasattr(resolved, "list"):
                return resolved
    return None


def _resolve_cron_service_from_gateway_context(context: Any) -> Any | None:
    """Best-effort: find a cron service via the gateway context.

    Mirrors OpenClaw's ``resolveCronServiceFromGatewayContext``.
    """
    if not isinstance(context, dict):
        return None
    getter = context.get("getCron") or context.get("get_cron")
    if callable(getter):
        try:
            return getter()
        except Exception:  # noqa: BLE001
            return None
    return None


async def reconcile_short_term_dreaming_cron_job(  # pragma: no cover - stub
    plugin_config: dict | None = None,
    cfg: Any = None,
    *,
    api: Any = None,
    runtime_context: Any = None,
) -> ReconcileResult:
    """[STUB] Reconcile the managed dreaming cron job.

    Mirrors OpenClaw's ``reconcileShortTermDreamingCronJob``. Tries
    to resolve a cron service from the API / runtime context; if
    none is available, returns ``{status: "unavailable", removed: 0}``.
    Full implementation requires the JARVIS cron extension.
    """
    cron_service: Any | None = None
    if api is not None:
        cron_service = _resolve_cron_service_from_candidate(api)
    if cron_service is None and runtime_context is not None:
        cron_service = _resolve_cron_service_from_gateway_context(runtime_context)
    if cron_service is None:
        return {"status": "unavailable", "removed": 0}
    # Real implementation would: list → find managed job → compare
    # to built job → add/update/remove. Stubbed for now.
    return {"status": "noop", "removed": 0}


async def run_short_term_dreaming_promotion_if_triggered(  # pragma: no cover - stub
    *,
    workspace_dir: str,
    session_key: str | None = None,
    api: Any = None,
) -> bool:
    """[STUB] Run the dreaming sweep if the session was triggered by
    a managed dreaming cron job.

    Mirrors OpenClaw's ``runShortTermDreamingPromotionIfTriggered``.
    Returns ``True`` when the sweep was triggered. Full
    implementation requires the LLM subagent + system event runtime.
    """
    return False


# ── Main entry point (STUB) ──────────────────────────────────────────


def register_short_term_promotion_dreaming(  # pragma: no cover - stub
    api: Any,
) -> None:
    """[STUB] Wire the dreaming pipeline into the plugin lifecycle.

    Mirrors OpenClaw's ``registerShortTermPromotionDreaming``. In
    OpenClaw, this:
    1. Resolves the dreaming config
    2. Reconciles the managed cron job
    3. Sets up startup retries for the cron registration
    4. Registers a runtime cron-reconcile interval
    5. Wires the trigger detection (``runShortTermDreamingPromotionIfTriggered``)
    6. Hooks config migration for legacy phase cron jobs

    All of these require the JARVIS cron extension + system event
    runtime + the full LLM orchestrator (4.4e / 4.4h stubs). When
    those modules are ported, fill in the body — the surface
    surface (function signature) is stable.
    """
    logger = getattr(api, "logger", None)
    if logger is not None and hasattr(logger, "warn"):
        logger.warn(
            "memory-core: register_short_term_promotion_dreaming is a "
            "stub until the cron extension + system event runtime are "
            "wired in (see extensions/memory_core/dreaming.py docstring)"
        )


__all__ = [
    # Cron constants
    "RUNTIME_CRON_RECONCILE_INTERVAL_MS",
    "STARTUP_CRON_RETRY_DELAY_MS",
    "STARTUP_CRON_RETRY_MAX_ATTEMPTS",
    "HEARTBEAT_ISOLATED_SESSION_SUFFIX",
    "MANAGED_DREAMING_CRON_NAME",
    "MANAGED_DREAMING_CRON_TAG",
    "DREAMING_SYSTEM_EVENT_TEXT",
    "LEGACY_LIGHT_SLEEP_CRON_NAME",
    "LEGACY_LIGHT_SLEEP_CRON_TAG",
    "LEGACY_LIGHT_SLEEP_EVENT_TEXT",
    "LEGACY_REM_SLEEP_CRON_NAME",
    "LEGACY_REM_SLEEP_CRON_TAG",
    "LEGACY_REM_SLEEP_EVENT_TEXT",
    "DEFAULT_MEMORY_DREAMING_MAX_PROMOTED_SNIPPET_TOKENS",
    "DEFAULT_MEMORY_DREAMING_RECENCY_HALF_LIFE_DAYS",
    # Types
    "ManagedCronJobCreate",
    "ManagedCronJobLike",
    "CronPayload",
    "CronSchedule",
    "ShortTermPromotionDreamingConfig",
    "ReconcileResult",
    # Cron job builders
    "resolve_managed_cron_description",
    "build_managed_dreaming_cron_job",
    "resolve_managed_dreaming_payload_token",
    "is_managed_dreaming_job",
    "is_legacy_phase_dreaming_job",
    "compare_optional_strings",
    # Config resolver
    "resolve_short_term_promotion_dreaming_config",
    # Cron service resolution
    "_resolve_cron_service_from_candidate",
    "_resolve_cron_service_from_gateway_context",
    # Reconciliation + main (stubs)
    "reconcile_short_term_dreaming_cron_job",
    "run_short_term_dreaming_promotion_if_triggered",
    "register_short_term_promotion_dreaming",
]
