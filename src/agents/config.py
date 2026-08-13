"""jarvis.agents.config — agent package paths + config.

OpenClaw parity: mirrors
``openclaw-main/src/agents/config.ts`` (the
path-getter surface used by the system-prompt
builder: ``getPackageDir`` / ``getReadmePath`` /
``getDocsPath`` / ``getExamplesPath``,
``config.ts:37-84``).

Adaptations
-----------
- The OpenClaw source's package-dir discovery walks
  up from the compiled module until it finds a
  ``package.json`` (Node) or uses the Bun binary
  dir. The Python port walks up from this module
  until it finds a ``pyproject.toml`` **or**
  ``package.json`` (the JARVIS repo root carries
  both markers in different layouts).
- The env override ``OPENCLAW_PACKAGE_DIR``
  (``config.ts:39``) is honoured as
  ``JARVIS_PACKAGE_DIR`` first, then
  ``OPENCLAW_PACKAGE_DIR`` for drop-in parity.
"""
from __future__ import annotations

import os
from pathlib import Path


def get_package_dir() -> str:
    """Return the package root dir. Mirrors
    ``getPackageDir`` (``config.ts:37-64``):
    env override first (``~`` expansion
    included), else walk up until a package
    marker is found, else fall back to the
    current dir."""
    for env_name in ("JARVIS_PACKAGE_DIR", "OPENCLAW_PACKAGE_DIR"):
        env_dir = os.environ.get(env_name)
        if env_dir:
            if env_dir == "~":
                return str(Path.home())
            if env_dir.startswith("~/"):
                return str(Path.home()) + env_dir[1:]
            return env_dir
    # Walk up from this module until we find a
    # package marker (ts:55-61 — package.json;
    # the Python port also accepts
    # pyproject.toml).
    current = Path(__file__).resolve().parent
    d = current
    while d != d.parent:
        if (d / "pyproject.toml").exists() or (d / "package.json").exists():
            return str(d)
        d = d.parent
    # Fallback (shouldn't happen) — ts:63.
    return str(current)


def get_readme_path() -> str:
    """Path to README.md. Mirrors
    ``getReadmePath`` (``config.ts:72-74``)."""
    return str(Path(get_package_dir()) / "README.md")


def get_docs_path() -> str:
    """Path to the docs directory. Mirrors
    ``getDocsPath`` (``config.ts:77-79``)."""
    return str(Path(get_package_dir()) / "docs")


def get_examples_path() -> str:
    """Path to the examples directory. Mirrors
    ``getExamplesPath`` (``config.ts:82-84``)."""
    return str(Path(get_package_dir()) / "examples")


__all__ = [
    "get_docs_path",
    "get_examples_path",
    "get_package_dir",
    "get_readme_path",
]
