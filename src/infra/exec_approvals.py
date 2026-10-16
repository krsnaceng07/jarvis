"""src.infra.exec_approvals - exec mode definitions and resolvers.

OpenClaw parity: mirrors ``openclaw-main/src/infra/exec-approvals.ts``
and related schema logic.
"""

from typing import Literal, TypedDict

from src.infra.exec_approvals_store import (
    read_exec_approvals_snapshot,
    write_exec_approvals_snapshot,
)
from src.infra.exec_approvals_types import ExecAllowlistEntry


ExecHost = Literal["sandbox", "gateway", "node"]
ExecTarget = Literal["auto", "sandbox", "gateway", "node"]
ExecSecurity = Literal["deny", "allowlist", "full"]
ExecAsk = Literal["off", "on-miss", "always"]
ExecMode = Literal["deny", "allowlist", "ask", "auto", "full"]

EXEC_TARGET_VALUES = ("auto", "sandbox", "gateway", "node")


def normalize_exec_host(value: str | None) -> ExecHost | None:
    if not value:
        return None
    normalized = value.strip().lower()
    if normalized in ("sandbox", "gateway", "node"):
        return normalized  # type: ignore
    return None


def normalize_exec_target(value: str | None) -> ExecTarget | None:
    if not value:
        return None
    normalized = value.strip().lower()
    if normalized == "auto":
        return "auto"
    return normalize_exec_host(normalized)  # type: ignore


def require_valid_exec_target(value: str | None) -> ExecTarget | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(
            f"Invalid exec host value type {type(value).__name__}. "
            f"Allowed values: {', '.join(EXEC_TARGET_VALUES)}."
        )
    normalized = value.strip().lower()
    if not normalized:
        return None
    target = normalize_exec_target(normalized)
    if target:
        return target
    raise ValueError(
        f'Invalid exec host "{value}". Allowed values: {", ".join(EXEC_TARGET_VALUES)}.'
    )


def normalize_exec_security(value: str | None) -> ExecSecurity | None:
    if not value:
        return None
    normalized = value.strip().lower()
    if normalized in ("deny", "allowlist", "full"):
        return normalized  # type: ignore
    return None


def normalize_exec_ask(value: str | None) -> ExecAsk | None:
    if not value:
        return None
    normalized = value.strip().lower()
    if normalized in ("off", "on-miss", "always"):
        return normalized  # type: ignore
    return None


def normalize_exec_mode(value: str | None) -> ExecMode | None:
    if not value:
        return None
    normalized = value.strip().lower()
    if normalized in ("deny", "allowlist", "ask", "auto", "full"):
        return normalized  # type: ignore
    return None


def resolve_exec_mode_from_policy(security: ExecSecurity, ask: ExecAsk) -> ExecMode:
    if security == "deny":
        return "deny"
    if security == "allowlist" and ask == "off":
        return "allowlist"
    if security == "full" and ask != "always":
        return "full"
    return "ask"


class ExecPolicyForModeResult(TypedDict):
    security: ExecSecurity
    ask: ExecAsk
    autoReview: bool


def resolve_exec_policy_for_mode(mode: ExecMode) -> ExecPolicyForModeResult:
    if mode == "deny":
        return {"security": "deny", "ask": "off", "autoReview": False}
    if mode == "allowlist":
        return {"security": "allowlist", "ask": "off", "autoReview": False}
    if mode == "ask":
        return {"security": "allowlist", "ask": "on-miss", "autoReview": False}
    if mode == "auto":
        return {"security": "allowlist", "ask": "on-miss", "autoReview": True}
    if mode == "full":
        return {"security": "full", "ask": "off", "autoReview": False}
    
    raise ValueError(f"Unsupported exec mode: {mode}")


class ResolvedExecModePolicy(TypedDict):
    mode: ExecMode
    security: ExecSecurity
    ask: ExecAsk
    autoReview: bool


def resolve_exec_mode_policy(
    mode: ExecMode | None, security: ExecSecurity, ask: ExecAsk
) -> ResolvedExecModePolicy:
    if not mode:
        return {
            "mode": resolve_exec_mode_from_policy(security, ask),
            "security": security,
            "ask": ask,
            "autoReview": False,
        }
    policy = resolve_exec_policy_for_mode(mode)
    return {
        "mode": mode,
        "security": policy["security"],
        "ask": policy["ask"],
        "autoReview": policy["autoReview"],
    }


def add_allowlist_entry(
    agent_id: str | None,
    pattern: str,
    arg_pattern: str | None = None,
    source: Literal["allow-always"] | None = None,
) -> None:
    snapshot = read_exec_approvals_snapshot()
    file_data = snapshot["file"]

    target = agent_id or "main"
    agents = file_data.setdefault("agents", {})
    existing = agents.setdefault(target, {})
    allowlist: list[ExecAllowlistEntry] = existing.setdefault("allowlist", [])

    trimmed = pattern.strip()
    if not trimmed:
        return

    arg_pattern_val = None if arg_pattern == "" else arg_pattern

    for entry in allowlist:
        if entry.get("pattern") == trimmed and entry.get("argPattern") == arg_pattern_val:
            if not source or entry.get("source") == source:
                return  # Already exists with same source

            entry["source"] = source
            write_exec_approvals_snapshot(file_data)
            return

    new_entry: ExecAllowlistEntry = {"pattern": trimmed}
    if arg_pattern_val is not None:
        new_entry["argPattern"] = arg_pattern_val
    if source is not None:
        new_entry["source"] = source

    allowlist.append(new_entry)
    write_exec_approvals_snapshot(file_data)


def add_durable_command_approval(agent_id: str | None, command_text: str) -> None:
    normalized = command_text.strip()
    if not normalized:
        return
    add_allowlist_entry(agent_id, normalized, source="allow-always")
