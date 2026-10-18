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

        elif action in ("read", "inspect", "view"):
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

        elif action in ("write_file", "add_file"):
            if not skill_name:
                raise ValueError("'name' is required for action='write_file'")
            file_path = params.get("file_path") or params.get("path")
            if not file_path:
                raise ValueError("'file_path' is required for action='write_file'")
            content = params.get("content", "")
            reason = params.get("reason")
            out_p = service.write_support_file(skill_name, file_path, content, reason=reason)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Successfully wrote file '{file_path}' for skill '{skill_name}'.",
                    }
                ],
                "details": {
                    "status": "written",
                    "skill": skill_name,
                    "file_path": str(file_path),
                },
            }

        elif action == "patch":
            if not skill_name:
                raise ValueError("'name' is required for action='patch'")
            old_text = params.get("old_text", "")
            new_text = params.get("new_text", "")
            target_file = Path(workspace_dir) / "skills" / skill_name / "SKILL.md"
            if not target_file.exists():
                raise FileNotFoundError(f"Skill '{skill_name}' does not exist")
            raw = target_file.read_text(encoding="utf-8")
            if old_text not in raw:
                raise ValueError(f"old_text not found in {target_file}")
            patched = raw.replace(old_text, new_text, 1)
            target_file.write_text(patched, encoding="utf-8")
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Successfully patched skill '{skill_name}'.",
                    }
                ],
                "details": {
                    "status": "patched",
                    "skill": skill_name,
                },
            }

        elif action == "archive":
            if not skill_name:
                raise ValueError("'name' is required for action='archive'")
            reason = params.get("reason")
            archive_path = service.archive_skill(skill_name, reason=reason)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Successfully archived skill '{skill_name}' to {archive_path}.",
                    }
                ],
                "details": {
                    "status": "archived",
                    "skill": skill_name,
                    "path": str(archive_path),
                },
            }

        elif action == "restore":
            if not skill_name:
                raise ValueError("'name' is required for action='restore'")
            restored_path = service.restore_skill(skill_name)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Successfully restored skill '{skill_name}' from archive.",
                    }
                ],
                "details": {
                    "status": "restored",
                    "skill": skill_name,
                    "path": str(restored_path),
                },
            }

        elif action == "install":
            source = params.get("source") or params.get("url") or skill_name
            if not source:
                raise ValueError("'source' or 'name' is required for action='install'")
            installed_dir = service.install_skill(source, name=skill_name or None)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Successfully installed skill '{installed_dir.name}' from '{source}'.",
                    }
                ],
                "details": {
                    "status": "installed",
                    "skill": installed_dir.name,
                    "path": str(installed_dir),
                },
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
                    "enum": ["create", "apply", "list", "inspect", "read", "view", "write_file", "patch", "archive", "restore", "install"],
                    "description": "Action: 'create' | 'apply' | 'list' | 'inspect' | 'view' | 'write_file' | 'patch' | 'archive' | 'restore' | 'install'.",
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
