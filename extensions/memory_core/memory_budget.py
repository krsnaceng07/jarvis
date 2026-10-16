"""memory_core.memory_budget — bounded MEMORY.md compaction for dreaming writes.

OpenClaw parity: mirrors ``extensions/memory-core/src/memory-budget.ts``.

Background: the dreaming pipeline appends promoted entries to MEMORY.md via
``short_term_promotion.apply_short_term_promotions``. Without a size budget,
MEMORY.md grows unboundedly and eventually exceeds bootstrap's per-file
injection cap, breaking session bootstrap. See issue #73691 (upstream).

Strategy: drop the OLDEST auto-promoted sections (date-ordered) until the
file plus the new section fit within the budget. User-authored content
(anything that is not a ``## Promoted From Short-Term Memory (DATE)``
section) is preserved unconditionally — only dreaming-owned sections are
eligible for compaction.
"""

from __future__ import annotations

import re
from typing import TypedDict

# ── Constants ─────────────────────────────────────────────────────────────────

PROMOTION_SECTION_HEADING_RE = re.compile(r"^## Promoted From Short-Term Memory \(([^)]+)\)\s*$")

# Default budget for MEMORY.md content on disk, in characters. Chosen to stay
# safely below the bootstrap injection cap (~12KB per file at the time of
# writing) so promoted memory keeps reaching new sessions.
DEFAULT_MEMORY_FILE_MAX_CHARS = 10_000

# Reserve for writer-side overhead that the helper does not see directly:
# the "# Long-Term Memory\n\n" header (20 chars) + withTrailingNewline's
# trailing "\n" (1 char). Subtracting from budgetChars keeps the on-disk
# file inside the caller's stated budget.
_WRITE_OVERHEAD_RESERVE = 21


# ── Internal types ────────────────────────────────────────────────────────────


class _PreservedBlock(TypedDict):
    kind: str  # "preserved"
    text: str


class _PromotionBlock(TypedDict):
    kind: str  # "promotion"
    date: str
    text: str


_MemoryBlock = _PreservedBlock | _PromotionBlock


class CompactMemoryResult(TypedDict):
    compacted: str
    dropped_dates: list[str]


# ── Block parsing ─────────────────────────────────────────────────────────────


def _parse_memory_blocks(content: str) -> list[_MemoryBlock]:
    """Split MEMORY.md into preserved and promotion blocks.

    Mirrors OpenClaw's ``parseMemoryBlocks``.
    """
    if not content:
        return []

    lines = re.split(r"\r?\n", content)
    blocks: list[_MemoryBlock] = []
    current_lines: list[str] = []
    current_kind = "preserved"
    current_date: str | None = None

    def _flush() -> None:
        nonlocal current_lines, current_kind, current_date
        if not current_lines:
            return
        text = "\n".join(current_lines)
        if current_kind == "promotion" and current_date:
            blocks.append({"kind": "promotion", "date": current_date, "text": text})
        else:
            blocks.append({"kind": "preserved", "text": text})
        current_lines = []
        current_kind = "preserved"
        current_date = None

    for line in lines:
        if line.startswith("## "):
            _flush()
            m = PROMOTION_SECTION_HEADING_RE.match(line)
            if m:
                current_kind = "promotion"
                current_date = m.group(1)
            else:
                current_kind = "preserved"
            current_lines = [line]
        else:
            current_lines.append(line)

    _flush()
    return blocks


def _join_blocks(blocks: list[_MemoryBlock]) -> str:
    """Re-join blocks into a single string.

    Mirrors OpenClaw's ``joinBlocks``.
    """
    return "\n".join(b["text"] for b in blocks)


# ── Public API ────────────────────────────────────────────────────────────────


def compact_memory_for_budget(
    *,
    existing_memory: str,
    new_section: str,
    budget_chars: int,
) -> CompactMemoryResult:
    """Drop oldest auto-promotion sections until the file fits within budget.

    Mirrors OpenClaw's ``compactMemoryForBudget``. Guarantees:
    - Non-promotion content (user-authored markdown, the file header, any
      ``##`` heading not matching the promotion pattern) is preserved.
    - Promotion sections are dropped in ascending date order (oldest first).
    - If existing_memory + new_section already fits the budget, the existing
      memory is returned unchanged.
    - If the budget cannot be satisfied even by dropping every promotion
      section, drops them all and returns; the caller writes the new section
      anyway.
    """
    if budget_chars <= 0:
        return {"compacted": existing_memory, "dropped_dates": []}

    # Reserve writer-side overhead so the on-disk file fits the stated budget.
    effective_budget = max(0, budget_chars - _WRITE_OVERHEAD_RESERVE)

    if len(existing_memory) + len(new_section) <= effective_budget:
        return {"compacted": existing_memory, "dropped_dates": []}

    blocks = _parse_memory_blocks(existing_memory)
    promotion_entries: list[dict] = []
    for idx, block in enumerate(blocks):
        if block["kind"] == "promotion":
            promotion_entries.append(
                {"index": idx, "date": block["date"], "length": len(block["text"])}
            )

    if not promotion_entries:
        return {"compacted": existing_memory, "dropped_dates": []}

    # Sort oldest-first so we drop the oldest sections first.
    promotion_entries.sort(key=lambda e: e["date"])

    dropped_indices: set[int] = set()
    dropped_dates: list[str] = []
    projected_existing_size = len(existing_memory)
    block_separator_cost = 1 if len(blocks) > 1 else 0

    for entry in promotion_entries:
        if projected_existing_size + len(new_section) <= effective_budget:
            break
        projected_existing_size -= entry["length"] + block_separator_cost
        dropped_indices.add(entry["index"])
        dropped_dates.append(entry["date"])

    if not dropped_indices:
        return {"compacted": existing_memory, "dropped_dates": []}

    retained = [b for idx, b in enumerate(blocks) if idx not in dropped_indices]
    return {"compacted": _join_blocks(retained), "dropped_dates": dropped_dates}


__all__ = [
    "DEFAULT_MEMORY_FILE_MAX_CHARS",
    "PROMOTION_SECTION_HEADING_RE",
    "CompactMemoryResult",
    "compact_memory_for_budget",
]
