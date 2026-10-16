"""jarvis.agents.sessions.tools.skill_workshop_tool — Dynamic Skill Workshop Tool.

OpenClaw parity: mirrors OpenClaw's skill_workshop tool
for creating, evaluating, and applying declarative skills to the workspace.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from src.skills.skill_workshop import (
    SkillWorkshopService,
)
from ..extensions.types import AgentToolResult, ToolDefinition


def create_skill_workshop_tool_definition(
    cwd: str = "",
    options: Optional[dict] = None,
) -> ToolDefinition:
    """Build the ToolDefinition for the skill_workshop tool."""
    options = options or {}
    workspace_dir = cwd or options.get("workspace_dir") or os.getcwd()
    service = SkillWorkshopService(workspace_dir=workspace_dir)

    async def _execute(
        tool_call_id: str,
        params: dict,
        signal: object = None,
        on_update: object = None,
        ctx: object = None,
    ) -> AgentToolResult:
        if signal is not None and getattr(signal, "is_set", lambda: False)():
            raise RuntimeError("Operation aborted")

        action = params.get("action", "list")
        skill_name = params.get("name") or params.get("skill_name") or ""
        proposal_id = params.get("proposal_id") or params.get("proposalId") or ""

        if action == "list":
            skills_dir = Path(workspace_dir) / "skills"
            active_skills = []
            if skills_dir.exists():
                for d in skills_dir.iterdir():
                    if d.is_dir() and (d / "SKILL.md").exists():
                        active_skills.append(d.name)
            pending_proposals = [
                f"{p.id} ({p.name}): {p.description} [{p.status}]"
                for p in service.proposals.values()
            ]
            msg = "### Workspace Skills:\n"
            msg += "\n".join(f"- `{s}`" for s in active_skills) if active_skills else "No skills in workspace yet.\n"
            if pending_proposals:
                msg += "\n\n### Pending Proposals:\n" + "\n".join(f"- {p}" for p in pending_proposals)
            return {
                "content": [{"type": "text", "text": msg}],
                "details": {"action": "list", "active_skills": active_skills, "proposals_count": len(pending_proposals)},
            }

        elif action in ("create", "propose"):
            if not skill_name:
                raise ValueError("'name' is required for action='create'")
            description = params.get("description", "")
            content = params.get("content", "")
            if not content:
                # Generate standard SKILL.md template with YAML frontmatter if not provided
                content = (
                    f"---\n"
                    f"name: {skill_name}\n"
                    f"description: {description or skill_name}\n"
                    f"---\n\n"
                    f"# {skill_name.title()}\n\n"
                    f"{description or 'Instructions for ' + skill_name}\n"
                )
            goal = params.get("goal")
            evidence = params.get("evidence")

            try:
                proposal = service.create_proposal(
                    name=skill_name,
                    description=description or skill_name,
                    content=content,
                    goal=goal,
                    evidence=evidence,
                )
                auto_apply = params.get("apply", True)
                if auto_apply:
                    applied = service.apply_proposal(proposal.id)
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    f"Successfully created and applied skill '{applied.name}' to workspace.\n"
                                    f"Path: skills/{applied.name}/SKILL.md\n"
                                    f"Status: {applied.status}"
                                ),
                            }
                        ],
                        "details": {"proposal_id": proposal.id, "status": "applied", "skill": applied.name},
                    }
                else:
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    f"Created skill proposal '{proposal.id}' for '{proposal.name}'.\n"
                                    f"Status: pending. Use action='apply' with proposal_id='{proposal.id}' to commit."
                                ),
                            }
                        ],
                        "details": {"proposal_id": proposal.id, "status": "pending"},
                    }
            except Exception as e:
                return {
                    "content": [{"type": "text", "text": f"Failed to create skill proposal: {e}"}],
                    "details": {"error": str(e)},
                }

        elif action == "apply":
            if not proposal_id:
                raise ValueError("'proposal_id' is required for action='apply'")
            try:
                applied = service.apply_proposal(proposal_id)
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Successfully applied skill '{applied.name}' (proposal {applied.id}).",
                        }
                    ],
                    "details": {"status": "applied", "proposal_id": applied.id, "skill": applied.name},
                }
            except Exception as e:
                return {
                    "content": [{"type": "text", "text": f"Failed to apply proposal '{proposal_id}': {e}"}],
                    "details": {"error": str(e)},
                }

        elif action in ("read", "inspect"):
            target_name = skill_name or proposal_id
            target_file = Path(workspace_dir) / "skills" / target_name / "SKILL.md"
            if target_file.exists():
                text = target_file.read_text(encoding="utf-8")
                return {
                    "content": [{"type": "text", "text": f"### Skill: {target_name}\n\n```markdown\n{text}\n```"}],
                    "details": {"skill": target_name, "found": True},
                }
            if proposal_id in service.proposals:
                rec = service.proposals[proposal_id]
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"### Proposal: {rec.id} ({rec.name})\n"
                                f"Status: {rec.status}\n\n"
                                f"```markdown\n{rec.content}\n```"
                            ),
                        }
                    ],
                    "details": {"proposal_id": rec.id, "status": rec.status},
                }
            return {
                "content": [{"type": "text", "text": f"Skill or proposal '{target_name}' not found."}],
                "details": {"found": False},
            }

        else:
            return {"content": [{"type": "text", "text": f"Unsupported action: {action}"}]}

    return {
        "name": "skill_workshop",
        "label": "Skill Workshop",
        "description": (
            "Author, create, inspect, and manage workspace skills (SKILL.md). "
            "Use this tool whenever the user asks to save a new skill, create a reusable capability, "
            "or manage agent skills."
        ),
        "promptSnippet": "Create and manage reusable agent skills",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "apply", "list", "inspect", "read"],
                    "description": "Action: 'create' (create new skill), 'apply' (commit proposal), 'list' (list skills), 'inspect' (read skill).",
                },
                "name": {
                    "type": "string",
                    "description": "Short identifier for the skill (e.g. 'git-release-manager', 'weather-reporter').",
                },
                "description": {
                    "type": "string",
                    "description": "Short description of what the skill does (under 160 bytes).",
                },
                "content": {
                    "type": "string",
                    "description": "The markdown content of the SKILL.md file with YAML frontmatter.",
                },
                "proposal_id": {
                    "type": "string",
                    "description": "Proposal ID when applying or inspecting a pending skill proposal.",
                },
                "apply": {
                    "type": "boolean",
                    "description": "Set true to immediately commit and apply upon creation (default: true).",
                },
            },
            "required": ["action"],
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "array"},
                "details": {"type": "object"},
            },
        },
        "execute": _execute,
    }


create_skill_workshop_tool = create_skill_workshop_tool_definition
