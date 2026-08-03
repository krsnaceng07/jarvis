"""jarvis.agents.embedded_agent_runner.run.attempt_bootstrap_context — remap injected context files to the workspace.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt.bootstrap-context.ts``.

Public surface:

- :func:`remap_injected_context_files_to_workspace`

Phase 7.6d-1 — focused minimal port.

The OpenClaw source is small (~1.5K) and resolves bootstrap
context file paths into the workspace. The Python port keeps the
public surface and delegates the heavy work to installable hooks.
"""
from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional


#: Injected-context file shape.
InjectedContextFile = Dict[str, Any]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_relative_path_inside_or_equal(relative_path: str) -> bool:
    if not isinstance(relative_path, str) or not relative_path:
        return False
    if relative_path.startswith("/") or relative_path.startswith("\\"):
        return False
    if os.path.splitdrive(relative_path)[0]:
        return False
    return True


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


#: Hook for the isRelativePathInsideOrEqual step.
_IS_RELATIVE_PATH_INSIDE_OR_EQUAL: Callable[[str], bool] = (
    _is_relative_path_inside_or_equal
)


def set_is_relative_path_inside_or_equal_hook(
    hook: Callable[[str], bool],
) -> None:
    """Install a custom isRelativePathInsideOrEqual hook."""
    global _IS_RELATIVE_PATH_INSIDE_OR_EQUAL
    _IS_RELATIVE_PATH_INSIDE_OR_EQUAL = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def remap_injected_context_files_to_workspace(
    params: Dict[str, Any],
) -> List[InjectedContextFile]:
    """Remap injected-context files into the workspace.

    Mirrors :func:`remapInjectedContextFilesToWorkspace`
    (``attempt.bootstrap-context.ts``).
    """
    files = params.get("files") or []
    workspace_dir = params.get("workspaceDir") or ""
    if not isinstance(files, list):
        return []
    remapped: List[InjectedContextFile] = []
    for entry in files:
        if not isinstance(entry, dict):
            continue
        path = entry.get("path")
        if not isinstance(path, str) or not path:
            continue
        if not _IS_RELATIVE_PATH_INSIDE_OR_EQUAL(path):
            new_path = (workspace_dir.rstrip("/\\") + "/" + os.path.basename(path).replace("\\", "/"))
        else:
            new_path = (workspace_dir.rstrip("/\\") + "/" + path.replace("\\", "/"))
        new_entry = dict(entry)
        new_entry["path"] = new_path
        remapped.append(new_entry)
    return remapped


__all__ = [
    "InjectedContextFile",
    "remap_injected_context_files_to_workspace",
    "set_is_relative_path_inside_or_equal_hook",
]
