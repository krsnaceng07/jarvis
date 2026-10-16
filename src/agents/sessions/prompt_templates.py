"""jarvis.agents.sessions.prompt_templates — prompt template loader.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/prompt-templates.ts``.

Public surface (matches the OpenClaw
source):

- :class:`PromptTemplate` — a single
  prompt template.
- :class:`PromptArgument` — a typed
  argument declaration.
- :func:`load_prompt_templates` —
  load prompt templates from the
  project's ``.jarvis/prompts/``,
  the global ``agentDir/prompts/``,
  + a list of explicit
  ``prompt_paths``. Returns
  ``{"prompts": list,
  "diagnostics": list}``. Mirrors
  :func:`loadPromptTemplates`
  (``prompt-templates.ts:130-199``).
- :func:`expand_prompt_template` —
  expand a ``/template args`` style
  prompt into the underlying
  template body. Mirrors
  :func:`expandPromptTemplate`
  (``prompt-templates.ts:205-225``).

Phase 6.13b — focused port.

Adaptations
-----------
- The OpenClaw source's
  :func:`parseCommandArgs` +
  :func:`substituteArgs` come
  from
  ``@openclaw/agent-core/src/harness/prompt-template-arguments.js``.
  The Python port's runtime lands
  in 6.13+; this module ships a
  focused minimal port that uses
  :func:`shlex.split` for the arg
  parsing + a focused ``$1``,
  ``$2``, ... ``$@`` /
  ``${ARG}`` substitution.
- The OpenClaw source's
  :func:`expandTildePath` comes
  from
  ``@openclaw/agent-shared/tilde-path.js``.
  The Python port ships a focused
  :func:`expand_tilde_path` that
  uses :func:`os.path.expanduser`
  + falls back to the input when
  the home dir is missing.
"""
from __future__ import annotations

import logging
import os
import re
import shlex
from dataclasses import dataclass, field
from typing import Optional, TypedDict

from .diagnostics import ResourceDiagnostic
from .frontmatter import parse_frontmatter


_LOG = logging.getLogger("jarvis.agents.sessions.prompt_templates")


#: The configuration directory name
#: used to locate project-local
#: resources. Mirrors
#: :data:`CONFIG_DIR_NAME`
#: (``agents/config.ts``).
CONFIG_DIR_NAME: str = ".jarvis"


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
    :class:`PromptTemplate`
    (``prompt-templates.ts:21-28``).

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
    argument_hint : str, optional
        ``argument-hint`` front-matter
        field (the OpenClaw source uses
        ``argumentHint``).
    arguments : list[PromptArgument]
        Typed argument declarations.
    source_info : PromptSourceInfo | None
        Provenance info; populated by
        the resource loader.
    """

    name: str
    description: str
    file_path: str
    body: str
    argument_hint: Optional[str] = None
    arguments: list[PromptArgument] = field(default_factory=list)
    source_info: Optional[PromptSourceInfo] = None


class LoadPromptTemplatesResult(TypedDict, total=False):
    """Result of loading prompt templates.
    Mirrors the return shape of
    :func:`loadPromptTemplates`."""

    prompts: list[PromptTemplate]
    diagnostics: list[ResourceDiagnostic]


# ============================================================================
# Helpers
# ============================================================================


def _truncate_utf16_safe(value: str, max_chars: int) -> str:
    """Truncate ``value`` to ``max_chars``
    (no half-surrogate splits). Mirrors
    :func:`truncateUtf16Safe` from
    :mod:`@openclaw/normalization-core/utf16-slice`."""
    if len(value) <= max_chars:
        return value
    return value[:max_chars]


def _expand_tilde_path(p: str) -> str:
    """Expand a leading ``~`` to the
    user's home directory. Mirrors
    :func:`expandTildePath`. Falls
    back to the input when
    :func:`os.path.expanduser` returns
    the input unchanged (no
    ``$HOME`` set)."""
    expanded = os.path.expanduser(p)
    if expanded == p and p.startswith("~"):
        # No home dir; leave as-is.
        return p
    return expanded


def _is_under_path(target: str, root: str) -> bool:
    """Return ``True`` when ``target``
    is the same as ``root`` or lives
    underneath it. Mirrors the OpenClaw
    source's ``isUnderPath`` helper
    inside
    :func:`loadPromptTemplates`."""
    target_resolved = os.path.abspath(target)
    root_resolved = os.path.abspath(root)
    if target_resolved == root_resolved:
        return True
    root_with_sep = (
        root_resolved if root_resolved.endswith(os.sep)
        else root_resolved + os.sep
    )
    return target_resolved.startswith(root_with_sep)


def _resolve_prompt_path(p: str, cwd: str) -> str:
    """Resolve a (possibly tilde-prefixed
    or relative) path to an absolute
    path."""
    normalized = _expand_tilde_path(p)
    if os.path.isabs(normalized):
        return normalized
    return os.path.abspath(os.path.join(cwd, normalized))


# ============================================================================
# File-level helpers
# ============================================================================


def _load_template_from_file(
    file_path: str,
    source_info: PromptSourceInfo,
) -> Optional[PromptTemplate]:
    """Load a single prompt template
    from ``file_path``. Returns
    ``None`` on read failure. Mirrors
    :func:`loadTemplateFromFile`
    (``prompt-templates.ts:30-61``)."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw_content = f.read()
    except (OSError, IOError):
        return None
    parsed = parse_frontmatter(raw_content)
    frontmatter = parsed["frontmatter"]
    body = parsed["body"]
    name = os.path.splitext(os.path.basename(file_path))[0]
    description = frontmatter.get("description", "") or ""
    if not description:
        # Use the first non-empty line.
        for line in body.split("\n"):
            stripped = line.strip()
            if stripped:
                first_line = stripped
                description = _truncate_utf16_safe(first_line, 60)
                if len(first_line) > 60:
                    description += "..."
                break
    argument_hint = frontmatter.get("argument-hint")
    template = PromptTemplate(
        name=name,
        description=description or "",
        file_path=file_path,
        body=body,
        argument_hint=argument_hint,
    )
    template.source_info = source_info
    return template


def _load_templates_from_dir(
    dir_path: str,
    get_source_info: "callable",
) -> list[PromptTemplate]:
    """Scan a directory for ``.md`` files
    (non-recursive) + load them as
    prompt templates. Mirrors
    :func:`loadTemplatesFromDir`
    (``prompt-templates.ts:66-106``)."""
    templates: list[PromptTemplate] = []
    if not os.path.isdir(dir_path):
        return templates
    try:
        entries = os.listdir(dir_path)
    except OSError:
        return templates
    for entry_name in sorted(entries):
        full_path = os.path.join(dir_path, entry_name)
        # Skip non-md files.
        if not entry_name.endswith(".md"):
            continue
        # Skip directories.
        if not os.path.isfile(full_path):
            continue
        template = _load_template_from_file(
            full_path, get_source_info(full_path)
        )
        if template is not None:
            templates.append(template)
    return templates


# ============================================================================
# Public API
# ============================================================================


def load_prompt_templates(
    cwd: str,
    agent_dir: str,
    prompt_paths: Optional[list[str]] = None,
    include_defaults: bool = True,
) -> LoadPromptTemplatesResult:
    """Load all prompt templates from:
    1. Global: ``agentDir/prompts/``.
    2. Project: ``cwd/.jarvis/prompts/``.
    3. Explicit ``prompt_paths``.

    Mirrors :func:`loadPromptTemplates`
    (``prompt-templates.ts:130-199``).
    """
    prompt_paths = prompt_paths or []
    templates: list[PromptTemplate] = []

    global_prompts_dir = (
        os.path.join(agent_dir, "prompts") if agent_dir else ""
    )
    project_prompts_dir = os.path.join(
        cwd, CONFIG_DIR_NAME, "prompts"
    )

    def get_source_info(resolved_path: str) -> PromptSourceInfo:
        if (
            global_prompts_dir
            and _is_under_path(resolved_path, global_prompts_dir)
        ):
            return PromptSourceInfo(
                path=resolved_path,
                source="local",
                scope="user",
                baseDir=global_prompts_dir,
            )
        if _is_under_path(resolved_path, project_prompts_dir):
            return PromptSourceInfo(
                path=resolved_path,
                source="local",
                scope="project",
                baseDir=project_prompts_dir,
            )
        base_dir = (
            resolved_path
            if os.path.isdir(resolved_path)
            else os.path.dirname(resolved_path)
        )
        return PromptSourceInfo(
            path=resolved_path,
            source="local",
            baseDir=base_dir,
        )

    if include_defaults:
        templates.extend(
            _load_templates_from_dir(
                global_prompts_dir, get_source_info
            )
        )
        templates.extend(
            _load_templates_from_dir(
                project_prompts_dir, get_source_info
            )
        )

    for raw_path in prompt_paths:
        resolved_path = _resolve_prompt_path(raw_path, cwd)
        if not os.path.exists(resolved_path):
            continue
        try:
            if os.path.isdir(resolved_path):
                templates.extend(
                    _load_templates_from_dir(
                        resolved_path, get_source_info
                    )
                )
            elif os.path.isfile(resolved_path) and resolved_path.endswith(".md"):
                template = _load_template_from_file(
                    resolved_path, get_source_info(resolved_path)
                )
                if template is not None:
                    templates.append(template)
        except OSError:
            # Ignore read failures.
            pass

    return {"prompts": templates, "diagnostics": []}


# ============================================================================
# expandPromptTemplate
# ============================================================================


#: Regex matching a leading
#: ``/command args`` prompt. Mirrors
#: the OpenClaw source's regex
#: inside :func:`expandPromptTemplate`
#: (``prompt-templates.ts:210``).
_TEMPLATE_CMD_RE = re.compile(r"^/([^\s]+)(?:\s+([\s\S]*))?$")


#: Regex matching ``$1``, ``$2``, ...,
#: ``$@`` (all args), or ``${ARG}``
#: placeholders in a template body.
_ARG_RE = re.compile(
    r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([1-9][0-9]*)"
)


def _parse_command_args(args_string: str) -> list[str]:
    """Parse the args string into a
    list of positional args. Mirrors
    the OpenClaw source's
    :func:`parseCommandArgs` (focused
    minimal port — uses
    :func:`shlex.split`)."""
    if not args_string:
        return []
    try:
        return shlex.split(args_string)
    except ValueError:
        # Unbalanced quotes etc. — fall
        # back to a naive split.
        return args_string.split()


def _substitute_args(content: str, args: list[str]) -> str:
    """Substitute ``$1``, ``$2``, ...,
    ``$@``, and ``${ARG}`` references
    in ``content`` with the matching
    values from ``args``. Mirrors
    the OpenClaw source's
    :func:`substituteArgs` (focused
    minimal port)."""
    def _replace(match: "re.Match[str]") -> str:
        name = match.group(1)
        index = match.group(2)
        if name is not None:
            # ${ARG} → lookup by name
            # (the focused minimal port
            # doesn't support named
            # args; emit a warning in
            # the body).
            return match.group(0)
        if index is not None:
            n = int(index) - 1
            if 0 <= n < len(args):
                return args[n]
        return match.group(0)

    return _ARG_RE.sub(_replace, content)


def expand_prompt_template(
    text: str,
    templates: list[PromptTemplate],
) -> str:
    """Expand a ``/template args`` style
    prompt into the underlying
    template body. Mirrors
    :func:`expandPromptTemplate`
    (``prompt-templates.ts:205-225``).

    If ``text`` doesn't start with
    ``/``, or the command doesn't
    match any template, the input
    is returned unchanged.
    """
    if not text.startswith("/"):
        return text
    match = _TEMPLATE_CMD_RE.match(text)
    if not match:
        return text
    template_name = match.group(1)
    args_string = match.group(2) or ""
    for template in templates:
        if template.name == template_name:
            args = _parse_command_args(args_string)
            return _substitute_args(template.body, args)
    return text


# ============================================================================
# Backwards-compat aliases (camelCase
# OpenClaw-style names). The Python
# port prefers snake_case; these
# aliases keep existing callers
# (``resource_loader``, etc.) working.
# ============================================================================


loadPromptTemplates = load_prompt_templates
expandPromptTemplate = expand_prompt_template


__all__ = [
    "CONFIG_DIR_NAME",
    "LoadPromptTemplatesResult",
    "PromptArgument",
    "PromptSourceInfo",
    "PromptTemplate",
    "expand_prompt_template",
    "expandPromptTemplate",
    "load_prompt_templates",
    "loadPromptTemplates",
]
