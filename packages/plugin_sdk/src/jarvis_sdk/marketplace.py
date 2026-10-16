"""jarvis_sdk.marketplace -- Marketplace manifest loading and known-marketplace registry.

Mirrors OpenClaw's ``marketplace.ts``.

A *marketplace* is a JSON file listing community extension sources.  It can be
a local directory/file or a remote git repository.  This module handles:

- Parsing and validating ``marketplace.json`` / ``.jarvis-plugin/marketplace.json``.
- Cloning a remote marketplace repo into a temporary directory.
- Reading and writing ``~/.jarvis/plugins/known_marketplaces.json``
  (mirrors OpenClaw's ``CLAUDE_KNOWN_MARKETPLACES_PATH``).
- Resolving known-marketplace aliases to avoid install-time cycles.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .install_source import (
    normalize_git_clone_source,
    looks_like_github_shorthand,
    is_git_url,
)


# -- constants -------------------------------------------------------------

#: Mirrors OpenClaw's ``MARKETPLACE_MANIFEST_CANDIDATES``.
MANIFEST_CANDIDATES = (
    Path(".jarvis-plugin") / "marketplace.json",
    Path("marketplace.json"),
)

#: Mirrors OpenClaw's ``CLAUDE_KNOWN_MARKETPLACES_PATH``.
KNOWN_MARKETPLACES_PATH = Path.home() / ".jarvis" / "plugins" / "known_marketplaces.json"

DEFAULT_GIT_TIMEOUT_S = 120
MAX_MANIFEST_BYTES = 16 * 1024 * 1024


# -- types -----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MarketplaceEntryPathSource:
    kind: Literal["path"] = "path"
    path: str = ""


@dataclass(frozen=True, slots=True)
class MarketplaceEntryGitHubSource:
    kind: Literal["github"] = "github"
    repo: str = ""
    path: str | None = None
    ref: str | None = None


@dataclass(frozen=True, slots=True)
class MarketplaceEntryGitSource:
    kind: Literal["git"] = "git"
    url: str = ""
    path: str | None = None
    ref: str | None = None


@dataclass(frozen=True, slots=True)
class MarketplaceEntryGitSubdirSource:
    kind: Literal["git-subdir"] = "git-subdir"
    url: str = ""
    path: str = ""
    ref: str | None = None


@dataclass(frozen=True, slots=True)
class MarketplaceEntryUrlSource:
    kind: Literal["url"] = "url"
    url: str = ""


MarketplaceEntrySource = (
    MarketplaceEntryPathSource
    | MarketplaceEntryGitHubSource
    | MarketplaceEntryGitSource
    | MarketplaceEntryGitSubdirSource
    | MarketplaceEntryUrlSource
)


@dataclass(frozen=True, slots=True)
class MarketplacePluginEntry:
    name: str
    source: MarketplaceEntrySource
    version: str | None = None
    description: str | None = None


@dataclass(frozen=True, slots=True)
class MarketplaceManifest:
    plugins: list[MarketplacePluginEntry]
    name: str | None = None
    version: str | None = None
    source_label: str = "(unknown)"
    root_dir: str = ""
    origin: Literal["local", "remote"] = "local"


# -- source normalisation (mirrors normalizeEntrySource in marketplace.ts) -


def _str_or_none(value: Any) -> str | None:
    if isinstance(value, str):
        s = value.strip()
        return s if s else None
    return None


def _normalize_entry_source(raw: Any, source_label: str, entry_name: str) -> MarketplaceEntrySource:
    """Parse a single entry source field.  Raises ValueError on bad input."""

    def _err(msg: str) -> ValueError:
        return ValueError(f'invalid marketplace entry "{entry_name}" in {source_label}: {msg}')

    if isinstance(raw, str):
        trimmed = raw.strip()
        if not trimmed:
            raise _err("empty plugin source")
        if trimmed.startswith("http://") or trimmed.startswith("https://"):
            return MarketplaceEntryUrlSource(url=trimmed)
        return MarketplaceEntryPathSource(path=trimmed)

    if not isinstance(raw, dict):
        raise _err("plugin source must be a string or object")

    kind: str = _str_or_none(raw.get("type")) or _str_or_none(raw.get("source")) or ""
    if not kind:
        raise _err('plugin source object missing "type" or "source"')

    if kind == "path":
        p = _str_or_none(raw.get("path"))
        if not p:
            raise _err('path source missing "path"')
        return MarketplaceEntryPathSource(path=p)

    if kind == "github":
        repo = _str_or_none(raw.get("repo")) or _str_or_none(raw.get("url"))
        if not repo:
            raise _err('github source missing "repo"')
        return MarketplaceEntryGitHubSource(
            repo=repo,
            path=_str_or_none(raw.get("path")),
            ref=_str_or_none(raw.get("ref"))
            or _str_or_none(raw.get("branch"))
            or _str_or_none(raw.get("tag")),
        )

    if kind == "git":
        url = _str_or_none(raw.get("url")) or _str_or_none(raw.get("repo"))
        if not url:
            raise _err('git source missing "url"')
        return MarketplaceEntryGitSource(
            url=url,
            path=_str_or_none(raw.get("path")),
            ref=_str_or_none(raw.get("ref"))
            or _str_or_none(raw.get("branch"))
            or _str_or_none(raw.get("tag")),
        )

    if kind == "git-subdir":
        url = _str_or_none(raw.get("url")) or _str_or_none(raw.get("repo"))
        subpath = _str_or_none(raw.get("path")) or _str_or_none(raw.get("subdir"))
        if not url:
            raise _err('git-subdir source missing "url"')
        if not subpath:
            raise _err('git-subdir source missing "path"')
        return MarketplaceEntryGitSubdirSource(
            url=url,
            path=subpath,
            ref=_str_or_none(raw.get("ref"))
            or _str_or_none(raw.get("branch"))
            or _str_or_none(raw.get("tag")),
        )

    if kind == "url":
        url = _str_or_none(raw.get("url"))
        if not url:
            raise _err('url source missing "url"')
        return MarketplaceEntryUrlSource(url=url)

    raise _err(f"unsupported plugin source kind: {kind}")


# -- manifest parsing (mirrors parseMarketplaceManifest) -------------------


def parse_marketplace_manifest(
    raw: str, source_label: str, root_dir: str, origin: Literal["local", "remote"] = "local"
) -> MarketplaceManifest:
    """Parse and validate marketplace JSON.

    Raises ``ValueError`` on malformed input (mirrors OC's parse failures).
    """
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid marketplace JSON at {source_label}: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ValueError(f"invalid marketplace JSON at {source_label}: expected object")

    plugins_raw = parsed.get("plugins")
    if not isinstance(plugins_raw, list):
        raise ValueError(f"invalid marketplace JSON at {source_label}: missing plugins[]")

    plugins: list[MarketplacePluginEntry] = []
    for entry in plugins_raw:
        if not isinstance(entry, dict):
            raise ValueError(f"invalid marketplace entry in {source_label}: expected object")
        name = _str_or_none(entry.get("name"))
        if not name:
            raise ValueError(f"invalid marketplace entry in {source_label}: missing name")
        source = _normalize_entry_source(entry.get("source"), source_label, name)

        # Remote marketplaces: only path sources that are relative and inside root.
        if origin == "remote":
            if not isinstance(source, MarketplaceEntryPathSource):
                raise ValueError(
                    f'invalid marketplace entry "{name}" in {source_label}: '
                    f"remote marketplaces may not use {source.kind} plugin sources"
                )
            if source.path.startswith("http://") or source.path.startswith("https://"):
                raise ValueError(
                    f'invalid marketplace entry "{name}" in {source_label}: '
                    "remote marketplaces may not use HTTP(S) plugin paths"
                )
            if Path(source.path).is_absolute():
                raise ValueError(
                    f'invalid marketplace entry "{name}" in {source_label}: '
                    "remote marketplaces may only use relative plugin paths"
                )

        plugins.append(
            MarketplacePluginEntry(
                name=name,
                source=source,
                version=_str_or_none(entry.get("version")),
                description=_str_or_none(entry.get("description")),
            )
        )

    return MarketplaceManifest(
        plugins=plugins,
        name=_str_or_none(parsed.get("name")),
        version=_str_or_none(parsed.get("version")),
        source_label=source_label,
        root_dir=root_dir,
        origin=origin,
    )


# -- git clone (mirrors cloneMarketplaceRepo) ------------------------------


def _clone_marketplace_repo(
    source: str, timeout_s: int = DEFAULT_GIT_TIMEOUT_S
) -> tuple[str, str | None, str]:
    """Clone *source* into a temp directory.

    Returns ``(tmp_dir_to_cleanup, ref, label)``.
    Raises ``RuntimeError`` on failure.  The caller MUST remove *tmp_dir* with
    ``shutil.rmtree(tmp_dir, ignore_errors=True)`` even on exception.
    """
    normalized = normalize_git_clone_source(source)
    if normalized is None:
        raise RuntimeError(f"unsupported marketplace source: {source}")
    url, ref, label = normalized

    tmp_dir = tempfile.mkdtemp(prefix="jarvis-marketplace-")
    repo_dir = str(Path(tmp_dir) / "repo")

    argv = ["git", "clone"]
    # Shallow clone unless a commit SHA is given (commit SHAs can't be shallow-fetched directly).
    _is_commit_sha = bool(
        ref and len(ref) == 40 and all(c in "0123456789abcdefABCDEF" for c in ref)
    )
    if not ref or not _is_commit_sha:
        argv += ["--depth", "1"]
    if ref and not _is_commit_sha:
        argv += ["--branch", ref]
    argv += [url, repo_dir]

    result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout_s)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "git clone failed"
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise RuntimeError(f"failed to clone marketplace source {label}: {detail}")

    if _is_commit_sha and ref:
        checkout = subprocess.run(
            ["git", "switch", "--detach", "--", ref],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        if checkout.returncode != 0:
            detail = checkout.stderr.strip() or checkout.stdout.strip() or "git checkout failed"
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise RuntimeError(f"failed to checkout marketplace source {label}: {detail}")

    return tmp_dir, ref, label


# -- local source resolution -----------------------------------------------


def _resolve_local_marketplace(
    source: str,
) -> tuple[str, str] | None:
    """Return ``(manifest_path, root_dir)`` for a local source, or ``None``.

    Mirrors ``resolveLocalMarketplaceSource`` from ``marketplace.ts``.
    """
    resolved = Path(source).expanduser().resolve()
    if not resolved.exists():
        return None

    if resolved.is_file():
        root_dir = (
            resolved.parent.parent if resolved.parent.name == ".jarvis-plugin" else resolved.parent
        )
        return str(resolved), str(root_dir)

    if resolved.is_dir():
        root_dir = resolved.parent if resolved.name == ".jarvis-plugin" else resolved
        for candidate in MANIFEST_CANDIDATES:
            mp = root_dir / candidate
            if mp.exists():
                return str(mp), str(root_dir)

    return None


# -- top-level loader (mirrors loadMarketplace) ----------------------------


def load_marketplace(source: str) -> MarketplaceManifest:
    """Load a marketplace from a local path or remote git URL.

    Resolution order (mirrors OC's ``loadMarketplace``):

    1. Check ``known_marketplaces.json`` for an alias.
    2. Try local path.
    3. Clone as a git/GitHub repository.

    Raises ``RuntimeError`` on any failure.
    """
    known = read_known_marketplaces()
    visited: set[str] = set()
    current_source = source

    # Known-marketplace alias resolution (cycle-safe).
    while current_source in known:
        if current_source in visited:
            cycle = " -> ".join(visited) + " -> " + current_source
            raise RuntimeError(f"known marketplace source cycle: {cycle}")
        visited.add(current_source)
        current_source = known[current_source]

    local = _resolve_local_marketplace(current_source)
    if local is not None:
        manifest_path, root_dir = local
        raw = Path(manifest_path).read_text(encoding="utf-8")
        return parse_marketplace_manifest(raw, manifest_path, root_dir, origin="local")

    # Check if it looks like something git-cloneable.
    if not (
        looks_like_github_shorthand(current_source)
        or is_git_url(current_source)
        or current_source.startswith("https://")
    ):
        raise RuntimeError(f"marketplace source not found: {current_source}")

    tmp_dir, ref, label = _clone_marketplace_repo(current_source)
    try:
        repo_dir = Path(tmp_dir) / "repo"
        manifest_path = None
        for candidate in MANIFEST_CANDIDATES:
            mp = repo_dir / candidate
            if mp.exists():
                manifest_path = mp
                break
        if manifest_path is None:
            raise RuntimeError(f"marketplace manifest not found in {label}")
        raw = manifest_path.read_text(encoding="utf-8")
        return parse_marketplace_manifest(raw, label, str(repo_dir), origin="remote")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# -- known-marketplace registry (mirrors CLAUDE_KNOWN_MARKETPLACES_PATH) --


def read_known_marketplaces() -> dict[str, str]:
    """Read ``~/.jarvis/plugins/known_marketplaces.json`` → name → source mapping.

    Returns an empty dict if the file does not exist or is malformed.
    """
    if not KNOWN_MARKETPLACES_PATH.exists():
        return {}
    try:
        data = json.loads(KNOWN_MARKETPLACES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}


def write_known_marketplaces(mapping: dict[str, str]) -> None:
    """Write the known-marketplace registry atomically."""
    KNOWN_MARKETPLACES_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = KNOWN_MARKETPLACES_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(mapping, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(KNOWN_MARKETPLACES_PATH)


def resolve_marketplace_install_path(entry: MarketplacePluginEntry, root_dir: str) -> str | None:
    """Return the local filesystem path for a marketplace plugin entry's source.

    Only ``path`` sources are currently supported for install.  Other source
    kinds (git, url) will be supported once remote install is implemented.
    Returns ``None`` for unsupported/remote source kinds.
    """
    source = entry.source
    if isinstance(source, MarketplaceEntryPathSource):
        resolved = (Path(root_dir) / source.path).resolve()
        return str(resolved)
    return None


__all__ = [
    "MarketplaceManifest",
    "MarketplacePluginEntry",
    "MarketplaceEntrySource",
    "MarketplaceEntryPathSource",
    "MarketplaceEntryGitHubSource",
    "MarketplaceEntryGitSource",
    "MarketplaceEntryGitSubdirSource",
    "MarketplaceEntryUrlSource",
    "KNOWN_MARKETPLACES_PATH",
    "MANIFEST_CANDIDATES",
    "parse_marketplace_manifest",
    "load_marketplace",
    "read_known_marketplaces",
    "write_known_marketplaces",
    "resolve_marketplace_install_path",
]
