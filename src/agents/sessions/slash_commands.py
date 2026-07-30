"""jarvis.agents.sessions.slash_commands — slash command metadata registry.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/slash-commands.ts``.

Defines built-in command metadata and the source shape
used by prompts, skills, and extensions.

Parity
======
- ``SlashCommandSource`` literal: ``"extension" | "prompt" | "skill"``
  (``slash-commands.ts:8``).
- ``SlashCommandInfo`` dataclass with ``name``,
  ``description?``, ``source``, ``source_info``
  (``slash-commands.ts:10-15``).

Phase 6.0 — scaffolding + helpers + small types.

Note
----
The OpenClaw file currently only defines the *shape*;
the actual built-in command table is registered by
extensions. The Python port keeps the same surface so
later phases (PromptTemplate + ResourceLoader) can
populate it the same way.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .source_info import SourceInfo


#: Where a slash command was registered. Mirrors
#: ``SlashCommandSource`` (``slash-commands.ts:8``).
SlashCommandSource = Literal["extension", "prompt", "skill"]


@dataclass(frozen=True, slots=True)
class SlashCommandInfo:
    """Slash-command metadata. Mirrors
    ``SlashCommandInfo`` (``slash-commands.ts:10-15``).

    Attributes
    ----------
    name : str
        The slash-command name (without leading ``/``).
    description : str | None
        Optional user-facing help text.
    source : SlashCommandSource
        Where the command came from.
    source_info : SourceInfo
        The source metadata for diagnostics + UI
        breadcrumbs.
    """

    name: str
    description: str | None
    source: SlashCommandSource
    source_info: SourceInfo


__all__ = [
    "SlashCommandInfo",
    "SlashCommandSource",
]
