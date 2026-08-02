"""jarvis.agents.embedded_agent_runner.compaction_successor_transcript — rotate compacted transcripts.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/compaction-successor-transcript.ts``.

Public surface (mirrors the OpenClaw source):

- :func:`should_rotate_compaction_transcript` — config flag check.
- :func:`rotate_transcript_after_compaction` — write a successor
  transcript file after a successful compaction.
- :func:`rotate_transcript_file_after_compaction` — convenience
  variant that reads the file state first.

Phase 7.2b-2 — focused minimal port.

The OpenClaw source rewrites session entries (parent repair,
thinking-signature stripping, dedup state entries, label cascading,
duplicate user-message pruning, successor file path derivation).
The Python port keeps the same surface but writes the new
transcript through :data:`_WRITE_TRANSCRIPT_ATOMIC` and reads the
state through :data:`_READ_TRANSCRIPT_FILE_STATE`. The host installs
the real implementations; tests can swap in-memory fakes.

The Python port implements the core algorithm inline because the
OpenClaw source has 200+ lines of stateful entry manipulation that
the Python port condenses into a focused minimal equivalent.
"""
from __future__ import annotations

import os
import re
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Set


#: Current session version. Mirrors ``CURRENT_SESSION_VERSION``
#: (``config/sessions/version.ts``). The focused minimal port keeps
#: the constant local; the real version constant is owned by the
#: session module.
CURRENT_SESSION_VERSION: int = 1


#: Atomic transcript-file write sink. Replace in tests with an
#: in-memory capture.
_WRITE_TRANSCRIPT_ATOMIC: Optional[
    Callable[[str, List[Dict[str, Any]]], Any]
] = None


def set_write_transcript_atomic(
    sink: Optional[Callable[[str, List[Dict[str, Any]]], Any]],
) -> None:
    """Install a custom atomic write sink for the successor transcript."""
    global _WRITE_TRANSCRIPT_ATOMIC
    _WRITE_TRANSCRIPT_ATOMIC = sink


#: Read-transcript-file-state sink. Replace in tests.
_READ_TRANSCRIPT_FILE_STATE: Optional[Callable[[str], Any]] = None


def set_read_transcript_file_state(
    sink: Optional[Callable[[str], Any]],
) -> None:
    """Install a custom read-transcript-file-state sink."""
    global _READ_TRANSCRIPT_FILE_STATE
    _READ_TRANSCRIPT_FILE_STATE = sink


def should_rotate_compaction_transcript(
    config: Optional[Dict[str, Any]] = None,
) -> bool:
    """Return True if the configured session should be rotated after compaction.

    Mirrors :func:`shouldRotateCompactionTranscript``
    (``compaction-successor-transcript.ts:33-35``).
    """
    return bool(
        (config or {})
        .get("agents", {})
        .get("defaults", {})
        .get("compaction", {})
        .get("truncateAfterCompaction")
    )


def _resolve_timestamp_ms_to_iso_string(value: Optional[float]) -> str:
    """Format a millisecond timestamp as an ISO-8601 string.

    Mirrors :func:`resolveTimestampMsToIsoString``. Returns
    ``""`` for invalid input.
    """
    if value is None or value <= 0:
        return ""
    try:
        return time.strftime(
            "%Y-%m-%dT%H:%M:%S", time.gmtime(int(value) / 1000)
        )
    except Exception:
        return ""


def _strip_thinking_signatures_from_message(message: Dict[str, Any]) -> Dict[str, Any]:
    """Strip thinking signatures from a message's content blocks.

    Mirrors :func:`stripThinkingSignaturesFromMessage`` from
    ``thinking.ts``. The focused minimal port removes any
    ``thinkingSignature`` field from ``thinking`` content blocks.
    """
    if not isinstance(message, dict):
        return message
    content = message.get("content")
    if not isinstance(content, list):
        return message
    new_blocks: List[Any] = []
    for block in content:
        if not isinstance(block, dict):
            new_blocks.append(block)
            continue
        if block.get("type") == "thinking":
            new_block = {k: v for k, v in block.items() if k != "thinkingSignature"}
            new_blocks.append(new_block)
        else:
            new_blocks.append(block)
    new_message = dict(message)
    new_message["content"] = new_blocks
    return new_message


def _find_latest_compaction_index(branch: List[Dict[str, Any]]) -> int:
    """Find the index of the latest compaction entry in ``branch``."""
    for index in range(len(branch) - 1, -1, -1):
        entry = branch[index]
        if isinstance(entry, dict) and entry.get("type") == "compaction":
            return index
    return -1


def _collect_latest_state_entry_ids(entries: List[Dict[str, Any]]) -> Set[str]:
    """Return the ids of the latest state-only entries (deduped)."""
    latest_by_type: Dict[str, Dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if _is_deduped_state_entry(entry):
            latest_by_type[entry.get("type", "")] = entry
    return {entry.get("id", "") for entry in latest_by_type.values() if entry.get("id")}


def _is_deduped_state_entry(entry: Dict[str, Any]) -> bool:
    """Return True if the entry is a state entry we want to dedupe."""
    return entry.get("type") in {
        "model_change",
        "thinking_level_change",
        "session_info",
    }


def _collect_duplicate_user_message_ids(
    entries: List[Dict[str, Any]],
) -> Set[str]:
    """Collect entry ids for short-window duplicate user messages.

    Mirrors the inline call in
    :func:`buildSuccessorEntries``. The focused minimal port
    delegates to the helper from
    :mod:`compaction_duplicate_user_messages`.
    """
    from .compaction_duplicate_user_messages import (
        collect_duplicate_user_message_entry_ids_for_compaction,
    )

    return set(collect_duplicate_user_message_entry_ids_for_compaction(entries))


def _build_successor_entries(
    all_entries: List[Dict[str, Any]],
    branch: List[Dict[str, Any]],
    latest_compaction_index: int,
) -> List[Dict[str, Any]]:
    """Build the successor entry list.

    Mirrors :func:`buildSuccessorEntries``
    (``compaction-successor-transcript.ts:111-288``).
    """
    if latest_compaction_index < 0 or latest_compaction_index >= len(branch):
        return []
    compaction = branch[latest_compaction_index]
    summarized_branch_ids: Set[str] = set()
    pre_compaction_kept_branch_ids: Set[str] = set()
    found_first_kept = False
    for index in range(latest_compaction_index):
        entry = branch[index]
        if not isinstance(entry, dict):
            continue
        first_kept = compaction.get("firstKeptEntryId")
        if first_kept and entry.get("id") == first_kept:
            found_first_kept = True
        if found_first_kept:
            pre_compaction_kept_branch_ids.add(entry.get("id", ""))
        else:
            summarized_branch_ids.add(entry.get("id", ""))
    # Preserve last assistant message before firstKeptEntryId so the successor
    # transcript keeps a compactionSummary → assistant → user structure.
    is_hardened_boundary = compaction.get("firstKeptEntryId") == compaction.get("id")
    preserved_assistant_id: Optional[str] = None
    preserved_assistant_index = -1
    first_kept_index = -1
    if not is_hardened_boundary:
        for index in range(latest_compaction_index - 1, -1, -1):
            entry = branch[index]
            if not isinstance(entry, dict):
                continue
            if (
                entry.get("id", "") in summarized_branch_ids
                and entry.get("type") == "message"
                and isinstance(entry.get("message"), dict)
                and entry["message"].get("role") == "assistant"
            ):
                preserved_assistant_id = entry.get("id", "")
                preserved_assistant_index = index
                break
    first_kept = compaction.get("firstKeptEntryId")
    if first_kept:
        for index, entry in enumerate(branch):
            if isinstance(entry, dict) and entry.get("id") == first_kept:
                first_kept_index = index
                break
    branch_index_by_id = {
        entry.get("id", ""): index
        for index, entry in enumerate(branch)
        if isinstance(entry, dict)
    }
    preserved_pre_compaction_ids: Set[str] = set()
    if preserved_assistant_id and preserved_assistant_index >= 0:
        preserved_pre_compaction_ids.add(preserved_assistant_id)
        assistant = branch[preserved_assistant_index]
        content = (
            assistant.get("message", {}).get("content", [])
            if isinstance(assistant, dict)
            else []
        )
        tool_call_ids = {
            block.get("id", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "toolCall"
        }
        if tool_call_ids:
            for index in range(preserved_assistant_index + 1, first_kept_index):
                entry = branch[index] if 0 <= index < len(branch) else None
                if not isinstance(entry, dict):
                    continue
                if (
                    entry.get("type") == "message"
                    and isinstance(entry.get("message"), dict)
                    and entry["message"].get("role") == "toolResult"
                    and entry["message"].get("toolCallId") in tool_call_ids
                ):
                    preserved_pre_compaction_ids.add(entry.get("id", ""))
    pre_branch = branch[:latest_compaction_index]
    latest_state_ids = _collect_latest_state_entry_ids(pre_branch)
    stale_state_ids: Set[str] = set()
    for entry in pre_branch:
        if (
            isinstance(entry, dict)
            and _is_deduped_state_entry(entry)
            and entry.get("id", "") not in latest_state_ids
        ):
            stale_state_ids.add(entry.get("id", ""))
    kept_pre_compaction_entries = [
        entry
        for entry in pre_branch
        if isinstance(entry, dict)
        and entry.get("id", "") not in summarized_branch_ids
    ]
    post_compaction_entries = branch[latest_compaction_index + 1 :]
    duplicate_user_message_ids: Set[str] = set()
    duplicate_user_message_ids.update(
        _collect_duplicate_user_message_ids(kept_pre_compaction_entries)
    )
    duplicate_user_message_ids.update(
        _collect_duplicate_user_message_ids(post_compaction_entries)
    )
    removed_ids: Set[str] = set()
    for entry in all_entries:
        if not isinstance(entry, dict):
            continue
        entry_id = entry.get("id", "")
        branch_index = branch_index_by_id.get(entry_id, -1)
        summarized_context_marker = (
            branch_index > preserved_assistant_index
            and branch_index < first_kept_index
            and entry.get("type") in {"custom_message", "branch_summary"}
        )
        is_summarized_user_message = (
            entry_id in summarized_branch_ids
            and entry.get("type") == "message"
            and entry_id not in preserved_pre_compaction_ids
        )
        is_summarized_marker = (
            entry_id in summarized_branch_ids and summarized_context_marker
        )
        if (
            is_summarized_user_message
            or is_summarized_marker
            or entry_id in stale_state_ids
            or entry_id in duplicate_user_message_ids
        ):
            removed_ids.add(entry_id)
    for entry_id in preserved_pre_compaction_ids:
        pre_compaction_kept_branch_ids.add(entry_id)
    for entry in all_entries:
        if (
            isinstance(entry, dict)
            and entry.get("type") == "label"
            and entry.get("targetId") in removed_ids
        ):
            removed_ids.add(entry.get("id", ""))
    entry_by_id: Dict[str, Dict[str, Any]] = {}
    original_index_by_id: Dict[str, int] = {}
    for index, entry in enumerate(all_entries):
        if not isinstance(entry, dict):
            continue
        entry_id = entry.get("id", "")
        if entry_id:
            entry_by_id[entry_id] = entry
            original_index_by_id[entry_id] = index
    active_branch_ids: Set[str] = {
        entry.get("id", "")
        for entry in branch
        if isinstance(entry, dict)
    }
    kept_entries: List[Dict[str, Any]] = []
    for entry in all_entries:
        if not isinstance(entry, dict):
            continue
        entry_id = entry.get("id", "")
        if entry_id in removed_ids:
            continue
        parent_id = entry.get("parentId")
        while parent_id is not None and parent_id in removed_ids:
            parent_id = (
                entry_by_id.get(parent_id, {}).get("parentId")
                if isinstance(entry_by_id.get(parent_id), dict)
                else None
            )
        reparented: Dict[str, Any] = (
            entry if parent_id == entry.get("parentId") else {**entry, "parentId": parent_id}
        )
        transformed = reparented
        if (
            reparented.get("type") == "message"
            and entry_id in pre_compaction_kept_branch_ids
            and isinstance(reparented.get("message"), dict)
        ):
            transformed = {
                **reparented,
                "message": _strip_thinking_signatures_from_message(
                    reparented["message"]
                ),
            }
        if (
            reparented.get("type") == "compaction"
            and reparented.get("id") == compaction.get("id")
            and preserved_assistant_id
            and reparented.get("firstKeptEntryId") != reparented.get("id")
        ):
            transformed = {
                **reparented,
                "firstKeptEntryId": preserved_assistant_id,
            }
        kept_entries.append(transformed)
    return _order_successor_entries(
        entries=kept_entries,
        active_branch_ids=active_branch_ids,
        original_index_by_id=original_index_by_id,
    )


def _order_successor_entries(
    *,
    entries: List[Dict[str, Any]],
    active_branch_ids: Set[str],
    original_index_by_id: Dict[str, int],
) -> List[Dict[str, Any]]:
    """Order successor entries, preferring active branch first.

    Mirrors :func:`orderSuccessorEntries``
    (``compaction-successor-transcript.ts:312-364``).
    """
    entry_ids = {entry.get("id", "") for entry in entries if isinstance(entry, dict)}
    children_by_parent: Dict[Optional[str], List[Dict[str, Any]]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        original_parent = entry.get("parentId")
        parent = (
            original_parent
            if original_parent is not None and original_parent in entry_ids
            else None
        )
        bucket = children_by_parent.setdefault(parent, [])
        if parent == original_parent:
            bucket.append(entry)
        else:
            bucket.append({**entry, "parentId": parent})
    emitted_ids: Set[str] = set()
    ordered: List[Dict[str, Any]] = []

    def _sort_active(left: Dict[str, Any], right: Dict[str, Any]) -> int:
        left_active = left.get("id", "") in active_branch_ids
        right_active = right.get("id", "") in active_branch_ids
        if left_active != right_active:
            return -1 if left_active else 1
        return original_index_by_id.get(left.get("id", ""), 0) - original_index_by_id.get(
            right.get("id", ""), 0
        )

    def _emit_subtree(entry: Dict[str, Any]) -> None:
        entry_id = entry.get("id", "")
        if entry_id in emitted_ids:
            return
        emitted_ids.add(entry_id)
        ordered.append(entry)
        for child in sorted(
            children_by_parent.get(entry_id, []), key=lambda x: (
                0 if x.get("id", "") in active_branch_ids else 1,
                original_index_by_id.get(x.get("id", ""), 0),
            )
        ):
            _emit_subtree(child)

    for root in sorted(
        children_by_parent.get(None, []),
        key=lambda x: (
            0 if x.get("id", "") in active_branch_ids else 1,
            original_index_by_id.get(x.get("id", ""), 0),
        ),
    ):
        _emit_subtree(root)
    # Defensive fallback for malformed transcripts.
    for entry in sorted(
        [e for e in entries if isinstance(e, dict)],
        key=lambda x: (
            0 if x.get("id", "") in active_branch_ids else 1,
            original_index_by_id.get(x.get("id", ""), 0),
        ),
    ):
        _emit_subtree(entry)
    return ordered


def _build_successor_header(
    *,
    previous_header: Optional[Dict[str, Any]],
    session_id: str,
    timestamp: str,
    cwd: str,
    parent_session: str,
) -> Dict[str, Any]:
    """Build the successor session header.

    Mirrors :func:`buildSuccessorHeader``
    (``compaction-successor-transcript.ts:366-381``).
    """
    return {
        "type": "session",
        "version": CURRENT_SESSION_VERSION,
        "id": session_id,
        "timestamp": timestamp,
        "cwd": (previous_header or {}).get("cwd") or cwd,
        "parentSession": parent_session,
    }


def _resolve_successor_session_file(
    *,
    session_file: str,
    session_id: str,
    timestamp: str,
) -> str:
    """Build the successor transcript path.

    Mirrors :func:`resolveSuccessorSessionFile``
    (``compaction-successor-transcript.ts:383-390``).
    """
    file_timestamp = re.sub(r"[:.]", "-", timestamp)
    return os.path.join(
        os.path.dirname(session_file),
        f"{file_timestamp}_{session_id}.jsonl",
    )


async def rotate_transcript_after_compaction(
    *,
    session_manager: Any,
    session_file: str,
    now: Optional[Callable[[], Any]] = None,
) -> Dict[str, Any]:
    """Rotate the session file into a successor transcript.

    Mirrors :func:`rotateTranscriptAfterCompaction``
    (``compaction-successor-transcript.ts:37-88``).
    """
    session_file = (session_file or "").strip()
    if not session_file:
        return {"rotated": False, "reason": "missing session file"}
    branch = session_manager.get_branch() or []
    latest_compaction_index = _find_latest_compaction_index(branch)
    if latest_compaction_index < 0:
        return {"rotated": False, "reason": "no compaction entry"}
    compaction = branch[latest_compaction_index]
    timestamp = _resolve_timestamp_ms_to_iso_string(
        (now or _default_now)().getTime()
        if hasattr((now or _default_now)(), "getTime")
        else None
    )
    if not timestamp:
        timestamp = _resolve_timestamp_ms_to_iso_string(_now_ms())
    session_id = str(uuid.uuid4())
    successor_file = _resolve_successor_session_file(
        session_file=session_file,
        session_id=session_id,
        timestamp=timestamp,
    )
    all_entries = session_manager.get_entries() or []
    successor_entries = _build_successor_entries(
        all_entries=all_entries,
        branch=branch,
        latest_compaction_index=latest_compaction_index,
    )
    if not successor_entries:
        return {"rotated": False, "reason": "empty successor transcript"}
    header = _build_successor_header(
        previous_header=session_manager.get_header(),
        session_id=session_id,
        timestamp=timestamp,
        cwd=session_manager.getCwd() if hasattr(session_manager, "getCwd") else "",
        parent_session=session_file,
    )
    write = _WRITE_TRANSCRIPT_ATOMIC
    if write is None:
        raise RuntimeError(
            "rotate_transcript_after_compaction: no write sink installed "
            "(call set_write_transcript_atomic)"
        )
    await write(successor_file, [header, *successor_entries])
    return {
        "rotated": True,
        "sessionId": session_id,
        "sessionFile": successor_file,
        "compactionEntryId": compaction.get("id"),
        "leafId": (
            successor_entries[-1].get("id") if successor_entries else None
        ),
        "entriesWritten": len(successor_entries),
    }


def _default_now() -> Any:
    """Default ``now`` provider — returns a Date-like with ``getTime``."""
    class _Now:
        def getTime(self) -> float:  # noqa: N802
            return _now_ms()

    return _Now()


def _now_ms() -> int:
    return int(time.time() * 1000)


async def rotate_transcript_file_after_compaction(
    *,
    session_file: str,
    now: Optional[Callable[[], Any]] = None,
) -> Dict[str, Any]:
    """Read the file state then rotate.

    Mirrors :func:`rotateTranscriptFileAfterCompaction``
    (``compaction-successor-transcript.ts:90-100``).
    """
    read = _READ_TRANSCRIPT_FILE_STATE
    if read is None:
        raise RuntimeError(
            "rotate_transcript_file_after_compaction: no read sink installed "
            "(call set_read_transcript_file_state)"
        )
    state = await read(session_file)
    return await rotate_transcript_after_compaction(
        session_manager=state,
        session_file=session_file,
        now=now,
    )


__all__ = [
    "CURRENT_SESSION_VERSION",
    "rotate_transcript_after_compaction",
    "rotate_transcript_file_after_compaction",
    "set_read_transcript_file_state",
    "set_write_transcript_atomic",
    "should_rotate_compaction_transcript",
]
