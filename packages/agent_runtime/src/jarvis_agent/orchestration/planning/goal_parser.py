"""Goal parser and structured intent extractor."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any


@dataclass(frozen=True, slots=True)
class ParsedGoal:
    """Structured decomposition of a user goal statement."""

    raw_goal: str
    primary_intent: (
        str  # e.g. "BROWSE", "PLAY_MEDIA", "WRITE_FILE", "READ_FILE", "EXECUTE_TOOL", "GENERAL"
    )
    target_entities: list[str] = field(default_factory=list)
    constraints: dict[str, Any] = field(default_factory=dict)
    suggested_capabilities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class GoalParser:
    """Extracts intent, entities, and capability requirements from goal descriptions."""

    def parse(self, goal_text: str) -> ParsedGoal:
        text = goal_text.strip()
        lower = text.lower()

        entities: list[str] = []
        capabilities: list[str] = []
        intent = "GENERAL"

        # Check media / browser keywords
        if "youtube" in lower or "video" in lower or "play" in lower or "song" in lower:
            intent = "PLAY_MEDIA"
            capabilities.extend(["browser.navigate", "browser.click", "browser.interact"])
            # Extract video query if present
            m = re.search(
                r"(?:play|watch|find|search for)\s+(?:on youtube\s+)?(.*?)(?:\s+on youtube)?$",
                text,
                re.IGNORECASE,
            )
            if m and m.group(1).strip():
                entities.append(m.group(1).strip())
            else:
                entities.append(text)

        elif "read" in lower or "view" in lower or "inspect" in lower or "cat " in lower:
            intent = "READ_FILE"
            capabilities.append("filesystem.read")
            # Extract potential file names
            m = re.findall(r"[\w./\\-]+\.[a-zA-Z0-9]+", text)
            if m:
                entities.extend(m)

        elif "write" in lower or "create" in lower or "save" in lower or "output" in lower:
            intent = "WRITE_FILE"
            capabilities.append("filesystem.write")
            m = re.findall(r"[\w./\\-]+\.[a-zA-Z0-9]+", text)
            if m:
                entities.extend(m)

        elif "run" in lower or "execute" in lower or "test" in lower:
            intent = "EXECUTE_TOOL"
            capabilities.append("system.command")

        return ParsedGoal(
            raw_goal=text,
            primary_intent=intent,
            target_entities=entities,
            constraints={},
            suggested_capabilities=capabilities,
        )


__all__ = ["GoalParser", "ParsedGoal"]
