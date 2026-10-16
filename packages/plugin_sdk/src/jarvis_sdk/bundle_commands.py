"""Bundle command markdown loader.

Exact Python port of the relevant parts of OpenClaw's
``src/plugins/bundle-commands.ts``.

Claude ``commands/`` and Cursor ``.cursor/commands/`` markdown files are
treated as skill roots.  This module walks those roots, strips YAML
frontmatter, and wraps each markdown file as a ``SkillDecl``.

Hook packs, settings, and MCP are handled elsewhere.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from .bundle_manifest import BundleManifest

_log = logging.getLogger("jarvis_sdk.bundle_commands")

_MAX_COMMAND_BYTES = 1 * 1024 * 1024  # 1 MB per file
_FRONTMATTER_RE = re.compile(r"^\s*---\s*\n(.*?)\n---\s*\n", re.DOTALL)


# ── SkillDecl shim ─────────────────────────────────────────────────────────────
# We import SkillDecl lazily to avoid circular imports; fall back to a local
# dataclass with the same public shape so tests remain import-independent.


@dataclass
class _BundleSkillDecl:
    name: str
    content: str
    source: str
    plugin_id: str


def _make_skill_decl(
    name: str,
    content: str,
    source_path: str,
    plugin_id: str,
) -> object:
    """Return a skill declaration descriptor."""
    return _BundleSkillDecl(
        name=name,
        content=content,
        source=source_path,
        plugin_id=plugin_id,
    )


# ── Helpers ────────────────────────────────────────────────────────────────────


def _strip_frontmatter(text: str) -> str:
    """Remove a leading YAML frontmatter block (``---\\n…\\n---\\n``)."""
    m = _FRONTMATTER_RE.match(text)
    return text[m.end() :] if m else text


def _name_from_path(md_path: Path, root: Path) -> str:
    """Derive a human-readable skill name from a markdown file path.

    Mirrors OpenClaw's name extraction: strip the root prefix, drop the
    extension, replace ``-`` / ``_`` / ``/`` with spaces, then title-case.
    """
    try:
        rel = md_path.relative_to(root)
    except ValueError:
        rel = md_path
    # Drop `.md` extension, replace separators with spaces.
    stem = rel.with_suffix("").as_posix()
    name = re.sub(r"[-_/]+", " ", stem).strip()
    return name.title() if name else md_path.stem


def _list_markdown_files(root_dir: Path) -> list[Path]:
    """Recursively list all ``.md`` files in ``root_dir``, skipping dot-prefixed entries."""
    results: list[Path] = []
    pending = [root_dir]
    while pending:
        current = pending.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for entry in sorted(entries, key=lambda e: e.name):
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                pending.append(entry)
            elif entry.suffix == ".md":
                results.append(entry)
    return results


def _is_inside(base: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


# ── Public API ────────────────────────────────────────────────────────────────


def load_bundle_command_skills(
    root_dir: Path,
    bundle_manifest: BundleManifest,
) -> list[object]:
    """Load Claude/Cursor command markdown files as SkillDecl objects.

    Reads ``.md`` files from the bundle's ``skills`` roots (which already
    include the merged command roots resolved by :func:`load_bundle_manifest`),
    strips frontmatter, and wraps each as a SkillDecl.

    Returns an empty list if the bundle has no skill roots.
    """
    skills: list[object] = []

    for skill_root_rel in bundle_manifest.skills:
        skill_root = root_dir / skill_root_rel
        if not skill_root.is_dir():
            _log.debug(
                "bundle_commands: skill root %s does not exist; skipping",
                skill_root,
            )
            continue

        md_files = _list_markdown_files(skill_root)
        for md_path in md_files:
            # Boundary check — path must stay inside root_dir
            if not _is_inside(root_dir, md_path):
                _log.warning(
                    "bundle_commands: %s escapes plugin root %s; skipping",
                    md_path,
                    root_dir,
                )
                continue

            try:
                size = md_path.stat().st_size
            except OSError:
                continue
            if size > _MAX_COMMAND_BYTES:
                _log.warning(
                    "bundle_commands: %s exceeds max size (%d bytes); skipping",
                    md_path,
                    _MAX_COMMAND_BYTES,
                )
                continue

            try:
                raw_text = md_path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                _log.warning("bundle_commands: cannot read %s: %s", md_path, exc)
                continue

            content = _strip_frontmatter(raw_text)
            name = _name_from_path(md_path, skill_root)

            skill = _make_skill_decl(
                name=name,
                content=content,
                source_path=str(md_path),
                plugin_id=bundle_manifest.id,
            )
            skills.append(skill)

    _log.debug(
        "bundle_commands: loaded %d skills from bundle %s",
        len(skills),
        bundle_manifest.id,
    )
    return skills


__all__ = [
    "load_bundle_command_skills",
]
