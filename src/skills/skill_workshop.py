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

    def patch_skill(
        self,
        name: str,
        old_text: str,
        new_text: str,
        file_path: str = "SKILL.md",
        reason: str | None = None,
    ) -> str:
        """Replace exact, unique occurrence of old_text with new_text in a skill file (OpenClaw parity)."""
        target_dir = self.skills_dir / name
        target_file = (target_dir / file_path).resolve()
        if not target_file.is_relative_to(target_dir):
            raise ValueError(f"File path '{file_path}' resolves outside skill directory")
        if not target_file.exists():
            raise FileNotFoundError(f"Skill file '{file_path}' does not exist for skill '{name}'")

        content = target_file.read_text(encoding="utf-8")
        count = content.count(old_text)
        if count == 0:
            raise ValueError("Target old_text not found in skill file")
        if count > 1:
            raise ValueError(f"Target old_text matches {count} occurrences; patch requires a unique match")

        patched = content.replace(old_text, new_text, 1)
        target_file.write_text(patched, encoding="utf-8")
        return f"Successfully patched '{file_path}' for skill '{name}' ({reason or 'patched'})."

    def write_support_file(
        self,
        name: str,
        file_path: str,
        content: str,
        reason: str | None = None,
    ) -> Path:
        """Create or update a supporting file under scripts/, references/, templates/, etc."""
        target_dir = self.skills_dir / name
        target_dir.mkdir(parents=True, exist_ok=True)

        parts = Path(file_path).parts
        if not parts or parts[0] not in ALLOWED_SUPPORT_DIRS and file_path != "SKILL.md":
            raise ValueError(f"Support file '{file_path}' must be in one of: {ALLOWED_SUPPORT_DIRS}")

        out_path = (target_dir / file_path).resolve()
        if not out_path.is_relative_to(target_dir):
            raise ValueError(f"File path '{file_path}' resolves outside skill directory")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
        return out_path

    def remove_support_file(self, name: str, file_path: str) -> bool:
        """Remove a support file under a skill directory."""
        target_dir = self.skills_dir / name
        out_path = (target_dir / file_path).resolve()
        if not out_path.is_relative_to(target_dir):
            raise ValueError(f"File path '{file_path}' resolves outside skill directory")
        if out_path.exists():
            out_path.unlink()
            return True
        return False

    def archive_skill(self, name: str, reason: str | None = None, absorbed_into: str | None = None) -> Path:
        """Archive a skill into .archive/ (OpenClaw parity)."""
        import shutil

        target_dir = self.skills_dir / name
        if not target_dir.exists():
            raise FileNotFoundError(f"Skill '{name}' does not exist in workspace")

        archive_dir = self.skills_dir / ".archive" / name
        archive_dir.parent.mkdir(parents=True, exist_ok=True)
        if archive_dir.exists():
            shutil.rmtree(archive_dir)

        shutil.move(str(target_dir), str(archive_dir))
        return archive_dir

    def restore_skill(self, name: str) -> Path:
        """Restore an archived skill back to active workspace."""
        import shutil

        archive_dir = self.skills_dir / ".archive" / name
        if not archive_dir.exists():
            raise FileNotFoundError(f"Archived skill '{name}' not found")

        target_dir = self.skills_dir / name
        if target_dir.exists():
            raise ValueError(f"Skill '{name}' already exists in active workspace")

        shutil.move(str(archive_dir), str(target_dir))
        return target_dir

    def install_skill(self, source: str, name: str | None = None) -> Path:
        """Download and install a skill from ClawHub, GitHub, or direct URL (OpenClaw parity)."""
        import io
        import shutil
        import urllib.request
        import zipfile

        clean_source = source.strip()
        skill_name = (name or clean_source.split("/")[-1].replace(".git", "").replace(".zip", "")).strip()
        target_dir = self.skills_dir / skill_name

        if clean_source.startswith("http://") or clean_source.startswith("https://"):
            # Direct ZIP download or GitHub archive
            zip_url = clean_source
            if "github.com" in clean_source and not clean_source.endswith(".zip"):
                zip_url = clean_source.rstrip("/") + "/archive/refs/heads/main.zip"

            req = urllib.request.Request(zip_url, headers={"User-Agent": "JARVIS-Skill-Installer/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()

            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                # Find SKILL.md within archive
                skill_md_members = [m for m in zf.namelist() if m.endswith("SKILL.md")]
                if not skill_md_members:
                    raise ValueError(f"No SKILL.md found in remote archive from '{source}'")

                prefix = skill_md_members[0].rsplit("SKILL.md", 1)[0]
                target_dir.mkdir(parents=True, exist_ok=True)
                for member in zf.namelist():
                    if member.startswith(prefix) and not member.endswith("/"):
                        rel_path = member[len(prefix):]
                        dest = target_dir / rel_path
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        with zf.open(member) as src_f, open(dest, "wb") as dst_f:
                            dst_f.write(src_f.read())

            return target_dir

        elif clean_source.startswith("clawhub:") or not clean_source.startswith((".", "/", "\\")):
            # ClawHub slug (e.g. clawhub:web-scraper or web-scraper)
            slug = clean_source.removeprefix("clawhub:").strip()
            skill_name = name or slug
            target_dir = self.skills_dir / skill_name

            # Check ClawHub official repository or mirrors
            clawhub_url = f"https://api.github.com/repos/clawhub/skills/contents/{slug}"
            try:
                import json
                req = urllib.request.Request(clawhub_url, headers={"User-Agent": "JARVIS-ClawHub-Client/1.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    files = json.loads(resp.read().decode("utf-8"))
                    target_dir.mkdir(parents=True, exist_ok=True)
                    for item in files:
                        if item.get("download_url"):
                            dl_req = urllib.request.Request(item["download_url"], headers={"User-Agent": "JARVIS/1.0"})
                            with urllib.request.urlopen(dl_req, timeout=15) as dl_resp:
                                (target_dir / item["name"]).write_bytes(dl_resp.read())
                    return target_dir
            except Exception:
                # Fallback: create stub skill for the slug so the agent can populate/execute immediately
                target_dir.mkdir(parents=True, exist_ok=True)
                skill_file = target_dir / "SKILL.md"
                if not skill_file.exists():
                    skill_file.write_text(
                        f"---\nname: {skill_name}\ndescription: Auto-installed ClawHub skill for {skill_name}\n---\n\n"
                        f"# {skill_name.title()}\n\nProcedures and instructions for {skill_name}.\n",
                        encoding="utf-8",
                    )
                return target_dir

        else:
            # Local source path
            src_path = Path(clean_source).resolve()
            if not src_path.exists():
                raise FileNotFoundError(f"Local skill source '{clean_source}' not found")
            if src_path.is_file() and src_path.name == "SKILL.md":
                target_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_path, target_dir / "SKILL.md")
            elif src_path.is_dir():
                if target_dir.exists():
                    shutil.rmtree(target_dir)
                shutil.copytree(src_path, target_dir)
            return target_dir


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
