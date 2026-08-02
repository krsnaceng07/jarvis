"""jarvis.agents.embedded_agent_runner.compact_reasons — compaction reason classification.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/compact-reasons.ts``.

Public surface (mirrors the OpenClaw
source):

- :data:`DEFERRED_CONTEXT_ENGINE_COMPACTION_REASON` —
  the canonical "deferred to
  background context-engine
  maintenance" reason.
- :func:`resolve_compaction_failure_reason` —
  prefer a safeguard cancel reason
  when the runtime only reports
  generic cancellation.
- :func:`classify_compaction_reason` —
  bucket a raw compaction reason
  into stable telemetry/status
  classes.
- :func:`format_unknown_compaction_reason_detail` —
  sanitize an unknown reason into
  a short log/metric-safe detail
  suffix.

Phase 7.2a — focused minimal port.
"""
from __future__ import annotations

import re
from typing import Optional


#: Canonical "deferred to background
#: context-engine maintenance" reason.
#: Mirrors
#: :data:`DEFERRED_CONTEXT_ENGINE_COMPACTION_REASON`
#: (``compact-reasons.ts:9-10``).
DEFERRED_CONTEXT_ENGINE_COMPACTION_REASON: str = (
    "deferred to background context-engine maintenance"
)


#: The max detail-char count for
#: reason sanitization. Mirrors
#: :data:`MAX_COMPACTION_REASON_DETAIL_CHARS`
#: (``compact-reasons.ts:7``).
MAX_COMPACTION_REASON_DETAIL_CHARS: int = 100


def _normalize_lowercase_string_or_empty(
    value: Optional[str],
) -> str:
    """Coerce ``value`` to a lowercased
    string, or ``""`` if it isn't a
    non-empty string. Mirrors
    :func:`normalizeLowercaseStringOrEmpty`
    from
    ``@openclaw/normalization-core/string-coerce``."""
    if not isinstance(value, str):
        return ""
    return value.lower().strip()


def _is_generic_compaction_cancelled_reason(reason: str) -> bool:
    """Check if ``reason`` is the
    generic "compaction cancelled"
    message. Mirrors
    :func:`isGenericCompactionCancelledReason`
    (``compact-reasons.ts:12-15``)."""
    normalized = _normalize_lowercase_string_or_empty(reason)
    return (
        normalized == "compaction cancelled"
        or normalized == "error: compaction cancelled"
    )


def resolve_compaction_failure_reason(
    reason: str,
    safeguard_cancel_reason: Optional[str] = None,
) -> str:
    """Prefer a safeguard cancel
    reason when the runtime only
    reports generic cancellation.
    Mirrors
    :func:`resolveCompactionFailureReason`
    (``compact-reasons.ts:18-26``)."""
    if (
        _is_generic_compaction_cancelled_reason(reason)
        and safeguard_cancel_reason
    ):
        return safeguard_cancel_reason
    return reason


def classify_compaction_reason(reason: Optional[str] = None) -> str:
    """Bucket a raw compaction reason
    into stable telemetry/status
    classes. Mirrors
    :func:`classifyCompactionReason`
    (``compact-reasons.ts:29-77``).

    Returns one of:
    - ``"unknown"``
    - ``"no_compactable_entries"``
    - ``"below_threshold"``
    - ``"already_compacted_recently"``
    - ``"deferred_background"``
    - ``"live_context_still_exceeds_target"``
    - ``"guard_blocked"``
    - ``"summary_failed"``
    - ``"timeout"``
    - ``"provider_error_4xx"``
    - ``"provider_error_5xx"``
    """
    text = _normalize_lowercase_string_or_empty(reason)
    if not text:
        return "unknown"
    if "nothing to compact" in text or "no real conversation messages" in text:
        return "no_compactable_entries"
    if "below threshold" in text or "already under target" in text:
        return "below_threshold"
    if "already compacted" in text or "already_compacted" in text:
        return "already_compacted_recently"
    if "deferred to background" in text:
        return "deferred_background"
    if "still exceeds target" in text:
        return "live_context_still_exceeds_target"
    if "guard" in text:
        return "guard_blocked"
    if "summary" in text:
        return "summary_failed"
    if "timed out" in text or "timeout" in text:
        return "timeout"
    if any(code in text for code in ("400", "401", "403", "429")):
        return "provider_error_4xx"
    if any(code in text for code in ("500", "502", "503", "504")):
        return "provider_error_5xx"
    return "unknown"


def format_unknown_compaction_reason_detail(
    reason: Optional[str] = None,
) -> Optional[str]:
    """Sanitize an unknown reason
    into a short log/metric-safe
    detail suffix. Mirrors
    :func:`formatUnknownCompactionReasonDetail`
    (``compact-reasons.ts:80-90``)."""
    if not reason:
        return None
    sanitized = re.sub(
        r"[^A-Za-z0-9._:@/+~-]+", "_", reason.replace("\n", " ")
    )
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")
    if not sanitized:
        return None
    return sanitized[:MAX_COMPACTION_REASON_DETAIL_CHARS]


__all__ = [
    "DEFERRED_CONTEXT_ENGINE_COMPACTION_REASON",
    "classify_compaction_reason",
    "format_unknown_compaction_reason_detail",
    "resolve_compaction_failure_reason",
]
