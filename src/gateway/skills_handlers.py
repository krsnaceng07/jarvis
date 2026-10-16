"""Gateway RPC handlers for skills operations — mirrors OpenClaw server-methods/skills.ts."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from src.skills import discover_skills

_log = logging.getLogger("jarvis.gateway.skills_handlers")


def _get_skills_dir() -> Path:
    base = Path(__file__).resolve().parents[2]
    skills_dir = base / "skills"
    if not skills_dir.exists():
        skills_dir = base / ".agents" / "skills"
    return skills_dir


def skills_list_handler(params: dict[str, Any]) -> dict[str, Any]:
    """Handle skills.list and skills.library.list RPC requests."""
    skills_dir = _get_skills_dir()
    decls = discover_skills(skills_dir)
    items = [
        {
            "id": s.name,
            "name": s.name,
            "description": s.description,
            "emoji": s.emoji,
            "requiresBins": list(s.requires_bins),
            "sourcePath": s.source_path,
        }
        for s in decls
    ]
    return {
        "ok": True,
        "count": len(items),
        "skills": items,
    }


def skills_status_handler(params: dict[str, Any]) -> dict[str, Any]:
    """Handle skills.status RPC request."""
    skills_dir = _get_skills_dir()
    decls = discover_skills(skills_dir)
    return {
        "ok": True,
        "total": len(decls),
        "enabled": len(decls),
        "skillsDir": str(skills_dir),
    }


def make_skills_handlers() -> dict[str, Any]:
    """Return all skills-related gateway RPC handlers."""
    return {
        "skills.status": skills_status_handler,
        "skills.list": skills_list_handler,
        "skills.library.list": skills_list_handler,
    }


__all__ = ["make_skills_handlers"]
