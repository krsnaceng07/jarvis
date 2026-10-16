"""Tests for src/channels/progress_draft.py.

Mirrors progress draft tests in OpenClaw.
"""

from __future__ import annotations


from src.channels.progress_draft import (
    ChannelProgressDraftCompositor,
    ChannelProgressReceiptTracker,
    format_progress_line,
    get_tool_icon,
    select_progress_label,
)


def test_get_tool_icon():
    assert get_tool_icon("bash") == "🛠️"
    assert get_tool_icon("exec") == "🛠️"
    assert get_tool_icon("read") == "📖"
    assert get_tool_icon("write") == "✍️"
    assert get_tool_icon("web_search") == "🔎"
    assert get_tool_icon("unknown_tool") == "🧩"


def test_select_progress_label():
    label = select_progress_label()
    assert label == "Working"

    label_seed = select_progress_label(labels=["Checking", "Testing"], seed="my-seed")
    assert label_seed in ("Checking", "Testing")


def test_format_progress_line():
    line = format_progress_line("read", "docs/setup.md")
    assert line == "📖 Read: docs/setup.md"

    line_trunc = format_progress_line("exec", "a" * 150, max_line_chars=20)
    assert len(line_trunc) <= 20
    assert line_trunc.endswith("...")


def test_channel_progress_receipt_tracker():
    t0 = 1000.0
    clock = [t0]

    tracker = ChannelProgressReceiptTracker(now_fn=lambda: clock[0])
    tracker.note_reasoning()
    tracker.note_reasoning()
    tracker.note_tool_call("exec")
    tracker.note_commentary("Looking at file...")

    clock[0] += 5.5  # 5 seconds elapsed
    summary = tracker.build_summary_line()
    assert "-# " in summary
    assert "🧠 2 thoughts" in summary
    assert "💬 1 note" in summary
    assert "🛠️ 1 tool call" in summary
    assert "⏱️ 5s" in summary


def test_channel_progress_draft_compositor():
    comp = ChannelProgressDraftCompositor(label="Working", max_lines=3)
    comp.add_line("📖 Read: file1.py")
    comp.add_line("🛠️ Exec: pytest")
    comp.add_line("✍️ Write: file2.py")
    comp.add_line("📝 Edit: file3.py")  # Evicts first line due to max_lines=3

    rendered = comp.render()
    assert "Working" in rendered
    assert "📖 Read: file1.py" not in rendered
    assert "🛠️ Exec: pytest" in rendered
    assert "✍️ Write: file2.py" in rendered
    assert "📝 Edit: file3.py" in rendered
