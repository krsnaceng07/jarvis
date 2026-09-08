"""Authorization predicates for `/codex` host mutations.

OpenClaw parity: mirrors
``openclaw-main/extensions/codex/src/command-authorization.ts``.

Adaptation: OpenClaw distinguishes owner senders from
``operator.admin``-scoped gateway clients (notably: ``yolo`` requires
admin even for an owner). Jarvis flattens both into
``CodexCommandContext.is_admin`` until gateway scopes land, so the two
predicates currently coincide. The separate names (and the yolo error
text) preserve the call sites the scope split will need.
"""

from __future__ import annotations

from typing import Any

#: Mirrors ``CODEX_NATIVE_EXECUTION_AUTH_ERROR``.
CODEX_NATIVE_EXECUTION_AUTH_ERROR = (
    "Only an owner or operator.admin can control Codex native execution."
)

#: Mirrors ``CODEX_HOST_INSPECTION_AUTH_ERROR``.
CODEX_HOST_INSPECTION_AUTH_ERROR = "Only an owner or operator.admin can inspect Codex host state."

#: Mirrors ``CODEX_FULL_PERMISSIONS_AUTH_ERROR``.
CODEX_FULL_PERMISSIONS_AUTH_ERROR = (
    "Full Codex permissions require operator.admin. Choose Admin in the "
    "Control UI permission picker, or use an admin-authenticated CLI."
)


def has_admin_scope(ctx: Any) -> bool:
    """Mirror ``hasCodexAdminScope`` over the flattened Jarvis context."""
    return bool(getattr(ctx, "is_admin", False))


def can_mutate_host(ctx: Any) -> bool:
    """Mirror ``canMutateCodexHost`` (owner or admin scope)."""
    return bool(getattr(ctx, "is_admin", False))


__all__ = [
    "CODEX_FULL_PERMISSIONS_AUTH_ERROR",
    "CODEX_HOST_INSPECTION_AUTH_ERROR",
    "CODEX_NATIVE_EXECUTION_AUTH_ERROR",
    "can_mutate_host",
    "has_admin_scope",
]
