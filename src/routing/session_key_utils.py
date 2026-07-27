"""jarvis.routing.session_key_utils — session-key normalization + classification.

OpenClaw parity: mirrors ``src/sessions/session-key-utils.ts`` exactly:
case-preserving peer registry (Signal segment spans #82853, Matrix tail
spans #75670), bounded normalization cache, agent-key parsing, cron /
subagent / acp classification, thread suffix parsing, delivery-route
parsing, raw conversation refs.

(Placed under routing/ for Phase 5.13; src/sessions/ gains the full
session core in Phase 5.14 and may re-export from here.)
"""

from __future__ import annotations

import re
from typing import Any

from jarvis_normalization_core.string_coerce import (
    normalize_lowercase_string_or_empty,
    normalize_optional_lowercase_string,
    normalize_optional_string,
)

# ---------------------------------------------------------------------------
# Case-preserving peer registry
# ---------------------------------------------------------------------------
# span "segment" — preserve a single colon-free id segment, matched anywhere
#                  (incl. unscoped keys without an `agent:<id>:` head).
# span "tail"    — preserve the entire opaque tail after the agent-scoped
#                  `agent:<id>:<channel>:<peerKind>:` head.

_CASE_PRESERVING_PEERS: tuple[dict[str, Any], ...] = (
    # #82853 — Signal group IDs (opaque). Encoded to match prior behavior exactly.
    {"channel": "signal", "peerKinds": frozenset({"group"}), "span": "segment", "unscoped": True},
    # #75670 — Matrix room IDs (opaque, embedded `:server`) plus thread event suffix.
    {
        "channel": "matrix",
        "peerKinds": frozenset({"channel", "group"}),
        "span": "tail",
        "unscoped": True,
    },
)


def _find_case_preserving_peer_descriptor(
    channel: object, peer_kind: object
) -> dict[str, Any] | None:
    c = normalize_lowercase_string_or_empty(channel)
    k = normalize_lowercase_string_or_empty(peer_kind)
    for descriptor in _CASE_PRESERVING_PEERS:
        if descriptor["channel"] == c and k in descriptor["peerKinds"]:
            return descriptor
    return None


def _is_case_preserving_peer(channel: object, peer_kind: object) -> bool:
    return _find_case_preserving_peer_descriptor(channel, peer_kind) is not None


def requires_folded_session_key_alias_proof(session_key: object) -> bool:
    """True when the key's peer tail is case-preserved (folded alias needs proof)."""
    raw = normalize_optional_string(session_key)
    if not raw:
        return False
    parts = raw.split(":")
    body_start = 0
    has_agent_wrapper = False
    while (
        len(parts) - body_start >= 3
        and normalize_optional_lowercase_string(parts[body_start]) == "agent"
    ):
        has_agent_wrapper = True
        body_start += 2
    if has_agent_wrapper:
        while body_start < len(parts) and not normalize_optional_string(parts[body_start]):
            body_start += 1
    channel = parts[body_start] if body_start < len(parts) else None
    peer_kind = parts[body_start + 1] if body_start + 1 < len(parts) else None
    descriptor = _find_case_preserving_peer_descriptor(channel, peer_kind)
    return descriptor is not None and descriptor["span"] == "tail"


def normalize_session_peer_id(params: dict[str, Any]) -> str:
    """Trim a peer id; lowercase unless (channel, peerKind) is case-preserving.

    Mirrors ``normalizeSessionPeerId`` (params: channel, peerKind, peerId).
    """
    peer_id = (params.get("peerId") or "").strip()
    if not peer_id:
        return ""
    if _is_case_preserving_peer(params.get("channel"), params.get("peerKind")):
        return peer_id
    return normalize_lowercase_string_or_empty(peer_id)


# ---------------------------------------------------------------------------
# Session-key normalization with preserved spans
# ---------------------------------------------------------------------------

_NORMALIZED_SESSION_KEY_CACHE_MAX_ENTRIES = 2048
_NORMALIZED_SESSION_KEY_CACHE_MAX_LENGTH = 4096
_normalized_session_key_cache: dict[str, str] = {}


def _read_normalized_session_key_cache(raw: str) -> str | None:
    if len(raw) <= _NORMALIZED_SESSION_KEY_CACHE_MAX_LENGTH:
        return _normalized_session_key_cache.get(raw)
    return None


def _write_normalized_session_key_cache(raw: str, normalized: str) -> None:
    if len(raw) > _NORMALIZED_SESSION_KEY_CACHE_MAX_LENGTH:
        return
    _normalized_session_key_cache[raw] = normalized
    while len(_normalized_session_key_cache) > _NORMALIZED_SESSION_KEY_CACHE_MAX_ENTRIES:
        oldest = next(iter(_normalized_session_key_cache), None)
        if oldest is None:
            return
        del _normalized_session_key_cache[oldest]


def _may_contain_case_preserving_peer(raw: str) -> bool:
    folded = raw.lower()
    return any(f"{descriptor['channel']}:" in folded for descriptor in _CASE_PRESERVING_PEERS)


def _collect_case_preserved_spans(raw: str) -> list[tuple[int, int, bool]]:
    """Collect (start, end, trim) ranges whose case must be preserved.

    Spans may come from multiple descriptors; the caller lowercases
    everything OUTSIDE their union — collect-then-emit, never sequential
    transforms that could re-lowercase an already-preserved span.
    """
    spans: list[tuple[int, int, bool]] = []
    for descriptor in _CASE_PRESERVING_PEERS:
        channel = re.escape(descriptor["channel"])
        for peer_kind in sorted(descriptor["peerKinds"]):
            kind = re.escape(peer_kind)
            if descriptor["span"] == "segment":
                # Unscoped: `<channel>:<peerKind>:<segment>` at start or after any colon.
                pattern = re.compile(rf"(^|:){channel}:{kind}:([^:]+)", re.IGNORECASE)
                for match in pattern.finditer(raw):
                    matched = match.group(0) or ""
                    segment = match.group(2) or ""
                    seg_start = match.start() + len(matched) - len(segment)
                    # Segment spans match the legacy `peerId.trim()` behavior exactly.
                    spans.append((seg_start, seg_start + len(segment), True))
            else:

                def collect_tail_span(tail_start: int) -> None:
                    if tail_start >= len(raw):
                        return
                    # Preserve Matrix room/event IDs, but keep structural thread
                    # marker casing canonical so `:Thread:` cannot fork a session key.
                    tail = raw[tail_start:]
                    thread_marker = ":thread:"
                    marker_index = normalize_lowercase_string_or_empty(tail).rfind(thread_marker)
                    if marker_index == -1:
                        spans.append((tail_start, len(raw), False))
                        return
                    spans.append((tail_start, tail_start + marker_index, False))
                    thread_id_start = tail_start + marker_index + len(thread_marker)
                    if thread_id_start < len(raw):
                        spans.append((thread_id_start, len(raw), False))

                # Preserve tails behind nested or malformed ownership wrappers without
                # treating an inner channel-shaped identity as a runtime route.
                scoped_re = re.compile(rf"^(?:agent:[^:]*:)+:*{channel}:{kind}:", re.IGNORECASE)
                scoped_match = scoped_re.match(raw)
                if scoped_match:
                    collect_tail_span(scoped_match.end())
                    continue
                if descriptor["unscoped"]:
                    unscoped_re = re.compile(rf"^{channel}:{kind}:", re.IGNORECASE)
                    unscoped_match = unscoped_re.match(raw)
                    if unscoped_match:
                        collect_tail_span(unscoped_match.end())
    return spans


def normalize_session_key_preserving_opaque_peer_ids(session_key: object) -> str:
    """Lowercase a session key, preserving registered opaque peer-id spans."""
    raw = normalize_optional_string(session_key)
    if not raw:
        return ""
    cached = _read_normalized_session_key_cache(raw)
    if cached is not None:
        return cached
    if not _may_contain_case_preserving_peer(raw):
        normalized = raw.lower()
        _write_normalized_session_key_cache(raw, normalized)
        return normalized
    spans = sorted(
        (span for span in _collect_case_preserved_spans(raw) if span[1] > span[0]),
        key=lambda span: span[0],
    )
    normalized = ""
    cursor = 0
    for start, end, trim in spans:
        if start < cursor:
            # Overlapping/contained in an already-emitted preserved range; skip.
            continue
        normalized += normalize_lowercase_string_or_empty(raw[cursor:start])
        preserved = raw[start:end]
        normalized += preserved.strip() if trim else preserved
        cursor = end
    normalized += normalize_lowercase_string_or_empty(raw[cursor:])
    _write_normalized_session_key_cache(raw, normalized)
    return normalized


# ---------------------------------------------------------------------------
# Agent-scoped session-key parsing + classification
# ---------------------------------------------------------------------------


def parse_agent_session_key(session_key: object) -> dict[str, str] | None:
    """Parse agent-scoped session keys canonically (case-insensitive).

    Mirrors ``parseAgentSessionKey``: requires ``agent:<id>:<rest>`` with
    ≥3 parts; ``rest`` may itself contain empty colon segments. Returns
    ``{"agentId", "rest"}`` or ``None``.
    """
    raw = normalize_session_key_preserving_opaque_peer_ids(session_key)
    if not raw:
        return None
    parts = raw.split(":")
    if len(parts) < 3 or not parts[1] or not parts[2]:
        return None
    if parts[0] != "agent":
        return None
    agent_id = normalize_optional_string(parts[1])
    rest = ":".join(parts[2:])
    if not agent_id or not rest:
        return None
    return {"agentId": agent_id, "rest": rest}


_CRON_RUN_RE = re.compile(r"^cron:[^:]+:run:[^:]+(?::|$)")
_CRON_RUN_EXACT_RE = re.compile(r"^cron:[^:]+:run:[^:]+$")


def is_cron_run_session_key(session_key: object) -> bool:
    parsed = parse_agent_session_key(session_key)
    if not parsed:
        return False
    return _CRON_RUN_RE.search(parsed["rest"]) is not None


def parse_cron_run_scope_suffix(session_key: object) -> dict[str, str | None]:
    """Split the terminal per-run ``:run:<id>`` scope off an isolated cron key.

    Gated to the exact ``agent:<id>:cron:<job>:run:<runId>`` shape; any
    other key is returned unchanged with ``runId`` ``None``.
    """
    raw = normalize_optional_string(session_key)
    if not raw:
        return {"baseSessionKey": None, "runId": None}
    parsed = parse_agent_session_key(raw)
    if not parsed or _CRON_RUN_EXACT_RE.match(parsed["rest"]) is None:
        return {"baseSessionKey": raw, "runId": None}
    run_marker = ":run:"
    marker_index = raw.lower().rfind(run_marker)
    return {
        "baseSessionKey": raw[:marker_index],
        "runId": raw[marker_index + len(run_marker) :],
    }


def is_cron_session_key(session_key: object) -> bool:
    parsed = parse_agent_session_key(session_key)
    if not parsed:
        return False
    rest = normalize_optional_lowercase_string(parsed["rest"])
    return rest is not None and rest.startswith("cron:")


def is_subagent_session_key(session_key: object) -> bool:
    raw = normalize_optional_string(session_key)
    if not raw:
        return False
    lowered = normalize_optional_lowercase_string(raw)
    if lowered is not None and lowered.startswith("subagent:"):
        return True
    parsed = parse_agent_session_key(raw)
    rest = normalize_optional_lowercase_string(parsed["rest"]) if parsed else None
    return rest is not None and rest.startswith("subagent:")


def get_subagent_depth(session_key: object) -> int:
    raw = normalize_optional_lowercase_string(session_key)
    if not raw:
        return 0
    parsed = parse_agent_session_key(raw)
    scoped = parsed["rest"] if parsed else raw
    normalized = scoped.lower()
    return len(re.findall(r"(?:^|:)subagent:", normalized))


def is_acp_session_key(session_key: object) -> bool:
    raw = normalize_optional_string(session_key)
    if not raw:
        return False
    normalized = normalize_lowercase_string_or_empty(raw)
    if normalized.startswith("acp:"):
        return True
    parsed = parse_agent_session_key(raw)
    rest = normalize_optional_lowercase_string(parsed["rest"]) if parsed else None
    return rest is not None and rest.startswith("acp:")


def parse_thread_session_suffix(session_key: object) -> dict[str, str | None]:
    """Strip a trailing ``:thread:<id>`` suffix (marker matched case-insensitively).

    Mirrors ``parseThreadSessionSuffix``:
    ``{"baseSessionKey": str | None, "threadId": str | None}``.
    """
    raw = normalize_optional_string(session_key)
    if not raw:
        return {"baseSessionKey": None, "threadId": None}
    lower_raw = normalize_lowercase_string_or_empty(raw)
    thread_marker = ":thread:"
    marker_index = lower_raw.rfind(thread_marker)
    base_session_key = raw if marker_index == -1 else raw[:marker_index]
    thread_id_raw = None if marker_index == -1 else raw[marker_index + len(thread_marker) :]
    thread_id = normalize_optional_string(thread_id_raw)
    return {"baseSessionKey": base_session_key, "threadId": thread_id}


_SESSION_DELIVERY_PEER_KINDS = frozenset({"channel", "direct", "dm", "group"})


def parse_session_delivery_route(session_key: object) -> dict[str, str | None] | None:
    """Parse only complete external delivery shapes; nested ownership stays opaque.

    Mirrors ``parseSessionDeliveryRoute``. Returns a dict with
    ``channel``, ``peerId``, ``peerKind``, optional ``accountId`` and
    ``threadId``, or ``None``.
    """
    parsed_thread = parse_thread_session_suffix(session_key)
    base = parsed_thread["baseSessionKey"]
    parsed = parse_agent_session_key(base if base is not None else session_key)
    if not parsed:
        return None
    parts = parsed["rest"].split(":")
    if parts[0] == "agent" or len(parts) < 3:
        return None
    channel = normalize_optional_lowercase_string(parts[0])
    if not channel:
        return None

    if len(parts) >= 4 and parts[2] in ("direct", "dm"):
        account_id = normalize_optional_string(parts[1])
        first_peer_id_segment = normalize_optional_string(parts[3])
        peer_id = normalize_optional_string(":".join(parts[3:]))
        if not account_id or not first_peer_id_segment or not peer_id:
            return None
        return {
            "accountId": account_id,
            "channel": channel,
            "peerId": peer_id,
            "peerKind": parts[2],
            "threadId": parsed_thread["threadId"],
        }

    peer_kind = parts[1] if len(parts) > 1 else None
    first_peer_id_segment = normalize_optional_string(parts[2])
    peer_id = normalize_optional_string(":".join(parts[2:]))
    if (
        not peer_kind
        or peer_kind not in _SESSION_DELIVERY_PEER_KINDS
        or not first_peer_id_segment
        or not peer_id
    ):
        return None
    return {
        "channel": channel,
        "peerId": peer_id,
        "peerKind": peer_kind,
        "threadId": parsed_thread["threadId"],
    }


def parse_raw_session_conversation_ref(session_key: object) -> dict[str, str] | None:
    """Parse a raw group/channel conversation reference from a session key.

    Mirrors ``parseRawSessionConversationRef``. Returns
    ``{"channel", "kind", "rawId", "prefix"}`` or ``None``.
    """
    raw = normalize_optional_string(session_key)
    if not raw:
        return None
    raw_parts = raw.split(":")
    # Only the outer ownership wrapper is authoritative for routing. Any inner
    # agent-shaped identity is opaque plugin input and must not inherit policy.
    has_agent_wrapper = normalize_optional_lowercase_string(raw_parts[0]) == "agent"
    if has_agent_wrapper and (
        not normalize_optional_string(raw_parts[1] if len(raw_parts) > 1 else None)
        or len(raw_parts) < 3
    ):
        return None
    body_start_index = 2 if has_agent_wrapper else 0
    parts = raw_parts[body_start_index:]
    if normalize_optional_lowercase_string(parts[0] if parts else None) == "agent":
        return None
    # Empty opaque tail segments are valid (for example compressed IPv6), but
    # structural owner/channel/kind/first-id segments must be present.
    if len(parts) < 3 or not normalize_optional_string(parts[2]):
        return None

    channel = normalize_optional_lowercase_string(parts[0])
    kind = normalize_optional_lowercase_string(parts[1])
    if not channel or kind not in ("group", "channel"):
        return None

    raw_id = normalize_optional_string(":".join(parts[2:]))
    prefix = normalize_optional_string(":".join(raw_parts[: body_start_index + 2]))
    if not raw_id or not prefix:
        return None
    return {"channel": channel, "kind": kind, "rawId": raw_id, "prefix": prefix}


__all__ = [
    "get_subagent_depth",
    "is_acp_session_key",
    "is_cron_run_session_key",
    "is_cron_session_key",
    "is_subagent_session_key",
    "normalize_session_key_preserving_opaque_peer_ids",
    "normalize_session_peer_id",
    "parse_agent_session_key",
    "parse_cron_run_scope_suffix",
    "parse_raw_session_conversation_ref",
    "parse_session_delivery_route",
    "parse_thread_session_suffix",
    "requires_folded_session_key_alias_proof",
]
