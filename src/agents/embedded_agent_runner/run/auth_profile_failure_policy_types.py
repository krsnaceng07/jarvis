"""jarvis.agents.embedded_agent_runner.run.auth_profile_failure_policy_types — auth-profile failure-policy types.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/auth-profile-failure-policy.types.ts``.

Public surface:

Types:

- :data:`AuthProfileFailureReason`

Phase 7.6h-2 — focused minimal port.
"""
from __future__ import annotations

from typing import Optional


#: Auth profile failure reason. Mirrors
#: :type:`AuthProfileFailureReason`
#: (``auth-profile-failure-policy.types.ts``).
AuthProfileFailureReason = Optional[str]


__all__ = [
    "AuthProfileFailureReason",
]
