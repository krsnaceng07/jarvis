"""jarvis.agents.sessions.package_manager — package / resource manager.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/package-manager.ts``.

Phase 6.11a — focused port.

Resolves extension, skill, prompt, and
theme sources from npm, git, local paths,
and project manifests.

Ships the critical contract:
- :class:`PathMetadata` — resource path
  metadata (source / scope / origin)
- :class:`ResolvedResource` — a single
  resolved resource (path + enabled + metadata)
- :class:`ResolvedPaths` — the four
  resolved resource lists (extensions /
  skills / prompts / themes)
- :class:`PackageManager` — Protocol
  interface
- :class:`DefaultPackageManager` — the
  default implementation

Adaptations
-----------
- The OpenClaw source uses Node's
  ``fs.globSync`` + ``addIgnoreRules`` from
  the shared ``ignore-rules`` module. The
  Python port uses :mod:`pathlib`'s glob
  + a hand-rolled gitignore-style matcher
  in :mod:`jarvis.agents.sessions.ignore_rules`.
- The OpenClaw source's npm install
  (real ``npm install`` of a package into
  the agent dir) is preserved via a
  pre-installed check only — the install
  itself is deferred to Phase 6.12+ with
  the full agent-dir wiring.
- The OpenClaw source's git clone is
  preserved via a pre-cloned check only —
  the clone itself is deferred.
- The OpenClaw source's ``minimatch``
  glob support is replaced with
  :mod:`fnmatch` (Python's stdlib).
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional, Union

from .git import GitSource, parse_git_url
from .ignore_rules import (
    IgnoreMatcher,
    add_ignore_rules,
    is_path_within_root,
    is_real_path_within_root,
)
from .path_utils import (
    canonicalize_path,
    is_local_path,
    to_posix_path,
)
from .settings_manager import SettingsManager, SettingsScope


_log = logging.getLogger("jarvis.agents.sessions.package_manager")


# ============================================================================
# Constants
# ============================================================================


#: The project config dir name. Mirrors
#: ``CONFIG_DIR_NAME = ".openclaw"`` in the
#: OpenClaw source. The Python port uses
#: ``.jarvis`` (the JARVIS config dir).
#: The package manager accepts either
#: ``.openclaw`` or ``.jarvis`` as a
#: forward-compat alias.
CONFIG_DIR_NAME_PRIMARY = ".jarvis"
CONFIG_DIR_NAME_ALIAS = ".openclaw"


#: File extensions per resource type. Mirrors
#: ``FILE_PATTERNS`` (``package-manager.ts:124-129``).
FILE_PATTERNS: dict[str, str] = {
    "extensions": "ts|js",  # regex
    "skills": "md",
    "prompts": "md",
    "themes": "json",
}


#: Resource type identifiers.
ResourceType = str  # "extensions" | "skills" | "prompts" | "themes"
TopLevelAutoResourceType = str  # "prompts" | "themes"

#: The four resource types in iteration order.
RESOURCE_TYPES: list[ResourceType] = [
    "extensions",
    "skills",
    "prompts",
    "themes",
]

#: Source scopes.
SourceScope = str  # "user" | "project" | "temporary"


# ============================================================================
# Types
# ============================================================================


@dataclass(frozen=True, slots=True)
class PathMetadata:
    """Resource path metadata. Mirrors
    ``PathMetadata`` (``package-manager.ts:26-31``).

    Attributes
    ----------
    source : str
        e.g. ``"npm:foo"``, ``"git:..."``,
        ``"local"``, ``"auto"``.
    scope : SourceScope
        ``"user"`` (the global agent dir) /
        ``"project"`` (the cwd's .jarvis dir) /
        ``"temporary"`` (CLI / inline).
    origin : str
        ``"package"`` (came from a package
        source) / ``"top-level"`` (a direct
        path entry).
    baseDir : str, optional
        The package root (for resources
        that come from a package).
    """

    source: str
    scope: SourceScope
    origin: str  # "package" | "top-level"
    baseDir: Optional[str] = None


@dataclass(frozen=True, slots=True)
class ResolvedResource:
    """A single resolved resource. Mirrors
    ``ResolvedResource`` (``package-manager.ts:33-37``)."""

    path: str
    enabled: bool
    metadata: PathMetadata


@dataclass(frozen=True, slots=True)
class ResolvedPaths:
    """The four resolved resource lists. Mirrors
    ``ResolvedPaths`` (``package-manager.ts:39-44``)."""

    extensions: list[ResolvedResource]
    skills: list[ResolvedResource]
    prompts: list[ResolvedResource]
    themes: list[ResolvedResource]


#: What to do when a package source is missing
#: on disk. Mirrors ``MissingSourceAction``.
MissingSourceAction = str  # "skip" | "error"


#: The package filter shape (a per-resource
#: type list of include/exclude patterns).
PackageFilter = dict


#: Package source (a string or a dict with
#: ``source`` + ``extensions``/``skills``/...
#: filter).
PackageSource = Union[str, dict]


#: Callback for missing source resolution.
OnMissingSource = Callable[[str], Awaitable[MissingSourceAction]]


# ============================================================================
# Protocol
# ============================================================================


class PackageManager:
    """Package manager protocol. Mirrors
    ``PackageManager`` (``package-manager.ts:48-54``).
    """

    def resolve(
        self,
        on_missing: Optional[OnMissingSource] = None,
    ) -> Awaitable[ResolvedPaths]:
        ...

    def resolve_extension_sources(
        self,
        sources: list[str],
        options: Optional[dict] = None,
    ) -> Awaitable[ResolvedPaths]:
        ...


# ============================================================================
# Helpers
# ============================================================================


def _resource_precedence_rank(metadata: PathMetadata) -> int:
    """Compute a numeric precedence rank for a
    resource (lower = higher precedence).
    Mirrors ``resourcePrecedenceRank``
    (``package-manager.ts:104-110``).

    Precedence (highest to lowest):
      0  project + settings entry (source: "local", scope: "project")
      1  project + auto-discovered (source: "auto", scope: "project")
      2  user + settings entry (source: "local", scope: "user")
      3  user + auto-discovered (source: "auto", scope: "user")
      4  package resource (origin: "package")
    """
    if metadata.origin == "package":
        return 4
    base = 0 if metadata.scope == "project" else 2
    return base + (0 if metadata.source == "local" else 1)


def _is_pattern(entry: str) -> bool:
    """Check whether a settings entry is a
    pattern (starts with ``!``/``+``/``-``
    or contains ``*``/``?``). Mirrors
    ``isPattern`` (``package-manager.ts:143-151``)."""
    return (
        entry.startswith("!")
        or entry.startswith("+")
        or entry.startswith("-")
        or "*" in entry
        or "?" in entry
    )


def _is_override_pattern(entry: str) -> bool:
    """Check whether a pattern is an override
    (``!``/``+``/``-``). Mirrors
    ``isOverridePattern`` (``package-manager.ts:153-155``)."""
    return entry.startswith(("!", "+", "-"))


def _has_glob_pattern(entry: str) -> bool:
    """Check whether an entry contains glob
    wildcards. Mirrors ``hasGlobPattern``
    (``package-manager.ts:157-159``)."""
    return "*" in entry or "?" in entry


def _split_patterns(entries: list[str]) -> tuple[list[str], list[str]]:
    """Split a list of settings entries into
    (plain, patterns). Mirrors ``splitPatterns``
    (``package-manager.ts:161-172``)."""
    plain: list[str] = []
    patterns: list[str] = []
    for entry in entries:
        if _is_pattern(entry):
            patterns.append(entry)
        else:
            plain.append(entry)
    return plain, patterns


def _get_home_dir() -> str:
    """Get the home directory. Mirrors
    ``getHomeDir`` (``package-manager.ts:131-133``)."""
    return os.environ.get("HOME") or os.path.expanduser("~")


def _get_agent_resource_temp_dir(agent_dir: str) -> str:
    """Create (if needed) + return the agent's
    temp resources dir. Mirrors
    ``getAgentResourceTempDir``
    (``package-manager.ts:135-141``)."""
    temp_dir = os.path.join(agent_dir, "tmp", "resources")
    os.makedirs(temp_dir, exist_ok=True)
    return temp_dir


def _collect_files(
    directory: str,
    file_pattern_re: str,
    skip_node_modules: bool = True,
    ignore_matcher: Optional[IgnoreMatcher] = None,
    root_dir: Optional[str] = None,
) -> list[str]:
    """Recursively collect files in
    ``directory`` matching the
    ``file_pattern_re`` (a regex). Mirrors
    ``collectFiles``
    (``package-manager.ts:174-232``).

    Skips dotfiles, node_modules, and
    ignore-matched paths.
    """
    files: list[str] = []
    if not os.path.isdir(directory):
        return files
    root = root_dir or directory
    ig = ignore_matcher or add_ignore_rules(directory, root)
    try:
        entries = list(os.scandir(directory))
    except OSError:
        return files
    for entry in entries:
        name = entry.name
        if name.startswith("."):
            continue
        if skip_node_modules and name == "node_modules":
            continue
        full_path = os.path.join(directory, name)
        # Resolve symlinks (the OpenClaw
        # source's ``isSymbolicLink`` check).
        is_dir = entry.is_dir(follow_symlinks=True)
        is_file = entry.is_file(follow_symlinks=True)
        if entry.is_symlink():
            try:
                st = os.stat(full_path)
                is_dir = (st.st_mode & 0o170000) == 0o040000
                is_file = (st.st_mode & 0o170000) == 0o100000
            except OSError:
                continue
        rel = to_posix_path(os.path.relpath(full_path, root))
        ignore_path = rel + ("/" if is_dir else "")
        if ig.ignores(ignore_path):
            continue
        if is_dir:
            files.extend(
                _collect_files(full_path, file_pattern_re, skip_node_modules, ig, root)
            )
        elif is_file and re.search(file_pattern_re, name):
            files.append(full_path)
    return files


def _collect_skill_entries(
    directory: str,
    mode: str = "openclaw",  # "openclaw" | "agents"
    ignore_matcher: Optional[IgnoreMatcher] = None,
    root_dir: Optional[str] = None,
) -> list[str]:
    """Collect skill entries. Skills live in
    a directory containing a ``SKILL.md``
    file. Mirrors ``collectSkillEntries``
    (``package-manager.ts:236-331``)."""
    entries: list[str] = []
    if not os.path.isdir(directory):
        return entries
    root = root_dir or directory
    ig = ignore_matcher or add_ignore_rules(directory, root)
    try:
        dir_entries = list(os.scandir(directory))
    except OSError:
        return entries
    # First: look for a ``SKILL.md`` in the
    # directory itself
    for entry in dir_entries:
        if entry.name != "SKILL.md":
            continue
        full_path = os.path.join(directory, entry.name)
        if not is_real_path_within_root(root, full_path):
            continue
        is_file = entry.is_file(follow_symlinks=True)
        if entry.is_symlink():
            try:
                is_file = os.path.isfile(full_path)
            except OSError:
                continue
        rel = to_posix_path(os.path.relpath(full_path, root))
        if is_file and not ig.ignores(rel):
            entries.append(full_path)
            return entries
    # Then: recurse into subdirectories
    for entry in dir_entries:
        name = entry.name
        if name.startswith("."):
            continue
        if name == "node_modules":
            continue
        full_path = os.path.join(directory, name)
        if not is_real_path_within_root(root, full_path):
            continue
        is_dir = entry.is_dir(follow_symlinks=True)
        is_file = entry.is_file(follow_symlinks=True)
        if entry.is_symlink():
            try:
                st = os.stat(full_path)
                is_dir = (st.st_mode & 0o170000) == 0o040000
                is_file = (st.st_mode & 0o170000) == 0o100000
            except OSError:
                continue
        rel = to_posix_path(os.path.relpath(full_path, root))
        if (
            mode == "openclaw"
            and directory == root
            and is_file
            and name.endswith(".md")
            and not ig.ignores(rel)
        ):
            entries.append(full_path)
            continue
        if not is_dir:
            continue
        if ig.ignores(rel + "/"):
            continue
        entries.extend(
            _collect_skill_entries(full_path, mode, ig, root)
        )
    return entries


def _collect_top_level_auto_resource_entries(
    directory: str,
    resource_type: TopLevelAutoResourceType,
) -> list[str]:
    """Collect top-level files (no recursion)
    matching the resource-type pattern.
    Mirrors ``collectTopLevelAutoResourceEntries``
    (``package-manager.ts:372-420``)."""
    entries: list[str] = []
    if not os.path.isdir(directory):
        return entries
    ig = add_ignore_rules(directory, directory)
    try:
        dir_entries = list(os.scandir(directory))
    except OSError:
        return entries
    file_pattern = FILE_PATTERNS.get(resource_type, "")
    if not file_pattern:
        return entries
    for entry in dir_entries:
        name = entry.name
        if name.startswith(".") or name == "node_modules":
            continue
        full_path = os.path.join(directory, name)
        if not is_real_path_within_root(directory, full_path):
            continue
        is_file = entry.is_file(follow_symlinks=True)
        if entry.is_symlink():
            try:
                is_file = os.path.isfile(full_path)
            except OSError:
                continue
        rel = to_posix_path(os.path.relpath(full_path, directory))
        if ig.ignores(rel):
            continue
        if is_file and re.search(file_pattern + r"$", name):
            entries.append(full_path)
    return entries


def _find_git_repo_root(start_dir: str) -> Optional[str]:
    """Walk up the directory tree to find the
    nearest ``.git``. Mirrors
    ``findGitRepoRoot``
    (``package-manager.ts:337-349``)."""
    current = os.path.realpath(start_dir)
    while True:
        if os.path.isdir(os.path.join(current, ".git")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def _collect_ancestor_agents_skill_dirs(start_dir: str) -> list[str]:
    """Collect the ``.agents/skills`` directories
    from the cwd up to the git root. Mirrors
    ``collectAncestorAgentsSkillDirs``
    (``package-manager.ts:351-370``)."""
    skill_dirs: list[str] = []
    resolved_start = os.path.realpath(start_dir)
    git_root = _find_git_repo_root(resolved_start)
    current = resolved_start
    while True:
        skill_dirs.append(os.path.join(current, ".agents", "skills"))
        if git_root and current == git_root:
            break
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return skill_dirs


def _read_resource_manifest_file(
    package_json_path: str,
) -> Optional[dict]:
    """Read the ``openclaw`` field from a
    package.json. Mirrors
    ``readResourceManifestFile``
    (``package-manager.ts:422-430``)."""
    try:
        with open(package_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data.get("openclaw")


def _resolve_extension_entries(
    directory: str,
    root_dir: Optional[str] = None,
) -> Optional[list[str]]:
    """Resolve extension entries from a
    directory: either the
    ``openclaw.extensions`` manifest entries
    or a single ``index.ts``/``index.js``.
    Mirrors ``resolveExtensionEntries``
    (``package-manager.ts:432-460``)."""
    root = root_dir or directory
    package_json_path = os.path.join(directory, "package.json")
    if os.path.isfile(package_json_path):
        manifest = _read_resource_manifest_file(package_json_path)
        if manifest and manifest.get("extensions"):
            entries: list[str] = []
            for ext_path in manifest["extensions"]:
                resolved = os.path.realpath(os.path.join(directory, ext_path))
                if os.path.exists(resolved) and is_real_path_within_root(root, resolved):
                    entries.append(resolved)
            if entries:
                return entries
    for filename in ("index.ts", "index.js"):
        index_path = os.path.join(directory, filename)
        if os.path.isfile(index_path) and is_real_path_within_root(root, index_path):
            return [index_path]
    return None


def _collect_auto_extension_entries(directory: str) -> list[str]:
    """Auto-discover extension entries in
    ``directory``. Mirrors
    ``collectAutoExtensionEntries``
    (``package-manager.ts:462-524``)."""
    entries: list[str] = []
    if not os.path.isdir(directory):
        return entries
    # First check if this directory itself
    # has explicit entries.
    root_entries = _resolve_extension_entries(directory)
    if root_entries:
        return root_entries
    ig = add_ignore_rules(directory, directory)
    try:
        dir_entries = list(os.scandir(directory))
    except OSError:
        return entries
    for entry in dir_entries:
        name = entry.name
        if name.startswith(".") or name == "node_modules":
            continue
        full_path = os.path.join(directory, name)
        if not is_real_path_within_root(directory, full_path):
            continue
        is_dir = entry.is_dir(follow_symlinks=True)
        is_file = entry.is_file(follow_symlinks=True)
        if entry.is_symlink():
            try:
                st = os.stat(full_path)
                is_dir = (st.st_mode & 0o170000) == 0o040000
                is_file = (st.st_mode & 0o170000) == 0o100000
            except OSError:
                continue
        rel = to_posix_path(os.path.relpath(full_path, directory))
        ignore_path = rel + ("/" if is_dir else "")
        if ig.ignores(ignore_path):
            continue
        if is_file and (name.endswith(".ts") or name.endswith(".js")):
            entries.append(full_path)
        elif is_dir:
            resolved = _resolve_extension_entries(full_path, directory)
            if resolved:
                entries.extend(resolved)
    return entries


def _collect_resource_files(directory: str, resource_type: ResourceType) -> list[str]:
    """Dispatch to the right collector for
    ``resource_type``. Mirrors
    ``collectResourceFiles``
    (``package-manager.ts:530-538``)."""
    if resource_type == "skills":
        return _collect_skill_entries(directory, "openclaw")
    if resource_type == "extensions":
        return _collect_auto_extension_entries(directory)
    file_pattern = FILE_PATTERNS.get(resource_type, "")
    if not file_pattern:
        return []
    return _collect_files(directory, file_pattern)


def _apply_patterns(
    all_paths: list[str],
    patterns: list[str],
    base_dir: str,
) -> set[str]:
    """Apply include / exclude / force-include
    / force-exclude patterns. Mirrors
    ``applyPatterns``
    (``package-manager.ts:604-650``).

    Pattern types:
    - ``pattern``: include matching paths
    - ``!pattern``: exclude matching paths
    - ``+path``: force-include exact path
    - ``-path``: force-exclude exact path
    """
    includes: list[str] = []
    excludes: list[str] = []
    force_includes: list[str] = []
    force_excludes: list[str] = []
    for p in patterns:
        if p.startswith("+"):
            force_includes.append(p[1:])
        elif p.startswith("-"):
            force_excludes.append(p[1:])
        elif p.startswith("!"):
            excludes.append(p[1:])
        else:
            includes.append(p)
    if not includes:
        result = list(all_paths)
    else:
        result = [
            p
            for p in all_paths
            if _matches_any_pattern(p, includes, base_dir)
        ]
    if excludes:
        result = [
            p for p in result if not _matches_any_pattern(p, excludes, base_dir)
        ]
    if force_includes:
        for p in all_paths:
            if p not in result and _matches_any_exact_pattern(
                p, force_includes, base_dir
            ):
                result.append(p)
    if force_excludes:
        result = [
            p
            for p in result
            if not _matches_any_exact_pattern(p, force_excludes, base_dir)
        ]
    return set(result)


def _matches_any_pattern(
    file_path: str, patterns: list[str], base_dir: str
) -> bool:
    """Check whether ``file_path`` matches any
    of the glob patterns. Mirrors the
    OpenClaw source's ``matchesAnyPattern``
    (uses ``minimatch``)."""
    candidates = _get_match_candidates(file_path, base_dir, include_names=True)
    for pattern in patterns:
        if _minimatch_any(candidates, to_posix_path(pattern)):
            return True
    return False


def _matches_any_exact_pattern(
    file_path: str, patterns: list[str], base_dir: str
) -> bool:
    candidates = set(_get_match_candidates(file_path, base_dir, include_names=False))
    for pattern in patterns:
        if _normalize_exact_pattern(pattern) in candidates:
            return True
    return False


def _normalize_exact_pattern(pattern: str) -> str:
    """Strip the ``./`` prefix and convert to
    POSIX path. Mirrors ``normalizeExactPattern``
    (``package-manager.ts:581-585``)."""
    if pattern.startswith("./") or pattern.startswith(".\\"):
        pattern = pattern[2:]
    return to_posix_path(pattern)


def _get_match_candidates(
    file_path: str, base_dir: str, include_names: bool
) -> list[str]:
    """Build the candidate list for matching
    against patterns. Mirrors
    ``getMatchCandidates``
    (``package-manager.ts:560-574``)."""
    name = os.path.basename(file_path)
    candidates = [
        to_posix_path(os.path.relpath(file_path, base_dir)),
        to_posix_path(file_path),
    ]
    if include_names:
        candidates.append(name)
    if name == "SKILL.md":
        parent_dir = os.path.dirname(file_path)
        candidates.append(to_posix_path(os.path.relpath(parent_dir, base_dir)))
        candidates.append(to_posix_path(parent_dir))
        if include_names:
            candidates.append(os.path.basename(parent_dir))
    return candidates


def _minimatch_any(candidates: list[str], pattern: str) -> bool:
    """Python equivalent of the OpenClaw source's
    ``minimatch.match(candidates, pattern).length > 0``
    (returns ``True`` when any candidate
    matches the pattern)."""
    for cand in candidates:
        if fnmatch.fnmatch(cand, pattern):
            return True
    # Also try without the leading ``./`` (fnmatch
    # doesn't handle POSIX-style globs the
    # same way as minimatch; this is a
    # best-effort port).
        if cand.startswith("./") and fnmatch.fnmatch(cand[2:], pattern):
            return True
    return False


# ============================================================================
# DefaultPackageManager
# ============================================================================


@dataclass
class DefaultPackageManager(PackageManager):
    """Default package manager implementation.
    Mirrors ``DefaultPackageManager``
    (``package-manager.ts:652-1485``).

    Resolves extension, skill, prompt, and
    theme sources from:
    - Settings-driven local paths
      (``globalSettings[resourceType]`` /
      ``projectSettings[resourceType]``)
    - Settings-driven package sources
      (``globalSettings.packages`` /
      ``projectSettings.packages``)
    - Auto-discovered files in the agent /
      project / .agents/ standard dirs
    - CLI-provided sources
      (``resolveExtensionSources``)

    The Python port preserves the public
    contract (the four ``resolve*`` methods +
    the same accumulator semantics) but
    defers the actual npm install + git
    clone to Phase 6.12+ (the install
    commands live outside the source
    tree).
    """

    cwd: str
    agent_dir: str
    settings_manager: SettingsManager

    def __post_init__(self) -> None:
        self.cwd = os.path.realpath(self.cwd)
        self.agent_dir = os.path.realpath(self.agent_dir)

    async def resolve(
        self,
        on_missing: Optional[OnMissingSource] = None,
    ) -> ResolvedPaths:
        """Resolve all resource paths from
        the settings + auto-discovery.
        Mirrors ``resolve``
        (``package-manager.ts:663-723``)."""
        accumulator = self._create_accumulator()
        global_settings = self.settings_manager.get_global_settings()
        project_settings = self.settings_manager.get_project_settings()
        # Collect all packages (project scope
        # wins over user).
        all_packages: list[dict] = []
        for pkg in project_settings.get("packages") or []:
            all_packages.append({"pkg": pkg, "scope": "project"})
        for pkg in global_settings.get("packages") or []:
            all_packages.append({"pkg": pkg, "scope": "user"})
        package_sources = self._dedupe_packages(all_packages)
        await self._resolve_package_sources(package_sources, accumulator, on_missing)
        global_base_dir = self.agent_dir
        project_base_dir = os.path.join(self.cwd, CONFIG_DIR_NAME_PRIMARY)
        for resource_type in RESOURCE_TYPES:
            target = self._get_target_map(accumulator, resource_type)
            global_entries = global_settings.get(resource_type) or []
            project_entries = project_settings.get(resource_type) or []
            self._resolve_local_entries(
                project_entries,
                resource_type,
                target,
                PathMetadata(
                    source="local",
                    scope="project",
                    origin="top-level",
                ),
                project_base_dir,
            )
            self._resolve_local_entries(
                global_entries,
                resource_type,
                target,
                PathMetadata(
                    source="local",
                    scope="user",
                    origin="top-level",
                ),
                global_base_dir,
            )
        self._add_auto_discovered_resources(
            accumulator,
            global_settings,
            project_settings,
            global_base_dir,
            project_base_dir,
        )
        return self._to_resolved_paths(accumulator)

    async def resolve_extension_sources(
        self,
        sources: list[str],
        options: Optional[dict] = None,
    ) -> ResolvedPaths:
        """Resolve a list of CLI-provided
        sources. Mirrors
        ``resolveExtensionSources``
        (``package-manager.ts:725-738``)."""
        accumulator = self._create_accumulator()
        options = options or {}
        if options.get("temporary"):
            scope: SourceScope = "temporary"
        elif options.get("local"):
            scope = "project"
        else:
            scope = "user"
        package_sources: list[dict] = [
            {"pkg": s, "scope": scope} for s in sources
        ]
        await self._resolve_package_sources(package_sources, accumulator)
        return self._to_resolved_paths(accumulator)

    # ------------------------------------------------------------------
    # Internal: package sources
    # ------------------------------------------------------------------

    async def _resolve_package_sources(
        self,
        sources: list[dict],
        accumulator: dict,
        on_missing: Optional[OnMissingSource] = None,
    ) -> None:
        """Resolve package sources (npm/git/local).
        Mirrors ``resolvePackageSources``
        (``package-manager.ts:740-791``)."""
        for entry in sources:
            source_str = (
                entry["pkg"] if isinstance(entry["pkg"], str) else entry["pkg"]["source"]
            )
            pkg_filter = (
                None if isinstance(entry["pkg"], str) else entry["pkg"]
            )
            scope = entry["scope"]
            parsed = self._parse_source(source_str)
            metadata = PathMetadata(
                source=source_str,
                scope=scope,
                origin="package",
            )
            if parsed["type"] == "local":
                base_dir = self._get_base_dir_for_scope(scope)
                self._resolve_local_extension_source(
                    parsed, accumulator, pkg_filter, metadata, base_dir
                )
                continue
            # npm / git — the install/clone is
            # deferred to Phase 6.12+. We
            # detect a missing install + call
            # on_missing (the OpenClaw source
            # auto-installs here).
            handle_missing = None
            if on_missing is not None:
                async def _handle_missing() -> None:
                    action = await on_missing(source_str)
                    if action == "error":
                        raise RuntimeError(f"Missing source: {source_str}")

                handle_missing = _handle_missing
            installed_path: Optional[str] = None
            if parsed["type"] == "npm":
                installed_path = self._get_npm_install_path(parsed, scope)
                pinned = self._installed_npm_matches_pinned_version(
                    parsed, installed_path
                )
                if not os.path.isdir(installed_path) or not pinned:
                    if handle_missing is not None:
                        await handle_missing()
                    continue
                metadata = PathMetadata(
                    source=source_str,
                    scope=scope,
                    origin="package",
                    baseDir=installed_path,
                )
            elif parsed["type"] == "git":
                installed_path = self._get_git_install_path(parsed["git"], scope)
                if not os.path.isdir(installed_path):
                    if handle_missing is not None:
                        await handle_missing()
                    continue
                metadata = PathMetadata(
                    source=source_str,
                    scope=scope,
                    origin="package",
                    baseDir=installed_path,
                )
            if installed_path is not None:
                self._collect_package_resources(
                    installed_path, accumulator, pkg_filter, metadata
                )

    def _resolve_local_extension_source(
        self,
        source: dict,
        accumulator: dict,
        pkg_filter: Optional[dict],
        metadata: PathMetadata,
        base_dir: str,
    ) -> None:
        """Resolve a local extension source.
        Mirrors ``resolveLocalExtensionSource``
        (``package-manager.ts:793-820``)."""
        resolved = self._resolve_path_from_base(source["path"], base_dir)
        if not os.path.exists(resolved):
            return
        try:
            st = os.stat(resolved)
            is_file = (st.st_mode & 0o170000) == 0o100000
            is_dir = (st.st_mode & 0o170000) == 0o040000
        except OSError:
            return
        if is_file:
            metadata = PathMetadata(
                source=metadata.source,
                scope=metadata.scope,
                origin=metadata.origin,
                baseDir=os.path.dirname(resolved),
            )
            self._add_resource(accumulator["extensions"], resolved, metadata, True)
            return
        if is_dir:
            metadata = PathMetadata(
                source=metadata.source,
                scope=metadata.scope,
                origin=metadata.origin,
                baseDir=resolved,
            )
            resources = self._collect_package_resources(
                resolved, accumulator, pkg_filter, metadata
            )
            if not resources:
                self._add_resource(accumulator["extensions"], resolved, metadata, True)

    def _parse_source(self, source: str) -> dict:
        """Parse a source string into
        ``{type, ...}``. Mirrors ``parseSource``
        (``package-manager.ts:822-845``).

        For ``npm:`` sources the returned dict
        carries ``type`` + ``name`` + ``version``
        + ``pinned`` + ``spec``. For ``git``
        sources the returned dict carries
        ``type`` + ``git`` (a
        :class:`GitSource`). For everything
        else the source is treated as a local
        path.
        """
        if source.startswith("npm:"):
            spec = source[4:].strip()
            parsed = self._parse_npm_spec(spec)
            return {
                "type": "npm",
                "spec": spec,
                "name": parsed["name"],
                "version": parsed.get("version"),
                "pinned": bool(parsed.get("version")),
            }
        if not is_local_path(source):
            git = parse_git_url(source)
            if git is not None:
                return {"type": "git", "git": git}
        return {"type": "local", "path": source}

    def _parse_npm_spec(self, spec: str) -> dict:
        """Parse an npm spec. Mirrors
        ``parseNpmSpec``
        (``package-manager.ts:924-932``)."""
        match = re.match(r"^(@?[^@]+(?:/[^@]+)?)(?:@(.+))?$", spec)
        if not match:
            return {"name": spec}
        name = match.group(1) or spec
        version = match.group(2)
        if version is not None:
            return {"name": name, "version": version}
        return {"name": name}

    def _get_npm_install_path(self, source: dict, scope: SourceScope) -> str:
        """Get the install path for an npm
        package. Mirrors ``getNpmInstallPath``
        (``package-manager.ts:934-942``)."""
        if scope == "temporary":
            return os.path.join(
                self._get_temporary_dir("npm"),
                "node_modules",
                source["name"],
            )
        if scope == "project":
            return os.path.join(
                self.cwd, CONFIG_DIR_NAME_PRIMARY, "npm", "node_modules", source["name"]
            )
        return os.path.join(self.agent_dir, "npm", "node_modules", source["name"])

    def _get_git_install_path(self, source: GitSource, scope: SourceScope) -> str:
        """Get the install path for a git
        package. Mirrors ``getGitInstallPath``
        (``package-manager.ts:944-952``)."""
        if scope == "temporary":
            return self._get_temporary_dir(f"git-{source.host}", source.path)
        if scope == "project":
            return os.path.join(
                self.cwd, CONFIG_DIR_NAME_PRIMARY, "git", source.host, source.path
            )
        return os.path.join(self.agent_dir, "git", source.host, source.path)

    def _get_temporary_dir(self, prefix: str, suffix: Optional[str] = None) -> str:
        """Get a unique temp dir under the
        agent's resource temp dir. Mirrors
        ``getTemporaryDir``
        (``package-manager.ts:954-960``)."""
        hash_input = f"{prefix}-{suffix or ''}".encode("utf-8")
        digest = hashlib.sha256(hash_input).hexdigest()[:8]
        return os.path.join(
            _get_agent_resource_temp_dir(self.agent_dir),
            prefix,
            digest,
            suffix or "",
        )

    def _get_base_dir_for_scope(self, scope: SourceScope) -> str:
        """Get the base directory for a given
        scope. Mirrors ``getBaseDirForScope``
        (``package-manager.ts:962-970``)."""
        if scope == "project":
            return os.path.join(self.cwd, CONFIG_DIR_NAME_PRIMARY)
        if scope == "user":
            return self.agent_dir
        return self.cwd

    def _resolve_path(self, input_path: str) -> str:
        return self._resolve_path_from_base(input_path, self.cwd)

    def _resolve_path_from_base(self, input_path: str, base_dir: str) -> str:
        """Resolve a path with ~ / absolute
        expansion. Mirrors ``resolvePathFromBase``
        (``package-manager.ts:986-998``)."""
        trimmed = input_path.strip()
        if trimmed == "~":
            return _get_home_dir()
        if trimmed.startswith("~/"):
            return os.path.join(_get_home_dir(), trimmed[2:])
        if trimmed.startswith("~"):
            return os.path.join(_get_home_dir(), trimmed[1:])
        return os.path.realpath(os.path.join(base_dir, trimmed))

    # ------------------------------------------------------------------
    # Internal: package resource collection
    # ------------------------------------------------------------------

    def _collect_package_resources(
        self,
        package_root: str,
        accumulator: dict,
        pkg_filter: Optional[dict],
        metadata: PathMetadata,
    ) -> bool:
        """Collect resources from a package
        root. Mirrors ``collectPackageResources``
        (``package-manager.ts:1000-1047``)."""
        if pkg_filter is not None:
            for resource_type in RESOURCE_TYPES:
                patterns = pkg_filter.get(resource_type)
                target = self._get_target_map(accumulator, resource_type)
                if patterns is not None:
                    self._apply_package_filter(
                        package_root, patterns, resource_type, target, metadata
                    )
                else:
                    self._collect_default_resources(
                        package_root, resource_type, target, metadata
                    )
            return True
        manifest = self._read_resource_manifest(package_root)
        if manifest is not None:
            for resource_type in RESOURCE_TYPES:
                entries = manifest.get(resource_type)
                self._add_manifest_entries(
                    entries,
                    package_root,
                    resource_type,
                    self._get_target_map(accumulator, resource_type),
                    metadata,
                )
            return True
        has_any = False
        for resource_type in RESOURCE_TYPES:
            resource_dir = os.path.join(package_root, resource_type)
            if os.path.isdir(resource_dir):
                files = self._collect_convention_resource_files(
                    package_root, resource_type
                )
                for f in files:
                    self._add_resource(
                        self._get_target_map(accumulator, resource_type),
                        f,
                        metadata,
                        True,
                    )
                has_any = True
        return has_any

    def _collect_default_resources(
        self,
        package_root: str,
        resource_type: ResourceType,
        target: dict,
        metadata: PathMetadata,
    ) -> None:
        manifest = self._read_resource_manifest(package_root)
        entries = (manifest or {}).get(resource_type)
        if entries:
            self._add_manifest_entries(entries, package_root, resource_type, target, metadata)
            return
        resource_dir = os.path.join(package_root, resource_type)
        if os.path.isdir(resource_dir):
            files = self._collect_convention_resource_files(package_root, resource_type)
            for f in files:
                self._add_resource(target, f, metadata, True)

    def _apply_package_filter(
        self,
        package_root: str,
        user_patterns: list[str],
        resource_type: ResourceType,
        target: dict,
        metadata: PathMetadata,
    ) -> None:
        """Apply a per-resource-type user
        pattern filter. Mirrors
        ``applyPackageFilter``
        (``package-manager.ts:1071-1095``)."""
        collected = self._collect_manifest_files(package_root, resource_type)
        all_files = collected["allFiles"]
        if not user_patterns:
            # Empty array explicitly disables
            for f in all_files:
                self._add_resource(target, f, metadata, False)
            return
        enabled_by_user = _apply_patterns(all_files, user_patterns, package_root)
        for f in all_files:
            self._add_resource(target, f, metadata, f in enabled_by_user)

    def _collect_manifest_files(
        self, package_root: str, resource_type: ResourceType
    ) -> dict:
        manifest = self._read_resource_manifest(package_root)
        entries = (manifest or {}).get(resource_type)
        if entries and len(entries) > 0:
            all_files = self._collect_files_from_manifest_entries(
                entries, package_root, resource_type
            )
            manifest_patterns = [e for e in entries if _is_override_pattern(e)]
            enabled = (
                _apply_patterns(all_files, manifest_patterns, package_root)
                if manifest_patterns
                else set(all_files)
            )
            return {
                "allFiles": list(enabled),
                "enabledByManifest": enabled,
            }
        all_files = self._collect_convention_resource_files(package_root, resource_type)
        return {"allFiles": all_files, "enabledByManifest": set(all_files)}

    def _collect_convention_resource_files(
        self, package_root: str, resource_type: ResourceType
    ) -> list[str]:
        convention_dir = os.path.join(package_root, resource_type)
        if not os.path.isdir(convention_dir):
            return []
        return self._filter_manifest_resource_paths(
            _collect_resource_files(convention_dir, resource_type),
            package_root,
        )

    def _read_resource_manifest(self, package_root: str) -> Optional[dict]:
        package_json_path = os.path.join(package_root, "package.json")
        if not os.path.isfile(package_json_path):
            return None
        try:
            with open(package_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        return data.get("openclaw")

    def _add_manifest_entries(
        self,
        entries: Optional[list[str]],
        root: str,
        resource_type: ResourceType,
        target: dict,
        metadata: PathMetadata,
    ) -> None:
        if not entries:
            return
        all_files = self._collect_files_from_manifest_entries(
            entries, root, resource_type
        )
        patterns = [e for e in entries if _is_override_pattern(e)]
        enabled = _apply_patterns(all_files, patterns, root)
        for f in all_files:
            if f in enabled:
                self._add_resource(target, f, metadata, True)

    def _collect_files_from_manifest_entries(
        self,
        entries: list[str],
        root: str,
        resource_type: ResourceType,
    ) -> list[str]:
        """Resolve manifest entries to actual
        file paths. Supports ``**`` glob
        (Python's :mod:`glob` with
        ``recursive=True``). Mirrors
        ``collectFilesFromManifestEntries``
        (``package-manager.ts:1173-1192``)."""
        source_entries = [e for e in entries if not _is_override_pattern(e)]
        resolved: list[str] = []
        for entry in source_entries:
            if not _has_glob_pattern(entry):
                resolved.append(os.path.realpath(os.path.join(root, entry)))
                continue
            # Glob expansion (the OpenClaw
            # source uses ``fs.globSync``).
            # Python's :mod:`glob` with
            # ``recursive=True`` supports ``**``.
            from glob import glob
            for match in glob(entry, recursive=True, root_dir=root):
                resolved.append(os.path.realpath(os.path.join(root, match)))
        return self._filter_manifest_resource_paths(
            self._collect_files_from_paths(resolved, resource_type),
            root,
        )

    def _filter_manifest_resource_paths(self, paths: list[str], root: str) -> list[str]:
        resolved_root = os.path.realpath(root)
        real_root = self._realpath_if_possible(resolved_root)
        out: list[str] = []
        for path in paths:
            resolved_path = os.path.realpath(path)
            if not is_path_within_root(resolved_root, resolved_path):
                continue
            if not is_path_within_root(real_root, self._realpath_if_possible(resolved_path)):
                continue
            out.append(path)
        return out

    def _realpath_if_possible(self, path: str) -> str:
        try:
            return os.path.realpath(path)
        except (OSError, ValueError):
            return os.path.normpath(os.path.abspath(path))

    # ------------------------------------------------------------------
    # Internal: local entry resolution
    # ------------------------------------------------------------------

    def _resolve_local_entries(
        self,
        entries: list[str],
        resource_type: ResourceType,
        target: dict,
        metadata: PathMetadata,
        base_dir: str,
    ) -> None:
        """Resolve a list of local entries
        (paths + patterns). Mirrors
        ``resolveLocalEntries``
        (``package-manager.ts:1206-1229``)."""
        if not entries:
            return
        plain, patterns = _split_patterns(entries)
        resolved_plain = [self._resolve_path_from_base(p, base_dir) for p in plain]
        all_files = self._collect_files_from_paths(resolved_plain, resource_type)
        enabled = _apply_patterns(all_files, patterns, base_dir)
        for f in all_files:
            self._add_resource(target, f, metadata, f in enabled)

    def _collect_files_from_paths(
        self, paths: list[str], resource_type: ResourceType
    ) -> list[str]:
        files: list[str] = []
        for p in paths:
            if not os.path.exists(p):
                continue
            try:
                st = os.stat(p)
                if (st.st_mode & 0o170000) == 0o100000:
                    files.append(p)
                elif (st.st_mode & 0o170000) == 0o040000:
                    files.extend(_collect_resource_files(p, resource_type))
            except OSError:
                continue
        return files

    # ------------------------------------------------------------------
    # Internal: auto-discovery
    # ------------------------------------------------------------------

    def _add_auto_discovered_resources(
        self,
        accumulator: dict,
        global_settings: dict,
        project_settings: dict,
        global_base_dir: str,
        project_base_dir: str,
    ) -> None:
        """Auto-discover resources in the
        standard dirs. Mirrors
        ``addAutoDiscoveredResources``
        (``package-manager.ts:1231-1390``)."""
        user_metadata = PathMetadata(
            source="auto",
            scope="user",
            origin="top-level",
            baseDir=global_base_dir,
        )
        project_metadata = PathMetadata(
            source="auto",
            scope="project",
            origin="top-level",
            baseDir=project_base_dir,
        )
        user_overrides = {
            "extensions": global_settings.get("extensions") or [],
            "skills": global_settings.get("skills") or [],
            "prompts": global_settings.get("prompts") or [],
            "themes": global_settings.get("themes") or [],
        }
        project_overrides = {
            "extensions": project_settings.get("extensions") or [],
            "skills": project_settings.get("skills") or [],
            "prompts": project_settings.get("prompts") or [],
            "themes": project_settings.get("themes") or [],
        }
        user_dirs = {
            "extensions": os.path.join(global_base_dir, "extensions"),
            "skills": os.path.join(global_base_dir, "skills"),
            "prompts": os.path.join(global_base_dir, "prompts"),
            "themes": os.path.join(global_base_dir, "themes"),
        }
        project_dirs = {
            "extensions": os.path.join(project_base_dir, "extensions"),
            "skills": os.path.join(project_base_dir, "skills"),
            "prompts": os.path.join(project_base_dir, "prompts"),
            "themes": os.path.join(project_base_dir, "themes"),
        }
        user_agents_skills_dir = os.path.join(_get_home_dir(), ".agents", "skills")
        project_agents_skill_dirs = [
            d
            for d in _collect_ancestor_agents_skill_dirs(self.cwd)
            if os.path.realpath(d) != os.path.realpath(user_agents_skills_dir)
        ]

        def _add_resources(
            resource_type: ResourceType,
            paths: list[str],
            metadata: PathMetadata,
            overrides: list[str],
            base_dir: str,
        ) -> None:
            target = self._get_target_map(accumulator, resource_type)
            for path in paths:
                enabled = _is_enabled_by_overrides(path, overrides, base_dir)
                self._add_resource(target, path, metadata, enabled)

        # Project
        _add_resources(
            "extensions",
            _collect_auto_extension_entries(project_dirs["extensions"]),
            project_metadata,
            project_overrides["extensions"],
            project_base_dir,
        )
        _add_resources(
            "skills",
            _collect_skill_entries(project_dirs["skills"], "openclaw"),
            project_metadata,
            project_overrides["skills"],
            project_base_dir,
        )
        for agents_skills_dir in project_agents_skill_dirs:
            agents_base_dir = os.path.dirname(agents_skills_dir)
            agents_metadata = PathMetadata(
                source=project_metadata.source,
                scope=project_metadata.scope,
                origin=project_metadata.origin,
                baseDir=agents_base_dir,
            )
            _add_resources(
                "skills",
                _collect_skill_entries(agents_skills_dir, "agents"),
                agents_metadata,
                project_overrides["skills"],
                agents_base_dir,
            )
        _add_resources(
            "prompts",
            _collect_top_level_auto_resource_entries(project_dirs["prompts"], "prompts"),
            project_metadata,
            project_overrides["prompts"],
            project_base_dir,
        )
        _add_resources(
            "themes",
            _collect_top_level_auto_resource_entries(project_dirs["themes"], "themes"),
            project_metadata,
            project_overrides["themes"],
            project_base_dir,
        )
        # User
        _add_resources(
            "extensions",
            _collect_auto_extension_entries(user_dirs["extensions"]),
            user_metadata,
            user_overrides["extensions"],
            global_base_dir,
        )
        _add_resources(
            "skills",
            _collect_skill_entries(user_dirs["skills"], "openclaw"),
            user_metadata,
            user_overrides["skills"],
            global_base_dir,
        )
        user_agents_base_dir = os.path.dirname(user_agents_skills_dir)
        user_agents_metadata = PathMetadata(
            source=user_metadata.source,
            scope=user_metadata.scope,
            origin=user_metadata.origin,
            baseDir=user_agents_base_dir,
        )
        _add_resources(
            "skills",
            _collect_skill_entries(user_agents_skills_dir, "agents"),
            user_agents_metadata,
            user_overrides["skills"],
            user_agents_base_dir,
        )
        _add_resources(
            "prompts",
            _collect_top_level_auto_resource_entries(user_dirs["prompts"], "prompts"),
            user_metadata,
            user_overrides["prompts"],
            global_base_dir,
        )
        _add_resources(
            "themes",
            _collect_top_level_auto_resource_entries(user_dirs["themes"], "themes"),
            user_metadata,
            user_overrides["themes"],
            global_base_dir,
        )

    # ------------------------------------------------------------------
    # Internal: accumulator helpers
    # ------------------------------------------------------------------

    def _get_target_map(
        self, accumulator: dict, resource_type: ResourceType
    ) -> dict:
        return accumulator[resource_type]

    def _add_resource(
        self,
        target: dict,
        path: str,
        metadata: PathMetadata,
        enabled: bool,
    ) -> None:
        if not path:
            return
        if path not in target:
            target[path] = {"metadata": metadata, "enabled": enabled}

    def _create_accumulator(self) -> dict:
        return {
            "extensions": {},
            "skills": {},
            "prompts": {},
            "themes": {},
        }

    def _to_resolved_paths(self, accumulator: dict) -> ResolvedPaths:
        def _map_to_resolved(
            entries: dict,
        ) -> list[ResolvedResource]:
            resolved: list[ResolvedResource] = []
            for path, entry in entries.items():
                resolved.append(
                    ResolvedResource(
                        path=path,
                        enabled=entry["enabled"],
                        metadata=entry["metadata"],
                    )
                )
            # Sort by precedence (lower = higher
            # priority), preserving the OpenClaw
            # source's "first wins" ordering.
            resolved.sort(
                key=lambda r: _resource_precedence_rank(r.metadata)
            )
            # Dedupe by canonical path.
            seen: set[str] = set()
            unique: list[ResolvedResource] = []
            for entry in resolved:
                canonical = canonicalize_path(entry.path)
                if canonical in seen:
                    continue
                seen.add(canonical)
                unique.append(entry)
            return unique

        return ResolvedPaths(
            extensions=_map_to_resolved(accumulator["extensions"]),
            skills=_map_to_resolved(accumulator["skills"]),
            prompts=_map_to_resolved(accumulator["prompts"]),
            themes=_map_to_resolved(accumulator["themes"]),
        )

    # ------------------------------------------------------------------
    # Internal: dedupe + version check
    # ------------------------------------------------------------------

    def _installed_npm_matches_pinned_version(
        self, source: dict, installed_path: str
    ) -> bool:
        """Check whether the installed package
        matches the pinned version. Mirrors
        ``installedNpmMatchesPinnedVersion``
        (``package-manager.ts:847-859``)."""
        installed_version = self._get_installed_npm_version(installed_path)
        if not installed_version:
            return False
        pinned_version = source.get("version")
        if not pinned_version:
            return True
        return installed_version == pinned_version

    def _get_installed_npm_version(self, installed_path: str) -> Optional[str]:
        package_json_path = os.path.join(installed_path, "package.json")
        if not os.path.isfile(package_json_path):
            return None
        try:
            with open(package_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        return data.get("version")

    def _get_package_identity(self, source: str, scope: Optional[SourceScope] = None) -> str:
        """Get a unique package identity
        (project wins over user for the same
        package). Mirrors ``getPackageIdentity``
        (``package-manager.ts:881-895``)."""
        parsed = self._parse_source(source)
        if parsed["type"] == "npm":
            return f"npm:{parsed['name']}"
        if parsed["type"] == "git":
            git_src = parsed["git"]
            return f"git:{git_src.host}/{git_src.path}"
        if scope:
            base_dir = self._get_base_dir_for_scope(scope)
            return f"local:{self._resolve_path_from_base(parsed['path'], base_dir)}"
        return f"local:{self._resolve_path(parsed['path'])}"

    def _dedupe_packages(
        self, packages: list[dict]
    ) -> list[dict]:
        """Dedupe packages: project wins over
        user. Mirrors ``dedupePackages``
        (``package-manager.ts:901-922``)."""
        seen: dict[str, dict] = {}
        for entry in packages:
            source_str = (
                entry["pkg"]
                if isinstance(entry["pkg"], str)
                else entry["pkg"]["source"]
            )
            identity = self._get_package_identity(source_str, entry["scope"])
            existing = seen.get(identity)
            if not existing:
                seen[identity] = entry
            elif entry["scope"] == "project" and existing["scope"] == "user":
                seen[identity] = entry
        return list(seen.values())


# ============================================================================
# Internal: enabled-by-overrides check
# ============================================================================


def _is_enabled_by_overrides(
    file_path: str, patterns: list[str], base_dir: str
) -> bool:
    """Check whether a path is enabled by
    the override patterns. Mirrors
    ``isEnabledByOverrides``
    (``package-manager.ts:592-594``)."""
    return file_path in _apply_patterns(
        [file_path], [p for p in patterns if _is_override_pattern(p)], base_dir
    )


__all__ = [
    "CONFIG_DIR_NAME_PRIMARY",
    "CONFIG_DIR_NAME_ALIAS",
    "DefaultPackageManager",
    "FILE_PATTERNS",
    "GitSource",
    "MissingSourceAction",
    "OnMissingSource",
    "PackageFilter",
    "PackageManager",
    "PackageSource",
    "PathMetadata",
    "RESOURCE_TYPES",
    "ResourceType",
    "ResolvedPaths",
    "ResolvedResource",
    "SettingsScope",
    "SourceScope",
    "TopLevelAutoResourceType",
    "add_ignore_rules",
    "canonicalize_path",
    "is_local_path",
    "is_path_within_root",
    "is_real_path_within_root",
    "parse_git_url",
    "to_posix_path",
]
