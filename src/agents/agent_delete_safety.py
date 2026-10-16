"""jarvis.agents.agent_delete_safety — workspace overlap detection.

OpenClaw parity: mirrors ``src/agents/agent-delete-safety.ts``.

Detects agents whose workspaces would overlap a candidate delete target,
so the CLI can warn before a ``jarvis agents remove`` wipes shared state.
"""

from __future__ import annotations

import os
import sys
from typing import Any

from .agent_scope_config import list_agent_entries, resolve_agent_workspace_dir
from src.routing.agent_id import normalize_agent_id


# ---------------------------------------------------------------------------
# Filesystem helpers
# ---------------------------------------------------------------------------


def _normalize_workspace_path_for_comparison(path: str) -> str:
    """Resolve and optionally lowercase a workspace path for comparison.

    Mirrors ``normalizeWorkspacePathForComparison``:
    - Resolve to absolute.
    - Try ``os.path.realpath`` (follows symlinks).
    - On Windows/macOS, lowercase for case-insensitive FS.
    """
    # Strip null bytes (matches TS ``replaceAll('\0', '')``)
    path = path.replace("\0", "")
    resolved = os.path.abspath(path)
    try:
        resolved = os.path.realpath(resolved)
    except Exception:
        # Non-existent directories keep the lexical path.
        pass
    if sys.platform in ("darwin", "win32"):
        return resolved.lower()
    return resolved


def _is_path_inside(child: str, parent: str) -> bool:
    """Return True when *child* is inside *parent* (or equal to it).

    Mirrors ``isPathInside`` from OpenClaw's infra/path-guards.ts.
    """
    # Normalize separators for comparison.
    child_norm = os.path.normcase(os.path.normpath(child))
    parent_norm = os.path.normcase(os.path.normpath(parent))
    if child_norm == parent_norm:
        return True
    sep = os.sep
    return child_norm.startswith(parent_norm + sep)


def _workspace_paths_overlap(left: str, right: str) -> bool:
    """Return True when left and right are the same or one contains the other.

    Mirrors ``workspacePathsOverlap``.
    """
    l_norm = _normalize_workspace_path_for_comparison(left)
    r_norm = _normalize_workspace_path_for_comparison(right)
    return _is_path_inside(r_norm, l_norm) or _is_path_inside(l_norm, r_norm)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def find_overlapping_workspace_agent_ids(
    cfg: dict[str, Any],
    agent_id: str,
    workspace_dir: str,
    env: dict[str, str] | None = None,
) -> list[str]:
    """List ids of other agents whose workspaces overlap *workspace_dir*.

    Mirrors ``findOverlappingWorkspaceAgentIds``.

    Parameters
    ----------
    cfg:
        Jarvis config dict.
    agent_id:
        The agent being considered for deletion (excluded from results).
    workspace_dir:
        The resolved workspace dir of that agent.
    env:
        Optional env dict for path resolution (defaults to ``os.environ``).

    Returns
    -------
    list[str]
        Sorted list of overlapping agent ids (normalized).
    """
    normalized_agent_id = normalize_agent_id(agent_id)
    overlapping: list[str] = []

    for entry in list_agent_entries(cfg):
        try:
            other_id = normalize_agent_id(entry.get("id", ""))
        except ValueError:
            continue
        if other_id == normalized_agent_id:
            continue
        try:
            other_workspace = resolve_agent_workspace_dir(cfg, other_id, env)
        except Exception:
            continue
        if _workspace_paths_overlap(workspace_dir, other_workspace):
            overlapping.append(other_id)

    return sorted(overlapping)


__all__ = [
    "find_overlapping_workspace_agent_ids",
]
