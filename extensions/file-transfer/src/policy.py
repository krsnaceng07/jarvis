"""File Transfer policy engine and path security checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

MAX_FILE_BYTES = 16 * 1024 * 1024  # 16 MB


@dataclass(frozen=True, slots=True)
class NodePolicyConfig:
    """Per-node security policy configuration."""

    ask: Literal["off", "on-miss", "always"] = "on-miss"
    allow_read_paths: list[str] = field(default_factory=list)
    allow_write_paths: list[str] = field(default_factory=list)
    deny_paths: list[str] = field(default_factory=list)
    max_bytes: int = MAX_FILE_BYTES
    follow_symlinks: bool = False


@dataclass(frozen=True, slots=True)
class LiteralGrant:
    """A granted literal path approval."""

    node_id: str
    command: Literal["file.fetch", "dir.list", "dir.fetch", "file.write"]
    requested_path: str
    canonical_path: str


def normalize_path_for_policy(path_str: str) -> str:
    """Normalize file path to absolute canonical form."""
    p = Path(path_str).expanduser()
    try:
        resolved = p.resolve()
        return str(resolved)
    except Exception:
        return str(p.absolute())


def is_path_contained_in(child_path: str, parent_path: str) -> bool:
    """Check if child_path is strictly within parent_path."""
    try:
        child = Path(normalize_path_for_policy(child_path))
        parent = Path(normalize_path_for_policy(parent_path))
        return child == parent or parent in child.parents
    except Exception:
        return False


def check_path_policy(
    node_id: str,
    action: Literal["read", "write", "list", "archive"],
    target_path: str,
    policy: NodePolicyConfig | None = None,
    grants: list[LiteralGrant] | None = None,
) -> tuple[bool, str | None]:
    """Verify if the requested operation on target_path is allowed under policy.

    Returns (allowed, reason_or_error).
    """
    canonical = normalize_path_for_policy(target_path)

    # Check deny paths first
    if policy and policy.deny_paths:
        for deny in policy.deny_paths:
            if is_path_contained_in(canonical, deny):
                return False, f"Access denied: path is within denied root '{deny}'"

    # Check literal standing grants
    if grants:
        command_name = {
            "read": "file.fetch",
            "write": "file.write",
            "list": "dir.list",
            "archive": "dir.fetch",
        }.get(action, "file.fetch")
        for grant in grants:
            if grant.node_id == node_id and grant.command == command_name:
                if grant.canonical_path == canonical or is_path_contained_in(
                    canonical, grant.canonical_path
                ):
                    return True, None

    if not policy:
        return True, None

    # Check allowed paths
    allowed_list = policy.allow_write_paths if action == "write" else policy.allow_read_paths
    if allowed_list:
        matched = any(is_path_contained_in(canonical, allow) for allow in allowed_list)
        if not matched:
            return False, f"Path '{target_path}' is not in configured allowed paths"

    return True, None
