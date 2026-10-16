"""jarvis.agents.delegation_capability — delegation capability enforcement.

OpenClaw parity: mirrors ``src/agents/delegation-capability.ts``.

Controls whether an agent run may spawn new sub-agents / delegation tools
or is restricted to read-only completion-reporting.

Two modes:
  ``full``        — run may use all delegation tools
  ``report_only`` — run is delivering a completion through a fallback model;
                    new delegation is blocked; only safe status/list/get
                    actions on task-management tools are permitted.

Public surface
--------------
``DelegationCapability``
``NEW_DELEGATION_TOOL_NAMES``
``REPORT_ONLY_TOOL_ACTIONS``
``resolve_delegation_capability``
``enforce_delegation_capability``
"""

from __future__ import annotations

from typing import Any, Literal

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

DelegationCapability = Literal["full", "report_only"]

# ---------------------------------------------------------------------------
# Tool name/action constants (mirrors delegation-capability.ts)
# ---------------------------------------------------------------------------

NEW_DELEGATION_TOOL_NAMES: frozenset[str] = frozenset({
    "codex_session_send",
    "llm-task",
    "openclaw",
    "sessions_send",
    "sessions_spawn",
})

# Tools restricted to these actions in report_only mode.
REPORT_ONLY_TOOL_ACTIONS: dict[str, frozenset[str]] = {
    "cron": frozenset({"get", "list", "remove", "runs", "status"}),
    "image_generate": frozenset({"list", "status"}),
    "music_generate": frozenset({"list", "status"}),
    "video_generate": frozenset({"list", "status"}),
}

_REPORT_ONLY_ERROR = (
    "New delegation is unavailable while reporting a completion through a fallback model."
)

# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def resolve_delegation_capability(
    *,
    fallback_active: bool,
    input_provenance: Any = None,
) -> DelegationCapability:
    """Resolve the delegation capability for a run.

    Mirrors ``resolveDelegationCapability``.

    When both *fallback_active* is True AND the input comes from a
    completion-report provenance, delegation is restricted to ``report_only``.
    """
    if fallback_active and _is_completion_report_provenance(input_provenance):
        return "report_only"
    return "full"


def _is_completion_report_provenance(provenance: Any) -> bool:
    """True when *provenance* marks a completion-report input.

    Mirrors ``isCompletionReportInputProvenance``.
    """
    if not provenance or not isinstance(provenance, dict):
        return False
    kind = provenance.get("kind") or provenance.get("type") or ""
    return str(kind).lower() in {"completion_report", "completionreport", "completion-report"}


# ---------------------------------------------------------------------------
# Enforcement
# ---------------------------------------------------------------------------


def _read_tool_action(params: Any) -> str:
    """Extract the ``action`` field from tool params. Mirrors ``readToolAction``."""
    if not params or not isinstance(params, dict):
        return ""
    action = params.get("action")
    return str(action).strip().lower() if isinstance(action, str) else ""


class DelegationCapabilityError(Exception):
    """Raised when a delegation-restricted tool is called in report_only mode."""


def enforce_delegation_capability(
    tool_name: str,
    params: Any,
    capability: DelegationCapability | None,
) -> None:
    """Raise :class:`DelegationCapabilityError` if *capability* blocks this call.

    Mirrors ``applyDelegationCapability`` (the per-call enforcement logic).

    Call this before executing any tool whose name is in
    ``NEW_DELEGATION_TOOL_NAMES`` or ``REPORT_ONLY_TOOL_ACTIONS``.
    """
    if capability != "report_only":
        return

    normalized = (tool_name or "").strip().lower()

    # Fully-blocked delegation tools.
    if normalized in NEW_DELEGATION_TOOL_NAMES:
        raise DelegationCapabilityError(_REPORT_ONLY_ERROR)

    # Partially-blocked task tools — only safe read/status actions are allowed.
    allowed_actions = REPORT_ONLY_TOOL_ACTIONS.get(normalized)
    if allowed_actions is not None:
        action = _read_tool_action(params)
        if action not in allowed_actions:
            raise DelegationCapabilityError(_REPORT_ONLY_ERROR)


__all__ = [
    "REPORT_ONLY_TOOL_ACTIONS",
    "NEW_DELEGATION_TOOL_NAMES",
    "DelegationCapability",
    "DelegationCapabilityError",
    "enforce_delegation_capability",
    "resolve_delegation_capability",
]
