"""Session key parsing + canonicalization utilities.

Mirrors OpenClaw's ``extensions/sessions/session-key-utils.ts``:
the foundational helpers for normalizing, parsing, and
classifying persisted session keys. Many other session
modules (``session-chat-type``, ``session-id-resolution``,
``send-policy``) build on these.

The Python port preserves the OpenClaw public contract:
- Same exported function names (snake_case)
- Same return shapes (TypedDict / dataclass)
- Same tri-state sentinel conventions
- Same LRU cache (insertion-ordered via ``dict``)

Key Python adaptations (documented in code):
- TS ``undefined`` → Python ``None``
- TS ``Set`` (insertion-ordered) → Python ``dict[k, None]``
- TS ``Map`` (insertion-ordered) → Python ``dict``
- TS regex with ``/u`` flag → Python ``re.IGNORECASE`` where appropriate
- TS ``toSorted`` (immutable sort) → Python ``sorted()`` (already immutable)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal, Optional

# ── Case-preserving peer registry ─────────────────────────────────


@dataclass(frozen=True, slots=True)
class CasePreservingPeerDescriptor:
    """Per-channel case-preservation policy.

    Mirrors the TS ``CasePreservingPeerDescriptor`` type. Channels
    enroll here individually; un-enrolled channels keep the
    default lowercase behavior.

    ``span``:
    - ``"segment"`` — preserve a single colon-free id segment,
      matched anywhere (incl. unscoped keys without an
      ``agent:<id>:`` head).
    - ``"tail"`` — preserve the entire opaque tail after the
      agent-scoped head (opaque id with embedded colons plus
      any ``:thread:<event>`` suffix).

    ``unscoped`` — preserve even without the ``agent:<id>:``
      structural head (legacy Signal).
    """

    channel: str
    peer_kinds: frozenset[str]
    span: Literal["segment", "tail"]
    unscoped: bool


# Case-preserving peers registry. Mirrors the TS
# ``CASE_PRESERVING_PEERS`` constant exactly. Adding a
# new channel: add a new entry here.
_CASE_PRESERVING_PEERS: tuple[CasePreservingPeerDescriptor, ...] = (
    # Signal group IDs (opaque; legacy behavior preserved)
    CasePreservingPeerDescriptor(
        channel="signal",
        peer_kinds=frozenset({"group"}),
        span="segment",
        unscoped=True,
    ),
    # Matrix room IDs (opaque, embedded ``:server``) plus
    # thread event suffix
    CasePreservingPeerDescriptor(
        channel="matrix",
        peer_kinds=frozenset({"channel", "group"}),
        span="tail",
        unscoped=True,
    ),
)


def _normalize_lowercase_string_or_empty(value: object) -> str:
    """Return the lowercase-trimmed value, or ``""`` for empty/non-string.

    Mirrors OpenClaw's ``normalizeLowercaseStringOrEmpty`` from
    ``@openclaw/normalization-core/string-coerce``.
    """
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


def _normalize_optional_string(value: object) -> Optional[str]:
    """Return the trimmed value, or ``None`` for empty/non-string.

    Mirrors ``normalizeOptionalString``.
    """
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed or None


def _normalize_optional_lowercase_string(value: object) -> Optional[str]:
    """Return the lowercase-trimmed value, or ``None`` for empty/non-string.

    Mirrors ``normalizeOptionalLowercaseString``.
    """
    s = _normalize_optional_string(value)
    return s.lower() if s is not None else None


def _find_case_preserving_peer_descriptor(
    channel: object,
    peer_kind: object,
) -> Optional[CasePreservingPeerDescriptor]:
    """Find a descriptor matching the (channel, peer_kind) pair.

    Returns ``None`` when neither field is recognized.
    """
    c = _normalize_lowercase_string_or_empty(channel)
    k = _normalize_lowercase_string_or_empty(peer_kind)
    if not c or not k:
        return None
    for descriptor in _CASE_PRESERVING_PEERS:
        if descriptor.channel == c and k in descriptor.peer_kinds:
            return descriptor
    return None


def is_case_preserving_peer(channel: object, peer_kind: object) -> bool:
    """True when (channel, peer_kind) owns a case-sensitive opaque peer ID."""
    return _find_case_preserving_peer_descriptor(channel, peer_kind) is not None


# ── Public surface ────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ParsedAgentSessionKey:
    """Result of ``parse_agent_session_key``.

    Mirrors the TS ``ParsedAgentSessionKey`` type. Supports both
    attribute and dict-key access.
    """

    agent_id: str
    rest: str

    def __getitem__(self, key: str) -> str:
        if key in ("agent_id", "agentId"):
            return self.agent_id
        if key == "rest":
            return self.rest
        raise KeyError(key)

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        if key in ("agent_id", "agentId"):
            return self.agent_id
        if key == "rest":
            return self.rest
        return default


@dataclass(frozen=True, slots=True)
class ParsedThreadSessionSuffix:
    """Result of ``parse_thread_session_suffix``."""

    base_session_key: Optional[str]
    thread_id: Optional[str]

    def __getitem__(self, key: str) -> Optional[str]:
        if key in ("base_session_key", "baseSessionKey"):
            return self.base_session_key
        if key in ("thread_id", "threadId"):
            return self.thread_id
        raise KeyError(key)

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        if key in ("base_session_key", "baseSessionKey"):
            return self.base_session_key
        if key in ("thread_id", "threadId"):
            return self.thread_id
        return default


@dataclass(frozen=True, slots=True)
class ParsedSessionDeliveryRoute:
    """Result of ``parse_session_delivery_route``."""

    account_id: Optional[str]
    channel: str
    peer_id: str
    peer_kind: Literal["channel", "direct", "dm", "group"]
    thread_id: Optional[str] = None

    def __getitem__(self, key: str) -> Any:
        if key in ("account_id", "accountId"):
            return self.account_id
        if key == "channel":
            return self.channel
        if key in ("peer_id", "peerId"):
            return self.peer_id
        if key in ("peer_kind", "peerKind"):
            return self.peer_kind
        if key in ("thread_id", "threadId"):
            return self.thread_id
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default


@dataclass(frozen=True, slots=True)
class ParsedCronRunScopeSuffix:
    """Result of ``parse_cron_run_scope_suffix``."""

    base_session_key: Optional[str]
    run_id: Optional[str]

    def __getitem__(self, key: str) -> Optional[str]:
        if key in ("base_session_key", "baseSessionKey"):
            return self.base_session_key
        if key in ("run_id", "runId"):
            return self.run_id
        raise KeyError(key)

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        if key in ("base_session_key", "baseSessionKey"):
            return self.base_session_key
        if key in ("run_id", "runId"):
            return self.run_id
        return default


@dataclass(frozen=True, slots=True)
class RawSessionConversationRef:
    """Result of ``parse_raw_session_conversation_ref``."""

    channel: str
    kind: Literal["group", "channel"]
    raw_id: str
    prefix: str

    def __getitem__(self, key: str) -> Any:
        if key == "channel":
            return self.channel
        if key == "kind":
            return self.kind
        if key in ("raw_id", "rawId"):
            return self.raw_id
        if key == "prefix":
            return self.prefix
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default


# ── Top-level utilities ────────────────────────────────────────────


def to_agent_request_session_key(store_key: object) -> Optional[str]:
    """Convert a storage session key to an agent request session key.

    Mirrors OpenClaw's ``toAgentRequestSessionKey``: strips the
    ``agent:<id>:`` prefix, returning the scoped rest or the key itself.
    """
    raw = (store_key if isinstance(store_key, str) else "").strip()
    if not raw:
        return None
    parsed = parse_agent_session_key(raw)
    return parsed.rest if parsed is not None else raw


def requires_folded_session_key_alias_proof(
    session_key: object,
) -> bool:
    """Return True when the (channel, peer_kind) pair has a ``"tail"`` span.

    Mirrors ``requiresFoldedSessionKeyAliasProof`` — used to
    detect Matrix-style opaque tails that need special
    alias-proof handling.
    """
    raw = _normalize_optional_string(session_key)
    if not raw:
        return False
    parts = raw.split(":")
    body_start_index = 0
    has_agent_wrapper = False
    while (
        len(parts) - body_start_index >= 3
        and _normalize_optional_lowercase_string(parts[body_start_index]) == "agent"
    ):
        has_agent_wrapper = True
        body_start_index += 2
    if has_agent_wrapper:
        while body_start_index < len(parts) and not _normalize_optional_string(
            parts[body_start_index]
        ):
            body_start_index += 1
    descriptor = _find_case_preserving_peer_descriptor(
        parts[body_start_index] if body_start_index < len(parts) else None,
        parts[body_start_index + 1] if body_start_index + 1 < len(parts) else None,
    )
    return descriptor is not None and descriptor.span == "tail"


def normalize_session_peer_id(params: dict[str, Any]) -> str:
    """Normalize a peer id, preserving case for opaque channels.

    Mirrors ``normalizeSessionPeerId``. Returns ``""`` when
    ``peer_id`` is missing or blank.
    """
    peer_id = (params.get("peer_id") or params.get("peerId") or "").strip()
    if not peer_id:
        return ""
    channel = params.get("channel")
    peer_kind = params.get("peer_kind") or params.get("peerKind")
    if is_case_preserving_peer(channel, peer_kind):
        return peer_id
    return _normalize_lowercase_string_or_empty(peer_id)


# ── Cached normalization for whole session keys ───────────────────


_NORMALIZED_SESSION_KEY_CACHE_MAX_ENTRIES = 2048
_NORMALIZED_SESSION_KEY_CACHE_MAX_LENGTH = 4096
_normalized_session_key_cache: dict[str, str] = {}


def _read_normalized_session_key_cache(raw: str) -> Optional[str]:
    if len(raw) > _NORMALIZED_SESSION_KEY_CACHE_MAX_LENGTH:
        return None
    return _normalized_session_key_cache.get(raw)


def _write_normalized_session_key_cache(raw: str, normalized: str) -> None:
    if len(raw) > _NORMALIZED_SESSION_KEY_CACHE_MAX_LENGTH:
        return
    _normalized_session_key_cache[raw] = normalized
    while len(_normalized_session_key_cache) > _NORMALIZED_SESSION_KEY_CACHE_MAX_ENTRIES:
        oldest = next(iter(_normalized_session_key_cache))
        del _normalized_session_key_cache[oldest]


def _escape_regex(value: str) -> str:
    return re.sub(r"[.*+?^${}()|[\]\\]", r"\\$&", value)


def _may_contain_case_preserving_peer(raw: str) -> bool:
    folded = raw.lower()
    return any(f"{descriptor.channel}:" in folded for descriptor in _CASE_PRESERVING_PEERS)


@dataclass(frozen=True, slots=True)
class _PreservedSpan:
    start: int
    end: int
    trim: bool


def _collect_case_preserved_spans(raw: str) -> list[_PreservedSpan]:
    """Collect [start,end) index ranges whose case must be preserved."""
    spans: list[_PreservedSpan] = []
    for descriptor in _CASE_PRESERVING_PEERS:
        channel = _escape_regex(descriptor.channel)
        for peer_kind in descriptor.peer_kinds:
            kind = _escape_regex(peer_kind)
            if descriptor.span == "segment":
                pattern = re.compile(
                    rf"(?:^|:){channel}:{kind}:([^:]+)",
                    re.IGNORECASE,
                )
                for match in pattern.finditer(raw):
                    matched = match.group(0) or ""
                    segment = match.group(1) or ""
                    seg_start = (match.start() or 0) + len(matched) - len(segment)
                    spans.append(
                        _PreservedSpan(
                            start=seg_start,
                            end=seg_start + len(segment),
                            trim=True,
                        )
                    )
            else:  # span == "tail"
                thread_marker = ":thread:"

                def collect_tail_span(tail_start: int) -> None:
                    if tail_start >= len(raw):
                        return
                    tail = raw[tail_start:]
                    marker_index = tail.lower().rfind(thread_marker)
                    if marker_index == -1:
                        spans.append(_PreservedSpan(start=tail_start, end=len(raw), trim=False))
                        return
                    spans.append(
                        _PreservedSpan(
                            start=tail_start,
                            end=tail_start + marker_index,
                            trim=False,
                        )
                    )
                    thread_id_start = tail_start + marker_index + len(thread_marker)
                    if thread_id_start < len(raw):
                        spans.append(
                            _PreservedSpan(
                                start=thread_id_start,
                                end=len(raw),
                                trim=False,
                            )
                        )

                scoped_re = re.compile(
                    rf"^(?:agent:[^:]*:)+:*{channel}:{kind}:",
                    re.IGNORECASE,
                )
                scoped_match = scoped_re.match(raw)
                if scoped_match:
                    collect_tail_span(scoped_match.end())
                    continue
                if descriptor.unscoped:
                    unscoped_re = re.compile(rf"^{channel}:{kind}:", re.IGNORECASE)
                    unscoped_match = unscoped_re.match(raw)
                    if unscoped_match:
                        collect_tail_span(unscoped_match.end())
    return spans


def normalize_session_key_preserving_opaque_peer_ids(
    session_key: object,
) -> str:
    """Normalize a session key, preserving opaque peer-id case.

    Mirrors ``normalizeSessionKeyPreservingOpaquePeerIds``:
    lowercases the structural prefix while leaving opaque
    peer ids (Signal groups, Matrix rooms) untouched. Uses
    an insertion-ordered LRU cache.
    """
    raw = _normalize_optional_string(session_key)
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
        [s for s in _collect_case_preserved_spans(raw) if s.end > s.start],
        key=lambda s: s.start,
    )
    normalized = ""
    cursor = 0
    for span in spans:
        if span.start < cursor:
            # Overlapping/contained; skip
            continue
        normalized += _normalize_lowercase_string_or_empty(raw[cursor : span.start])
        preserved = raw[span.start : span.end]
        normalized += preserved.strip() if span.trim else preserved
        cursor = span.end
    normalized += _normalize_lowercase_string_or_empty(raw[cursor:])
    _write_normalized_session_key_cache(raw, normalized)
    return normalized


# ── Public parsers ────────────────────────────────────────────────


def parse_agent_session_key(session_key: object) -> Optional[ParsedAgentSessionKey]:
    """Parse an agent-scoped session key in canonical, case-insensitive form.

    Mirrors ``parseAgentSessionKey``: returns ``None`` for
    non-agent keys or malformed input.
    """
    raw = normalize_session_key_preserving_opaque_peer_ids(session_key)
    if not raw:
        return None
    parts = raw.split(":")
    if len(parts) < 3 or not parts[1] or not parts[2]:
        return None
    if parts[0] != "agent":
        return None
    agent_id = _normalize_optional_string(parts[1])
    rest = ":".join(parts[2:])
    if not agent_id or not rest:
        return None
    return ParsedAgentSessionKey(agent_id=agent_id, rest=rest)


_CRON_RUN_PATTERN = re.compile(r"^cron:[^:]+:run:[^:]+(?::|$)")


def is_cron_run_session_key(session_key: object) -> bool:
    """True when the session key is an isolated cron run.

    Mirrors ``isCronRunSessionKey``. Matches
    ``agent:<id>:cron:<job>:run:<runId>``.
    """
    parsed = parse_agent_session_key(session_key)
    if parsed is None:
        return False
    return bool(_CRON_RUN_PATTERN.match(parsed.rest))


_CRON_RUN_SUFFIX_PATTERN = re.compile(r"^cron:[^:]+:run:[^:]+$")


def parse_cron_run_scope_suffix(session_key: object) -> ParsedCronRunScopeSuffix:
    """Split the per-run ``:run:<id>`` suffix off an isolated cron key.

    Mirrors ``parseCronRunScopeSuffix``: returns the
    cache-stable base key + run id for cron run keys;
    returns the input unchanged + ``None`` run id for any
    other shape (including channel keys that embed a
    ``:run:`` segment).
    """
    raw = _normalize_optional_string(session_key)
    if not raw:
        return ParsedCronRunScopeSuffix(base_session_key=None, run_id=None)
    parsed = parse_agent_session_key(raw)
    if parsed is None or not _CRON_RUN_SUFFIX_PATTERN.match(parsed.rest):
        return ParsedCronRunScopeSuffix(base_session_key=raw, run_id=None)
    run_marker = ":run:"
    marker_index = raw.lower().rfind(run_marker)
    return ParsedCronRunScopeSuffix(
        base_session_key=raw[:marker_index],
        run_id=raw[marker_index + len(run_marker) :],
    )


def is_cron_session_key(session_key: object) -> bool:
    """True when the session key is a cron session (any run scope)."""
    parsed = parse_agent_session_key(session_key)
    if parsed is None:
        return False
    rest_lower = _normalize_optional_lowercase_string(parsed.rest) or ""
    return rest_lower.startswith("cron:")


def is_subagent_session_key(session_key: object) -> bool:
    """True when the session key is a subagent session.

    Mirrors ``isSubagentSessionKey``.
    """
    raw = _normalize_optional_string(session_key)
    if not raw:
        return False
    if (_normalize_optional_lowercase_string(raw) or "").startswith("subagent:"):
        return True
    parsed = parse_agent_session_key(raw)
    if parsed is None:
        return False
    rest_lower = _normalize_optional_lowercase_string(parsed.rest) or ""
    return rest_lower.startswith("subagent:")


_SUBAGENT_PATTERN = re.compile(r"(?:^|:)subagent:", re.IGNORECASE)


def get_subagent_depth(session_key: object) -> int:
    """Return the subagent nesting depth (0 for top-level)."""
    raw = _normalize_optional_lowercase_string(session_key)
    if not raw:
        return 0
    scoped = parse_agent_session_key(raw)
    scoped_rest = scoped.rest if scoped else raw
    normalized = scoped_rest.lower()
    matches = _SUBAGENT_PATTERN.findall(normalized)
    return len(matches)


def is_acp_session_key(session_key: object) -> bool:
    """True when the session key is an ACP (agent-client-protocol) session."""
    raw = _normalize_optional_string(session_key)
    if not raw:
        return False
    normalized = _normalize_lowercase_string_or_empty(raw)
    if normalized.startswith("acp:"):
        return True
    parsed = parse_agent_session_key(raw)
    if parsed is None:
        return False
    rest_lower = _normalize_optional_lowercase_string(parsed.rest) or ""
    return rest_lower.startswith("acp:")


def parse_thread_session_suffix(session_key: object) -> ParsedThreadSessionSuffix:
    """Split the trailing ``:thread:<id>`` suffix off a session key."""
    raw = _normalize_optional_string(session_key)
    if not raw:
        return ParsedThreadSessionSuffix(base_session_key=None, thread_id=None)
    lower_raw = raw.lower()
    thread_marker = ":thread:"
    marker_index = lower_raw.rfind(thread_marker)
    if marker_index == -1:
        return ParsedThreadSessionSuffix(base_session_key=raw, thread_id=None)
    return ParsedThreadSessionSuffix(
        base_session_key=raw[:marker_index],
        thread_id=_normalize_optional_string(raw[marker_index + len(thread_marker) :]),
    )


_SESSION_DELIVERY_PEER_KINDS = frozenset({"channel", "direct", "dm", "group"})


def parse_session_delivery_route(
    session_key: object,
) -> Optional[ParsedSessionDeliveryRoute]:
    """Parse a complete external delivery shape from a session key."""
    parsed_thread = parse_thread_session_suffix(session_key)
    parsed = parse_agent_session_key(parsed_thread.base_session_key or session_key)
    if parsed is None:
        return None
    parts = parsed.rest.split(":")
    if parts[0] == "agent" or len(parts) < 3:
        return None
    channel = _normalize_optional_lowercase_string(parts[0])
    if not channel:
        return None
    if len(parts) >= 4 and parts[2] in ("direct", "dm"):
        account_id = _normalize_optional_string(parts[1])
        first_peer_id_segment = _normalize_optional_string(parts[3])
        peer_id = _normalize_optional_string(":".join(parts[3:]))
        if not account_id or not first_peer_id_segment or not peer_id:
            return None
        return ParsedSessionDeliveryRoute(
            account_id=account_id,
            channel=channel,
            peer_id=peer_id,
            peer_kind=parts[2],  # type: ignore[arg-type]
            thread_id=parsed_thread.thread_id,
        )
    peer_kind = parts[1] if parts[1] in _SESSION_DELIVERY_PEER_KINDS else None
    first_peer_id_segment = _normalize_optional_string(parts[2])
    peer_id = _normalize_optional_string(":".join(parts[2:]))
    if not peer_kind or not first_peer_id_segment or not peer_id:
        return None
    return ParsedSessionDeliveryRoute(
        account_id=None,
        channel=channel,
        peer_id=peer_id,
        peer_kind=peer_kind,  # type: ignore[arg-type]
        thread_id=parsed_thread.thread_id,
    )


def parse_raw_session_conversation_ref(
    session_key: object,
) -> Optional[RawSessionConversationRef]:
    """Parse the outer ownership wrapper for raw session conversation refs."""
    raw = _normalize_optional_string(session_key)
    if not raw:
        return None
    raw_parts = raw.split(":")
    has_agent_wrapper = (
        _normalize_optional_lowercase_string(raw_parts[0]) == "agent" if raw_parts else False
    )
    if has_agent_wrapper and (len(raw_parts) < 3 or not _normalize_optional_string(raw_parts[1])):
        return None
    body_start_index = 2 if has_agent_wrapper else 0
    parts = raw_parts[body_start_index:]
    if parts and _normalize_optional_lowercase_string(parts[0]) == "agent":
        return None
    if len(parts) < 3 or not _normalize_optional_string(parts[2]):
        return None
    channel = _normalize_optional_lowercase_string(parts[0])
    kind = _normalize_optional_lowercase_string(parts[1])
    if not channel or kind not in ("group", "channel"):
        return None
    raw_id = _normalize_optional_string(":".join(parts[2:]))
    prefix = _normalize_optional_string(":".join(raw_parts[: body_start_index + 2]))
    if not raw_id or not prefix:
        return None
    return RawSessionConversationRef(
        channel=channel,
        kind=kind,  # type: ignore[arg-type]
        raw_id=raw_id,
        prefix=prefix,
    )


# ── Test helpers ────────────────────────────────────────────────────


def _reset_session_key_cache_for_tests() -> None:
    """Clear the normalized-session-key cache. Test-only helper."""
    _normalized_session_key_cache.clear()


__all__ = [
    "CasePreservingPeerDescriptor",
    "ParsedAgentSessionKey",
    "ParsedCronRunScopeSuffix",
    "ParsedSessionDeliveryRoute",
    "ParsedThreadSessionSuffix",
    "RawSessionConversationRef",
    "_reset_session_key_cache_for_tests",
    "get_subagent_depth",
    "is_acp_session_key",
    "is_case_preserving_peer",
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
    "to_agent_request_session_key",
]
