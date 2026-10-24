"""System-prompt tool list — generated from the admitted surface.

OpenClaw parity: mirrors ``openclaw-main/src/agents/system-prompt-tool-list.ts``.

The live prompts used to carry hand-written capability prose that drifted from
the real inventory (it advertised ``youtube_*`` and ``mkdir`` tools that are not
declared). The list below is derived from the same ``ToolSurface`` that supplies
the provider declarations, so prompt and schema cannot disagree.
"""

from __future__ import annotations

from typing import Iterable

from .tools_effective_inventory import ToolEntry, ToolSurface

#: Stable core ordering plus one-line summaries (OpenClaw core order, JARVIS ids).
CORE_TOOL_SUMMARIES: dict[str, str] = {
    "read": "Read files",
    "write": "Write files",
    "edit": "Exact file edits",
    "apply_patch": "Patch files",
    "grep": "Search file contents",
    "find": "Find files by glob",
    "ls": "List directories",
    "exec": "Run shell commands on the host PC",
    "process": "Control background processes",
    "web_search": "Web search",
    "web_fetch": "Fetch/extract a URL",
    "browser": "Control the browser (navigate, search, click, type, YouTube)",
    "screen": "Drive the operator web UI",
    "computer": "Mouse, keyboard, and window control on the desktop",
    "pdf": "Read or create PDF documents",
    "automations": "Schedule reminders and wake-ups",
    "message": "Message/channel actions",
    "conversations_list": "List external conversation addresses",
    "conversations_send": "Send to an external conversation",
    "conversations_turn": "Send and wait for one external reply",
    "sessions_list": "List visible sessions",
    "sessions_history": "Read session/subagent history",
    "sessions_search": "Search past sessions",
    "sessions_send": "Message another session/subagent",
    "sessions_spawn": "Spawn a subagent",
    "sessions_yield": "End turn and await subagent events",
    "subagents": "Subagent status",
    "session_status": "Session/model/usage/status",
    "skill_workshop": "Author reusable skills",
    "view_image": "Inspect an image",
    "image_generate": "Generate/edit images",
    "video_generate": "Generate video",
    "music_generate": "Generate music",
    "tts": "Text to speech",
    "stt": "Speech to text",
    "save_memory": "Save a durable fact to long-term memory",
    "recall_memory": "Search long-term memory",
    "memory_search": "Search memory records",
    "shutdown_jarvis": "Shut JARVIS down (explicit user command only)",
    "standby_jarvis": "Enter standby (explicit user command only)",
}


def _summary_for(entry: ToolEntry) -> str:
    summary = CORE_TOOL_SUMMARIES.get(entry.name)
    if summary:
        return summary
    first_line = entry.description.strip().split("\n")[0].strip()
    if not first_line:
        return ""
    return first_line[:120]


def build_prompt_tool_lines(surface: ToolSurface) -> list[str]:
    """Render ``- name: summary`` lines in stable core order, then extras."""
    available = {entry.name: entry for entry in surface.entries}
    ordered: list[str] = [name for name in CORE_TOOL_SUMMARIES if name in available]
    ordered.extend(sorted(name for name in available if name not in CORE_TOOL_SUMMARIES))
    lines: list[str] = []
    for name in ordered:
        summary = _summary_for(available[name])
        lines.append(f"- {name}: {summary}" if summary else f"- {name}")
    return lines


def build_tooling_section(surface: ToolSurface, *, include_guidance: bool = True) -> str:
    """Build the ``## Tooling`` prompt block for an admitted surface."""
    if not include_guidance:
        return ""
    lines = build_prompt_tool_lines(surface)
    body = "\n".join(lines) if lines else "- (no tools are available in this surface)"
    return (
        "## Tooling\n"
        "Tools are policy-filtered. Names are case-sensitive; call the exact name.\n"
        f"{body}\n"
        "Prefer the dedicated tool over shell when one exists. Call tools in the same turn "
        "as the request; never state that an action happened unless a tool result in this "
        "turn reports success."
    )


def iter_tool_lines(entries: Iterable[ToolEntry]) -> list[str]:
    """Render lines from already-filtered entries (helper for tests/tools)."""
    return build_prompt_tool_lines(ToolSurface({entry.name: entry for entry in entries}))


__all__ = [
    "CORE_TOOL_SUMMARIES",
    "build_prompt_tool_lines",
    "build_tooling_section",
    "iter_tool_lines",
]
