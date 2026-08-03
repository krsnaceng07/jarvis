"""jarvis.agents.embedded_agent_runner.sandbox_skills — sandbox skill runtime input selection.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/sandbox-skills.ts``.

Public surface:

- :func:`map_sandbox_skill_entries_for_prompt`
- :func:`map_sandbox_skill_usage_paths`
- :func:`resolve_sandbox_skill_runtime_inputs`

Phase 7.6h-3 — focused minimal port.
"""
from __future__ import annotations

import os
import posixpath
from typing import Any, Dict, List, Optional


MATERIALIZED_SKILLS_WORKSPACE_CONTAINER_PARTS = (".jarvis", "sandbox-skills")


# Installable hooks ---------------------------------------------------------

_map_sandbox_skill_entries_for_prompt_hook = None
_map_sandbox_skill_usage_paths_hook = None
_resolve_sandbox_skill_runtime_inputs_hook = None


def set_map_sandbox_skill_entries_for_prompt_hook(fn) -> None:
    global _map_sandbox_skill_entries_for_prompt_hook
    _map_sandbox_skill_entries_for_prompt_hook = fn


def set_map_sandbox_skill_usage_paths_hook(fn) -> None:
    global _map_sandbox_skill_usage_paths_hook
    _map_sandbox_skill_usage_paths_hook = fn


def set_resolve_sandbox_skill_runtime_inputs_hook(fn) -> None:
    global _resolve_sandbox_skill_runtime_inputs_hook
    _resolve_sandbox_skill_runtime_inputs_hook = fn


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _container_join(root: str, *parts: str) -> str:
    normalized = (root or "/").replace("\\", "/").rstrip("/") or "/"
    suffix = "/".join(p.strip("/") for p in parts if p)
    return f"{normalized}/{suffix}" if suffix else normalized


def _path_escapes_root(relative_path: str) -> bool:
    if relative_path == "..":
        return True
    if relative_path.startswith(".." + os.sep):
        return True
    if os.path.isabs(relative_path):
        return True
    return False


def _map_path_from_workspace_to_container(params: Dict[str, Any]) -> Optional[str]:
    file_path = params.get("filePath")
    source_workspace_dir = params.get("sourceWorkspaceDir")
    target_workspace_dir = params.get("targetWorkspaceDir")
    if not file_path or not os.path.isabs(file_path):
        return file_path
    try:
        relative = os.path.relpath(
            os.path.normpath(file_path),
            os.path.normpath(source_workspace_dir),
        )
    except Exception:
        return file_path
    if _path_escapes_root(relative):
        return file_path
    if not relative or relative == ".":
        return (target_workspace_dir or "").replace("\\", "/")
    parts = [p for p in relative.split(os.sep) if p]
    return _container_join(target_workspace_dir, *parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def map_sandbox_skill_entries_for_prompt(params: Dict[str, Any]) -> Optional[List[Any]]:
    """Map skill entries from the host workspace to the in-sandbox container.

    Mirrors :func:`mapSandboxSkillEntriesForPrompt` (``sandbox-skills.ts``).
    """
    if _map_sandbox_skill_entries_for_prompt_hook is not None:
        return _map_sandbox_skill_entries_for_prompt_hook(params)
    entries = params.get("entries")
    if not entries or params.get("skillsWorkspaceDir") == params.get("skillsPromptWorkspaceDir"):
        return entries
    out: List[Any] = []
    for entry in entries:
        if not isinstance(entry, dict):
            out.append(entry)
            continue
        skill = entry.get("skill") if isinstance(entry.get("skill"), dict) else {}
        file_path = _map_path_from_workspace_to_container(
            {
                "filePath": skill.get("filePath"),
                "sourceWorkspaceDir": params["skillsWorkspaceDir"],
                "targetWorkspaceDir": params["skillsPromptWorkspaceDir"],
            }
        ) or skill.get("filePath")
        base_dir = _map_path_from_workspace_to_container(
            {
                "filePath": skill.get("baseDir"),
                "sourceWorkspaceDir": params["skillsWorkspaceDir"],
                "targetWorkspaceDir": params["skillsPromptWorkspaceDir"],
            }
        ) or skill.get("baseDir")
        source_info = skill.get("sourceInfo") if isinstance(skill.get("sourceInfo"), dict) else {}
        source_info_path = _map_path_from_workspace_to_container(
            {
                "filePath": source_info.get("path"),
                "sourceWorkspaceDir": params["skillsWorkspaceDir"],
                "targetWorkspaceDir": params["skillsPromptWorkspaceDir"],
            }
        ) or source_info.get("path")
        source_info_base_dir = _map_path_from_workspace_to_container(
            {
                "filePath": source_info.get("baseDir"),
                "sourceWorkspaceDir": params["skillsWorkspaceDir"],
                "targetWorkspaceDir": params["skillsPromptWorkspaceDir"],
            }
        )
        new_skill = dict(skill)
        new_skill["filePath"] = file_path
        new_skill["baseDir"] = base_dir
        new_source_info = dict(source_info)
        new_source_info["path"] = source_info_path
        if source_info_base_dir is not None:
            new_source_info["baseDir"] = source_info_base_dir
        new_skill["sourceInfo"] = new_source_info
        new_entry = dict(entry)
        new_entry["skill"] = new_skill
        out.append(new_entry)
    return out


def map_sandbox_skill_usage_paths(params: Dict[str, Any]) -> Optional[List[Any]]:
    """Map skill usage paths from the host workspace to the in-sandbox container.

    Mirrors :func:`mapSandboxSkillUsagePaths` (``sandbox-skills.ts``).
    """
    if _map_sandbox_skill_usage_paths_hook is not None:
        return _map_sandbox_skill_usage_paths_hook(params)
    paths = params.get("paths")
    if not paths or params.get("skillsWorkspaceDir") == params.get("skillsPromptWorkspaceDir"):
        return paths
    out: List[Any] = []
    for entry in paths:
        if not isinstance(entry, dict):
            out.append(entry)
            continue
        new_entry = dict(entry)
        new_entry["readPath"] = _map_path_from_workspace_to_container(
            {
                "filePath": entry.get("readPath"),
                "sourceWorkspaceDir": params["skillsWorkspaceDir"],
                "targetWorkspaceDir": params["skillsPromptWorkspaceDir"],
            }
        ) or entry.get("readPath")
        out.append(new_entry)
    return out


def resolve_sandbox_skill_runtime_inputs(params: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve the runtime inputs for sandbox-aware skill loading.

    Mirrors :func:`resolveSandboxSkillRuntimeInputs` (``sandbox-skills.ts``).
    """
    if _resolve_sandbox_skill_runtime_inputs_hook is not None:
        return _resolve_sandbox_skill_runtime_inputs_hook(params) or {}
    sandbox = params.get("sandbox") if isinstance(params.get("sandbox"), dict) else None
    effective_workspace = params.get("effectiveWorkspace") or ""
    skills_snapshot = params.get("skillsSnapshot")
    if sandbox and sandbox.get("enabled") is True:
        skills_workspace_dir = sandbox.get("skillsWorkspaceDir") or effective_workspace
        if (
            sandbox.get("workspaceAccess") == "rw"
            and sandbox.get("skillsWorkspaceDir")
            and sandbox.get("containerWorkdir")
        ):
            skills_prompt_workspace_dir = _container_join(
                sandbox["containerWorkdir"],
                *MATERIALIZED_SKILLS_WORKSPACE_CONTAINER_PARTS,
            )
        else:
            skills_prompt_workspace_dir = sandbox.get("containerWorkdir") or skills_workspace_dir
        out: Dict[str, Any] = {
            "skillsPromptWorkspaceDir": skills_prompt_workspace_dir,
            "skillsSnapshot": None,
            "skillsWorkspaceDir": skills_workspace_dir,
            "workspaceOnly": True,
        }
        if sandbox.get("skillsEligibility"):
            out["skillsEligibility"] = sandbox["skillsEligibility"]
        return out
    return {
        "skillsPromptWorkspaceDir": effective_workspace,
        "skillsSnapshot": skills_snapshot,
        "skillsWorkspaceDir": effective_workspace,
        "workspaceOnly": False,
    }


__all__ = [
    "MATERIALIZED_SKILLS_WORKSPACE_CONTAINER_PARTS",
    "map_sandbox_skill_entries_for_prompt",
    "map_sandbox_skill_usage_paths",
    "resolve_sandbox_skill_runtime_inputs",
    "set_map_sandbox_skill_entries_for_prompt_hook",
    "set_map_sandbox_skill_usage_paths_hook",
    "set_resolve_sandbox_skill_runtime_inputs_hook",
]
