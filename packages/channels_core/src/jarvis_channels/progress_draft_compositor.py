"""Channel progress draft compositor — streaming previews, plan steps, diffstat.

Mirrors OpenClaw's:
- ``src/channels/progress-draft-compositor.ts``
- ``src/channels/progress-draft-diffstat.ts``
- ``src/channels/progress-draft-lines.ts``
- ``src/shared/progress-labels.ts``

Features:
- Dynamic tool progress lines with emoji mapping (📖 read, 🛠️ exec, 🔎 search, etc.).
- Plan checklist rendering (``[x] Done``, ``[ ] Todo``, ``⏳ Active``).
- Git diffstat summarization (``+24 -8 lines across 3 files``).
- Compact receipt tracking (``-# 🧠 2 thoughts · 🛠️ 5 tool calls · ⏱️ 12s``).
- Bounded line buffer and quiet mode support.
"""

from __future__ import annotations

import time
import zlib
from dataclasses import dataclass, field
from typing import Any, Sequence

DEFAULT_PROGRESS_DRAFT_LABELS: tuple[str, ...] = ("Working",)

TOOL_DISPLAY_ICONS: dict[str, str] = {
    "bash": "🛠️",
    "exec": "🛠️",
    "read": "📖",
    "write": "✍️",
    "edit": "📝",
    "apply_patch": "📝",
    "web_search": "🔎",
    "web_fetch": "🌐",
    "browser": "🌐",
    "attach": "📎",
    "computer": "🖱️",
    "screen": "🖥️",
    "process": "🧰",
    "sessions": "💬",
    "cron": "⏰",
}

DEFAULT_TOOL_ICON: str = "🧩"


def get_tool_icon(tool_name: str | None) -> str:
    """Return the display emoji icon for a tool name."""
    if not tool_name or not isinstance(tool_name, str):
        return DEFAULT_TOOL_ICON
    key = tool_name.strip().lower()
    return TOOL_DISPLAY_ICONS.get(key, DEFAULT_TOOL_ICON)


def select_progress_label(
    labels: Sequence[str] | None = None,
    seed: str | None = None,
) -> str | None:
    """Select a progress label deterministically from seed or default."""
    effective_labels = list(labels) if labels else list(DEFAULT_PROGRESS_DRAFT_LABELS)
    if not effective_labels:
        return None

    if seed:
        idx = zlib.crc32(seed.encode("utf-8")) % len(effective_labels)
        return effective_labels[idx]

    return effective_labels[0]


def format_progress_line(
    tool_name: str,
    detail: str | None = None,
    *,
    max_line_chars: int = 120,
) -> str:
    """Format a single progress draft line."""
    icon = get_tool_icon(tool_name)
    title = tool_name.replace("_", " ").title()

    if detail and detail.strip():
        line = f"{icon} {title}: {detail.strip()}"
    else:
        line = f"{icon} {title}"

    if len(line) > max_line_chars:
        line = line[: max_line_chars - 3] + "..."

    return line


def format_diffstat(files_changed: int, insertions: int, deletions: int) -> str:
    """Format git-style diffstat summary."""
    parts: list[str] = []
    if insertions > 0:
        parts.append(f"+{insertions}")
    if deletions > 0:
        parts.append(f"-{deletions}")
    stat_str = " ".join(parts) if parts else "+0 -0"
    file_str = "1 file" if files_changed == 1 else f"{files_changed} files"
    return f"`{stat_str}` in {file_str}"


def format_plan_step(step: dict[str, Any]) -> str:
    """Format a plan step for checklist display."""
    status = step.get("status", "pending")
    desc = step.get("description", step.get("title", "")).strip()

    if status in ("completed", "done", "passed"):
        icon = "[x]"
    elif status in ("in_progress", "running", "active"):
        icon = "⏳"
    elif status in ("failed", "error"):
        icon = "[!]"
    else:
        icon = "[ ]"

    return f"{icon} {desc}"


class ChannelProgressReceiptTracker:
    """Tracks turn activity counters for compact summary receipts."""

    def __init__(self, now_fn: Any = None) -> None:
        self._now_fn = now_fn or time.time
        self.started_at: float = self._now_fn()
        self.reasoning_steps: int = 0
        self.tool_calls: int = 0
        self.commentary_notes: int = 0

    def note_reasoning(self) -> None:
        self.reasoning_steps += 1

    def note_tool_call(self, tool_name: str | None = None) -> None:
        self.tool_calls += 1

    def note_commentary(self, text: str | None = None) -> None:
        if text and text.strip():
            self.commentary_notes += 1

    def reset(self) -> None:
        self.started_at = self._now_fn()
        self.reasoning_steps = 0
        self.tool_calls = 0
        self.commentary_notes = 0

    def build_summary_line(self) -> str:
        """Build compact activity summary line (e.g. -# 🧠 2 thoughts · 🛠️ 5 tool calls · ⏱️ 12s)."""
        elapsed_sec = max(1, int(self._now_fn() - self.started_at))
        parts: list[str] = []

        if self.reasoning_steps > 0:
            s = "s" if self.reasoning_steps != 1 else ""
            parts.append(f"🧠 {self.reasoning_steps} thought{s}")

        if self.commentary_notes > 0:
            s = "s" if self.commentary_notes != 1 else ""
            parts.append(f"💬 {self.commentary_notes} note{s}")

        if self.tool_calls > 0:
            s = "s" if self.tool_calls != 1 else ""
            parts.append(f"🛠️ {self.tool_calls} tool call{s}")

        parts.append(f"⏱️ {elapsed_sec}s")
        return "-# " + " · ".join(parts)


@dataclass
class ChannelProgressDraftCompositor:
    """Stateful progress-draft compositor for channel streaming previews."""

    label: str | None = "Working"
    status_headline: str | None = None
    lines: list[str] = field(default_factory=list)
    plan_steps: list[str] = field(default_factory=list)
    diffstat: str | None = None
    max_lines: int = 8
    max_line_chars: int = 120
    quiet: bool = False

    def add_line(self, line: str) -> None:
        """Add a progress line, bounded by max_lines."""
        if line and line.strip():
            self.lines.append(line.strip())
            if len(self.lines) > self.max_lines:
                self.lines = self.lines[-self.max_lines :]

    def set_plan_steps(self, steps: Sequence[dict[str, Any]]) -> None:
        """Set plan checklist steps."""
        self.plan_steps = [format_plan_step(s) for s in steps if s]

    def set_diffstat(self, files_changed: int, insertions: int, deletions: int) -> None:
        """Set diffstat summary line."""
        self.diffstat = format_diffstat(files_changed, insertions, deletions)

    def render(self) -> str:
        """Render composite draft markdown text."""
        if self.quiet:
            return self.status_headline or self.label or ""

        parts: list[str] = []

        if self.status_headline:
            parts.append(self.status_headline.strip())
        elif self.label:
            parts.append(self.label.strip())

        if self.plan_steps:
            parts.append("\n".join(self.plan_steps))

        if self.lines:
            parts.append("\n".join(self.lines))

        if self.diffstat:
            parts.append(f"Changes: {self.diffstat}")

        return "\n\n".join(p for p in parts if p.strip())


__all__ = [
    "DEFAULT_PROGRESS_DRAFT_LABELS",
    "DEFAULT_TOOL_ICON",
    "TOOL_DISPLAY_ICONS",
    "ChannelProgressDraftCompositor",
    "ChannelProgressReceiptTracker",
    "format_diffstat",
    "format_plan_step",
    "format_progress_line",
    "get_tool_icon",
    "select_progress_label",
]
