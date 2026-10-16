"""Agent-harness session-key helpers.

Mirrors OpenClaw's ``src/sessions/agent-harness-session-key.ts``:

- The agent-harness namespace (``harness:``) is reserved for
  agent-harness-owned sessions. Public session APIs must not
  create rows in this namespace.
- Locked rows require a durable transcript identity; reserved
  rows must also match the key owner.

Public surface (mirrors the TS source):
- ``is_agent_harness_session_key(session_key)``
- ``is_agent_harness_session_key_owned_by(session_key, agent_harness_id)``
- ``resolve_missing_agent_harness_session_error(session_key, entry)``
- ``resolve_agent_harness_session_context_error(session_key, entry)``
- ``resolve_agent_harness_session_store_entry_error(session_key, entry)``
- ``resolve_agent_harness_session_id_mismatch_error(entry, requested_session_id)``
- ``is_valid_agent_harness_session_store_entry(session_key, entry)``
- ``is_agent_harness_session_store_entry_protected(session_key, entry)``
- ``resolve_agent_harness_session_store_error(store)``
- ``resolve_agent_harness_session_store_transition_error(params)``

Python adaptations (documented in code):
- TS ``Record<string, Entry>`` → Python ``dict[str, Entry]``
- TS ``ReadonlyMap`` → Python ``Mapping`` (dict-compatible)
- Runtime-id normalization reuses the canonical
  ``src/agents/agent_runtime_id.py`` (mirrors OpenClaw's
  ``src/agents/agent-runtime-id.ts``); the underscore aliases below
  stay as thin same-module shims for existing callers
- TS ``JSON.stringify(a) === JSON.stringify(b)`` is preserved as
  ``json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)``
  so the canonical equality is order-independent
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Optional, TypedDict

from jarvis_normalization_core.string_coerce import normalize_optional_string

from src.sessions.session_key_utils import parse_agent_session_key

# Reserved namespace prefix; mirrors the TS constant.
AGENT_HARNESS_SESSION_KEY_PREFIX = "harness:"
# Public message constants (mirrors TS exports).
AGENT_HARNESS_SESSION_KEY_RESERVED_MESSAGE = (
    "Session key namespace is reserved for agent harness-owned sessions."
)
AGENT_HARNESS_SESSION_ID_LOCKED_MESSAGE = (
    "Agent harness-owned session identity is locked and cannot be replaced or shared."
)
AGENT_HARNESS_MODEL_RUN_FORBIDDEN_MESSAGE = (
    "Agent harness-owned sessions cannot be used for one-shot model runs."
)
MODEL_SELECTION_LOCK_REMOVAL_MESSAGE = (
    "Model-selection-locked sessions cannot be removed, unlocked, or reassigned."
)

# Canonical agent-runtime-id surface (single home:
# ``src/agents/agent_runtime_id.py``). The underscore alias below preserves
# this module's existing private call sites.
from src.agents.agent_runtime_id import (  # noqa: E402
    normalize_optional_agent_runtime_id as _normalize_optional_agent_runtime_id,
)


# Minimal store-entry TypedDict covering the fields this module
# touches. Real callers can layer their own TypedDict on top.
class AgentHarnessSessionStoreEntry(TypedDict, total=False):
    agentHarnessId: Any
    modelSelectionLocked: bool
    sessionId: Any


def _resolve_agent_harness_session_key_rest(session_key: str) -> str:
    """Return the trimmed lowercase post-``agent:...:`` part of ``session_key``.

    Mirrors the private ``resolveAgentHarnessSessionKeyRest`` helper.
    """
    if not isinstance(session_key, str):
        return ""
    trimmed = session_key.strip().lower()
    parsed = parse_agent_session_key(trimmed)
    return parsed.rest if parsed else trimmed


def _resolve_agent_harness_session_key_owner(session_key: str) -> Optional[str]:
    """Return the runtime owner of a reserved harness key, or ``None`` if not reserved.

    Mirrors the private ``resolveAgentHarnessSessionKeyOwner`` helper.
    """
    rest = _resolve_agent_harness_session_key_rest(session_key)
    if not rest.startswith(AGENT_HARNESS_SESSION_KEY_PREFIX):
        return None
    owner_segment = rest[len(AGENT_HARNESS_SESSION_KEY_PREFIX) :].split(":", 1)[0]
    return _normalize_optional_agent_runtime_id(owner_segment)


def is_agent_harness_session_key(session_key: object) -> bool:
    """Return ``True`` when ``session_key`` falls in the reserved agent-harness namespace.

    Mirrors ``isAgentHarnessSessionKey``.
    """
    if not isinstance(session_key, str):
        return False
    return _resolve_agent_harness_session_key_rest(session_key).startswith(
        AGENT_HARNESS_SESSION_KEY_PREFIX
    )


def resolve_missing_agent_harness_session_error(
    session_key: object, entry: object
) -> Optional[str]:
    """Return the reserved-namespace error when the key is reserved and no entry exists.

    Mirrors ``resolveMissingAgentHarnessSessionError``.
    """
    if entry is None and isinstance(session_key, str) and is_agent_harness_session_key(session_key):
        return AGENT_HARNESS_SESSION_KEY_RESERVED_MESSAGE
    return None


def is_agent_harness_session_key_owned_by(session_key: object, agent_harness_id: object) -> bool:
    """Return ``True`` when ``session_key``'s owner segment matches ``agent_harness_id``.

    Mirrors ``isAgentHarnessSessionKeyOwnedBy``.
    """
    if not isinstance(session_key, str):
        return False
    normalized_harness_id = _normalize_optional_agent_runtime_id(agent_harness_id)
    if not normalized_harness_id:
        return False
    return normalized_harness_id == _resolve_agent_harness_session_key_owner(session_key)


def _session_lock_owner_matches(previous: Mapping[str, Any], next_: Mapping[str, Any]) -> bool:
    """Return ``True`` when both entries have equivalent normalized harness owners.

    Mirrors the private ``sessionLockOwnerMatches`` helper.
    """
    previous_owner = (normalize_optional_string(previous.get("agentHarnessId")) or "").lower()
    next_owner = (normalize_optional_string(next_.get("agentHarnessId")) or "").lower()
    if previous_owner != next_owner:
        return False
    return _normalize_optional_agent_runtime_id(
        previous_owner
    ) == _normalize_optional_agent_runtime_id(next_owner)


def _has_equivalent_relocated_locked_entry(
    *,
    previous_key: str,
    previous_entry: Mapping[str, Any],
    store: Mapping[str, Mapping[str, Any]],
) -> bool:
    """Return ``True`` when an equivalent locked row exists at a different key.

    Mirrors the private ``hasEquivalentRelocatedLockedEntry`` helper.
    """
    if is_agent_harness_session_key(previous_key):
        return False
    session_id = normalize_optional_string(previous_entry.get("sessionId"))
    if not session_id:
        return False
    for session_key, entry in store.items():
        if session_key == previous_key:
            continue
        if (
            entry.get("modelSelectionLocked") is True
            and entry.get("sessionId") == session_id
            and _session_lock_owner_matches(previous_entry, entry)
        ):
            return True
    return False


def resolve_agent_harness_session_store_transition_error(
    *,
    allowed_removals: Optional[Mapping[str, Mapping[str, Any]]] = None,
    before: Optional[Mapping[str, Mapping[str, Any]]] = None,
    store: Mapping[str, Mapping[str, Any]],
) -> Optional[str]:
    """Validate a whole-store compatibility projection, preserving durable locks.

    Mirrors ``resolveAgentHarnessSessionStoreTransitionError``.
    Returns an error message or ``None``.
    """
    for session_key, previous_entry in (before or {}).items():
        next_entry = store.get(session_key)
        if (
            next_entry is not None
            and next_entry.get("modelSelectionLocked") is True
            and _session_lock_owner_matches(previous_entry, next_entry)
        ):
            if next_entry.get("sessionId") != previous_entry.get("sessionId"):
                return AGENT_HARNESS_SESSION_ID_LOCKED_MESSAGE
            continue
        allowed_removal = allowed_removals.get(session_key) if allowed_removals else None
        if (
            next_entry is None
            and allowed_removal is not None
            and json.dumps(previous_entry, sort_keys=True)
            == json.dumps(allowed_removal, sort_keys=True)
        ):
            continue
        if next_entry is None and _has_equivalent_relocated_locked_entry(
            previous_key=session_key,
            previous_entry=previous_entry,
            store=store,
        ):
            continue
        return MODEL_SELECTION_LOCK_REMOVAL_MESSAGE
    return None


def is_agent_harness_session_store_entry_protected(
    session_key: object, entry: Mapping[str, Any]
) -> bool:
    """Return ``True`` when a reserved-looking row carries the durable harness lock.

    Mirrors ``isAgentHarnessSessionStoreEntryProtected``.
    """
    return is_agent_harness_session_key(session_key) and entry.get("modelSelectionLocked") is True


def resolve_agent_harness_session_store_entry_error(
    session_key: object, entry: Mapping[str, Any]
) -> Optional[str]:
    """Validate the lock metadata on a single session store row.

    Mirrors ``resolveAgentHarnessSessionStoreEntryError``.
    """
    if entry.get("modelSelectionLocked") is not True:
        return None
    raw_harness_id = (normalize_optional_string(entry.get("agentHarnessId")) or "").lower()
    has_canonical_harness_owner = bool(
        raw_harness_id
    ) and raw_harness_id == _normalize_optional_agent_runtime_id(raw_harness_id)
    if not normalize_optional_string(entry.get("sessionId")) and (
        is_agent_harness_session_key(session_key) or "agentHarnessId" in entry
    ):
        return AGENT_HARNESS_SESSION_ID_LOCKED_MESSAGE
    if is_agent_harness_session_key(session_key):
        if has_canonical_harness_owner and is_agent_harness_session_key_owned_by(
            session_key, entry.get("agentHarnessId")
        ):
            return None
        return AGENT_HARNESS_SESSION_KEY_RESERVED_MESSAGE
    # ``modelSelectionLocked`` predates harness-owned sessions and
    # still protects ordinary UI sessions. Only rows with an
    # explicit harness owner opt into the stronger transcript
    # identity invariant.
    if "agentHarnessId" not in entry:
        return None
    if not has_canonical_harness_owner:
        return AGENT_HARNESS_SESSION_ID_LOCKED_MESSAGE
    return None


def is_valid_agent_harness_session_store_entry(
    session_key: object, entry: Mapping[str, Any]
) -> bool:
    """Return ``True`` when the row is a valid durable harness lock.

    Mirrors ``isValidAgentHarnessSessionStoreEntry``.
    """
    if entry.get("modelSelectionLocked") is not True:
        return False
    if not (
        is_agent_harness_session_key(session_key)
        or _normalize_optional_agent_runtime_id(entry.get("agentHarnessId")) is not None
    ):
        return False
    return resolve_agent_harness_session_store_entry_error(session_key, entry) is None


def resolve_agent_harness_session_store_error(
    store: Mapping[str, Mapping[str, Any]],
) -> Optional[str]:
    """Validate a full session store for harness-lock consistency and identity aliases.

    Mirrors ``resolveAgentHarnessSessionStoreError``.
    """
    locked_session_ids: dict[str, str] = {}
    for session_key, entry in store.items():
        entry_error = resolve_agent_harness_session_store_entry_error(session_key, entry)
        if entry_error is not None:
            return entry_error
        if not is_valid_agent_harness_session_store_entry(session_key, entry):
            continue
        session_id = normalize_optional_string(entry.get("sessionId"))
        if not session_id or session_id in locked_session_ids:
            return AGENT_HARNESS_SESSION_ID_LOCKED_MESSAGE
        locked_session_ids[session_id] = session_key
    for session_key, entry in store.items():
        session_id = normalize_optional_string(entry.get("sessionId"))
        if not session_id:
            continue
        locked_owner = locked_session_ids.get(session_id)
        if locked_owner and locked_owner != session_key:
            return AGENT_HARNESS_SESSION_ID_LOCKED_MESSAGE
    return None


def resolve_agent_harness_session_id_mismatch_error(
    entry: Optional[Mapping[str, Any]], requested_session_id: object
) -> Optional[str]:
    """Reject caller-selected transcript identities that would rotate a durable harness lock.

    Mirrors ``resolveAgentHarnessSessionIdMismatchError``.
    """
    if (
        not entry
        or entry.get("modelSelectionLocked") is not True
        or not _normalize_optional_agent_runtime_id(entry.get("agentHarnessId"))
    ):
        return None
    requested = normalize_optional_string(requested_session_id)
    if not requested:
        return None
    return (
        None
        if requested == normalize_optional_string(entry.get("sessionId"))
        else AGENT_HARNESS_SESSION_ID_LOCKED_MESSAGE
    )


def resolve_agent_harness_session_context_error(
    session_key: object,
    entry: Optional[Mapping[str, Any]],
) -> Optional[str]:
    """Resolve the per-context harness error for a session lookup.

    Mirrors ``resolveAgentHarnessSessionContextError``. Missing
    reserved keys fail closed; pre-feature unlocked collisions
    stay ordinary.
    """
    if not is_agent_harness_session_key(session_key):
        return None
    if entry is None:
        return AGENT_HARNESS_SESSION_KEY_RESERVED_MESSAGE
    return resolve_agent_harness_session_store_entry_error(session_key, entry)


__all__ = [
    "AGENT_HARNESS_MODEL_RUN_FORBIDDEN_MESSAGE",
    "AGENT_HARNESS_SESSION_ID_LOCKED_MESSAGE",
    "AGENT_HARNESS_SESSION_KEY_PREFIX",
    "AGENT_HARNESS_SESSION_KEY_RESERVED_MESSAGE",
    "AgentHarnessSessionStoreEntry",
    "MODEL_SELECTION_LOCK_REMOVAL_MESSAGE",
    "is_agent_harness_session_key",
    "is_agent_harness_session_key_owned_by",
    "is_agent_harness_session_store_entry_protected",
    "is_valid_agent_harness_session_store_entry",
    "resolve_agent_harness_session_context_error",
    "resolve_agent_harness_session_id_mismatch_error",
    "resolve_agent_harness_session_store_entry_error",
    "resolve_agent_harness_session_store_error",
    "resolve_agent_harness_session_store_transition_error",
    "resolve_missing_agent_harness_session_error",
]
