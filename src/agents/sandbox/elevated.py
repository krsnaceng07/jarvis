"""jarvis.agents.sandbox.elevated — Elevated execution gate for the exec tool.

Mirrors OpenClaw's ``docs/gateway/sandbox-vs-tool-policy-vs-elevated.md``:
- "Elevated" is an exec-only escape hatch from ordinary sandboxes.
- It does NOT grant extra tools; it only changes WHERE exec runs (host vs sandbox).
- Creator-role-required sandboxes REJECT elevated execution completely.
- Gated by tools.elevated.enabled and tools.elevated.allowFrom.<provider>.
"""

from __future__ import annotations

from typing import Any
from .context import SandboxContext


def evaluate_elevated_execution(
    *,
    elevated_requested: bool,
    context: SandboxContext,
    elevated_config: dict[str, Any] | None = None,
    sender_provider: str | None = None,
) -> tuple[bool, str | None]:
    """Evaluate whether an elevated exec request is allowed to escape the sandbox.

    Parameters
    ----------
    elevated_requested:
        Whether the caller passed elevated=True or session has /elevated on.
    context:
        Active SandboxContext facts.
    elevated_config:
        Optional ``tools.elevated`` configuration mapping.
    sender_provider:
        Provider/channel ID of the user requesting execution.

    Returns
    -------
    tuple[bool, str | None]
        (is_elevated_granted, refusal_reason)
    """
    if not elevated_requested:
        return False, None

    # 1. Creator role immutable requirement
    # Creator-role-required sandboxes reject elevated execution completely.
    if context.creator_required:
        return (
            False,
            "Elevated execution is blocked: this session's creator role requires sandboxing.",
        )

    # 2. If already running on host (not sandboxed), elevated is a no-op
    if not context.is_sandboxed:
        return True, None

    # 3. Check tools.elevated.enabled
    cfg = elevated_config or {}
    enabled = bool(cfg.get("enabled", True))
    if not enabled:
        return (
            False,
            "Elevated execution is disabled by configuration (tools.elevated.enabled=false).",
        )

    # 4. Check sender allowlists
    allow_from = cfg.get("allowFrom", cfg.get("allow_from"))
    if allow_from and isinstance(allow_from, dict) and sender_provider:
        prov_allow = allow_from.get(sender_provider)
        if prov_allow is not None:
            if not prov_allow:
                return (
                    False,
                    f"Elevated execution is not allowed from provider '{sender_provider}'.",
                )

    return True, None
