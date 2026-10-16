"""jarvis.agents.sandbox.filesystem_guard — Deep ancestor symlink path containment.

Mirrors OpenClaw's ``src/agents/agent-tools.read.ts`` and ``src/agents/apply-patch-paths.ts``:
- Dual-layer containment verification (normalized path + deepest existing ancestor).
- Defends against symlink-parent escapes (e.g. workspace/symlink_out/file -> /etc/shadow).
- Enforces workspaceAccess policy ("none", "ro", "rw").
"""

from __future__ import annotations

from pathlib import Path


def resolve_deepest_existing_ancestor(path: Path) -> tuple[Path, list[str]]:
    """Walk up the directory hierarchy until an existing filesystem node is found.

    Returns (deepest_existing_resolved, remaining_uncreated_parts).
    """
    uncreated: list[str] = []
    curr = path
    while not curr.exists() and curr.parent != curr:
        uncreated.append(curr.name)
        curr = curr.parent

    # Reverse to keep order from existing parent to leaf
    uncreated.reverse()
    return curr.resolve(), uncreated


def is_path_contained(target_path: Path | str, workspace_root: Path | str) -> bool:
    """Return True if target_path strictly resolves inside workspace_root."""
    try:
        ws = Path(workspace_root).resolve()
        raw_p = Path(target_path)
        p = raw_p if raw_p.is_absolute() else (ws / raw_p)

        existing_ancestor, remaining = resolve_deepest_existing_ancestor(p)
        if not existing_ancestor.is_relative_to(ws):
            return False

        # Reconstruct full resolved path
        reconstructed = existing_ancestor
        for part in remaining:
            reconstructed = reconstructed / part

        return reconstructed.resolve().is_relative_to(ws)
    except Exception:
        return False


def validate_sandbox_path(
    target_path: Path | str,
    workspace_root: Path | str,
    *,
    is_mutation: bool = False,
    access_mode: str = "rw",
) -> Path:
    """Validate that target_path is strictly within workspace_root.

    Parameters
    ----------
    target_path:
        Path requested by the tool call.
    workspace_root:
        Authorized workspace root directory.
    is_mutation:
        True if the tool will write, edit, delete, or create a file.
    access_mode:
        Effective workspace access ("none", "ro", "rw").

    Returns
    -------
    Path
        Canonical resolved target path.

    Raises
    ------
    PermissionError
        If path resolves outside the workspace or violates access_mode.
    """
    mode = (access_mode or "rw").strip().lower()
    if mode == "none":
        raise PermissionError(
            f"Sandbox workspace access is disabled (workspaceAccess: 'none'). "
            f"Cannot access '{target_path}'."
        )

    if is_mutation and mode == "ro":
        raise PermissionError(
            f"Sandbox workspace is mounted read-only (workspaceAccess: 'ro'). "
            f"Cannot mutate '{target_path}'."
        )

    ws = Path(workspace_root).resolve()
    raw_p = Path(target_path)
    p = raw_p if raw_p.is_absolute() else (ws / raw_p)

    # 1. Check existing path directly
    if p.exists():
        resolved = p.resolve()
        if not resolved.is_relative_to(ws):
            raise PermissionError(
                f"Security violation: path '{target_path}' resolves to '{resolved}', "
                f"which is outside authorized workspace '{ws}'."
            )
        return resolved

    # 2. Path does not exist yet: resolve deepest existing ancestor to guard against symlink parents
    existing_ancestor, remaining = resolve_deepest_existing_ancestor(p)
    if not existing_ancestor.is_relative_to(ws):
        raise PermissionError(
            f"Security violation: parent directory of '{target_path}' resolves to '{existing_ancestor}', "
            f"which escapes authorized workspace '{ws}'."
        )

    reconstructed = existing_ancestor
    for part in remaining:
        reconstructed = reconstructed / part

    return reconstructed


def guard_sandbox_tool_access(
    tool_name: str,
    target_path: str | Path | None,
    cwd: str,
    options: dict[str, object] | None = None,
    ctx: object = None,
    *,
    is_mutation: bool = False,
) -> tuple[object, Path | None]:
    """Guard a tool invocation against sandbox policies, permissions, and path limits.

    1. Resolves SandboxContext.
    2. Evaluates sandbox tool policy allow/deny for tool_name.
    3. If sandboxed, validates workspaceAccess (none/ro/rw) and path containment
       via deepest existing ancestor symlink resolution.
    """
    import os
    from .context import resolve_sandbox_context
    from .tool_policy import evaluate_sandbox_tool_policy

    opts = options or {}
    session_key = opts.get("session_key") or getattr(ctx, "session_key", None) or "agent:main:main"
    agent_id = (
        opts.get("agent_id")
        or getattr(ctx, "agent_id", None)
        or (str(session_key).split(":")[1] if str(session_key).startswith("agent:") else "main")
    )
    sandbox_config = (
        opts.get("sandbox_config")
        or opts.get("config")
        or getattr(ctx, "sandbox_config", None)
        or getattr(ctx, "config", None)
    )
    creator_role = opts.get("creator_role") or getattr(ctx, "creator_role", None)
    creator_sandbox_policy = opts.get("creator_sandbox_policy") or getattr(
        ctx, "creator_sandbox_policy", None
    )
    workspace_root = cwd or getattr(ctx, "workspace", None) or os.getcwd()

    sandbox_ctx = resolve_sandbox_context(
        session_key=str(session_key),
        agent_id=str(agent_id),
        workspace_path=workspace_root,
        config=sandbox_config if isinstance(sandbox_config, (dict, object)) else None,
        creator_role=str(creator_role) if creator_role else None,
        creator_sandbox_policy=str(creator_sandbox_policy) if creator_sandbox_policy else None,
    )

    tools_policy = (
        opts.get("tools_policy")
        or opts.get("tool_policy")
        or getattr(ctx, "tools_policy", None)
        or getattr(ctx, "tool_policy", None)
    )

    is_allowed, reason = evaluate_sandbox_tool_policy(
        tool_name,
        tools_policy if isinstance(tools_policy, dict) else None,
        is_sandboxed=sandbox_ctx.is_sandboxed,
    )
    if not is_allowed:
        raise PermissionError(reason or f"Tool '{tool_name}' is blocked by sandbox tool policy.")

    if not sandbox_ctx.is_sandboxed:
        return sandbox_ctx, Path(target_path) if target_path else None

    # Sandbox mode is active
    if target_path is not None:
        validated = validate_sandbox_path(
            target_path,
            sandbox_ctx.workspace_path,
            is_mutation=is_mutation,
            access_mode=sandbox_ctx.workspace_access,
        )
        return sandbox_ctx, validated

    # General check when no specific path is given (e.g. tool initialization or general mutation check)
    if sandbox_ctx.workspace_access == "none":
        raise PermissionError(
            f"Sandbox workspace access is disabled (workspaceAccess: 'none'). "
            f"Tool '{tool_name}' cannot access the filesystem."
        )
    if is_mutation and sandbox_ctx.workspace_access == "ro":
        raise PermissionError(
            f"Sandbox workspace is mounted read-only (workspaceAccess: 'ro'). "
            f"Tool '{tool_name}' cannot mutate the filesystem."
        )

    return sandbox_ctx, None
