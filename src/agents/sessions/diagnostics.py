"""jarvis.agents.sessions.diagnostics — resource diagnostic types.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/diagnostics.ts``.

Describes collisions and warnings discovered while
loading extensions, skills, prompts, and themes.

Parity
======
- ``ResourceCollision`` dataclass
  (``diagnostics.ts:6-13``):
  - ``resource_type`` (literal):
    ``"extension" | "skill" | "prompt" | "theme"``
  - ``name`` (str): skill / command / tool / flag /
    prompt / theme name
  - ``winner_path`` (str): the resource that won the
    collision
  - ``loser_path`` (str): the resource that was
    shadowed
  - ``winner_source`` (str | None)
  - ``loser_source`` (str | None)
- ``ResourceDiagnostic`` dataclass
  (``diagnostics.ts:15-20``):
  - ``type`` (literal): ``"warning" | "error" | "collision"``
  - ``message`` (str)
  - ``path`` (str | None) — optional path of the
    offending resource
  - ``collision`` (``ResourceCollision`` | None) — the
    collision detail, when ``type == "collision"``

Phase 6.0 — scaffolding + helpers + small types.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


#: Type of resource that collided. Mirrors
#: ``resourceType`` (``diagnostics.ts:7``).
ResourceType = Literal["extension", "skill", "prompt", "theme"]


#: Severity of a diagnostic. Mirrors ``type``
#: (``diagnostics.ts:16``).
DiagnosticType = Literal["warning", "error", "collision"]


@dataclass(frozen=True, slots=True)
class ResourceCollision:
    """Two resources with the same name from different
    sources. Mirrors ``ResourceCollision``
    (``diagnostics.ts:6-13``).

    Attributes
    ----------
    resource_type : ResourceType
        Kind of resource that collided.
    name : str
        Skill name, command/tool/flag name, prompt name,
        or theme name.
    winner_path : str
        Filesystem path of the resource that won the
        collision (the active one).
    loser_path : str
        Filesystem path of the resource that was
        shadowed.
    winner_source : str | None
        e.g. ``"npm:foo"``, ``"git:..."``, ``"local"``.
    loser_source : str | None
        Same shape as ``winner_source`` for the
        shadowed entry.
    """

    resource_type: ResourceType
    name: str
    winner_path: str
    loser_path: str
    winner_source: str | None = None
    loser_source: str | None = None


@dataclass(frozen=True, slots=True)
class ResourceDiagnostic:
    """A single diagnostic emitted while loading
    extensions / skills / prompts / themes. Mirrors
    ``ResourceDiagnostic`` (``diagnostics.ts:15-20``).

    Attributes
    ----------
    type : DiagnosticType
        Severity — ``"warning"``, ``"error"``, or
        ``"collision"``.
    message : str
        Human-readable diagnostic message.
    path : str | None
        Filesystem path of the offending resource, if
        applicable.
    collision : ResourceCollision | None
        Set when ``type == "collision"``; describes
        the two clashing resources.
    """

    type: DiagnosticType
    message: str
    path: str | None = None
    collision: ResourceCollision | None = None


__all__ = [
    "DiagnosticType",
    "ResourceCollision",
    "ResourceDiagnostic",
    "ResourceType",
]
