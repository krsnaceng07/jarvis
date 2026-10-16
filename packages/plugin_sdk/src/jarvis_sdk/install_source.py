"""jarvis_sdk.install_source -- Typed install-source spec for the plugin install pipeline.

Mirrors OpenClaw's ``install-source-info.ts`` and the source-normalisation
helpers inside ``marketplace.ts``.

A raw user-supplied spec string (``"./my-ext"``, ``"user/repo"``,
``"git+https://..."``, ``"clawhub:my-pkg"``, ``"marketplace:src:name"``) is
parsed into one of the typed ``InstallSource`` variants so that the install
dispatcher can switch on kind without re-parsing strings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


# -- source variants -------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LocalPathSource:
    """Extension is at a local filesystem path."""

    kind: Literal["local-path"] = "local-path"
    path: str = ""
    link: bool = False


@dataclass(frozen=True, slots=True)
class GitSource:
    """Clone from any git URL (ssh, https, git@)."""

    kind: Literal["git"] = "git"
    url: str = ""
    ref: str | None = None
    subdir: str | None = None


@dataclass(frozen=True, slots=True)
class GitHubSource:
    """Shorthand ``owner/repo`` resolved to https://github.com/<owner>/<repo>.git."""

    kind: Literal["github"] = "github"
    repo: str = ""
    ref: str | None = None
    subdir: str | None = None


@dataclass(frozen=True, slots=True)
class MarketplaceSource:
    """Install a named plugin from a marketplace manifest."""

    kind: Literal["marketplace"] = "marketplace"
    marketplace: str = ""
    plugin: str = ""


@dataclass(frozen=True, slots=True)
class ClawHubSource:
    """Future: install from the ClawHub hosted registry (``clawhub:<pkg>``)."""

    kind: Literal["clawhub"] = "clawhub"
    spec: str = ""


@dataclass(frozen=True, slots=True)
class NpmSource:
    """Future: install from npm (``npm:<pkg>``)."""

    kind: Literal["npm"] = "npm"
    spec: str = ""


InstallSource = (
    LocalPathSource | GitSource | GitHubSource | MarketplaceSource | ClawHubSource | NpmSource
)


# -- helper predicates (ported from marketplace.ts) ------------------------

_GIT_URL_RE = re.compile(
    r"^git@|^ssh://|^https?://.+\.git(#.*)?$",
    re.IGNORECASE,
)

_GITHUB_SHORTHAND_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:#.+)?$")


def is_git_url(value: str) -> bool:
    """Return True if *value* looks like a git remote URL.

    Mirrors ``isGitUrl()`` from ``marketplace.ts``.
    """
    return bool(_GIT_URL_RE.match(value.strip()))


def looks_like_github_shorthand(value: str) -> bool:
    """Return True for ``owner/repo[#ref]`` style specs.

    Mirrors ``looksLikeGitHubRepoShorthand()`` from ``marketplace.ts``.
    """
    return bool(_GITHUB_SHORTHAND_RE.match(value.strip()))


def split_ref(value: str) -> tuple[str, str | None]:
    """Split ``base[#ref]`` into ``(base, ref | None)``.

    Mirrors ``splitRef()`` from ``marketplace.ts``.
    """
    trimmed = value.strip()
    idx = trimmed.rfind("#")
    if idx <= 0 or idx >= len(trimmed) - 1:
        return trimmed, None
    return trimmed[:idx], trimmed[idx + 1 :] or None


def normalize_git_clone_source(
    spec: str,
) -> tuple[str, str | None, str] | None:
    """Resolve *spec* to ``(clone_url, ref, label)`` or ``None``.

    Mirrors ``normalizeGitCloneSource()`` from ``marketplace.ts``.
    """
    base, ref = split_ref(spec)

    if looks_like_github_shorthand(base):
        url = f"https://github.com/{base}.git"
        return url, ref, base

    if is_git_url(spec):
        return base, ref, base

    if base.startswith("https://") or base.startswith("http://"):
        try:
            from urllib.parse import urlparse

            parsed = urlparse(base)
            if parsed.hostname == "github.com":
                parts = [p for p in parsed.path.rstrip("/").split("/") if p]
                if len(parts) >= 2:
                    repo_name = parts[1].removesuffix(".git")
                    repo = f"{parts[0]}/{repo_name}"
                    url = f"https://github.com/{repo}.git"
                    return url, ref, repo
        except Exception:  # noqa: BLE001
            pass

    return None


# -- spec string parser -----------------------------------------------------


def parse_install_spec(spec: str, *, link: bool = False) -> InstallSource:
    """Parse a raw install spec string into a typed ``InstallSource``.

    Priority order (mirrors OpenClaw's ``management-mutations.ts`` dispatch):

    1. ``clawhub:<pkg>``            -> :class:`ClawHubSource`
    2. ``npm:<pkg>``                -> :class:`NpmSource`
    3. ``git+<url>``                -> :class:`GitSource`
    4. ``marketplace:<src>:<name>`` -> :class:`MarketplaceSource`
    5. GitHub shorthand             -> :class:`GitHubSource`
    6. SSH / HTTPS git URL          -> :class:`GitSource`
    7. Everything else              -> :class:`LocalPathSource`
    """
    s = spec.strip()

    if s.startswith("clawhub:"):
        return ClawHubSource(spec=s[len("clawhub:") :])

    if s.startswith("npm:"):
        return NpmSource(spec=s[len("npm:") :])

    if s.startswith("git+"):
        raw_url = s[len("git+") :]
        url, ref = split_ref(raw_url)
        return GitSource(url=url, ref=ref)

    if s.startswith("marketplace:"):
        rest = s[len("marketplace:") :]
        last_colon = rest.rfind(":")
        if last_colon > 0:
            marketplace = rest[:last_colon]
            plugin = rest[last_colon + 1 :]
        else:
            marketplace = rest
            plugin = ""
        return MarketplaceSource(marketplace=marketplace, plugin=plugin)

    if looks_like_github_shorthand(s):
        base, ref = split_ref(s)
        parts = base.split("/")
        if len(parts) > 2:
            repo = "/".join(parts[:2])
            subdir = "/".join(parts[2:])
        else:
            repo = base
            subdir = None
        return GitHubSource(repo=repo, ref=ref, subdir=subdir)

    if is_git_url(s):
        url, ref = split_ref(s)
        return GitSource(url=url, ref=ref)

    return LocalPathSource(path=s, link=link)


__all__ = [
    "InstallSource",
    "LocalPathSource",
    "GitSource",
    "GitHubSource",
    "MarketplaceSource",
    "ClawHubSource",
    "NpmSource",
    "is_git_url",
    "looks_like_github_shorthand",
    "split_ref",
    "normalize_git_clone_source",
    "parse_install_spec",
]
