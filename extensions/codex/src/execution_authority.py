"""Gateway-provided Codex execution authority and runtime inventory checks."""

from __future__ import annotations

from typing import Any


def check_codex_execution_authority(
    *,
    scheduled: bool = False,
    authority: dict[str, Any] | None = None,
    inventory_snapshot: dict[str, Any] | None = None,
    expected_inventory_snapshot: dict[str, Any] | None = None,
) -> tuple[bool, str | None]:
    """Validate optional Gateway controls before starting a native turn.

    Interactive turns need no extra authority. Scheduled turns require an
    explicit Gateway grant, and supplied runtime snapshots must match exactly
    on the fields that protect provider/app/plugin ownership.
    """
    if scheduled and (not isinstance(authority, dict) or authority.get("allowed") is not True):
        return False, "scheduled Codex execution requires Gateway authority"

    if expected_inventory_snapshot is None:
        return True, None
    if not isinstance(inventory_snapshot, dict):
        return False, "Codex runtime inventory snapshot is missing"
    for key in ("providerId", "modelId", "appServerVersion", "pluginIds"):
        if inventory_snapshot.get(key) != expected_inventory_snapshot.get(key):
            return False, f"Codex runtime inventory snapshot mismatch: {key}"
    return True, None


__all__ = ["check_codex_execution_authority"]
