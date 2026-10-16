"""jarvis.skills.skill_workshop — Governed path for creating and updating workspace skills.

OpenClaw parity: mirrors
``openclaw-main/docs/tools/skill-workshop.md`` and
``openclaw-main/src/skills/workshop/types.ts``.

Lifecycle:
create/update -> pending
revise        -> pending
evaluate      -> pending
apply         -> applied
reject        -> rejected
quarantine    -> quarantined
target change -> stale

Features:
- `SkillProposalStatus`: `"pending"` | `"applied"` | `"rejected"` | `"quarantined"` | `"stale"`
- `SkillWorkshopAction`: `"create"` | `"read"` | `"patch"` | `"update"` | `"revise"` | `"list"` | `"inspect"` | `"evaluate"` | `"apply"` | `"reject"` | `"quarantine"`
- `SkillProposalRecord`: Dataclass holding proposal details.
- Limits validation:
  - `DESCRIPTION_MAX_BYTES`: 160
  - `MAX_SKILL_BYTES`: 40000 (default, max 200000)
  - `MAX_SUPPORT_FILES`: 64
  - `ALLOWED_SUPPORT_DIRS`: `{"assets", "examples", "references", "scripts", "templates"}`
- `SkillWorkshopService`: Governed service handling proposal creation, revision, evaluation, and application.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

SkillProposalStatus = Literal["pending", "applied", "rejected", "quarantined", "stale"]
SkillWorkshopAction = Literal[
    "create",
    "read",
    "patch",
    "update",
    "revise",
    "list",
    "inspect",
    "evaluate",
    "apply",
    "reject",
    "quarantine",
]

DESCRIPTION_MAX_BYTES = 160
DEFAULT_MAX_SKILL_BYTES = 40000
HARD_MAX_SKILL_BYTES = 200000
MAX_SUPPORT_FILES = 64
ALLOWED_SUPPORT_DIRS = {"assets", "examples", "references", "scripts", "templates"}


@dataclass
class SupportFile:
    path: str
    content: str


@dataclass
class SkillProposalRecord:
    id: str
    name: str
    description: str
    content: str
    status: SkillProposalStatus = "pending"
    version: str = "v1"
    created_at: str = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    target_skill_name: str | None = None
    target_content_hash: str | None = None
    support_files: list[SupportFile] = field(default_factory=list)
    reason: str | None = None
    goal: str | None = None
    evidence: str | None = None


class SkillWorkshopService:
    """Governed service managing skill proposals and live workspace writes."""

    def __init__(self, workspace_dir: str | Path, max_skill_bytes: int = DEFAULT_MAX_SKILL_BYTES) -> None:
        self.workspace_dir = Path(workspace_dir).resolve()
        self.skills_dir = self.workspace_dir / "skills"
        self.max_skill_bytes = min(max_skill_bytes, HARD_MAX_SKILL_BYTES)
        self.proposals: dict[str, SkillProposalRecord] = {}

    def validate_proposal(self, description: str, content: str, support_files: list[SupportFile]) -> None:
        """Validate proposal limits and support file constraints."""
        if len(description.encode("utf-8")) > DESCRIPTION_MAX_BYTES:
            raise ValueError(f"Skill proposal description exceeds max length of {DESCRIPTION_MAX_BYTES} bytes")
        if len(content.encode("utf-8")) > self.max_skill_bytes:
            raise ValueError(f"Skill proposal content exceeds max length of {self.max_skill_bytes} bytes")
        if len(support_files) > MAX_SUPPORT_FILES:
            raise ValueError(f"Support file count exceeds max limit of {MAX_SUPPORT_FILES}")

        for sf in support_files:
            parts = Path(sf.path).parts
            if not parts or parts[0] not in ALLOWED_SUPPORT_DIRS:
                raise ValueError(f"Support file '{sf.path}' must be in one of: {ALLOWED_SUPPORT_DIRS}")

    def create_proposal(
        self,
        name: str,
        description: str,
        content: str,
        support_files: list[SupportFile] | None = None,
        goal: str | None = None,
        evidence: str | None = None,
    ) -> SkillProposalRecord:
        """Create a new pending skill proposal."""
        sf = support_files or []
        self.validate_proposal(description, content, sf)

        # Ensure target skill doesn't already exist for create
        target_path = self.skills_dir / name / "SKILL.md"
        if target_path.exists():
            raise ValueError(f"Target skill '{name}' already exists in workspace")

        proposal_id = f"proposal-{len(self.proposals) + 1}"
        record = SkillProposalRecord(
            id=proposal_id,
            name=name,
            description=description,
            content=content,
            status="pending",
            support_files=sf,
            goal=goal,
            evidence=evidence,
        )
        self.proposals[proposal_id] = record
        return record

    def apply_proposal(self, proposal_id: str, reason: str | None = None) -> SkillProposalRecord:
        """Apply a pending proposal to active workspace SKILL.md."""
        record = self.proposals.get(proposal_id)
        if not record:
            raise ValueError(f"Unknown proposal ID '{proposal_id}'")
        if record.status != "pending":
            raise ValueError(f"Proposal '{proposal_id}' is in '{record.status}' state and cannot be applied")

        # Write to workspace skills directory
        target_dir = self.skills_dir / record.name
        target_dir.mkdir(parents=True, exist_ok=True)

        target_file = target_dir / "SKILL.md"
        target_file.write_text(record.content, encoding="utf-8")

        # Write support files
        for sf in record.support_files:
            sp = target_dir / sf.path
            sp.parent.mkdir(parents=True, exist_ok=True)
            sp.write_text(sf.content, encoding="utf-8")

        record.status = "applied"
        record.reason = reason
        return record

    def reject_proposal(self, proposal_id: str, reason: str | None = None) -> SkillProposalRecord:
        """Reject a pending proposal."""
        record = self.proposals.get(proposal_id)
        if not record:
            raise ValueError(f"Unknown proposal ID '{proposal_id}'")
        if record.status != "pending":
            raise ValueError(f"Proposal '{proposal_id}' is in '{record.status}' state and cannot be rejected")

        record.status = "rejected"
        record.reason = reason
        return record


__all__ = [
    "ALLOWED_SUPPORT_DIRS",
    "DEFAULT_MAX_SKILL_BYTES",
    "DESCRIPTION_MAX_BYTES",
    "HARD_MAX_SKILL_BYTES",
    "MAX_SUPPORT_FILES",
    "SkillProposalRecord",
    "SkillProposalStatus",
    "SkillWorkshopAction",
    "SkillWorkshopService",
    "SupportFile",
]
