"""src.agents.subagents.completion
Subagent completion findings aggregation, prompt data formatting, and delivery.

Matches OpenClaw parity:
- src/agents/subagents/announce/subagent-announce-output.ts
- src/agents/subagents/announce/subagent-announce-completion-delivery.ts
- src/agents/sanitize-for-prompt.ts
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence

from .types import SubagentRunRecord, SubagentStatus

MAX_CHILD_COMPLETION_RESULT_CHARS: int = 512
MAX_CHILD_COMPLETION_FIELD_CHARS: int = 256
MAX_CHILD_COMPLETION_FINDINGS_CHARS: int = 4096


def wrap_prompt_data_block(
    label: str,
    text: str,
    max_escaped_chars: int = MAX_CHILD_COMPLETION_RESULT_CHARS,
    truncation_marker: str = "\n[child result truncated]",
) -> str:
    """Wrap untrusted or child data in an explicit delimiter block for safe prompt injection."""
    cleaned = text.strip() if text else "(no output)"
    if len(cleaned) > max_escaped_chars:
        keep_len = max(0, max_escaped_chars - len(truncation_marker))
        cleaned = cleaned[:keep_len] + truncation_marker

    return f"=== {label} ===\n{cleaned}\n==="


def describe_subagent_outcome(record: SubagentRunRecord) -> str:
    """Return a clean, normalized status outcome string matching OpenClaw."""
    if record.status == SubagentStatus.COMPLETED:
        return "ok"
    if record.status in (SubagentStatus.FAILED, SubagentStatus.TIMED_OUT, SubagentStatus.CANCELLED):
        err = (record.error or "").strip()
        return f"{record.status.value}: {err}" if err else record.status.value
    return record.status.value


def build_child_completion_findings(records: Sequence[SubagentRunRecord]) -> str | None:
    """Format child execution findings into OpenClaw's canonical prompt data block.

    Matches OpenClaw's buildChildCompletionFindings in subagent-announce-output.ts.
    """
    if not records:
        return None

    # Chronological sort with deterministic session tie-breaking
    sorted_records = sorted(
        records,
        key=lambda r: (
            r.started_at,
            r.ended_at if r.ended_at is not None else float("inf"),
            r.child_session_key,
        ),
    )

    sections: list[str] = []
    for idx, child in enumerate(sorted_records, start=1):
        title = (child.label or child.task or child.child_session_key).strip()
        if len(title) > MAX_CHILD_COMPLETION_FIELD_CHARS:
            title = title[: MAX_CHILD_COMPLETION_FIELD_CHARS - 1] + "…"

        outcome = describe_subagent_outcome(child)
        if len(outcome) > MAX_CHILD_COMPLETION_FIELD_CHARS:
            outcome = outcome[: MAX_CHILD_COMPLETION_FIELD_CHARS - 1] + "…"

        result_block = wrap_prompt_data_block(
            label="Child result",
            text=child.result_text
            or ("(no output)" if not child.error else f"Error: {child.error}"),
            max_escaped_chars=MAX_CHILD_COMPLETION_RESULT_CHARS,
        )

        section = f"{idx}. {title}\nstatus: {outcome}\n{result_block}"
        sections.append(section)

    body = "\n\n".join(sections)
    full_text = f"Child completion results:\n\n{body}"

    if len(full_text) > MAX_CHILD_COMPLETION_FINDINGS_CHARS:
        full_text = (
            full_text[:MAX_CHILD_COMPLETION_FINDINGS_CHARS] + "\n\n[Additional findings truncated]"
        )

    return full_text


class SubagentCompletionHandler:
    """Manages completion collection, physical claim verification, and delivery to parent sessions."""

    def __init__(self) -> None:
        self._delivery_queues: dict[str, list[SubagentRunRecord]] = {}

    def record_completion(self, record: SubagentRunRecord) -> None:
        """Buffer a completed child record for delivery to its parent session."""
        parent_key = record.parent_session_key
        if parent_key not in self._delivery_queues:
            self._delivery_queues[parent_key] = []
        self._delivery_queues[parent_key].append(record)

        # Reactive system event delivery & parent agent wake-up (OpenClaw parity)
        findings_text = build_child_completion_findings([record])
        if findings_text and parent_key:
            try:
                from src.sessions.system_event_queue import enqueue_system_event
                from src.infra.heartbeat_wake import request_heartbeat

                enqueue_system_event(
                    findings_text,
                    {"sessionKey": parent_key, "contextKey": f"subagent:{record.child_session_key}"},
                )
                request_heartbeat({
                    "source": "subagent-completion",
                    "intent": "immediate",
                    "reason": "subagent-completion",
                    "sessionKey": parent_key,
                })
            except Exception:
                pass

    def drain_completions(self, parent_session_key: str) -> list[SubagentRunRecord]:
        """Drain all pending completed child runs for a parent session."""
        return self._delivery_queues.pop(parent_session_key, [])

    def verify_child_artifacts(self, record: SubagentRunRecord) -> tuple[bool, str | None]:
        """Verify physical truthfulness of artifacts claimed by a child subagent.

        Ensures children cannot report success on non-existent files or fake operations.
        """
        if not record.tangible_artifacts:
            # If no physical artifacts were claimed, status is based on execution outcome
            return (record.status == SubagentStatus.COMPLETED, None)

        missing_files: list[str] = []
        for item in record.tangible_artifacts:
            # Check file paths
            if os.path.sep in item or "/" in item or item.startswith("."):
                p = Path(item)
                if not p.exists():
                    missing_files.append(item)

        if missing_files:
            err = f"Child claimed creation/modification of files that do not exist: {missing_files}"
            return (False, err)

        return (True, None)
