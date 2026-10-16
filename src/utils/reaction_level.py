"""jarvis.utils.reaction_level — resolve reaction-level config.

OpenClaw parity: mirrors ``openclaw-main/src/utils/reaction-level.ts``.

Public surface:

- :class:`ReactionLevel`
- :class:`ResolvedReactionLevel`
- :func:`resolve_reaction_level`
"""
from __future__ import annotations

from typing import Any, Literal, Optional


ReactionLevel = str  # "off" | "ack" | "minimal" | "extensive"

_LEVELS = frozenset({"off", "ack", "minimal", "extensive"})


class ResolvedReactionLevel:
    """Expanded reaction flags consumed by runtime delivery + prompt guidance."""

    def __init__(
        self,
        level: str = "off",
        ack_enabled: bool = False,
        agent_reactions_enabled: bool = False,
        agent_reaction_guidance: Optional[str] = None,
    ) -> None:
        self.level = level
        self.ack_enabled = ack_enabled
        self.agent_reactions_enabled = agent_reactions_enabled
        self.agent_reaction_guidance = agent_reaction_guidance

    def to_dict(self) -> dict:
        out = {
            "level": self.level,
            "ackEnabled": self.ack_enabled,
            "agentReactionsEnabled": self.agent_reactions_enabled,
        }
        if self.agent_reaction_guidance is not None:
            out["agentReactionGuidance"] = self.agent_reaction_guidance
        return out


def _parse_level(value: Any) -> tuple[Literal["ok", "missing", "invalid"], Optional[str]]:
    """Returns 'ok', 'missing', or 'invalid' plus the parsed value when ok."""
    if value is None:
        return ("missing", None)
    if not isinstance(value, str):
        return ("invalid", None)
    trimmed = value.strip()
    if not trimmed:
        return ("missing", None)
    if trimmed in _LEVELS:
        return ("ok", trimmed)
    return ("invalid", None)


def resolve_reaction_level(params: dict) -> ResolvedReactionLevel:
    """Resolve raw reaction config into ACK + agent-reaction runtime flags.

    Mirrors :func:`resolveReactionLevel` (``utils/reaction-level.ts``).
    """
    parsed_kind, parsed_value = _parse_level(params.get("value"))
    if parsed_kind == "ok":
        effective = parsed_value
    elif parsed_kind == "missing":
        effective = params.get("defaultLevel", "off")
    else:
        effective = params.get("invalidFallback", "ack")
    if effective == "off":
        return ResolvedReactionLevel(level="off")
    if effective == "ack":
        return ResolvedReactionLevel(level="ack", ack_enabled=True)
    if effective == "minimal":
        return ResolvedReactionLevel(
            level="minimal",
            agent_reactions_enabled=True,
            agent_reaction_guidance="minimal",
        )
    if effective == "extensive":
        return ResolvedReactionLevel(
            level="extensive",
            agent_reactions_enabled=True,
            agent_reaction_guidance="extensive",
        )
    return ResolvedReactionLevel(
        level="minimal",
        agent_reactions_enabled=True,
        agent_reaction_guidance="minimal",
    )


__all__ = [
    "ReactionLevel",
    "ResolvedReactionLevel",
    "resolve_reaction_level",
]
