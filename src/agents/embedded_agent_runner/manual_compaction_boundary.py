"""jarvis.agents.embedded_agent_runner.manual_compaction_boundary — hardens manual compaction boundaries.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/manual-compaction-boundary.ts``.

Public surface:

- :func:`harden_manual_compaction_boundary`

Phase 7.6h-3 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Dict, List


_harden_manual_compaction_boundary_hook = None


def set_harden_manual_compaction_boundary_hook(fn) -> None:
    global _harden_manual_compaction_boundary_hook
    _harden_manual_compaction_boundary_hook = fn


def _record_from_unknown(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _replace_latest_compaction_boundary(
    entries: List[Dict[str, Any]],
    compaction_entry_id: str,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for entry in entries:
        if (
            isinstance(entry, dict)
            and entry.get("type") == "compaction"
            and entry.get("id") == compaction_entry_id
        ):
            # Manual /compact: rebuilt context starts from the summary itself.
            new = dict(entry)
            new["firstKeptEntryId"] = entry.get("id")
            out.append(new)
        else:
            out.append(entry)
    return out


def _entry_creates_compaction_input_message(entry: Any) -> bool:
    if not isinstance(entry, dict):
        return False
    t = entry.get("type")
    return t in ("message", "custom_message", "branch_summary")


def _has_messages_to_summarize_before_kept_tail(
    branch: List[Dict[str, Any]],
    compaction: Dict[str, Any],
) -> bool:
    compaction_index = -1
    for i, entry in enumerate(branch):
        if isinstance(entry, dict) and entry.get("id") == compaction.get("id"):
            compaction_index = i
            break
    first_kept_index = -1
    for i, entry in enumerate(branch):
        if isinstance(entry, dict) and entry.get("id") == compaction.get("firstKeptEntryId"):
            first_kept_index = i
            break
    if compaction_index <= 0 or first_kept_index < 0 or first_kept_index >= compaction_index:
        return False

    boundary_start_index = 0
    for i in range(compaction_index - 1, -1, -1):
        entry = branch[i]
        if not (isinstance(entry, dict) and entry.get("type") == "compaction"):
            continue
        previous_first_kept = -1
        for j, candidate in enumerate(branch):
            if isinstance(candidate, dict) and candidate.get("id") == entry.get("firstKeptEntryId"):
                previous_first_kept = j
                break
        boundary_start_index = previous_first_kept if previous_first_kept >= 0 else i + 1
        break

    for entry in branch[boundary_start_index:first_kept_index]:
        if _entry_creates_compaction_input_message(entry):
            return True
    return False


def harden_manual_compaction_boundary(
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """Rewrite the latest manual compaction leaf so replay starts from its summary.

    Mirrors :func:`hardenManualCompactionBoundary` (``manual-compaction-boundary.ts``).
    """
    if _harden_manual_compaction_boundary_hook is not None:
        return _harden_manual_compaction_boundary_hook(params) or {}
    # Minimal port: surface the contract. Heavy I/O is delegated to the
    # transcript_file_state plugin hook at runtime.
    return {
        "applied": False,
        "firstKeptEntryId": params.get("firstKeptEntryId"),
        "leafId": params.get("leafId"),
        "messages": [],
    }


__all__ = [
    "harden_manual_compaction_boundary",
    "set_harden_manual_compaction_boundary_hook",
]
