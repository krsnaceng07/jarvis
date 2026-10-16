"""jarvis.channels.progress_draft — progress-draft line formatting and receipt tracking.

OpenClaw parity: mirrors
``openclaw-main/src/shared/progress-labels.ts``,
``openclaw-main/src/agents/tool-display-config.ts``, and
``openclaw-main/src/channels/progress-draft-compositor.ts``.

Features:
- `TOOL_DISPLAY_CONFIG`: Maps tool names to icons (🛠️, 📖, ✍️, 📝, 🔎, 🌐, 🖱️, 🧩).
- `select_progress_label`: Selects progress label from pool or seed.
- `format_progress_line`: Renders formatted status lines (e.g. ``📖 Read: docs/setup.md``).
- `ChannelProgressReceiptTracker`: Tracks activity counters (thoughts, tool calls, notes, elapsed seconds)
  and builds compact summary receipts (``-# 🧠 2 thoughts · 🛠️ 5 tool calls · ⏱️ 12s``).
- `ChannelProgressDraftCompositor`: Assembles status headlines, labels, and progress lines into final draft text.
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
    """Return the display emoji icon for *tool_name*."""
    if not tool_name or not isinstance(tool_name, str):
        return DEFAULT_TOOL_ICON
    key = tool_name.strip().lower()
    return TOOL_DISPLAY_ICONS.get(key, DEFAULT_TOOL_ICON)


def select_progress_label(
    labels: Sequence[str] | None = None,
    seed: str | None = None,
) -> str | None:
    """Select a progress label from candidate *labels* using optional deterministic *seed*.

    Mirrors ``selectProgressLabel`` (``shared/progress-labels.ts``).
    """
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
    detail_mode: str = "explain",
    max_line_chars: int = 120,
) -> str:
    """Format a single progress draft line.

    Example:
    - ``format_progress_line("read", "docs/setup.md")`` -> ``📖 Read: docs/setup.md``
    - ``format_progress_line("exec", "pytest", detail_mode="raw")`` -> ``🛠️ Exec: pytest``
    """
    icon = get_tool_icon(tool_name)
    title = tool_name.replace("_", " ").title()

    if detail and detail.strip():
        line = f"{icon} {title}: {detail.strip()}"
    else:
        line = f"{icon} {title}"

    if len(line) > max_line_chars:
        line = line[: max_line_chars - 3] + "..."

    return line


class ChannelProgressReceiptTracker:
    """Tracks per-turn activity for compact progress receipts.

    Mirrors ``createChannelProgressReceiptTracker`` (``progress-draft-compositor.ts``).
    """

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
        """Build compact activity summary line.

        Example: ``-# 🧠 2 thoughts · 💬 1 note · 🛠️ 5 tool calls · ⏱️ 12s``
        """
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
    """Stateful progress-draft compositor for channel streaming previews.

    Mirrors ``ChannelProgressDraftCompositor`` (``progress-draft-compositor.ts``).
    """

    label: str | None = "Working"
    status_headline: str | None = None
    lines: list[str] = field(default_factory=list)
    max_lines: int = 8
    max_line_chars: int = 120

    def add_line(self, line: str) -> None:
        """Add a progress line, truncating to max_lines."""
        if line and line.strip():
            self.lines.append(line.strip())
            if len(self.lines) > self.max_lines:
                self.lines = self.lines[-self.max_lines :]

    def render(self) -> str:
        """Render the composite progress draft text."""
        parts: list[str] = []

        if self.status_headline:
            parts.append(self.status_headline.strip())
        elif self.label:
            parts.append(self.label.strip())

        for line in self.lines:
            parts.append(line)

        return "\n".join(parts)


__all__ = [
    "DEFAULT_PROGRESS_DRAFT_LABELS",
    "DEFAULT_TOOL_ICON",
    "TOOL_DISPLAY_ICONS",
    "ChannelProgressDraftCompositor",
    "ChannelProgressReceiptTracker",
    "format_progress_line",
    "get_tool_icon",
    "select_progress_label",
]
