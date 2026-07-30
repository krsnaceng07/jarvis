"""jarvis.agents.sessions.source_info — source metadata helpers.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/source-info.ts``.

Tracks where prompts, skills, and extension-provided
assets came from for diagnostics and UI.

Parity
======
- ``SourceScope = "user" | "project" | "temporary"``
  (``source-info.ts:8``).
- ``SourceOrigin = "package" | "top-level"``
  (``source-info.ts:9``).
- ``SourceInfo`` dataclass with ``path``, ``source``,
  ``scope``, ``origin``, ``base_dir?``
  (``source-info.ts:11-17``).
- ``create_source_info(path, metadata) -> SourceInfo``
  (``source-info.ts:20-28``) — converts
  package-manager path metadata into the session
  source-info shape.
- ``create_synthetic_source_info(path, options) -> SourceInfo``
  (``source-info.ts:31-46``) — builds source metadata
  for generated / synthetic session entries.

Phase 6.0 — scaffolding + helpers + small types.

Naming note
-----------
The OpenClaw file is ``source-info.ts`` (kebab-case);
the Python port uses ``source_info.py`` (snake-case)
per the existing JARVIS convention. The public symbols
remain identical so callers import from the same
logical path.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypedDict


#: Mirrors ``SourceScope`` (``source-info.ts:8``).
SourceScope = Literal["user", "project", "temporary"]

#: Mirrors ``SourceOrigin`` (``source-info.ts:9``).
SourceOrigin = Literal["package", "top-level"]


class _PathMetadataOptional(TypedDict, total=False):
    """Optional fields accepted by the package-manager
    ``PathMetadata`` shape. The full type lives in
    ``package_manager.py`` (Phase 6.11) but we declare
    the subset we need here so this module stays
    dependency-free in Phase 6.0.
    """

    baseDir: str | None  # noqa: N815 (TS field name)


class PathMetadata(TypedDict):
    """Subset of the package-manager ``PathMetadata``
    shape consumed by ``create_source_info``. Mirrors
    the fields read in ``source-info.ts:21-27``.
    """

    source: str
    scope: SourceScope
    origin: SourceOrigin
    baseDir: str | None  # noqa: N815


@dataclass(frozen=True, slots=True)
class SourceInfo:
    """Mirrors ``SourceInfo`` (``source-info.ts:11-17``).

    Tracks where a prompt / skill / extension-provided
    asset came from. Frozen dataclass matches the
    JARVIS convention for value types.

    Attributes
    ----------
    path : str
        Filesystem path to the resource.
    source : str
        Where the resource was loaded from (e.g.
        ``"npm:foo"``, ``"git:..."``, ``"local"``).
    scope : SourceScope
        Where the resource lives (user / project / temporary).
    origin : SourceOrigin
        Whether the resource was installed as part of a
        package or top-level.
    base_dir : str | None
        Optional base directory of the package
        (present when ``origin == "package"``).
    """

    path: str
    source: str
    scope: SourceScope
    origin: SourceOrigin
    base_dir: str | None = None


def create_source_info(path: str, metadata: PathMetadata) -> SourceInfo:
    """Convert package-manager path metadata into the
    session source-info shape.

    Mirrors ``createSourceInfo``
    (``source-info.ts:20-28``).

    Parameters
    ----------
    path : str
        Filesystem path of the resource.
    metadata : PathMetadata
        The package-manager metadata to project.

    Returns
    -------
    SourceInfo
        The source-info shape, with ``base_dir`` left as
        ``None`` if the metadata did not include one.
    """
    return SourceInfo(
        path=path,
        source=metadata["source"],
        scope=metadata["scope"],
        origin=metadata["origin"],
        base_dir=metadata.get("baseDir"),
    )


def create_synthetic_source_info(
    path: str,
    options: dict,
) -> SourceInfo:
    """Build source metadata for generated or synthetic
    session entries.

    Mirrors ``createSyntheticSourceInfo``
    (``source-info.ts:31-46``). Defaults to
    ``scope="temporary"`` and ``origin="top-level"``
    when the caller does not provide them — matches
    the OpenClaw ``??`` fallbacks.

    The OpenClaw source uses an inline TS object type
    for ``options`` (``{source, scope?, origin?,
    baseDir?}``). The Python port accepts a plain
    ``dict`` with the same shape so the runtime check
    is identical.
    """
    return SourceInfo(
        path=path,
        source=options["source"],
        scope=options.get("scope", "temporary"),
        origin=options.get("origin", "top-level"),
        base_dir=options.get("base_dir"),
    )


__all__ = [
    "PathMetadata",
    "SourceInfo",
    "SourceOrigin",
    "SourceScope",
    "create_source_info",
    "create_synthetic_source_info",
]
