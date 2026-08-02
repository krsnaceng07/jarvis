"""jarvis.agents.embedded_agent_runner.transcript_rewrite — rewrite transcript message entries.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/transcript-rewrite.ts``.

Public surface (mirrors the OpenClaw source):

- :func:`rewrite_transcript_entries_in_session_manager` —
  rewrite message entries on the active branch by branching
  from the first rewritten message's parent and re-appending
  the suffix.
- :func:`rewrite_transcript_entries_in_state` — same
  operation against an in-memory :class:`TranscriptFileState`.
- :func:`rewrite_transcript_entries_in_runtime_transcript` —
  acquire a session write lock, run the state-based rewrite,
  persist, and emit a transcript update.

Phase 7.5a — focused minimal port.

The OpenClaw source is 600+ lines and tightly coupled to the
session accessor, session-write-lock, transcript-file-state,
and session-manager layers. The Python port keeps the public
surface but delegates the heavy persistence + locking to
installable hooks so the host can plug in the real layers as
they land.
"""
from __future__ import annotations

import json
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, Tuple


#: Transcript-rewrite replacement shape. Mirrors
#: :class:`TranscriptRewriteReplacement`` from
#: ``context-engine/types.js``.
TranscriptRewriteReplacement = Dict[str, Any]


#: Transcript-rewrite request shape. Mirrors
#: :class:`TranscriptRewriteRequest``.
TranscriptRewriteRequest = Dict[str, Any]


#: Transcript-rewrite result shape. Mirrors
#: :class:`TranscriptRewriteResult``.
TranscriptRewriteResult = Dict[str, Any]


#: Transcript-file-state shape used by
#: :func:`rewrite_transcript_entries_in_state``.
TranscriptFileState = Any


#: Session-write-lock acquire timeout config.
SessionWriteLockAcquireTimeoutConfig = Dict[str, Any]


#: Runtime transcript scope.
RuntimeTranscriptScope = Dict[str, Any]


def _estimate_message_bytes(message: Any) -> int:
    """Estimate the byte size of a serialized message.

    Mirrors :func:`estimateMessageBytes``
    (``transcript-rewrite.ts:124-126``).
    """
    try:
        return len(json.dumps(message).encode("utf-8"))
    except (TypeError, ValueError):
        return 0


def _find_transcript_rewrite_matches(
    branch: List[Dict[str, Any]],
    replacements_by_id: Dict[str, Any],
) -> Tuple[List[int], int]:
    """Find the indices in ``branch`` that match the replacement map.

    Mirrors :func:`findTranscriptRewriteMatches``
    (``transcript-rewrite.ts:128-150``).
    """
    matched_indices: List[int] = []
    bytes_freed = 0
    for index, entry in enumerate(branch):
        if not isinstance(entry, dict):
            continue
        if entry.get("type") != "message":
            continue
        entry_id = entry.get("id")
        if entry_id is None:
            continue
        replacement = replacements_by_id.get(entry_id)
        if replacement is None:
            continue
        original_bytes = _estimate_message_bytes(entry.get("message"))
        replacement_bytes = _estimate_message_bytes(replacement)
        matched_indices.append(index)
        bytes_freed += max(0, original_bytes - replacement_bytes)
    return matched_indices, bytes_freed


def _append_message_to_session_manager(
    session_manager: Any,
    entry: Dict[str, Any],
    replacement: Any,
) -> str:
    """Append one entry to the session manager, using the replacement if present.

    Mirrors :func:`appendBranchEntry``
    (``transcript-rewrite.ts:162-216``).
    """
    if replacement is not None:
        return session_manager.appendMessage(replacement)
    if entry.get("type") == "message":
        return session_manager.appendMessage(entry.get("message"))
    if entry.get("type") == "compaction":
        return session_manager.appendCompaction(
            entry.get("summary", ""),
            entry.get("firstKeptEntryId"),
            entry.get("tokensBefore", 0),
            entry.get("details"),
            entry.get("fromHook", False),
        )
    if entry.get("type") == "thinking_level_change":
        return session_manager.appendThinkingLevelChange(entry.get("thinkingLevel", ""))
    if entry.get("type") == "model_change":
        return session_manager.appendModelChange(
            entry.get("provider", ""), entry.get("modelId", "")
        )
    if entry.get("type") == "custom":
        return session_manager.appendCustomEntry(
            entry.get("customType", ""), entry.get("data")
        )
    if entry.get("type") == "custom_message":
        return session_manager.appendCustomMessageEntry(
            entry.get("customType", ""),
            entry.get("content"),
            entry.get("display", True),
            entry.get("details"),
        )
    if entry.get("type") == "session_info":
        return session_manager.appendSessionInfo(entry.get("name", "") or "")
    if entry.get("type") == "branch_summary":
        return session_manager.branchWithSummary(
            entry.get("parentId"),
            entry.get("summary", ""),
            entry.get("details"),
            entry.get("fromHook", False),
        )
    return session_manager.appendLabelChange(
        entry.get("targetId"), entry.get("label", "")
    )


def _append_message_to_state(
    state: Any,
    entry: Dict[str, Any],
    replacement: Any,
) -> Dict[str, Any]:
    """Append one entry to an in-memory :class:`TranscriptFileState`.

    Mirrors :func:`appendTranscriptStateBranchEntry``
    (``transcript-rewrite.ts:218-268``).
    """
    if replacement is not None:
        return state.appendMessage(replacement)
    if entry.get("type") == "message":
        return state.appendMessage(entry.get("message"))
    if entry.get("type") == "compaction":
        return state.appendCompaction(
            entry.get("summary", ""),
            entry.get("firstKeptEntryId"),
            entry.get("tokensBefore", 0),
            entry.get("details"),
            entry.get("fromHook", False),
        )
    if entry.get("type") == "thinking_level_change":
        return state.appendThinkingLevelChange(entry.get("thinkingLevel", ""))
    if entry.get("type") == "model_change":
        return state.appendModelChange(
            entry.get("provider", ""), entry.get("modelId", "")
        )
    if entry.get("type") == "custom":
        return state.appendCustomEntry(
            entry.get("customType", ""), entry.get("data")
        )
    if entry.get("type") == "custom_message":
        return state.appendCustomMessageEntry(
            entry.get("customType", ""),
            entry.get("content"),
            entry.get("display", True),
            entry.get("details"),
        )
    if entry.get("type") == "session_info":
        return state.appendSessionInfo(entry.get("name", "") or "")
    if entry.get("type") == "branch_summary":
        return state.branchWithSummary(
            entry.get("parentId"),
            entry.get("summary", ""),
            entry.get("details"),
            entry.get("fromHook", False),
        )
    return state.appendLabelChange(
        entry.get("targetId"), entry.get("label", "")
    )


def _empty_result(reason: str) -> TranscriptRewriteResult:
    return {
        "changed": False,
        "bytesFreed": 0,
        "rewrittenEntries": 0,
        "reason": reason,
    }


def rewrite_transcript_entries_in_session_manager(
    *,
    session_manager: Any,
    replacements: List[TranscriptRewriteReplacement],
) -> TranscriptRewriteResult:
    """Rewrite message entries on the active branch.

    Mirrors :func:`rewriteTranscriptEntriesInSessionManager``
    (``transcript-rewrite.ts:274-355``).
    """
    replacements_by_id: Dict[str, Any] = {}
    for replacement in replacements:
        if not isinstance(replacement, dict):
            continue
        entry_id = replacement.get("entryId")
        if not isinstance(entry_id, str) or not entry_id.strip():
            continue
        replacements_by_id[entry_id] = replacement.get("message")
    if not replacements_by_id:
        return _empty_result("no replacements requested")
    branch = session_manager.getBranch() or []
    if not branch:
        return _empty_result("empty session")
    matched_indices, bytes_freed = _find_transcript_rewrite_matches(
        branch, replacements_by_id
    )
    if not matched_indices:
        return _empty_result("no matching message entries")
    first_matched_index = matched_indices[0]
    first_matched_entry = branch[first_matched_index]
    if not isinstance(first_matched_entry, dict) or first_matched_entry.get("type") != "message":
        return _empty_result("invalid first rewrite target")
    if not first_matched_entry.get("parentId"):
        session_manager.resetLeaf()
    else:
        session_manager.branch(first_matched_entry["parentId"])
    rewritten_entry_ids: Dict[str, str] = {}
    for entry in branch[first_matched_index:]:
        if not isinstance(entry, dict):
            continue
        entry_id = entry.get("id")
        replacement = (
            replacements_by_id.get(entry_id) if entry.get("type") == "message" else None
        )
        new_id = _append_message_to_session_manager(
            session_manager, entry, replacement
        )
        if entry_id is not None:
            rewritten_entry_ids[entry_id] = new_id
    return {
        "changed": True,
        "bytesFreed": bytes_freed,
        "rewrittenEntries": len(matched_indices),
    }


def rewrite_transcript_entries_in_state(
    *,
    state: TranscriptFileState,
    replacements: List[TranscriptRewriteReplacement],
    allowed_rewrite_suffix_entry_ids: Optional[List[str]] = None,
) -> TranscriptRewriteResult:
    """Rewrite message entries on an in-memory :class:`TranscriptFileState`.

    Mirrors :func:`rewriteTranscriptEntriesInState``
    (``transcript-rewrite.ts:357-517``).
    """
    replacements_by_id: Dict[str, Any] = {}
    for replacement in replacements:
        if not isinstance(replacement, dict):
            continue
        entry_id = replacement.get("entryId")
        if not isinstance(entry_id, str) or not entry_id.strip():
            continue
        replacements_by_id[entry_id] = replacement.get("message")
    if not replacements_by_id:
        return {**_empty_result("no replacements requested"), "appendedEntries": []}
    original_leaf_id = state.getLeafId()
    original_append_parent_id = state.getAppendParentId()
    original_append_mode = state.getAppendMode()
    active_branch = state.getBranch()
    all_entries = state.getEntries()
    branch = active_branch
    restore_original_navigation = False

    def _replacement_ids_on_branch(candidate: List[Dict[str, Any]]) -> Set[str]:
        return {
            e.get("id", "")
            for e in candidate
            if isinstance(e, dict)
            and e.get("type") == "message"
            and e.get("id", "") in replacements_by_id
        }

    active_replacement_ids = _replacement_ids_on_branch(active_branch)
    if (
        0 < active_replacement_ids.size < len(replacements_by_id)
        if hasattr(active_replacement_ids, "size")
        else 0 < len(active_replacement_ids) < len(replacements_by_id)
    ):
        return {**_empty_result("rewrite targets span multiple branches"), "appendedEntries": []}
    active_branch_has_every = (
        len(active_replacement_ids) == len(replacements_by_id)
        if hasattr(active_replacement_ids, "size")
        else len(active_replacement_ids) == len(replacements_by_id)
    )
    if (
        not active_branch_has_every
        and allowed_rewrite_suffix_entry_ids
    ):
        allowed_ids = set(allowed_rewrite_suffix_entry_ids)
        for entry in reversed(all_entries):
            entry_id = entry.get("id") if isinstance(entry, dict) else None
            if not entry_id or entry_id not in allowed_ids:
                continue
            candidate = state.getBranch(entry_id) or []
            if len(_replacement_ids_on_branch(candidate)) == len(replacements_by_id):
                branch = candidate
                restore_original_navigation = True
                break
    if not branch:
        return {**_empty_result("empty session"), "appendedEntries": []}
    matched_indices, bytes_freed = _find_transcript_rewrite_matches(
        branch, replacements_by_id
    )
    if not matched_indices:
        return {**_empty_result("no matching message entries"), "appendedEntries": []}
    first_matched_index = matched_indices[0]
    first_matched_entry = branch[first_matched_index]
    if not isinstance(first_matched_entry, dict) or first_matched_entry.get("type") != "message":
        return {**_empty_result("invalid first rewrite target"), "appendedEntries": []}
    if allowed_rewrite_suffix_entry_ids:
        allowed_ids = set(allowed_rewrite_suffix_entry_ids)
        has_unexpected = any(
            isinstance(e, dict)
            and isinstance(e.get("id"), str)
            and e["id"] not in allowed_ids
            for e in branch[first_matched_index:]
        )
        if has_unexpected:
            return {**_empty_result("rewrite suffix guard failed"), "appendedEntries": []}
    if not first_matched_entry.get("parentId"):
        state.resetLeaf()
    else:
        state.branch(first_matched_entry["parentId"])
    appended_entries: List[Dict[str, Any]] = []
    rewritten_entry_ids: Dict[str, str] = {}
    for entry in branch[first_matched_index:]:
        if not isinstance(entry, dict):
            continue
        entry_id = entry.get("id")
        replacement = (
            replacements_by_id.get(entry_id) if entry.get("type") == "message" else None
        )
        new_entry = _append_message_to_state(state, entry, replacement)
        if entry_id is not None:
            rewritten_entry_ids[entry_id] = new_entry.get("id", "")
        appended_entries.append(new_entry)
    if restore_original_navigation:
        append_leaf_control_kwargs: Dict[str, Any] = {
            "targetId": original_leaf_id,
            "appendParentId": original_append_parent_id,
        }
        if original_append_mode:
            append_leaf_control_kwargs["appendMode"] = original_append_mode
        appended_entries.append(
            state.appendLeafControl(**append_leaf_control_kwargs)
        )
    return {
        "changed": True,
        "bytesFreed": bytes_freed,
        "rewrittenEntries": len(matched_indices),
        "appendedEntries": appended_entries,
    }


#: Session-write-lock acquire hook. The host installs the real
#: :func:`acquireSessionWriteLock`` when the session-write-lock
#: layer lands. The default returns ``None`` (no lock).
_ACQUIRE_SESSION_WRITE_LOCK: Callable[..., Awaitable[Optional[Any]]] = (
    lambda *_args, **_kwargs: _default_acquire_noop()
)


async def _default_acquire_noop() -> None:
    return None


def set_acquire_session_write_lock_hook(
    hook: Callable[..., Awaitable[Optional[Any]]],
) -> None:
    """Install a custom acquire-session-write-lock hook."""
    global _ACQUIRE_SESSION_WRITE_LOCK
    _ACQUIRE_SESSION_WRITE_LOCK = hook


#: Resolve-session-write-lock-options hook.
_RESOLVE_SESSION_WRITE_LOCK_OPTIONS: Callable[..., Dict[str, Any]] = (
    lambda config: config or {}
)


def set_resolve_session_write_lock_options_hook(
    hook: Callable[..., Dict[str, Any]],
) -> None:
    """Install a custom resolve-session-write-lock-options hook."""
    global _RESOLVE_SESSION_WRITE_LOCK_OPTIONS
    _RESOLVE_SESSION_WRITE_LOCK_OPTIONS = hook


#: Read-transcript-file-state hook.
_READ_TRANSCRIPT_FILE_STATE: Callable[..., Awaitable[TranscriptFileState]] = (
    lambda _path: _default_read_state()
)


async def _default_read_state() -> Any:
    return None


def set_read_transcript_file_state_hook(
    hook: Callable[..., Awaitable[TranscriptFileState]],
) -> None:
    """Install a custom read-transcript-file-state hook."""
    global _READ_TRANSCRIPT_FILE_STATE
    _READ_TRANSCRIPT_FILE_STATE = hook


#: Persist-runtime-transcript-state-mutation hook.
_PERSIST_RUNTIME_TRANSCRIPT_STATE_MUTATION: Callable[..., Awaitable[None]] = (
    lambda *_args, **_kwargs: _default_persist_noop()
)


async def _default_persist_noop() -> None:
    return None


def set_persist_runtime_transcript_state_mutation_hook(
    hook: Callable[..., Awaitable[None]],
) -> None:
    """Install a custom persist-runtime-transcript-state-mutation hook."""
    global _PERSIST_RUNTIME_TRANSCRIPT_STATE_MUTATION
    _PERSIST_RUNTIME_TRANSCRIPT_STATE_MUTATION = hook


#: Resolve-runtime-transcript-read-target hook.
_RESOLVE_RUNTIME_TRANSCRIPT_READ_TARGET: Callable[
    [RuntimeTranscriptScope], Awaitable[RuntimeTranscriptScope]
] = (
    lambda scope: _default_resolve_target(scope)
)


async def _default_resolve_target(
    scope: RuntimeTranscriptScope,
) -> RuntimeTranscriptScope:
    return scope


def set_resolve_runtime_transcript_read_target_hook(
    hook: Callable[[RuntimeTranscriptScope], Awaitable[RuntimeTranscriptScope]],
) -> None:
    """Install a custom resolve-runtime-transcript-read-target hook."""
    global _RESOLVE_RUNTIME_TRANSCRIPT_READ_TARGET
    _RESOLVE_RUNTIME_TRANSCRIPT_READ_TARGET = hook


#: Parse-sqlite-session-file-marker hook.
_PARSE_SQLITE_SESSION_FILE_MARKER: Callable[[str], Optional[Dict[str, Any]]] = (
    lambda _path: None
)


def set_parse_sqlite_session_file_marker_hook(
    hook: Callable[[str], Optional[Dict[str, Any]]],
) -> None:
    """Install a custom parse-sqlite-session-file-marker hook."""
    global _PARSE_SQLITE_SESSION_FILE_MARKER
    _PARSE_SQLITE_SESSION_FILE_MARKER = hook


#: Emit-session-transcript-update hook.
_EMIT_SESSION_TRANSCRIPT_UPDATE: Callable[..., None] = lambda *_args, **_kwargs: None


def set_emit_session_transcript_update_hook(
    hook: Callable[..., None],
) -> None:
    """Install a custom emit-session-transcript-update hook."""
    global _EMIT_SESSION_TRANSCRIPT_UPDATE
    _EMIT_SESSION_TRANSCRIPT_UPDATE = hook


async def rewrite_transcript_entries_in_runtime_transcript(
    *,
    scope: RuntimeTranscriptScope,
    request: TranscriptRewriteRequest,
    config: Optional[SessionWriteLockAcquireTimeoutConfig] = None,
) -> TranscriptRewriteResult:
    """Rewrite message entries for a runtime transcript.

    Mirrors :func:`rewriteTranscriptEntriesInRuntimeTranscript``
    (``transcript-rewrite.ts:523-585``).
    """
    from .transcript_runtime_state import (
        persist_runtime_transcript_state_mutation,
        resolve_runtime_transcript_read_target,
    )

    session_lock: Optional[Any] = None
    try:
        target = await resolve_runtime_transcript_read_target(scope)
        session_file = (target or {}).get("sessionFile", "")
        if _PARSE_SQLITE_SESSION_FILE_MARKER(session_file):
            return _empty_result("sqlite marker; runtime path not active")
        session_lock = await _ACQUIRE_SESSION_WRITE_LOCK(
            sessionFile=session_file,
            **_RESOLVE_SESSION_WRITE_LOCK_OPTIONS(config),
        )
        state = await _READ_TRANSCRIPT_FILE_STATE(session_file)
        if state is None:
            return _empty_result("no transcript file state")
        replacements = request.get("replacements") or []
        allowed_ids = request.get("allowedRewriteSuffixEntryIds")
        result = rewrite_transcript_entries_in_state(
            state=state,
            replacements=replacements,
            **({"allowed_rewrite_suffix_entry_ids": allowed_ids} if allowed_ids else {}),
        )
        if result.get("changed"):
            await persist_runtime_transcript_state_mutation(
                appended_entries=result.get("appendedEntries", []),
                state=state,
                target=target,
            )
            _EMIT_SESSION_TRANSCRIPT_UPDATE(
                sessionFile=session_file,
                sessionKey=(target or {}).get("sessionKey"),
                agentId=(target or {}).get("agentId"),
                target=target,
            )
        return result
    except Exception as err:
        return {**_empty_result(str(err)), "reason": str(err)}
    finally:
        release = getattr(session_lock, "release", None) if session_lock else None
        if callable(release):
            result = release()
            if result is not None and hasattr(result, "__await__"):
                await result


__all__ = [
    "RuntimeTranscriptScope",
    "SessionWriteLockAcquireTimeoutConfig",
    "TranscriptFileState",
    "TranscriptRewriteReplacement",
    "TranscriptRewriteRequest",
    "TranscriptRewriteResult",
    "rewrite_transcript_entries_in_runtime_transcript",
    "rewrite_transcript_entries_in_session_manager",
    "rewrite_transcript_entries_in_state",
    "set_acquire_session_write_lock_hook",
    "set_emit_session_transcript_update_hook",
    "set_parse_sqlite_session_file_marker_hook",
    "set_persist_runtime_transcript_state_mutation_hook",
    "set_read_transcript_file_state_hook",
    "set_resolve_runtime_transcript_read_target_hook",
    "set_resolve_session_write_lock_options_hook",
]
