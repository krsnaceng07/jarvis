"""jarvis.agents.embedded_agent_runner.run.permission_change — Permission change coordination.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/permission-change.ts``.
"""

from __future__ import annotations

import asyncio
from typing import Any

PERMISSION_CHANGE_NOTICE = (
    "Permission change. The operator changed this session's permissions. "
    "Continue with the updated policy, preserving completed work. "
    "Inspect interrupted actions before retrying them; do not repeat completed actions."
)

_permission_change_authorities: dict[int, dict[str, Any]] = {}


def with_authorized_permission_change(owner: Any, mode: str | None, apply_fn: Any) -> Any:
    key = id(owner)
    authority = _permission_change_authorities.get(key)
    if authority is None:
        raise RuntimeError("Permission change run owner is no longer active.")
    previous = authority.get("authorized")
    authority["authorized"] = {"mode": mode}
    try:
        return apply_fn()
    finally:
        authority["authorized"] = previous


class EmbeddedRunPermissionChanges:
    def __init__(self, params: dict[str, Any]) -> None:
        self.params = params
        self.owner = object()
        self.authority: dict[str, Any] = {}
        _permission_change_authorities[id(self.owner)] = self.authority
        self.base_exec_overrides = dict(params.get("execOverrides") or {})
        self.revision = 0
        self.pending_future: asyncio.Future[bool] | None = None
        self.pending_mode: str | None = None

    def _assert_authorized(self, mode: str | None) -> None:
        auth = _permission_change_authorities.get(id(self.owner))
        if auth is not self.authority or auth.get("authorized", {}).get("mode") != mode:
            raise RuntimeError("Permission change was not authorized by the current operator request.")

    def _update_permission_mode(self, mode: str | None) -> None:
        self.params["permissionMode"] = mode
        if "execOverrides" not in self.params:
            self.params["execOverrides"] = {}
        if mode:
            self.params["execOverrides"]["mode"] = mode
        else:
            self.params["execOverrides"]["mode"] = self.base_exec_overrides.get("mode")

    def for_attempt(self) -> dict[str, Any]:
        prepared_revision = self.revision
        res: dict[str, Any] = {
            "owner": self.owner,
            "baseExecOverrides": self.base_exec_overrides,
            "recordApplied": lambda mode: (self._assert_authorized(mode), self._update_permission_mode(mode)),
            "applied": lambda: self._applied(prepared_revision),
        }
        if self.revision > 0:
            res["notice"] = (
                f"{PERMISSION_CHANGE_NOTICE} Requested mode: "
                f"{self.params.get('permissionMode') or 'default'}."
            )
        return res

    def _applied(self, prepared_revision: int) -> bool:
        if id(self.owner) not in _permission_change_authorities or prepared_revision != self.revision:
            return False
        if self.pending_future and not self.pending_future.done():
            self.pending_future.set_result(True)
        self.pending_future = None
        self.pending_mode = None
        return True

    def prepare_restart(self) -> bool:
        if id(self.owner) not in _permission_change_authorities or not self.pending_future:
            return False
        self._update_permission_mode(self.pending_mode)
        return True

    def close(self) -> None:
        _permission_change_authorities.pop(id(self.owner), None)
        if self.pending_future and not self.pending_future.done():
            self.pending_future.set_result(False)
        self.pending_future = None
        self.pending_mode = None


def create_embedded_run_permission_changes(params: dict[str, Any]) -> EmbeddedRunPermissionChanges:
    return EmbeddedRunPermissionChanges(params)


__all__ = [
    "PERMISSION_CHANGE_NOTICE",
    "with_authorized_permission_change",
    "EmbeddedRunPermissionChanges",
    "create_embedded_run_permission_changes",
]
