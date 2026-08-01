"""jarvis.agents.sessions.prompt_templates — prompt template loader (stub).

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/prompt-templates.ts``.

Public surface (matches the OpenClaw source):

- :class:`PromptTemplate` — a single
  prompt template.
- :class:`PromptArgument` — a typed
  argument declaration.
- :func:`loadPromptTemplates` — load
  prompt templates from a list of paths.

Phase 6.11b — STUB. Returns an empty
list. The full loader (parse front-matter,
walk the project's ``.jarvis/prompts/``,
dedupe by name) lands in Phase 6.12+.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, TypedDict

from .diagnostics import ResourceDiagnostic


class PromptSourceInfo(TypedDict, total=False):
    """Where a prompt came from. Mirrors the
    ``sourceInfo`` field on
    :class:`PromptTemplate`."""

    path: str
    source: str
    scope: str
    origin: str
    baseDir: Optional[str]


@dataclass
class PromptArgument:
    """A typed argument on a prompt
    template. Mirrors ``PromptArgument``
    (``prompt-templates.ts:5-10``)."""

    name: str
    description: str = ""
    required: bool = False


@dataclass
class PromptTemplate:
    """A single prompt template. Mirrors
    ``PromptTemplate``
    (``prompt-templates.ts:12-30``).

    Attributes
    ----------
    name : str
        Slash command name (e.g.
        ``"review-pr"`` → ``/review-pr``).
    description : str
        Human-readable description.
    file_path : str
        Filesystem path of the prompt file.
    body : str
        Prompt body (markdown).
    arguments : list[PromptArgument]
        Typed argument declarations.
    source_info : PromptSourceInfo | None
        Provenance info; populated by the
        resource loader.
    """

    name: str
    description: str
    file_path: str
    body: str
    arguments: list[PromptArgument] = field(default_factory=list)
    source_info: Optional[PromptSourceInfo] = None


class LoadPromptTemplatesResult(TypedDict, total=False):
    """Result of loading prompt templates.
    Mirrors the return shape of
    ``loadPromptTemplates``
    (``prompt-templates.ts:32-50``)."""

    prompts: list[PromptTemplate]
    diagnostics: list[ResourceDiagnostic]


def loadPromptTemplates(
    cwd: str,
    agent_dir: str,
    prompt_paths: Optional[list[str]] = None,
    include_defaults: bool = True,
) -> LoadPromptTemplatesResult:
    """Load prompt templates from the
    project's ``.jarvis/prompts/`` + the
    supplied ``prompt_paths``. Mirrors
    ``loadPromptTemplates``
    (``prompt-templates.ts:32-50``).

    Phase 6.11b — STUB. Returns an empty
    list.
    """
    return {"prompts": [], "diagnostics": []}


def expandPromptTemplate(
    text: str,
    templates: list[PromptTemplate],
) -> str:
    """Expand a ``/template args`` style
    prompt into the underlying template
    body. Mirrors ``expandPromptTemplate``
    (``prompt-templates.ts:52-90``).

    Phase 6.12c — STUB. The OpenClaw
    source matches the leading ``/``
    command against the supplied
    templates; on a match, it substitutes
    the template body + handles the
    remaining args. The Python port
    returns the text unchanged (the
    matching + substitution lands in
    Phase 6.13).
    """
    return text


__all__ = [
    "LoadPromptTemplatesResult",
    "PromptArgument",
    "PromptSourceInfo",
    "PromptTemplate",
    "expandPromptTemplate",
    "loadPromptTemplates",
]
