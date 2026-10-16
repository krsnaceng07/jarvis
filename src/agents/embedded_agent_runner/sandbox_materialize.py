"""Workspace materialization helpers for sandbox/container runs.

Provides a minimal `materialize_skill_entries` that copies listed source
files into a temporary workspace directory suitable for mounting into
containers. This is a small, test-friendly implementation used by the
Docker runner when preparing a prompt workspace.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from typing import Any, Dict, Iterable, List, Tuple


def _ensure_parent(path: str) -> None:
    parent = os.path.dirname(path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)


def materialize_skill_entries(entries: Iterable[Dict[str, Any]], source_workspace_dir: str) -> Tuple[str, List[Dict[str, Any]]]:
    """Copy the files referenced in `entries` into a new temp workspace.

    Returns (temp_dir, new_entries) where `new_entries` mirrors `entries`
    but with file paths updated to the new temp workspace layout.
    """
    tmpdir = tempfile.mkdtemp(prefix="jarvis_sandbox_")
    new_entries: List[Dict[str, Any]] = []

    for e in entries:
        if not isinstance(e, dict):
            new_entries.append(e)
            continue
        skill = e.get("skill") if isinstance(e.get("skill"), dict) else {}
        file_path = skill.get("filePath")
        if not file_path:
            new_entries.append(e)
            continue

        # Resolve absolute path relative to source_workspace_dir when needed
        abs_path = file_path
        if not os.path.isabs(file_path):
            abs_path = os.path.normpath(os.path.join(source_workspace_dir, file_path))

        if not os.path.exists(abs_path):
            # Missing files are ignored but preserved in output mapping
            new_skill = dict(skill)
            new_skill["filePath"] = file_path
            new_entry = dict(e)
            new_entry["skill"] = new_skill
            new_entries.append(new_entry)
            continue

        # Copy file into tempdir preserving relative path
        rel = os.path.relpath(abs_path, start=source_workspace_dir)
        target_path = os.path.join(tmpdir, rel)
        _ensure_parent(target_path)
        shutil.copy2(abs_path, target_path)

        new_skill = dict(skill)
        new_skill["filePath"] = os.path.normpath(target_path)
        new_entry = dict(e)
        new_entry["skill"] = new_skill
        new_entries.append(new_entry)

    return tmpdir, new_entries


__all__ = ["materialize_skill_entries"]
