"""Declares the explicitly approved, lazily loaded node-backed Codex exec-server.

OpenClaw parity: ``extensions/codex/src/node-exec-server.ts``.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any

CODEX_NODE_EXEC_SERVER_COMMAND: str = "codex.exec-server.stdio.v1"
CODEX_NODE_EXEC_SERVER_CAPABILITY: str = "codex.exec-server"


@dataclass(frozen=True, slots=True)
class CodexNodePlacementWorkspace:
    """Verified placement workspace details for remote Codex execution."""

    cwd: str
    environment_id: str
    session_id: str
    owner_epoch: int
    session_key: str


def parse_codex_node_placement_workspace(value: Any) -> CodexNodePlacementWorkspace:
    """Parse and validate exact managed placement workspace properties.

    Mirrors ``parseCodexNodePlacementWorkspace``: the workspace must carry
    exactly the five managed keys — extra keys fail closed (ambiguous
    duplicates must not slip through). ``snake_case`` spellings are
    accepted as a Jarvis-local leniency on top of the exact shape.
    """
    if not isinstance(value, dict):
        raise ValueError("Codex node exec-server requires an exact managed placement workspace.")
    if len(value) != 5:
        raise ValueError("Codex node exec-server requires an exact managed placement workspace.")

    cwd = value.get("cwd")
    env_id = value.get("environmentId", value.get("environment_id"))
    session_id = value.get("sessionId", value.get("session_id"))
    session_key = value.get("sessionKey", value.get("session_key"))
    owner_epoch = value.get("ownerEpoch", value.get("owner_epoch"))

    if (
        not isinstance(cwd, str)
        or not cwd.strip()
        or "\0" in cwd
        or not isinstance(env_id, str)
        or not isinstance(session_id, str)
        or not (0 < len(env_id) <= 256 and 0 < len(session_id) <= 256)
        or "\0" in env_id
        or "\0" in session_id
        or not isinstance(session_key, str)
        or not session_key.strip()
        or "\0" in session_key
        or not isinstance(owner_epoch, int)
        or owner_epoch < 1
    ):
        raise ValueError("Codex node exec-server requires an exact managed placement workspace.")

    return CodexNodePlacementWorkspace(
        cwd=cwd,
        environment_id=env_id,
        session_id=session_id,
        owner_epoch=owner_epoch,
        session_key=session_key,
    )


@dataclass(frozen=True, slots=True)
class CodexNodeHostCommand:
    """Descriptor for the duplex node host command."""

    command: str
    cap: str
    dangerous: bool
    duplex: bool


def create_codex_node_exec_server_command() -> CodexNodeHostCommand:
    """Registers the exact pinned exec-server as an explicitly approved duplex node command."""
    return CodexNodeHostCommand(
        command=CODEX_NODE_EXEC_SERVER_COMMAND,
        cap=CODEX_NODE_EXEC_SERVER_CAPABILITY,
        dangerous=True,
        duplex=True,
    )


def is_codex_exec_server_effectively_invocable(
    cfg: Any, declared_commands: Any
) -> dict[str, Any] | None:
    """Resolve the Codex exec-server command to one closed authority state.

    Mirrors ``resolveRequiredNodeCommandAuthority`` for the single Codex
    command (``summarizeNodeEnvironment`` ``requiredNodeCommand`` shape):
    declaring the command without the Gateway allowlist is insufficient —
    the dangerous command must be explicitly allowed in
    ``gateway.nodes.commands.allow`` and absent from ``commands.deny``.
    Returns ``{"command", "state"}`` (``invocable`` / ``pending-approval``
    / ``undeclared`` / ``unauthorized``) or ``None`` when nothing is
    required. Lazy-imports the gateway policy so plugin load stays light.
    """
    from src.gateway.node_command_policy import (  # noqa: PLC0415
        resolve_required_node_command_authority,
    )

    nodes = (cfg.get("gateway") or {}).get("nodes") or {} if isinstance(cfg, dict) else {}
    commands = nodes.get("commands") or {} if isinstance(nodes, dict) else {}
    allow = commands.get("allow") or [] if isinstance(commands, dict) else []
    deny = commands.get("deny") or [] if isinstance(commands, dict) else []
    allowlist = {c.strip() for c in allow if isinstance(c, str) and c.strip()}
    denied = {c.strip() for c in deny if isinstance(c, str) and c.strip()}
    declared = (
        [c for c in declared_commands if isinstance(c, str)]
        if isinstance(declared_commands, list)
        else []
    )
    effective = [c for c in declared if c in allowlist and c not in denied]
    withheld = [c for c in declared if c in denied]
    return resolve_required_node_command_authority(
        {
            "required_commands": [CODEX_NODE_EXEC_SERVER_COMMAND],
            "declared_commands": declared,
            "effective_commands": effective,
            "withheld_commands": withheld,
            "allowlist": allowlist,
        }
    )


@dataclass(frozen=True, slots=True)
class CodexNodeInvokePolicyResult:
    """Result of an invoke policy evaluation."""

    ok: bool
    code: str | None = None
    message: str | None = None
    decision: str | None = None
    params: dict[str, Any] | None = None


def create_codex_node_exec_server_invoke_policy() -> dict[str, Any]:
    """Keeps node launch behind command opt-in and a live Full owner or human decision."""

    def classify_risk() -> dict[str, str]:
        return {"level": "high", "family": CODEX_NODE_EXEC_SERVER_CAPABILITY}

    async def handle(context: dict[str, Any]) -> CodexNodeInvokePolicyResult:
        risk = context.get("risk")
        if not isinstance(risk, dict) or risk.get("level") != "high":
            return CodexNodeInvokePolicyResult(
                ok=False,
                code="CODEX_NODE_EXEC_APPROVAL_REQUIRED",
                message="Codex node execution requires an available approval reviewer.",
            )

        try:
            placement = parse_codex_node_placement_workspace(context.get("params"))
        except Exception:
            return CodexNodeInvokePolicyResult(
                ok=False,
                code="CODEX_NODE_EXEC_WORKSPACE_INVALID",
                message="Codex node execution requires an exact managed placement workspace.",
            )

        full_launch = context.get("invoke_node_with_session_full")
        if callable(full_launch):
            res = full_launch(placement)
            if inspect.isawaitable(res):
                res = await res
            if res:
                return CodexNodeInvokePolicyResult(
                    ok=True,
                    decision="session-full",
                    params=res if isinstance(res, dict) else {},
                )

        approvals = context.get("approvals")
        if not approvals or not hasattr(approvals, "request"):
            return CodexNodeInvokePolicyResult(
                ok=False,
                code="CODEX_NODE_EXEC_APPROVAL_REQUIRED",
                message="Codex node execution requires an available approval reviewer.",
            )

        node_name = str(context.get("node_name", "paired-device"))
        req_fn = getattr(approvals, "request")
        req_res = req_fn(
            title="Run Codex on this node placement",
            description=(
                f"Allows arbitrary processes and filesystem access across the node account, "
                f"not only this workspace. Allow always applies only while this exact placement "
                f"remains active. {node_name}: {placement.cwd}"
            ),
            severity="critical",
            allowed_decisions=["allow-once", "allow-always"],
        )
        approval = await req_res if inspect.isawaitable(req_res) else req_res

        decision = getattr(approval, "decision", None) or (
            approval.get("decision") if isinstance(approval, dict) else None
        )
        if decision not in ("allow-once", "allow-always"):
            if decision == "deny":
                return CodexNodeInvokePolicyResult(
                    ok=False,
                    code="CODEX_NODE_EXEC_APPROVAL_DENIED",
                    message=(
                        "Codex node execution was denied. Retry the action and choose Allow once "
                        "or Allow always to continue."
                    ),
                )
            return CodexNodeInvokePolicyResult(
                ok=False,
                code="CODEX_NODE_EXEC_APPROVAL_EXPIRED",
                message="Codex node execution approval expired before a decision. Retry the action and approve the new request.",
            )

        invoke_node = context.get("invoke_node")
        if callable(invoke_node):
            node_res = invoke_node(placement=placement, authorization="human-approved")
            if inspect.isawaitable(node_res):
                node_res = await node_res
            return CodexNodeInvokePolicyResult(
                ok=True,
                decision=str(decision),
                params=node_res if isinstance(node_res, dict) else {},
            )

        return CodexNodeInvokePolicyResult(ok=True, decision=str(decision))

    return {
        "commands": [CODEX_NODE_EXEC_SERVER_COMMAND],
        "dangerous": True,
        "standing_approval": {"kind": "placement", "scope": CODEX_NODE_EXEC_SERVER_CAPABILITY},
        "classify_risk": classify_risk,
        "handle": handle,
    }


__all__ = [
    "CODEX_NODE_EXEC_SERVER_CAPABILITY",
    "CODEX_NODE_EXEC_SERVER_COMMAND",
    "CodexNodeHostCommand",
    "CodexNodeInvokePolicyResult",
    "CodexNodePlacementWorkspace",
    "create_codex_node_exec_server_command",
    "create_codex_node_exec_server_invoke_policy",
    "is_codex_exec_server_effectively_invocable",
    "parse_codex_node_placement_workspace",
]
