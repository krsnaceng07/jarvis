"""jarvis.agents.lane_contract — specialist lane contract helpers.

OpenClaw parity: implements the Phase 1 "lane contracts" pattern described
in the OpenClaw parallel-specialist-lanes docs.

Each specialist lane (agent workspace) should have a ``LANE_CONTRACT.md``
that declares:

  Purpose       — what this lane owns
  Non-goals     — what to hand off
  Chat budget   — quick answers vs background work
  Handoff rule  — how to route to another lane
  Tool posture  — smallest tool surface policy

This module provides:

  ``LaneContract``              — typed dataclass for a lane contract
  ``render_lane_contract``      — render contract to Markdown
  ``write_lane_contract``       — write contract into an agent workspace
  ``read_lane_contract``        — parse contract from workspace LANE_CONTRACT.md
  ``DEFAULT_LANE_CONTRACT``     — minimal contract template
  ``build_lane_contract_prompt_block``
                                — inject contract into system prompt
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

LANE_CONTRACT_FILENAME = "LANE_CONTRACT.md"

# ---------------------------------------------------------------------------
# Data shape
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class LaneContract:
    """A structured specialist lane contract.

    Mirrors the contract template from OpenClaw's parallel-lanes docs.
    All fields are optional strings; callers fill what they know.
    """

    # What this lane owns
    owns: list[str] = field(default_factory=list)
    # Work to hand off to other lanes
    does_not_own: list[str] = field(default_factory=list)
    # Quick-answer policy vs background-work policy
    chat_budget: str = (
        "Answer quick questions directly. "
        "Execute interactive and user-visible work in the foreground. "
        "Use background workers only when the user asks for asynchronous work "
        "or a headless job must continue independently; never claim work is running "
        "unless it was actually started."
    )
    # Handoff instructions
    handoff: str = (
        "If another lane owns the request, reply with: "
        "target lane, objective, relevant context, exact next action."
    )
    # Tool usage posture
    tool_posture: str = (
        "Use the smallest tool surface that can complete the task. "
        "Avoid broad shell or network work unless this lane explicitly owns it."
    )
    # Free-form notes
    notes: str = ""


DEFAULT_LANE_CONTRACT = LaneContract(
    owns=["<job this lane is responsible for>"],
    does_not_own=["<work to hand off>"],
)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)
_BULLET_RE = re.compile(r"^- (.+)$", re.MULTILINE)


def _bullet_lines(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- (none)"


def render_lane_contract(contract: LaneContract) -> str:
    """Render *contract* to the canonical LANE_CONTRACT.md format.

    Matches the OpenClaw parallel-lanes docs template.
    """
    sections: list[str] = ["# Lane contract", ""]

    sections += ["## Owns", "", _bullet_lines(contract.owns), ""]
    sections += ["## Does not own", "", _bullet_lines(contract.does_not_own), ""]
    sections += ["## Chat budget", "", contract.chat_budget, ""]
    sections += ["## Handoff", "", contract.handoff, ""]
    sections += ["## Tool posture", "", contract.tool_posture, ""]

    if contract.notes.strip():
        sections += ["## Notes", "", contract.notes.strip(), ""]

    return "\n".join(sections)


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------


def write_lane_contract(workspace_dir: str | Path, contract: LaneContract) -> Path:
    """Write *contract* to ``<workspace_dir>/LANE_CONTRACT.md``.

    Creates the workspace directory if it does not exist.
    Returns the written path.
    """
    workspace = Path(workspace_dir)
    workspace.mkdir(parents=True, exist_ok=True)
    target = workspace / LANE_CONTRACT_FILENAME
    target.write_text(render_lane_contract(contract), encoding="utf-8")
    return target


def read_lane_contract(workspace_dir: str | Path) -> LaneContract | None:
    """Parse ``<workspace_dir>/LANE_CONTRACT.md`` into a :class:`LaneContract`.

    Returns ``None`` if the file is absent or unparseable.
    """
    target = Path(workspace_dir) / LANE_CONTRACT_FILENAME
    if not target.exists():
        return None
    try:
        text = target.read_text(encoding="utf-8")
        return _parse_lane_contract(text)
    except Exception:
        return None


def _parse_lane_contract(text: str) -> LaneContract:
    """Best-effort parse of the LANE_CONTRACT.md markdown format."""
    sections: dict[str, str] = {}
    current_heading: str | None = None
    current_lines: list[str] = []

    for line in text.splitlines():
        m = re.match(r"^##\s+(.+)$", line)
        if m:
            if current_heading is not None:
                sections[current_heading.lower().replace(" ", "_")] = "\n".join(
                    current_lines
                ).strip()
            current_heading = m.group(1).strip()
            current_lines = []
        elif current_heading is not None:
            current_lines.append(line)

    if current_heading is not None:
        sections[current_heading.lower().replace(" ", "_")] = "\n".join(current_lines).strip()

    def _bullets(key: str) -> list[str]:
        raw = sections.get(key, "")
        return [
            m.group(1).strip()
            for m in re.finditer(r"^- (.+)$", raw, re.MULTILINE)
            if m.group(1).strip() and m.group(1).strip() != "(none)"
        ]

    return LaneContract(
        owns=_bullets("owns"),
        does_not_own=_bullets("does_not_own"),
        chat_budget=sections.get("chat_budget", DEFAULT_LANE_CONTRACT.chat_budget),
        handoff=sections.get("handoff", DEFAULT_LANE_CONTRACT.handoff),
        tool_posture=sections.get("tool_posture", DEFAULT_LANE_CONTRACT.tool_posture),
        notes=sections.get("notes", ""),
    )


# ---------------------------------------------------------------------------
# System prompt injection
# ---------------------------------------------------------------------------


def build_lane_contract_prompt_block(contract: LaneContract) -> str:
    """Build the system-prompt block that injects the lane contract.

    Produces a compact, model-friendly representation of the contract
    suitable for inclusion at the start of the system prompt.
    """
    parts: list[str] = ["## Lane contract"]

    if contract.owns:
        parts.append("**Owns:** " + "; ".join(contract.owns))
    if contract.does_not_own:
        parts.append("**Does not own:** " + "; ".join(contract.does_not_own))
    if contract.chat_budget:
        parts.append(f"**Chat budget:** {contract.chat_budget}")
    if contract.handoff:
        parts.append(f"**Handoff:** {contract.handoff}")
    if contract.tool_posture:
        parts.append(f"**Tool posture:** {contract.tool_posture}")

    return "\n\n".join(parts)


__all__ = [
    "DEFAULT_LANE_CONTRACT",
    "LANE_CONTRACT_FILENAME",
    "LaneContract",
    "build_lane_contract_prompt_block",
    "read_lane_contract",
    "render_lane_contract",
    "write_lane_contract",
]
