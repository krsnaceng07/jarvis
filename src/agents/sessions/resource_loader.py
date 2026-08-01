"""jarvis.agents.sessions.resource_loader — top-level session resource loader.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/resource-loader.ts``.

Ships the public surface:

- :class:`ResourceLoader` Protocol —
  the read-only interface the rest of
  the session uses.
- :class:`DefaultResourceLoader` — the
  default implementation. Resolves
  extension / skill / prompt / theme
  sources via :class:`DefaultPackageManager`
  + loads ``AGENTS.md`` ancestor files
  + resolves the system prompt
  (``SYSTEM.md`` + ``APPEND_SYSTEM.md``).

Sub-loaders (Phase 6.11b stubs):

- :func:`loadSkills` (``skills_loader``)
- :func:`loadPromptTemplates` (``prompt_templates``)
- :func:`loadThemeFromPath` (``theme_loader``)

Phase 6.11b — focused port.

Adaptations
-----------
- The OpenClaw source uses ``chalk`` for
  warning output. The Python port uses
  :mod:`logging` (Python convention).
- The OpenClaw source walks the project
  tree to discover ``.git`` repos. The
  Python port uses the same walk but
  bounds it to ``os.path.realpath`` to
  handle symlinks on Windows.
- The OpenClaw source uses ``fs.existsSync`` /
  ``fs.readFileSync``. The Python port uses
  :func:`os.path.isfile` +
  :func:`pathlib.Path.read_text`.
- The OpenClaw source attaches a
  ``sourceInfo`` to every loaded skill /
  prompt / theme. The Python port preserves
  the same shape but uses a
  :class:`TypedDict` instead of an
  inline object literal.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import (
    Awaitable,
    Optional,
    Protocol,
    TypedDict,
    runtime_checkable,
)

from .diagnostics import ResourceDiagnostic
from .event_bus import EventBus, create_event_bus
from .extensions.loader import (
    clear_extension_cache,
    create_extension_runtime,
    load_extension_from_factory,
    load_extensions_cached,
)
from .extensions.types import (
    Extension,
    ExtensionFactory,
    LoadExtensionsError,
    LoadExtensionsResult,
)
from .package_manager import DefaultPackageManager
from .prompt_templates import (
    LoadPromptTemplatesResult,
    PromptTemplate,
    loadPromptTemplates,
)
from .settings_manager import SettingsManager
from .skills_loader import LoadSkillsResult, Skill, loadSkills
from .theme_loader import Theme, loadThemeFromPath


_LOG = logging.getLogger("jarvis.agents.sessions.resource_loader")

#: The config dir name (project-side). Mirrors
#: ``CONFIG_DIR_NAME`` (``package-manager.ts:91``).
CONFIG_DIR_NAME = ".jarvis"

#: Candidate filenames for the project
#: ``AGENTS.md``-style context file. Mirrors
#: ``loadContextFileFromDir``
#: (``resource-loader.ts:72-88``).
_CONTEXT_FILE_CANDIDATES: tuple[str, ...] = (
    "AGENTS.md",
    "AGENTS.MD",
    "CLAUDE.md",
    "CLAUDE.MD",
)


# ============================================================================
# Public types
# ============================================================================


class ResourceExtensionPaths(TypedDict, total=False):
    """Resources added at runtime by
    extensions. Mirrors
    ``ResourceExtensionPaths``
    (``resource-loader.ts:35-39``)."""

    skillPaths: list[dict]  # [{"path": str, "metadata": PathMetadata}]
    promptPaths: list[dict]
    themePaths: list[dict]


@dataclass
class AgentsFile:
    """A single ``AGENTS.md`` context file.
    Mirrors the inline ``{ path, content }``
    shape in the OpenClaw source."""

    path: str
    content: str


#: Per-resource getter shape. The OpenClaw
#: source uses inline
#: ``{ skills, diagnostics }`` objects; the
#: Python port uses TypedDict for parity.
class _SkillsResult(TypedDict, total=False):
    skills: list[Skill]
    diagnostics: list[ResourceDiagnostic]


class _PromptsResult(TypedDict, total=False):
    prompts: list[PromptTemplate]
    diagnostics: list[ResourceDiagnostic]


class _ThemesResult(TypedDict, total=False):
    themes: list[Theme]
    diagnostics: list[ResourceDiagnostic]


class _AgentsFilesResult(TypedDict, total=False):
    agentsFiles: list[AgentsFile]


@runtime_checkable
class ResourceLoader(Protocol):
    """Read-only view over the loaded session
    resources. Mirrors ``ResourceLoader``
    (``resource-loader.ts:41-51``)."""

    def get_extensions(self) -> LoadExtensionsResult: ...
    def get_skills(self) -> _SkillsResult: ...
    def get_prompts(self) -> _PromptsResult: ...
    def get_themes(self) -> _ThemesResult: ...
    def get_agents_files(self) -> _AgentsFilesResult: ...
    def get_system_prompt(self) -> Optional[str]: ...
    def get_append_system_prompt(self) -> list[str]: ...
    def extend_resources(self, paths: ResourceExtensionPaths) -> None: ...
    def reload(self) -> Awaitable[None]: ...


# ============================================================================
# DefaultResourceLoaderOptions
# ============================================================================


@dataclass
class DefaultResourceLoaderOptions:
    """Constructor options for
    :class:`DefaultResourceLoader`. Mirrors
    ``DefaultResourceLoaderOptions``
    (``resource-loader.ts:134-169``)."""

    cwd: str
    agent_dir: str
    settings_manager: Optional[SettingsManager] = None
    event_bus: Optional[EventBus] = None
    additional_extension_paths: list[str] = field(default_factory=list)
    additional_skill_paths: list[str] = field(default_factory=list)
    additional_prompt_template_paths: list[str] = field(default_factory=list)
    additional_theme_paths: list[str] = field(default_factory=list)
    extension_factories: list[ExtensionFactory] = field(default_factory=list)
    no_extensions: bool = False
    no_skills: bool = False
    no_prompt_templates: bool = False
    no_themes: bool = False
    no_context_files: bool = False
    system_prompt: Optional[str] = None
    append_system_prompt: Optional[list[str]] = None


# ============================================================================
# DefaultResourceLoader
# ============================================================================


class DefaultResourceLoader:
    """The default :class:`ResourceLoader`
    implementation. Mirrors
    ``DefaultResourceLoader``
    (``resource-loader.ts:171-1036``).

    Phase 6.11b port — focuses on the public
    surface (constructor, getters,
    ``reload``, ``extendResources``) +
    self-contained helpers (AGENTS.md
    walking + system-prompt discovery).
    The skills / prompts / themes
    sub-loaders are stubbed (return empty
    lists) until Phase 6.12+ lands the full
    parsers.
    """

    def __init__(self, options: DefaultResourceLoaderOptions) -> None:
        self.cwd: str = options.cwd
        self.agent_dir: str = options.agent_dir
        self.settings_manager: SettingsManager = (
            options.settings_manager
            or SettingsManager.create(self.cwd, self.agent_dir)
        )
        self.event_bus: EventBus = options.event_bus or create_event_bus()
        self.package_manager: DefaultPackageManager = DefaultPackageManager(
            cwd=self.cwd,
            agent_dir=self.agent_dir,
            settings_manager=self.settings_manager,
        )
        self.additional_extension_paths: list[str] = list(
            options.additional_extension_paths
        )
        self.additional_skill_paths: list[str] = list(
            options.additional_skill_paths
        )
        self.additional_prompt_template_paths: list[str] = list(
            options.additional_prompt_template_paths
        )
        self.additional_theme_paths: list[str] = list(
            options.additional_theme_paths
        )
        self.extension_factories: list[ExtensionFactory] = list(
            options.extension_factories
        )
        self.no_extensions: bool = options.no_extensions
        self.no_skills: bool = options.no_skills
        self.no_prompt_templates: bool = options.no_prompt_templates
        self.no_themes: bool = options.no_themes
        self.no_context_files: bool = options.no_context_files
        self.system_prompt_source: Optional[str] = options.system_prompt
        self.append_system_prompt_source: Optional[list[str]] = (
            options.append_system_prompt
        )
        # Cached load results (set by reload()).
        self._extensions_result: LoadExtensionsResult = LoadExtensionsResult(
            extensions=[],
            errors=[],
            runtime=create_extension_runtime(),
        )
        self._skills: list[Skill] = []
        self._skill_diagnostics: list[ResourceDiagnostic] = []
        self._prompts: list[PromptTemplate] = []
        self._prompt_diagnostics: list[ResourceDiagnostic] = []
        self._themes: list[Theme] = []
        self._theme_diagnostics: list[ResourceDiagnostic] = []
        self._agents_files: list[AgentsFile] = []
        self._system_prompt: Optional[str] = None
        self._append_system_prompt: list[str] = []
        self._loaded: bool = False

    # ------------------------------------------------------------------
    # Getters
    # ------------------------------------------------------------------

    def get_extensions(self) -> LoadExtensionsResult:
        """Return the loaded extensions
        result. Mirrors ``getExtensions``
        (``resource-loader.ts:279-281``)."""
        return self._extensions_result

    def get_skills(self) -> _SkillsResult:
        """Return the loaded skills +
        diagnostics. Mirrors ``getSkills``
        (``resource-loader.ts:283-285``)."""
        return {
            "skills": list(self._skills),
            "diagnostics": list(self._skill_diagnostics),
        }

    def get_prompts(self) -> _PromptsResult:
        """Return the loaded prompt templates
        + diagnostics. Mirrors ``getPrompts``
        (``resource-loader.ts:287-289``)."""
        return {
            "prompts": list(self._prompts),
            "diagnostics": list(self._prompt_diagnostics),
        }

    def get_themes(self) -> _ThemesResult:
        """Return the loaded themes +
        diagnostics. Mirrors ``getThemes``
        (``resource-loader.ts:291-293``)."""
        return {
            "themes": list(self._themes),
            "diagnostics": list(self._theme_diagnostics),
        }

    def get_agents_files(self) -> _AgentsFilesResult:
        """Return the discovered
        ``AGENTS.md`` files (cwd + agent dir +
        ancestors). Mirrors ``getAgentsFiles``
        (``resource-loader.ts:295-297``)."""
        return {"agentsFiles": list(self._agents_files)}

    def get_system_prompt(self) -> Optional[str]:
        """Return the system prompt body (or
        ``None`` when not configured).
        Mirrors ``getSystemPrompt``
        (``resource-loader.ts:299-301``)."""
        return self._system_prompt

    def get_append_system_prompt(self) -> list[str]:
        """Return the append-system-prompt
        fragments. Mirrors
        ``getAppendSystemPrompt``
        (``resource-loader.ts:303-305``)."""
        return list(self._append_system_prompt)

    # ------------------------------------------------------------------
    # extendResources
    # ------------------------------------------------------------------

    def extend_resources(self, paths: ResourceExtensionPaths) -> None:
        """Add extension-provided resources
        at runtime. Mirrors ``extendResources``
        (``resource-loader.ts:307-345``).

        Phase 6.11b — focused port: stores
        the entries but does NOT trigger a
        re-load (the full OpenClaw behaviour
        re-derives the skill / prompt / theme
        lists). The next call to
        :meth:`reload` picks the new paths
        up via ``additional_*_paths`` +
        through the package manager.
        """
        for entry in paths.get("skillPaths", []) or []:
            resolved = self._resolve_resource_path(entry["path"])
            self.additional_skill_paths.append(resolved)
        for entry in paths.get("promptPaths", []) or []:
            resolved = self._resolve_resource_path(entry["path"])
            self.additional_prompt_template_paths.append(resolved)
        for entry in paths.get("themePaths", []) or []:
            resolved = self._resolve_resource_path(entry["path"])
            self.additional_theme_paths.append(resolved)

    # ------------------------------------------------------------------
    # reload
    # ------------------------------------------------------------------

    async def reload(self) -> None:
        """Reload every resource from disk.
        Mirrors ``reload``
        (``resource-loader.ts:347-531``).

        Phase 6.11b — focused port:
        - clears the extension cache
        - reloads the settings manager
        - calls ``packageManager.resolve()``
        - loads extensions via
          :func:`loadExtensionsCached`
        - calls the (stub) skills /
          prompts / themes loaders
        - loads ``AGENTS.md`` files
        - resolves the system prompt
        """
        if self._loaded:
            clear_extension_cache()
        await self.settings_manager.reload()
        resolved_paths = await self.package_manager.resolve()

        # ---- Extensions ----
        cli_extension_paths = await self.package_manager.resolve_extension_sources(
            self.additional_extension_paths,
            {"temporary": True},
        )
        enabled_extension_paths = [
            r.path for r in resolved_paths.extensions if r.enabled
        ]
        cli_enabled_extensions = [
            r.path for r in cli_extension_paths.extensions if r.enabled
        ]
        extension_paths = (
            cli_enabled_extensions
            if self.no_extensions
            else self._merge_paths(cli_enabled_extensions, enabled_extension_paths)
        )
        extensions_result = await load_extensions_cached(
            extension_paths, self.cwd, self.event_bus
        )
        # Inline factory extensions.
        for index, factory in enumerate(self.extension_factories):
            extension_path = f"<inline:{index + 1}>"
            try:
                extension = await load_extension_from_factory(
                    factory,
                    self.cwd,
                    self.event_bus,
                    extensions_result.runtime,
                    extension_path,
                )
                extensions_result.extensions.append(extension)
            except Exception as exc:  # noqa: BLE001 — load errors are typed.
                extensions_result.errors.append(
                    {
                        "path": extension_path,
                        "error": str(exc),
                    }
                )
        # Conflict detection.
        for conflict in self._detect_extension_conflicts(extensions_result.extensions):
            extensions_result.errors.append(conflict)
        self._extensions_result = extensions_result

        # ---- Skills (stub loader) ----
        if self.no_skills:
            cli_enabled_skills = [
                r.path for r in cli_extension_paths.skills if r.enabled
            ]
            skill_paths = self._merge_paths(
                cli_enabled_skills, self.additional_skill_paths
            )
        else:
            enabled_skills: list[str] = []
            for r in resolved_paths.skills:
                if not r.enabled:
                    continue
                # Map auto-discovered skill dirs to
                # their SKILL.md (mirrors
                # ``mapSkillPath`` at
                # ``resource-loader.ts:385-405``).
                if r.metadata.source == "auto" or r.metadata.origin == "package":
                    if os.path.isdir(r.path):
                        skill_md = os.path.join(r.path, "SKILL.md")
                        if os.path.isfile(skill_md):
                            enabled_skills.append(skill_md)
                            continue
                enabled_skills.append(r.path)
            cli_enabled_skills = [
                r.path for r in cli_extension_paths.skills if r.enabled
            ]
            skill_paths = self._merge_paths(
                [*cli_enabled_skills, *enabled_skills],
                self.additional_skill_paths,
            )
        skills_result: LoadSkillsResult = loadSkills(
            cwd=self.cwd,
            agent_dir=self.agent_dir,
            skill_paths=skill_paths,
            include_defaults=False,
        )
        self._skills = list(skills_result["skills"])
        self._skill_diagnostics = list(skills_result["diagnostics"])
        # Surface missing additional skill paths.
        for p in self.additional_skill_paths:
            if not os.path.isfile(p) and not any(
                d.path == p for d in self._skill_diagnostics
            ):
                self._skill_diagnostics.append(
                    ResourceDiagnostic(
                        type="error",
                        message="Skill path does not exist",
                        path=p,
                    )
                )

        # ---- Prompts (stub loader) ----
        if self.no_prompt_templates:
            cli_enabled_prompts = [
                r.path for r in cli_extension_paths.prompts if r.enabled
            ]
            prompt_paths = self._merge_paths(
                cli_enabled_prompts, self.additional_prompt_template_paths
            )
        else:
            enabled_prompts = [
                r.path for r in resolved_paths.prompts if r.enabled
            ]
            cli_enabled_prompts = [
                r.path for r in cli_extension_paths.prompts if r.enabled
            ]
            prompt_paths = self._merge_paths(
                [*cli_enabled_prompts, *enabled_prompts],
                self.additional_prompt_template_paths,
            )
        prompts_result: LoadPromptTemplatesResult = loadPromptTemplates(
            cwd=self.cwd,
            agent_dir=self.agent_dir,
            prompt_paths=prompt_paths,
            include_defaults=False,
        )
        self._prompts = list(prompts_result["prompts"])
        self._prompt_diagnostics = list(prompts_result["diagnostics"])
        for p in self.additional_prompt_template_paths:
            if not os.path.isfile(p) and not any(
                d.path == p for d in self._prompt_diagnostics
            ):
                self._prompt_diagnostics.append(
                    ResourceDiagnostic(
                        type="error",
                        message="Prompt template path does not exist",
                        path=p,
                    )
                )

        # ---- Themes (stub loader) ----
        if self.no_themes:
            cli_enabled_themes = [
                r.path for r in cli_extension_paths.themes if r.enabled
            ]
            theme_paths = self._merge_paths(
                cli_enabled_themes, self.additional_theme_paths
            )
        else:
            enabled_themes = [
                r.path for r in resolved_paths.themes if r.enabled
            ]
            cli_enabled_themes = [
                r.path for r in cli_extension_paths.themes if r.enabled
            ]
            theme_paths = self._merge_paths(
                [*cli_enabled_themes, *enabled_themes],
                self.additional_theme_paths,
            )
        self._themes, self._theme_diagnostics = self._load_themes(theme_paths)
        for p in self.additional_theme_paths:
            if not os.path.exists(p) and not any(
                d.path == p for d in self._theme_diagnostics
            ):
                self._theme_diagnostics.append(
                    ResourceDiagnostic(
                        type="error",
                        message="Theme path does not exist",
                        path=p,
                    )
                )

        # ---- AGENTS.md context files ----
        if self.no_context_files:
            self._agents_files = []
        else:
            self._agents_files = load_project_context_files(
                cwd=self.cwd, agent_dir=self.agent_dir
            )

        # ---- System prompt ----
        base_prompt = self.system_prompt_source or self._discover_system_prompt_file()
        self._system_prompt = self._resolve_prompt_input(base_prompt, "system prompt")
        append_sources = (
            self.append_system_prompt_source
            if self.append_system_prompt_source is not None
            else (
                [self._discover_append_system_prompt_file()]
                if self._discover_append_system_prompt_file()
                else []
            )
        )
        base_append: list[str] = []
        for source in append_sources:
            if source is None:
                continue
            resolved = self._resolve_prompt_input(source, "append system prompt")
            if resolved is not None:
                base_append.append(resolved)
        self._append_system_prompt = base_append

        self._loaded = True

    # ------------------------------------------------------------------
    # Internal: theme loading
    # ------------------------------------------------------------------

    def _load_themes(
        self, paths: list[str]
    ) -> tuple[list[Theme], list[ResourceDiagnostic]]:
        """Load themes from a list of paths.
        Phase 6.11b — every path returns
        a warning (the stub loader raises
        NotImplementedError). Full JSON
        parsing lands in 6.12+."""
        themes: list[Theme] = []
        diagnostics: list[ResourceDiagnostic] = []
        for p in paths:
            resolved = os.path.realpath(os.path.join(self.cwd, p))
            if not os.path.exists(resolved):
                diagnostics.append(
                    ResourceDiagnostic(
                        type="warning",
                        message="theme path does not exist",
                        path=resolved,
                    )
                )
                continue
            try:
                theme = loadThemeFromPath(resolved)
            except NotImplementedError:
                diagnostics.append(
                    ResourceDiagnostic(
                        type="warning",
                        message=(
                            "theme loader is a Phase 6.11b stub — "
                            "JSON parsing lands in Phase 6.12+"
                        ),
                        path=resolved,
                    )
                )
                continue
            except Exception as exc:  # noqa: BLE001
                diagnostics.append(
                    ResourceDiagnostic(
                        type="warning",
                        message=str(exc) or "failed to load theme",
                        path=resolved,
                    )
                )
                continue
            themes.append(theme)
        # Dedupe by name.
        seen: dict[str, Theme] = {}
        dedup_diagnostics: list[ResourceDiagnostic] = []
        for theme in themes:
            name = theme.name or "unnamed"
            existing = seen.get(name)
            if existing is not None:
                dedup_diagnostics.append(
                    ResourceDiagnostic(
                        type="collision",
                        message=f'name "{name}" collision',
                        path=theme.source_path,
                    )
                )
            else:
                seen[name] = theme
        return list(seen.values()), diagnostics + dedup_diagnostics

    # ------------------------------------------------------------------
    # Internal: AGENTS.md / system-prompt helpers
    # ------------------------------------------------------------------

    def _discover_system_prompt_file(self) -> Optional[str]:
        """Find the ``SYSTEM.md`` (project
        first, then global). Mirrors
        ``discoverSystemPromptFile``
        (``resource-loader.ts:960-972``)."""
        project = os.path.join(self.cwd, CONFIG_DIR_NAME, "SYSTEM.md")
        if os.path.isfile(project):
            return project
        global_path = os.path.join(self.agent_dir, "SYSTEM.md")
        if os.path.isfile(global_path):
            return global_path
        return None

    def _discover_append_system_prompt_file(self) -> Optional[str]:
        """Find the ``APPEND_SYSTEM.md``
        (project first, then global).
        Mirrors
        ``discoverAppendSystemPromptFile``
        (``resource-loader.ts:974-986``)."""
        project = os.path.join(self.cwd, CONFIG_DIR_NAME, "APPEND_SYSTEM.md")
        if os.path.isfile(project):
            return project
        global_path = os.path.join(self.agent_dir, "APPEND_SYSTEM.md")
        if os.path.isfile(global_path):
            return global_path
        return None

    def _resolve_prompt_input(
        self, input_str: Optional[str], description: str
    ) -> Optional[str]:
        """Resolve a system-prompt input:
        if ``input_str`` is a file path,
        read its contents; otherwise return
        the string as-is. Mirrors
        ``resolvePromptInput``
        (``resource-loader.ts:53-70``)."""
        if not input_str:
            return None
        if os.path.isfile(input_str):
            try:
                with open(input_str, "r", encoding="utf-8") as fh:
                    return fh.read()
            except OSError as exc:
                _LOG.warning(
                    "Could not read %s file %s: %s",
                    description,
                    input_str,
                    exc,
                )
                return None
        return input_str

    # ------------------------------------------------------------------
    # Internal: path helpers
    # ------------------------------------------------------------------

    def _resolve_resource_path(self, p: str) -> str:
        """Expand ``~`` + resolve against
        ``cwd``. Mirrors
        ``resolveResourcePath``
        (``resource-loader.ts:772-783``)."""
        trimmed = p.strip()
        expanded = trimmed
        if trimmed == "~":
            expanded = os.path.expanduser("~")
        elif trimmed.startswith("~/"):
            expanded = os.path.join(os.path.expanduser("~"), trimmed[2:])
        elif trimmed.startswith("~"):
            expanded = os.path.join(os.path.expanduser("~"), trimmed[1:])
        return os.path.realpath(os.path.join(self.cwd, expanded))

    def _merge_paths(
        self, primary: list[str], additional: list[str]
    ) -> list[str]:
        """Dedupe + canonicalize a list of
        paths. Mirrors ``mergePaths``
        (``resource-loader.ts:755-770``)."""
        merged: list[str] = []
        seen: set[str] = set()
        for p in [*primary, *additional]:
            resolved = self._resolve_resource_path(p)
            try:
                canonical = str(Path(resolved).resolve())
            except OSError:
                canonical = resolved
            if canonical in seen:
                continue
            seen.add(canonical)
            merged.append(resolved)
        return merged

    def _detect_extension_conflicts(
        self, extensions: list[Extension]
    ) -> list["LoadExtensionsError"]:
        """Detect tool / flag conflicts
        across extensions. Mirrors
        ``detectExtensionConflicts``
        (``resource-loader.ts:997-1035``)."""
        conflicts: list[LoadExtensionsError] = []
        tool_owners: dict[str, str] = {}
        flag_owners: dict[str, str] = {}
        for ext in extensions:
            for tool_name in (ext.tools or {}).keys():
                existing = tool_owners.get(tool_name)
                if existing is not None and existing != ext.path:
                    conflicts.append(
                        {
                            "path": ext.path,
                            "error": (
                                f'Tool "{tool_name}" conflicts with {existing}'
                            ),
                        }
                    )
                else:
                    tool_owners[tool_name] = ext.path
            for flag_name in (ext.flags or {}).keys():
                existing = flag_owners.get(flag_name)
                if existing is not None and existing != ext.path:
                    conflicts.append(
                        {
                            "path": ext.path,
                            "error": (
                                f'Flag "--{flag_name}" conflicts with {existing}'
                            ),
                        }
                    )
                else:
                    flag_owners[flag_name] = ext.path
        return conflicts


# ============================================================================
# Module-level helpers
# ============================================================================


def load_context_file_from_dir(dir_path: str) -> Optional[AgentsFile]:
    """Load the first matching
    ``AGENTS.md``-style file in ``dir``.
    Mirrors ``loadContextFileFromDir``
    (``resource-loader.ts:72-88``)."""
    for filename in _CONTEXT_FILE_CANDIDATES:
        file_path = os.path.join(dir_path, filename)
        if os.path.isfile(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as fh:
                    return AgentsFile(path=file_path, content=fh.read())
            except OSError as exc:
                _LOG.warning("Could not read %s: %s", file_path, exc)
                return None
    return None


def load_project_context_files(
    cwd: str, agent_dir: str
) -> list[AgentsFile]:
    """Load the ``AGENTS.md``-style files
    from the agent dir (first) + the cwd
    + its ancestors. Mirrors
    ``loadProjectContextFiles``
    (``resource-loader.ts:90-132``)."""
    context_files: list[AgentsFile] = []
    seen_paths: set[str] = set()

    # 1. Agent dir (highest priority).
    global_context = load_context_file_from_dir(agent_dir)
    if global_context is not None:
        context_files.append(global_context)
        seen_paths.add(global_context.path)

    # 2. Walk from cwd up to the filesystem root.
    ancestor_files: list[AgentsFile] = []
    current = os.path.realpath(cwd)
    root = os.path.realpath(os.sep)
    while True:
        context_file = load_context_file_from_dir(current)
        if context_file is not None and context_file.path not in seen_paths:
            ancestor_files.insert(0, context_file)
            seen_paths.add(context_file.path)
        if current == root:
            break
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent

    context_files.extend(ancestor_files)
    return context_files


__all__ = [
    "AgentsFile",
    "CONFIG_DIR_NAME",
    "DefaultResourceLoader",
    "DefaultResourceLoaderOptions",
    "ResourceExtensionPaths",
    "ResourceLoader",
    "load_context_file_from_dir",
    "load_project_context_files",
]
