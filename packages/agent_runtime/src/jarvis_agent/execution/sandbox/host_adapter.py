"""Sandbox Manager and Host Isolation Adapter for Track 3.2.

Integrates with Track 2.3 Host OS sandbox boundaries. Enforces the strict
FAIL-CLOSED INVARIANT: if a capability specifies a sandbox tier that is
unavailable or fails initialization, execution is rejected (SANDBOX_DENIED)
and NEVER silently downgraded to unconstrained host execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import platform
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SandboxContext:
    """Active isolation context for a sandboxed execution attempt."""

    tier: str
    is_confined: bool
    env_overrides: dict[str, str] = field(default_factory=dict)
    job_handle: Any = None
    token_handle: Any = None
    allowed_paths: list[str] = field(default_factory=list)


class SandboxManager:
    """Manages host isolation tiers with strict fail-closed enforcement."""

    def __init__(
        self,
        supported_tiers: set[str] | None = None,
        force_fail_tiers: set[str] | None = None,
    ) -> None:
        # By default on Windows, TIER_0_APP and TIER_1_RESTRICTED_TOKEN are supported.
        # Higher tiers require specific policy or container setups.
        if supported_tiers is not None:
            self._supported_tiers = set(supported_tiers)
        else:
            self._supported_tiers = {"TIER_0_APP"}
            if platform.system().lower() == "windows":
                self._supported_tiers.add("TIER_1_RESTRICTED_TOKEN")

        self._force_fail_tiers = set(force_fail_tiers or [])

    def is_tier_supported(self, tier: str) -> bool:
        """Check whether a requested sandbox tier is supported on this host."""
        if tier in self._force_fail_tiers:
            return False
        return tier in self._supported_tiers

    def check_tier_available(self, tier: str) -> tuple[bool, str | None]:
        """Validate if the required sandbox tier is operational.

        Returns (True, None) if tier is available, or (False, reason) if not.
        """
        if tier in self._force_fail_tiers:
            return False, f"Sandbox tier '{tier}' is explicitly disabled or faulted"
        if tier not in self._supported_tiers:
            return False, f"Sandbox tier '{tier}' is not supported on host OS '{platform.system()}'"
        return True, None

    def prepare_sandbox(
        self,
        capability_id: str,
        tier_required: str,
        allowed_paths: list[str] | None = None,
    ) -> tuple[bool, SandboxContext | None, str | None]:
        """Prepare sandbox isolation context.

        Fails closed: if the required tier cannot be prepared, returns (False, None, error_message).
        """
        ok, err = self.check_tier_available(tier_required)
        if not ok:
            logger.warning(
                "Sandbox preparation failed closed for %s (tier=%s): %s",
                capability_id,
                tier_required,
                err,
            )
            return False, None, err

        # Construct sandbox context
        env: dict[str, str] = {}
        if tier_required != "TIER_0_APP":
            env["JARVIS_SANDBOX_CONFINED"] = "1"
            env["JARVIS_SANDBOX_TIER"] = tier_required

        ctx = SandboxContext(
            tier=tier_required,
            is_confined=(tier_required != "TIER_0_APP"),
            env_overrides=env,
            allowed_paths=list(allowed_paths or []),
        )
        return True, ctx, None


__all__ = ["SandboxContext", "SandboxManager"]
