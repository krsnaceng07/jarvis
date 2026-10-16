"""jarvis.agents.sandbox.context — Sandbox execution context resolution.

Mirrors OpenClaw's ``src/agents/sandbox/context.ts`` and
``src/agents/embedded-agent-runner/sandbox-info.ts``:
- Computes whether a given turn / session runs sandboxed.
- Respects ``agents.defaults.sandbox.mode`` ("off" | "non-main" | "all").
- Honors creator-role immutable constraints (``sandbox: "required"``).
- Derives container name / isolation identity according to ``scope`` ("agent" | "session" | "shared").
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.config.sandbox_config import (
    BrowserSandboxConfig,
    DockerSandboxConfig,
    SandboxBackend,
    SandboxConfig,
    SandboxMode,
    SandboxScope,
    SandboxWorkspaceAccess,
    resolve_sandbox_config,
)


def is_main_session_key(session_key: str, agent_id: str = "main") -> bool:
    """Determine if a session key is the agent's main/primary session.

    Mirrors OpenClaw's rule:
    The main session key is always ``agent:<agentId>:main`` (or ``global``
    when session.scope is "global"). Channel sessions (e.g. telegram:...,
    discord:...) and subagent sessions always count as non-main.
    """
    key = (session_key or "").strip().lower()
    if key == "global":
        return True
    expected_main = f"agent:{agent_id.lower()}:main"
    return key == expected_main or key == "main"


def sanitize_identifier_for_container(name: str) -> str:
    """Sanitize arbitrary session/agent strings for Docker container names.

    Replaces non-alphanumeric chars with '-' and trims.
    """
    sanitized = re.sub(r"[^a-zA-Z0-9_.-]+", "-", name).strip("-")
    return sanitized[:63] if sanitized else "default"


@dataclass(slots=True)
class SandboxContext:
    """Effective sandbox execution context for a session turn.

    Mirrors OpenClaw's resolved SandboxContext facts.
    """

    is_sandboxed: bool
    effective_mode: SandboxMode
    effective_scope: SandboxScope
    backend: SandboxBackend
    workspace_access: SandboxWorkspaceAccess
    creator_required: bool
    workspace_path: Path
    container_name: str | None
    session_key: str
    agent_id: str
    docker_config: DockerSandboxConfig
    browser_config: BrowserSandboxConfig


def resolve_sandbox_context(
    *,
    session_key: str = "agent:main:main",
    agent_id: str = "main",
    workspace_path: Path | str | None = None,
    config: SandboxConfig | dict[str, Any] | None = None,
    creator_role: str | None = None,
    creator_sandbox_policy: str | None = None,
) -> SandboxContext:
    """Resolve the active sandbox execution context for a turn.

    Parameters
    ----------
    session_key:
        Canonical session identifier (e.g. "agent:main:main", "telegram:123").
    agent_id:
        Owning agent identifier (defaults to "main").
    workspace_path:
        Host workspace root directory.
    config:
        Configured SandboxConfig or raw dictionary.
    creator_role:
        Optional named operator role creating the session.
    creator_sandbox_policy:
        Optional role sandbox requirement ("required" | "inherit").

    Returns
    -------
    SandboxContext
        The resolved facts deciding whether execution is containerized or host.
    """
    cfg = config if isinstance(config, SandboxConfig) else resolve_sandbox_config(config)

    resolved_workspace = Path(workspace_path or Path.cwd()).resolve()

    # 1. Evaluate creator role immutable constraint
    # Role-required sandbox overrides agent mode and cannot be escaped.
    creator_required = (creator_sandbox_policy or "").strip().lower() == "required"

    # 2. Evaluate mode
    is_main = is_main_session_key(session_key, agent_id)
    if creator_required:
        is_sandboxed = True
    elif cfg.mode == "all":
        is_sandboxed = True
    elif cfg.mode == "non-main":
        is_sandboxed = not is_main
    else:  # "off"
        is_sandboxed = False

    # 3. Derive container name based on scope
    container_name: str | None = None
    if is_sandboxed and cfg.backend in ("docker", "podman"):
        clean_agent = sanitize_identifier_for_container(agent_id)
        clean_sess = sanitize_identifier_for_container(session_key)

        if cfg.scope == "shared":
            container_name = "jarvis-sandbox-shared"
        elif cfg.scope == "agent":
            container_name = f"jarvis-sandbox-{clean_agent}"
        else:  # "session"
            container_name = f"jarvis-sandbox-{clean_agent}-{clean_sess}"

    return SandboxContext(
        is_sandboxed=is_sandboxed,
        effective_mode=cfg.mode,
        effective_scope=cfg.scope,
        backend=cfg.backend,
        workspace_access=cfg.workspace_access,
        creator_required=creator_required,
        workspace_path=resolved_workspace,
        container_name=container_name,
        session_key=session_key,
        agent_id=agent_id,
        docker_config=cfg.docker,
        browser_config=cfg.browser,
    )
