"""jarvis.gateway.node_command_policy — node command allow/deny evaluation.

OpenClaw parity: mirrors the portable decision core of
``openclaw-main/src/gateway/node-command-policy.ts``
(``DEFAULT_DANGEROUS_NODE_COMMANDS``, ``normalizeDeclaredNodeCommands``,
``isNodeCommandAllowed``, ``resolveRequiredNodeCommandAuthority``,
``retainFulfilledNodeCapabilities``) plus the private-command set from
``openclaw-main/src/infra/node-commands.ts``.

Boundary: the per-platform default matrices, live plugin policy registry,
and pairing handshake live in surfaces Jarvis has not built yet
(no node command registry, no pairing approval flow). Those stay out
until their owners land; this module owns only the pure evaluation
(which command sets admit a required command), consumed today by the
Codex exec-server effectively-invocable check.
"""

from __future__ import annotations

from typing import Any

#: Desktop stream command (dangerous screen family). Mirrors
#: ``NODE_DESKTOP_STREAM_COMMAND``.
NODE_DESKTOP_STREAM_COMMAND = "desktop.stream"

#: Worker-private commands: never advertised or operator-invocable. Mirrors
#: ``NODE_WORKER_PRIVATE_COMMANDS``.
NODE_WORKER_PRIVATE_COMMANDS: tuple[str, ...] = (
    "worker.bundle.install.v1",
    "worker.launch.v1",
    "worker.status.v1",
    "worker.cancel.v1",
    "worker.environment.stop.v1",
    "worker.workspace.exec.v1",
    "worker.workspace.retain.v1",
    "worker.desktop.stream.v1",
    "worker.desktop.launch.v1",
    "worker.desktop.computer.v1",
    "worker.portal.stream.v1",
)

#: "High risk" built-in node commands. Enabled only by explicitly adding
#: them to ``gateway.nodes.commands.allow`` (and keeping them out of
#: ``commands.deny``). Mirrors ``DEFAULT_DANGEROUS_NODE_COMMANDS``.
DEFAULT_DANGEROUS_NODE_COMMANDS: tuple[str, ...] = (
    "camera.snap",
    "camera.clip",
    "camera.ptz.control",
    "screen.record",
    NODE_DESKTOP_STREAM_COMMAND,
    "contacts.add",
    "calendar.add",
    "reminders.add",
    "sms.send",
    "sms.search",
    "health.summary",
)

#: Capability → fulfilling command families. A capability whose commands
#: policy withheld, without admitting a sibling, reads as available and
#: then rejects every invoke — so it is dropped. Families core does not
#: own stay untouched. Mirrors ``CAPABILITY_COMMAND_FAMILIES``.
CAPABILITY_COMMAND_FAMILIES: dict[str, frozenset[str]] = {
    "camera": frozenset(
        {"camera.list", "camera.ptz.status", "camera.snap", "camera.clip", "camera.ptz.control"}
    ),
    "computer": frozenset({"computer.act"}),
    "location": frozenset({"location.get"}),
    "screen": frozenset({"screen.snapshot", "screen.record", NODE_DESKTOP_STREAM_COMMAND}),
}

_PRIVATE_COMMANDS = frozenset(NODE_WORKER_PRIVATE_COMMANDS)


def is_private_node_invoke_command(command: Any) -> bool:
    """Return whether *command* is a private worker control.

    Mirrors ``isPrivateNodeInvokeCommand``.
    """
    return isinstance(command, str) and command.strip() in _PRIVATE_COMMANDS


def normalize_declared_node_commands(params: dict[str, Any]) -> list[str]:
    """Filter node-declared commands to the allowlisted, public subset.

    Mirrors ``normalizeDeclaredNodeCommands``. Takes
    ``{"declared_commands": [...], "allowlist": set([...])}``.
    """
    declared = params.get("declared_commands")
    allowlist = params.get("allowlist") or set()
    if not isinstance(declared, list):
        return []
    seen: set[str] = set()
    normalized: list[str] = []
    for value in declared:
        if not isinstance(value, str):
            continue
        trimmed = value.strip()
        if not trimmed or trimmed in seen or is_private_node_invoke_command(trimmed):
            continue
        seen.add(trimmed)
        normalized.append(trimmed)
    return [command for command in normalized if command in allowlist]


def is_node_command_allowed(params: dict[str, Any]) -> dict[str, Any]:
    """Check one command against declaration + allowlist.

    Mirrors ``isNodeCommandAllowed``. Takes ``{"command": ...,
    "declared_commands": [...], "allowlist": set([...])}``. Returns
    ``{"ok": True}`` or ``{"ok": False, "reason": ...}`` with reasons
    ``command required`` / ``command not allowlisted`` /
    ``command not declared by node`` / ``node did not declare commands``.
    """
    raw = params.get("command")
    command = raw.strip() if isinstance(raw, str) else ""
    if not command:
        return {"ok": False, "reason": "command required"}
    if is_private_node_invoke_command(command):
        return {"ok": False, "reason": "command not allowlisted"}
    allowlist = params.get("allowlist") or set()
    if command not in allowlist:
        return {"ok": False, "reason": "command not allowlisted"}
    declared = params.get("declared_commands")
    if isinstance(declared, list) and len(declared) > 0:
        if command not in declared:
            return {"ok": False, "reason": "command not declared by node"}
    else:
        return {"ok": False, "reason": "node did not declare commands"}
    return {"ok": True}


def resolve_required_node_command_authority(params: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve declaration + pairing + runtime policy to one closed state.

    Mirrors ``resolveRequiredNodeCommandAuthority``. Takes
    ``{"required_commands": [...], "declared_commands": [...],
    "effective_commands": [...], "withheld_commands": [...], "allowlist":
    set([...])}``. Returns ``{"command", "state"}`` with state
    ``invocable`` / ``pending-approval`` / ``undeclared`` /
    ``unauthorized``, or ``None`` when nothing is required. A denial
    anywhere in the required set takes precedence over pairing approval.
    """
    required = params.get("required_commands") or []
    if not isinstance(required, list):
        return None
    declared = set(params.get("declared_commands") or [])
    effective = set(params.get("effective_commands") or [])
    withheld = list(params.get("withheld_commands") or [])
    allowlist = params.get("allowlist") or set()
    denied = next((cmd for cmd in required if cmd in withheld), None)
    if denied is not None:
        return {"command": denied, "state": "unauthorized"}
    for command in required:
        allowed = is_node_command_allowed(
            {"command": command, "declared_commands": list(effective), "allowlist": allowlist}
        )
        if command in effective and allowed.get("ok") is True:
            continue
        if command in declared and command not in effective:
            return {"command": command, "state": "pending-approval"}
        if command in declared:
            return {"command": command, "state": "unauthorized"}
        return {"command": command, "state": "undeclared"}
    first = required[0] if required else None
    return {"command": first, "state": "invocable"} if first is not None else None


def retain_fulfilled_node_capabilities(params: dict[str, Any]) -> list[str]:
    """Drop capabilities whose commands policy withheld without a sibling.

    Mirrors ``retainFulfilledNodeCapabilities``. Takes ``{"caps": [...],
    "admitted_commands": [...], "withheld_commands": [...]}``.
    """
    caps = params.get("caps") or []
    admitted = params.get("admitted_commands") or []
    withheld = params.get("withheld_commands") or []
    kept: list[str] = []
    for capability in caps:
        if not isinstance(capability, str):
            continue
        family = CAPABILITY_COMMAND_FAMILIES.get(capability)
        if (
            family is None
            or not any(command in family for command in withheld)
            or any(command in family for command in admitted)
        ):
            kept.append(capability)
    return kept


__all__ = [
    "CAPABILITY_COMMAND_FAMILIES",
    "DEFAULT_DANGEROUS_NODE_COMMANDS",
    "NODE_DESKTOP_STREAM_COMMAND",
    "NODE_WORKER_PRIVATE_COMMANDS",
    "is_node_command_allowed",
    "is_private_node_invoke_command",
    "normalize_declared_node_commands",
    "resolve_required_node_command_authority",
    "retain_fulfilled_node_capabilities",
]
