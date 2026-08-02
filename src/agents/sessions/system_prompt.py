"""jarvis.agents.sessions.system_prompt — system prompt builder.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/system-prompt.ts``.

Public surface (matches the OpenClaw
source):

- :class:`BuildSystemPromptOptions` —
  options for the system-prompt
  builder.
- :func:`build_system_prompt` —
  build a system prompt with tools,
  guidelines, and context.

Phase 6.13b — focused port.

Adaptations
-----------
- The OpenClaw source's
  :func:`formatSkillsForPrompt` +
  :class:`Skill` come from
  ``@openclaw/skills/loading/session.js``.
  The Python port ships a focused
  minimal :func:`format_skills_for_prompt`
  that emits the same wire format
  (``<skills>...</skills>`` block).
- The OpenClaw source's
  :func:`getReadmePath` +
  :func:`getDocsPath` +
  :func:`getExamplesPath` come
  from :mod:`agents/config.js`. The
  Python port ships a focused
  minimal port that returns
  empty / default paths (the real
  values come from
  ``jarvis_apps/config.py`` in
  6.13+).
- The OpenClaw source's
  :func:`buildPromisedWorkPromptSection`
  comes from
  :mod:`agents/promised-work-prompt.js`.
  The Python port skips the
  promised-work section (the full
  integration lands in 6.13+).
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Optional, TypedDict


_LOG = logging.getLogger("jarvis.agents.sessions.system_prompt")


#: The default list of tools. Mirrors
#: the OpenClaw source's
#: ``["read", "bash", "edit", "write"]``
#: default inside
#: :func:`buildSystemPrompt`
#: (``system-prompt.ts:91``).
DEFAULT_TOOLS: list[str] = [
    "read",
    "bash",
    "edit",
    "write",
]


#: A pre-loaded skill. Mirrors
#: :class:`Skill`
#: (``@openclaw/skills/loading/session.js``).
#: The Python port uses a plain
#: ``dict`` at runtime.
SkillDict = dict


class BuildSystemPromptOptions(TypedDict, total=False):
    """Options for the system-prompt
    builder. Mirrors
    :class:`BuildSystemPromptOptions`
    (``system-prompt.ts:9-26``).

    The Python port uses a TypedDict
    with ``total=False`` so every
    field is optional. The OpenClaw
    source uses an interface with
    optional fields marked ``?``.
    """

    customPrompt: Optional[str]
    selectedTools: Optional[list[str]]
    toolSnippets: Optional[dict]
    promptGuidelines: Optional[list[str]]
    appendSystemPrompt: Optional[str]
    cwd: str
    contextFiles: Optional[list[dict]]
    skills: Optional[list[SkillDict]]


# ============================================================================
# Helpers
# ============================================================================


def _get_readme_path() -> str:
    """Get the absolute path to the
    project README. Mirrors
    :func:`getReadmePath`
    (``agents/config.js``).

    Phase 6.13b — STUB. Returns
    ``""`` (the OpenClaw source uses
    the file to build the system
    prompt's "see also" section)."""
    return ""


def _get_docs_path() -> str:
    """Get the absolute path to the
    docs directory. Mirrors
    :func:`getDocsPath`."""
    return ""


def _get_examples_path() -> str:
    """Get the absolute path to the
    examples directory. Mirrors
    :func:`getExamplesPath`."""
    return ""


def _format_skills_for_prompt(skills: list[SkillDict]) -> str:
    """Format the skills for the system
    prompt. Mirrors
    :func:`formatSkillsForPrompt`
    (``@openclaw/skills/loading/session.js``).

    The OpenClaw source emits an
    XML-style ``<skills>...</skills>``
    block listing the skills. The
    Python port follows the same
    format.

    Returns
    -------
    str
        The formatted skills section
        (empty string when ``skills``
        is empty).
    """
    if not skills:
        return ""
    out: list[str] = ["\nThe following skills are available:"]
    out.append("\n<skills>")
    for skill in skills:
        name = (
            skill.get("name", "")
            if isinstance(skill, dict)
            else getattr(skill, "name", "")
        )
        description = (
            skill.get("description", "")
            if isinstance(skill, dict)
            else getattr(skill, "description", "")
        )
        out.append(f"\n<skill name=\"{name}\">")
        out.append(f"\n{description}")
        out.append("\n</skill>")
    out.append("\n</skills>\n")
    return "".join(out)


def _today_date() -> str:
    """Return today's date in
    ``YYYY-MM-DD`` format. Mirrors the
    OpenClaw source's ``new Date()``
    + ``getFullYear`` / ``getMonth``
    / ``getDate`` block."""
    from datetime import datetime
    now = datetime.now()
    return f"{now.year:04d}-{now.month:02d}-{now.day:02d}"


# ============================================================================
# Public API
# ============================================================================


def build_system_prompt(options: BuildSystemPromptOptions) -> str:
    """Build the system prompt with
    tools, guidelines, and context.
    Mirrors :func:`buildSystemPrompt`
    (``system-prompt.ts:29-182``).

    The function supports two modes:

    1. **Custom prompt** —
       ``options.customPrompt``
       replaces the default; the
       OpenClaw source appends the
       project context files + skills
       + date/cwd to the custom
       prompt.
    2. **Default prompt** — built
       from the tool list + tool
       snippets + guidelines +
       project context + skills +
       date/cwd.

    Parameters
    ----------
    options : BuildSystemPromptOptions
        ``cwd`` is required. Other
        fields are optional.

    Returns
    -------
    str
        The assembled system prompt.
    """
    custom_prompt = options.get("customPrompt")
    selected_tools = options.get("selectedTools")
    tool_snippets = options.get("toolSnippets") or {}
    prompt_guidelines = options.get("promptGuidelines") or []
    append_system_prompt = options.get("appendSystemPrompt")
    cwd = options.get("cwd", "")
    context_files = options.get("contextFiles") or []
    skills = options.get("skills") or []

    # The OpenClaw source's
    # ``resolvedCwd.replace(/\\/g, "/")``
    # — POSIX-style cwd for prompt
    # display.
    prompt_cwd = (cwd or "").replace("\\", "/")

    date_str = _today_date()
    append_section = (
        f"\n\n{append_system_prompt}"
        if append_system_prompt
        else ""
    )

    if custom_prompt:
        prompt = custom_prompt
        if append_section:
            prompt += append_section
        if context_files:
            prompt += "\n\n<project_context>\n\n"
            prompt += "Project-specific instructions and guidelines:\n\n"
            for entry in context_files:
                file_path = entry.get("path", "")
                content = entry.get("content", "")
                prompt += (
                    f'<project_instructions path="{file_path}">\n'
                    f"{content}\n"
                    f"</project_instructions>\n\n"
                )
            prompt += "</project_context>\n"
        # Append skills section (only
        # if read tool is available).
        custom_prompt_has_read = (
            not selected_tools or "read" in selected_tools
        )
        if custom_prompt_has_read and skills:
            prompt += _format_skills_for_prompt(skills)
        # Date + cwd.
        prompt += f"\nCurrent date: {date_str}"
        prompt += f"\nCurrent working directory: {prompt_cwd}"
        return prompt

    # Default mode: build the tool
    # list, guidelines, project
    # context, skills, date + cwd.
    _ = (
        _get_readme_path(),
        _get_docs_path(),
        _get_examples_path(),
    )

    tools = selected_tools or list(DEFAULT_TOOLS)
    visible_tools = [
        name for name in tools if tool_snippets.get(name)
    ]
    if visible_tools:
        tools_list = "\n".join(
            f"- {name}: {tool_snippets[name]}"
            for name in visible_tools
        )
    else:
        tools_list = "(none)"

    # Build guidelines based on which
    # tools are actually available.
    guidelines_list: list[str] = []
    guidelines_set: set = set()
    if "bash" in tools:
        for guideline in (
            "Execute bash commands only when necessary.",
            "Prefer running long-running commands in the background.",
        ):
            if guideline not in guidelines_set:
                guidelines_set.add(guideline)
                guidelines_list.append(guideline)
    if "edit" in tools or "write" in tools:
        for guideline in (
            "When editing files, prefer minimal patches.",
            "Always read the file before editing.",
        ):
            if guideline not in guidelines_set:
                guidelines_set.add(guideline)
                guidelines_list.append(guideline)
    # Append caller-supplied
    # guidelines.
    for guideline in prompt_guidelines:
        if guideline not in guidelines_set:
            guidelines_set.add(guideline)
            guidelines_list.append(guideline)
    guidelines_block = "\n".join(
        f"- {g}" for g in guidelines_list
    ) if guidelines_list else "(none)"

    sections: list[str] = [
        f"You are JARVIS, an AI assistant that helps users with tasks.",
        "",
        f"Current date: {date_str}",
        f"Current working directory: {prompt_cwd}",
        "",
        "# Tone and style",
        "",
        "- Be concise.",
        "- Avoid unnecessary repetition.",
        "",
        "# Available tools",
        "",
        tools_list,
        "",
        "# Guidelines",
        "",
        guidelines_block,
    ]

    if context_files:
        sections.append("")
        sections.append("# Project context")
        sections.append("")
        for entry in context_files:
            file_path = entry.get("path", "")
            content = entry.get("content", "")
            sections.append(
                f'<project_instructions path="{file_path}">'
            )
            sections.append(content)
            sections.append("</project_instructions>")
            sections.append("")

    # Append skills (only if read
    # tool is available).
    has_read = "read" in tools
    if has_read and skills:
        sections.append(_format_skills_for_prompt(skills))

    if append_section:
        sections.append(append_section)

    return "\n".join(sections)


# ============================================================================
# Backwards-compat alias (camelCase
# OpenClaw-style name).
# ============================================================================


buildSystemPrompt = build_system_prompt


__all__ = [
    "DEFAULT_TOOLS",
    "BuildSystemPromptOptions",
    "SkillDict",
    "build_system_prompt",
    "buildSystemPrompt",
]
