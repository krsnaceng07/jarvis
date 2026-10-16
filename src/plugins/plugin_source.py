"""jarvis.plugins.plugin_source — plugin install source specification resolution.

OpenClaw parity: mirrors
``openclaw-main/src/plugins/install-source-info.ts`` and
``openclaw-main/src/plugins/source-display.ts``.

Features:
- `SourceKind`: `"clawhub"`, `"npm"`, `"git"`, `"local"`, `"npm-pack"`, `"bundled"`.
- `ParsedPluginSourceSpec`: Dataclass containing parsed metadata (`kind`, `raw_spec`, `package_name`, `version`, `path`, `git_ref`).
- `parse_plugin_source_spec()`: Resolves raw CLI install specs like `clawhub:pkg@1.0`, `npm:@scope/pkg`, `git:repo@ref`, or `./local-path`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SourceKind = Literal["clawhub", "npm", "git", "local", "npm-pack", "bundled"]


@dataclass
class ParsedPluginSourceSpec:
    kind: SourceKind
    raw_spec: str
    package_name: str = ""
    version: str = ""
    path: str = ""
    git_ref: str = ""


def parse_plugin_source_spec(raw_spec: str) -> ParsedPluginSourceSpec:
    """Parse raw plugin spec string into structured source metadata."""
    if not raw_spec or not isinstance(raw_spec, str):
        return ParsedPluginSourceSpec(kind="local", raw_spec="", path="")

    spec = raw_spec.strip()

    # 1. clawhub:
    if spec.startswith("clawhub:"):
        rest = spec[len("clawhub:") :].strip()
        pkg_name = rest
        version = ""
        if "@" in rest:
            pkg_name, version = rest.rsplit("@", 1)
        return ParsedPluginSourceSpec(
            kind="clawhub",
            raw_spec=spec,
            package_name=pkg_name,
            version=version,
        )

    # 2. npm:
    if spec.startswith("npm:"):
        rest = spec[len("npm:") :].strip()
        pkg_name = rest
        version = ""
        if "@" in rest and not rest.startswith("@"):
            pkg_name, version = rest.rsplit("@", 1)
        elif rest.startswith("@") and rest.count("@") > 1:
            pkg_name, version = rest.rsplit("@", 1)
        return ParsedPluginSourceSpec(
            kind="npm",
            raw_spec=spec,
            package_name=pkg_name,
            version=version,
        )

    # 3. git:
    if spec.startswith("git:"):
        rest = spec[len("git:") :].strip()
        repo = rest
        ref = ""
        if "@" in rest:
            repo, ref = rest.rsplit("@", 1)
        return ParsedPluginSourceSpec(
            kind="git",
            raw_spec=spec,
            package_name=repo,
            git_ref=ref,
        )

    # 4. npm-pack:
    if spec.startswith("npm-pack:"):
        rest = spec[len("npm-pack:") :].strip()
        return ParsedPluginSourceSpec(
            kind="npm-pack",
            raw_spec=spec,
            path=rest,
        )

    # 5. Local paths: starts with ./, ../, /, or C:\
    if spec.startswith((".", "/", "\\")) or (len(spec) > 2 and spec[1] == ":"):
        return ParsedPluginSourceSpec(
            kind="local",
            raw_spec=spec,
            path=spec,
        )

    # Fallback default during launch cutover: npm package
    pkg_name = spec
    version = ""
    if "@" in spec and not spec.startswith("@"):
        pkg_name, version = spec.rsplit("@", 1)
    return ParsedPluginSourceSpec(
        kind="npm",
        raw_spec=spec,
        package_name=pkg_name,
        version=version,
    )


__all__ = [
    "ParsedPluginSourceSpec",
    "SourceKind",
    "parse_plugin_source_spec",
]
