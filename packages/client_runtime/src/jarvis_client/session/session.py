"""Session context and client identity container for Track 3.5.

Represents the client's logical interaction context across connections.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ClientSession:
    """Active client session state and identity."""

    session_id: str
    client_id: str
    user_id: str
    scopes: frozenset[str] = field(default_factory=frozenset)
    session_grants: frozenset[str] = field(default_factory=frozenset)
    metadata: dict[str, Any] = field(default_factory=dict)

    def has_scope(self, scope: str) -> bool:
        return "admin" in self.scopes or scope in self.scopes

    def is_authorized_for_task(self, task_id: str) -> bool:
        if "admin" in self.scopes or "*" in self.session_grants:
            return True
        return task_id in self.session_grants


__all__ = ["ClientSession"]
