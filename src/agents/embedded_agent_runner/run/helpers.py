"""jarvis.agents.embedded_agent_runner.run.helpers — shared run helpers.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/helpers.ts``.

Public surface (mirrors the OpenClaw source):

- :data:`RUNTIME_AUTH_REFRESH_MARGIN_MS` —
  ``5 * 60 * 1000`` (5 minutes).
- :data:`RUNTIME_AUTH_REFRESH_RETRY_MS` — ``60 * 1000`` (60
  seconds).
- :data:`RUNTIME_AUTH_REFRESH_MIN_DELAY_MS` — ``5 * 1000``
  (5 seconds).
- :data:`MAX_SAME_MODEL_RATE_LIMIT_RETRIES` — ``3``.
- :data:`RuntimeAuthState` — TypedDict for the runtime auth
  state.
- :func:`resolve_overload_failover_backoff_ms` — return the
  configured overloaded backoff.
- :func:`resolve_overload_profile_rotation_limit` — return the
  configured overloaded profile rotation limit.
- :func:`resolve_rate_limit_profile_rotation_limit` — return
  the configured rate-limited profile rotation limit.
- :func:`resolve_same_model_rate_limit_retry_delay_ms` —
  compute the next same-model rate-limit retry delay.
- :func:`resolve_next_same_model_rate_limit_retry_count` —
  compute the next same-model rate-limit retry count.
- :func:`scrub_anthropic_refusal_magic` — replace the
  Anthropic refusal-magic trigger string in a prompt.

Phase 7.6a — focused minimal port.

The OpenClaw source is 200+ lines and tightly coupled to the
agent-config, usage-accumulator, assistant-text-extraction, and
secure-random layers. The Python port keeps the public surface
and delegates the heavy extraction to installable hooks so the
host can plug in the real layers as they land.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional


#: Auth-refresh margin: 5 minutes. Mirrors
#: :data:`RUNTIME_AUTH_REFRESH_MARGIN_MS`` (``helpers.ts:39``).
RUNTIME_AUTH_REFRESH_MARGIN_MS: int = 5 * 60 * 1000

#: Auth-refresh retry: 60 seconds. Mirrors
#: :data:`RUNTIME_AUTH_REFRESH_RETRY_MS`` (``helpers.ts:40``).
RUNTIME_AUTH_REFRESH_RETRY_MS: int = 60 * 1000

#: Auth-refresh min delay: 5 seconds. Mirrors
#: :data:`RUNTIME_AUTH_REFRESH_MIN_DELAY_MS`` (``helpers.ts:41``).
RUNTIME_AUTH_REFRESH_MIN_DELAY_MS: int = 5 * 1000

#: Max same-model rate-limit retries: 3. Mirrors
#: :data:`MAX_SAME_MODEL_RATE_LIMIT_RETRIES`` (``helpers.ts:50``).
MAX_SAME_MODEL_RATE_LIMIT_RETRIES: int = 3

#: Same-model rate-limit backoff step: 10 seconds.
#: Mirrors :data:`SAME_MODEL_RATE_LIMIT_BACKOFF_STEP_MS``.
SAME_MODEL_RATE_LIMIT_BACKOFF_STEP_MS: int = 10_000

#: Same-model rate-limit max backoff: 60 seconds.
#: Mirrors :data:`SAME_MODEL_RATE_LIMIT_MAX_BACKOFF_MS``.
SAME_MODEL_RATE_LIMIT_MAX_BACKOFF_MS: int = 60_000

#: Default overload failover backoff: 0 ms.
#: Mirrors :data:`DEFAULT_OVERLOAD_FAILOVER_BACKOFF_MS``.
DEFAULT_OVERLOAD_FAILOVER_BACKOFF_MS: int = 0

#: Default max overload profile rotations: 1.
#: Mirrors :data:`DEFAULT_MAX_OVERLOAD_PROFILE_ROTATIONS``.
DEFAULT_MAX_OVERLOAD_PROFILE_ROTATIONS: int = 1

#: Default max rate-limit profile rotations: 1.
#: Mirrors :data:`DEFAULT_MAX_RATE_LIMIT_PROFILE_ROTATIONS``.
DEFAULT_MAX_RATE_LIMIT_PROFILE_ROTATIONS: int = 1

#: Anthropic magic-string trigger. Mirrors
#: :data:`ANTHROPIC_MAGIC_STRING_TRIGGER_REFUSAL``.
ANTHROPIC_MAGIC_STRING_TRIGGER_REFUSAL: str = "ANTHROPIC_MAGIC_STRING_TRIGGER_REFUSAL"

#: Anthropic magic-string replacement. Mirrors
#: :data:`ANTHROPIC_MAGIC_STRING_REPLACEMENT``.
ANTHROPIC_MAGIC_STRING_REPLACEMENT: str = (
    "ANTHROPIC MAGIC STRING TRIGGER REFUSAL (redacted)"
)


#: Runtime auth state shape. Mirrors
#: :class:`RuntimeAuthState`` (``helpers.ts:29-37``).
RuntimeAuthState = Dict[str, Any]


def resolve_overload_failover_backoff_ms(
    cfg: Optional[Dict[str, Any]] = None,
) -> int:
    """Return the configured overloaded backoff in ms.

    Mirrors :func:`resolveOverloadFailoverBackoffMs``
    (``helpers.ts:56-58``).
    """
    if not cfg:
        return DEFAULT_OVERLOAD_FAILOVER_BACKOFF_MS
    cooldowns = (
        (cfg.get("auth") or {}).get("cooldowns") or {}
    )
    return cooldowns.get("overloadedBackoffMs", DEFAULT_OVERLOAD_FAILOVER_BACKOFF_MS)


def resolve_overload_profile_rotation_limit(
    cfg: Optional[Dict[str, Any]] = None,
) -> int:
    """Return the configured overloaded profile rotation limit.

    Mirrors :func:`resolveOverloadProfileRotationLimit``
    (``helpers.ts:60-62``).
    """
    if not cfg:
        return DEFAULT_MAX_OVERLOAD_PROFILE_ROTATIONS
    cooldowns = (
        (cfg.get("auth") or {}).get("cooldowns") or {}
    )
    return cooldowns.get(
        "overloadedProfileRotations",
        DEFAULT_MAX_OVERLOAD_PROFILE_ROTATIONS,
    )


def resolve_rate_limit_profile_rotation_limit(
    cfg: Optional[Dict[str, Any]] = None,
) -> int:
    """Return the configured rate-limited profile rotation limit.

    Mirrors :func:`resolveRateLimitProfileRotationLimit``
    (``helpers.ts:64-68``).
    """
    if not cfg:
        return DEFAULT_MAX_RATE_LIMIT_PROFILE_ROTATIONS
    cooldowns = (
        (cfg.get("auth") or {}).get("cooldowns") or {}
    )
    return cooldowns.get(
        "rateLimitedProfileRotations",
        DEFAULT_MAX_RATE_LIMIT_PROFILE_ROTATIONS,
    )


def resolve_same_model_rate_limit_retry_delay_ms(
    *,
    retries_so_far: int,
    retry_after_seconds: Optional[float] = None,
) -> int:
    """Compute the next same-model rate-limit retry delay in ms.

    Mirrors :func:`resolveSameModelRateLimitRetryDelayMs``
    (``helpers.ts:75-86``).
    """
    backoff_delay_ms = SAME_MODEL_RATE_LIMIT_BACKOFF_STEP_MS * (
        max(0, retries_so_far) + 1
    )
    backoff_ms = min(SAME_MODEL_RATE_LIMIT_MAX_BACKOFF_MS, backoff_delay_ms)
    if retry_after_seconds is None or not (
        isinstance(retry_after_seconds, (int, float))
        and retry_after_seconds == retry_after_seconds
    ):
        retry_after_ms = 0
    else:
        retry_after_ms = int(max(0, retry_after_seconds) * 1000)
    return max(
        backoff_ms,
        min(SAME_MODEL_RATE_LIMIT_MAX_BACKOFF_MS, retry_after_ms),
    )


def resolve_next_same_model_rate_limit_retry_count(
    *,
    retries_so_far: int,
    retried_same_model_rate_limit: bool,
) -> int:
    """Compute the next same-model rate-limit retry count.

    Mirrors :func:`resolveNextSameModelRateLimitRetryCount``
    (``helpers.ts:88-93``).
    """
    if not retried_same_model_rate_limit:
        return 0
    return max(0, retries_so_far) + 1


def scrub_anthropic_refusal_magic(prompt: str) -> str:
    """Replace the Anthropic refusal-magic trigger string in ``prompt``.

    Mirrors :func:`scrubAnthropicRefusalMagic``
    (``helpers.ts:99-...``).
    """
    if not isinstance(prompt, str):
        return prompt
    if ANTHROPIC_MAGIC_STRING_TRIGGER_REFUSAL not in prompt:
        return prompt
    return prompt.replace(
        ANTHROPIC_MAGIC_STRING_TRIGGER_REFUSAL,
        ANTHROPIC_MAGIC_STRING_REPLACEMENT,
    )


__all__ = [
    "ANTHROPIC_MAGIC_STRING_REPLACEMENT",
    "ANTHROPIC_MAGIC_STRING_TRIGGER_REFUSAL",
    "DEFAULT_MAX_OVERLOAD_PROFILE_ROTATIONS",
    "DEFAULT_MAX_RATE_LIMIT_PROFILE_ROTATIONS",
    "DEFAULT_OVERLOAD_FAILOVER_BACKOFF_MS",
    "MAX_SAME_MODEL_RATE_LIMIT_RETRIES",
    "RUNTIME_AUTH_REFRESH_MARGIN_MS",
    "RUNTIME_AUTH_REFRESH_MIN_DELAY_MS",
    "RUNTIME_AUTH_REFRESH_RETRY_MS",
    "RuntimeAuthState",
    "SAME_MODEL_RATE_LIMIT_BACKOFF_STEP_MS",
    "SAME_MODEL_RATE_LIMIT_MAX_BACKOFF_MS",
    "resolve_next_same_model_rate_limit_retry_count",
    "resolve_overload_failover_backoff_ms",
    "resolve_overload_profile_rotation_limit",
    "resolve_rate_limit_profile_rotation_limit",
    "resolve_same_model_rate_limit_retry_delay_ms",
    "scrub_anthropic_refusal_magic",
]
