"""jarvis.routing.session_key — routing session-key builders + classifiers.

OpenClaw parity: mirrors ``src/routing/session-key.ts`` exactly, including
its re-exports from ``session-key-utils`` and ``account-id``.
"""

from __future__ import annotations

from typing import Any, Callable

from jarvis_normalization_core.string_coerce import (
    normalize_lowercase_string_or_empty,
    normalize_optional_string,
)

from .account_id import (  # noqa: F401  (re-exports, OpenClaw parity)
    DEFAULT_ACCOUNT_ID,
    normalize_account_id,
    normalize_optional_account_id,
)
from .agent_id import is_valid_agent_id, normalize_agent_id  # noqa: F401
from .session_key_utils import (  # noqa: F401  (re-exports, OpenClaw parity)
    is_acp_session_key,
    is_cron_run_session_key,
    is_cron_session_key,
    is_subagent_session_key,
    normalize_session_key_preserving_opaque_peer_ids,
    normalize_session_peer_id,
    parse_agent_session_key,
    parse_session_delivery_route,
    parse_thread_session_suffix,
)

DEFAULT_AGENT_ID = "main"
DEFAULT_MAIN_KEY = "main"

# SessionKeyShape = "missing" | "agent" | "legacy_or_alias" | "malformed_agent"


def _normalize_token(value: object) -> str:
    return normalize_lowercase_string_or_empty(value)


def scoped_heartbeat_wake_options(
    session_key: str,
    wake_options: dict[str, Any],
    main_key: str | None = None,
    scope: str | None = None,
) -> dict[str, Any]:
    """Scope heartbeat wake options to the session key's agent.

    Mirrors ``scopedHeartbeatWakeOptions``.
    """
    parsed = parse_agent_session_key(session_key)
    if not parsed:
        return wake_options
    if is_cron_run_session_key(session_key):
        # Global-scope agents drain the literal "global" queue, not agent-main;
        # a targeted wake on agent:<id>:main would be unresolvable. Drop the
        # sessionKey but carry the agent target so multi-agent global-scope
        # setups still wake the originating agent's heartbeat.
        if scope == "global":
            return {**wake_options, "agentId": parsed["agentId"]}
        return {
            **wake_options,
            "sessionKey": build_agent_main_session_key(
                {"agentId": parsed["agentId"], "mainKey": main_key}
            ),
        }
    return {**wake_options, "sessionKey": session_key}


def resolve_event_session_key(
    session_key: str,
    main_key: str | None = None,
    scope: str | None = None,
) -> str:
    """Mirrors ``resolveEventSessionKey``."""
    parsed = parse_agent_session_key(session_key)
    if not parsed or not is_cron_run_session_key(session_key):
        return session_key
    # Global-scope agents enqueue/drain via the literal "global" queue; agent-main
    # would strand the event in a queue the heartbeat never peeks.
    if scope == "global":
        return "global"
    return build_agent_main_session_key({"agentId": parsed["agentId"], "mainKey": main_key})


def normalize_main_key(value: object) -> str:
    return normalize_lowercase_string_or_empty(value) or DEFAULT_MAIN_KEY


def to_agent_request_session_key(store_key: object) -> str | None:
    raw = (store_key if isinstance(store_key, str) else "").strip()
    if not raw:
        return None
    parsed = parse_agent_session_key(raw)
    return parsed["rest"] if parsed else raw


def agent_session_keys_match_by_request_key(left: object, right: object) -> bool:
    left_raw = (left if isinstance(left, str) else "").strip()
    right_raw = (right if isinstance(right, str) else "").strip()
    if not left_raw or not right_raw:
        return False
    return left_raw == right_raw or (
        to_agent_request_session_key(left_raw) == to_agent_request_session_key(right_raw)
    )


def to_agent_store_session_key(params: dict[str, Any]) -> str:
    """Mirrors ``toAgentStoreSessionKey`` (params: agentId, requestKey, mainKey)."""
    request_key = params.get("requestKey")
    raw = (request_key if isinstance(request_key, str) else "").strip()
    lowered = normalize_lowercase_string_or_empty(raw)
    if not raw or lowered == DEFAULT_MAIN_KEY:
        return build_agent_main_session_key(
            {"agentId": params["agentId"], "mainKey": params.get("mainKey")}
        )
    parsed = parse_agent_session_key(raw)
    if parsed:
        return f"agent:{parsed['agentId']}:{parsed['rest']}"
    normalized = normalize_session_key_preserving_opaque_peer_ids(raw)
    if lowered.startswith("agent:"):
        return normalized
    return f"agent:{normalize_agent_id(params['agentId'])}:{normalized}"


def resolve_agent_id_from_session_key(session_key: object) -> str:
    parsed = parse_agent_session_key(session_key)
    return normalize_agent_id(parsed["agentId"] if parsed else DEFAULT_AGENT_ID)


def classify_session_key_shape(session_key: object) -> str:
    """Mirrors ``classifySessionKeyShape``:
    ``missing`` / ``agent`` / ``malformed_agent`` / ``legacy_or_alias``."""
    raw = (session_key if isinstance(session_key, str) else "").strip()
    if not raw:
        return "missing"
    if parse_agent_session_key(raw):
        return "agent"
    if normalize_lowercase_string_or_empty(raw).startswith("agent:"):
        return "malformed_agent"
    return "legacy_or_alias"


def is_unscoped_session_key_sentinel(session_key: object) -> bool:
    lowered = normalize_lowercase_string_or_empty(session_key)
    return lowered in ("global", "unknown")


def scope_legacy_session_key_to_agent(params: dict[str, Any]) -> str | None:
    """Mirrors ``scopeLegacySessionKeyToAgent`` (params: agentId, sessionKey, mainKey)."""
    session_key = params.get("sessionKey")
    raw = (session_key if isinstance(session_key, str) else "").strip()
    if not raw:
        return None
    agent_id_raw = params.get("agentId")
    agent_id = agent_id_raw.strip() if isinstance(agent_id_raw, str) else None
    if not agent_id or classify_session_key_shape(raw) != "legacy_or_alias":
        return raw
    return to_agent_store_session_key(
        {"agentId": agent_id, "requestKey": raw, "mainKey": params.get("mainKey")}
    )


def normalize_optional_agent_id(value: object) -> str | None:
    trimmed = normalize_optional_string(value)
    return normalize_agent_id(trimmed) if trimmed else None


def sanitize_agent_id(value: object) -> str:
    return normalize_agent_id(value)


def build_agent_main_session_key(params: dict[str, Any]) -> str:
    agent_id = normalize_agent_id(params["agentId"])
    main_key = normalize_main_key(params.get("mainKey"))
    return f"agent:{agent_id}:{main_key}"


def build_agent_peer_session_key(params: dict[str, Any]) -> str:
    """Mirrors ``buildAgentPeerSessionKey``.

    Params: agentId, mainKey?, channel, accountId?, peerKind?, peerId?,
    identityLinks?, dmScope? ("main" | "per-peer" | "per-channel-peer" |
    "per-account-channel-peer").
    """
    peer_kind = params.get("peerKind") or "direct"
    if peer_kind == "direct":
        dm_scope = params.get("dmScope") or "main"
        peer_id = (params.get("peerId") or "").strip()
        linked_peer_id = (
            None
            if dm_scope == "main"
            else _resolve_linked_peer_id(
                {
                    "identityLinks": params.get("identityLinks"),
                    "channel": params.get("channel") or "",
                    "peerId": peer_id,
                }
            )
        )
        if linked_peer_id:
            peer_id = linked_peer_id
        peer_id = normalize_lowercase_string_or_empty(peer_id)
        if dm_scope == "per-account-channel-peer" and peer_id:
            channel = normalize_lowercase_string_or_empty(params.get("channel")) or "unknown"
            account_id = normalize_account_id(params.get("accountId"))
            return (
                f"agent:{normalize_agent_id(params['agentId'])}:"
                f"{channel}:{account_id}:direct:{peer_id}"
            )
        if dm_scope == "per-channel-peer" and peer_id:
            channel = normalize_lowercase_string_or_empty(params.get("channel")) or "unknown"
            return f"agent:{normalize_agent_id(params['agentId'])}:{channel}:direct:{peer_id}"
        if dm_scope == "per-peer" and peer_id:
            return f"agent:{normalize_agent_id(params['agentId'])}:direct:{peer_id}"
        return build_agent_main_session_key(
            {"agentId": params["agentId"], "mainKey": params.get("mainKey")}
        )
    channel = normalize_lowercase_string_or_empty(params.get("channel")) or "unknown"
    peer_id = (
        normalize_session_peer_id(
            {
                "channel": params.get("channel"),
                "peerKind": peer_kind,
                "peerId": params.get("peerId"),
            }
        )
        or "unknown"
    )
    return f"agent:{normalize_agent_id(params['agentId'])}:{channel}:{peer_kind}:{peer_id}"


def _resolve_linked_peer_id(params: dict[str, Any]) -> str | None:
    """Mirrors ``resolveLinkedPeerId``."""
    identity_links = params.get("identityLinks")
    if not identity_links or not isinstance(identity_links, dict):
        return None
    peer_id = (params.get("peerId") or "").strip()
    if not peer_id:
        return None
    candidates: set[str] = set()
    raw_candidate = _normalize_token(peer_id)
    if raw_candidate:
        candidates.add(raw_candidate)
    channel = _normalize_token(params.get("channel"))
    if channel:
        scoped_candidate = _normalize_token(f"{channel}:{peer_id}")
        if scoped_candidate:
            candidates.add(scoped_candidate)
    if not candidates:
        return None
    for canonical, ids in identity_links.items():
        canonical_name = canonical.strip() if isinstance(canonical, str) else ""
        if not canonical_name:
            continue
        if not isinstance(ids, list):
            continue
        for entry in ids:
            normalized = _normalize_token(entry)
            if normalized and normalized in candidates:
                return canonical_name
    return None


def build_group_history_key(params: dict[str, Any]) -> str:
    """Mirrors ``buildGroupHistoryKey`` (params: channel, accountId?, peerKind, peerId)."""
    channel = _normalize_token(params.get("channel")) or "unknown"
    account_id = normalize_account_id(params.get("accountId"))
    peer_id = (
        normalize_session_peer_id(
            {
                "channel": channel,
                "peerKind": params["peerKind"],
                "peerId": params["peerId"],
            }
        )
        or "unknown"
    )
    return f"{channel}:{account_id}:{params['peerKind']}:{peer_id}"


def resolve_thread_session_keys(params: dict[str, Any]) -> dict[str, Any]:
    """Mirrors ``resolveThreadSessionKeys``.

    Params: baseSessionKey, threadId?, parentSessionKey?, useSuffix?,
    normalizeThreadId? (callable). Returns
    ``{"sessionKey", "parentSessionKey"}``.
    """
    thread_id = (params.get("threadId") or "").strip()
    if not thread_id:
        return {"sessionKey": params["baseSessionKey"], "parentSessionKey": None}
    normalize_thread_id: Callable[[str], str] | None = params.get("normalizeThreadId")
    normalized_thread = (
        normalize_thread_id(thread_id)
        if normalize_thread_id is not None
        else normalize_lowercase_string_or_empty(thread_id)
    )
    use_suffix = params.get("useSuffix", True)
    session_key = (
        f"{params['baseSessionKey']}:thread:{normalized_thread}"
        if use_suffix
        else params["baseSessionKey"]
    )
    return {"sessionKey": session_key, "parentSessionKey": params.get("parentSessionKey")}


__all__ = [
    "DEFAULT_ACCOUNT_ID",
    "DEFAULT_AGENT_ID",
    "DEFAULT_MAIN_KEY",
    "agent_session_keys_match_by_request_key",
    "build_agent_main_session_key",
    "build_agent_peer_session_key",
    "build_group_history_key",
    "classify_session_key_shape",
    "is_acp_session_key",
    "is_cron_session_key",
    "is_subagent_session_key",
    "is_unscoped_session_key_sentinel",
    "is_valid_agent_id",
    "normalize_account_id",
    "normalize_agent_id",
    "normalize_main_key",
    "normalize_optional_account_id",
    "normalize_optional_agent_id",
    "parse_agent_session_key",
    "parse_session_delivery_route",
    "parse_thread_session_suffix",
    "resolve_agent_id_from_session_key",
    "resolve_event_session_key",
    "resolve_thread_session_keys",
    "sanitize_agent_id",
    "scope_legacy_session_key_to_agent",
    "scoped_heartbeat_wake_options",
    "to_agent_request_session_key",
    "to_agent_store_session_key",
]
