"""Policy evaluation, approval grants, and bounded in-memory caching.

OpenClaw parity: mirrors @openclaw/onepassword policy handling:
- Tiers: `auto`, `approve`, `deny`
- Standing grants via SQLite with `grantTtlHours` (default 720h)
- Max 600s approval window
- Bounded in-memory cache with `cacheTtlSeconds` (default 300s)
- Policy is strictly evaluated before every cache hit
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Coroutine

from .config import MAX_APPROVAL_WAIT_SECONDS, OnepasswordConfig
from .storage import OnepasswordStorage
from .types import (
    APPROVAL_CANCELLED,
    POLICY_NOT_EVALUATED,
    UNKNOWN_SLUG,
    ApprovalDecision,
    PolicyTier,
)

logger = logging.getLogger("jarvis.onepassword.policy")

ApprovalHook = Callable[[str, str, str], Coroutine[Any, Any, ApprovalDecision]]


class BoundedInMemoryCache:
    """In-memory cache bounded by registered slugs with TTL."""

    def __init__(self, ttl_seconds: int = 300) -> None:
        self.ttl_seconds = ttl_seconds
        self._entries: dict[str, tuple[str, float]] = {}

    def get(self, slug: str, now: float | None = None) -> str | None:
        if self.ttl_seconds <= 0:
            return None
        current_time = time.time() if now is None else now
        entry = self._entries.get(slug)
        if not entry:
            return None
        value, timestamp = entry
        if current_time - timestamp > self.ttl_seconds:
            self._entries.pop(slug, None)
            return None
        return value

    def set(self, slug: str, value: str, now: float | None = None) -> None:
        if self.ttl_seconds <= 0:
            return
        current_time = time.time() if now is None else now
        self._entries[slug] = (value, current_time)

    def invalidate(self, slug: str | None = None) -> None:
        if slug:
            self._entries.pop(slug, None)
        else:
            self._entries.clear()


class PolicyEvaluator:
    """Coordinates policy checks, standing grant checks, and interactive approvals."""

    def __init__(
        self,
        config: OnepasswordConfig,
        storage: OnepasswordStorage,
        approval_hook: ApprovalHook | None = None,
    ) -> None:
        self.config = config
        self.storage = storage
        self.approval_hook = approval_hook
        self.cache = BoundedInMemoryCache(ttl_seconds=config.cache_ttl_seconds)

    def update_config(self, new_config: OnepasswordConfig) -> None:
        """Update runtime config and invalidate cache if settings change."""
        self.config = new_config
        self.cache.ttl_seconds = new_config.cache_ttl_seconds
        self.cache.invalidate()

    async def evaluate_access(
        self,
        slug: str,
        reason: str,
        agent_id: str = "",
        now: float | None = None,
    ) -> tuple[str | None, str | None, str | None]:
        """Evaluate access policy for slug.

        Returns (authorization_nonce, error_code, error_message).
        """
        current_time = time.time() if now is None else now

        # 1. Validate slug existence in registry
        if slug not in self.config.items:
            self.storage.record_audit(
                slug=slug,
                action="get",
                outcome="denied",
                agent_id=agent_id,
                error_code=UNKNOWN_SLUG,
                reason=reason,
                cached=False,
                now=current_time,
            )
            return None, UNKNOWN_SLUG, f"Slug '{slug}' is not in the configured registry"

        policy: PolicyTier = self.config.get_effective_policy(slug)

        # 2. Deny policy
        if policy == "deny":
            self.storage.record_audit(
                slug=slug,
                action="get",
                outcome="denied",
                agent_id=agent_id,
                error_code=POLICY_NOT_EVALUATED,
                reason=reason,
                cached=False,
                now=current_time,
            )
            return None, POLICY_NOT_EVALUATED, f"Access to secret slug '{slug}' is denied by policy"

        # 3. Auto policy
        if policy == "auto":
            nonce = self.storage.create_authorization_nonce(
                agent_id=agent_id,
                slug=slug,
                ttl_seconds=MAX_APPROVAL_WAIT_SECONDS,
                now=current_time,
            )
            return nonce, None, None

        # 4. Approve policy
        if policy == "approve":
            # Check standing grant
            if self.storage.has_standing_grant(agent_id, slug, now=current_time):
                nonce = self.storage.create_authorization_nonce(
                    agent_id=agent_id,
                    slug=slug,
                    ttl_seconds=MAX_APPROVAL_WAIT_SECONDS,
                    now=current_time,
                )
                return nonce, None, None

            # Need interactive approval
            if not self.approval_hook:
                # No approval hook registered -> deny
                self.storage.record_audit(
                    slug=slug,
                    action="get",
                    outcome="denied",
                    agent_id=agent_id,
                    error_code=POLICY_NOT_EVALUATED,
                    reason=reason,
                    cached=False,
                    now=current_time,
                )
                return (
                    None,
                    POLICY_NOT_EVALUATED,
                    f"Access to secret slug '{slug}' requires approval, but no approval handler is active",
                )

            try:
                # Wait for approval up to MAX_APPROVAL_WAIT_SECONDS
                decision: ApprovalDecision = await asyncio.wait_for(
                    self.approval_hook(slug, reason, agent_id),
                    timeout=float(MAX_APPROVAL_WAIT_SECONDS),
                )
            except asyncio.TimeoutError:
                self.storage.record_audit(
                    slug=slug,
                    action="get",
                    outcome="denied",
                    agent_id=agent_id,
                    error_code=APPROVAL_CANCELLED,
                    reason=reason,
                    cached=False,
                    now=current_time,
                )
                return None, APPROVAL_CANCELLED, "Approval request timed out"
            except Exception as exc:
                self.storage.record_audit(
                    slug=slug,
                    action="get",
                    outcome="denied",
                    agent_id=agent_id,
                    error_code=APPROVAL_CANCELLED,
                    reason=reason,
                    cached=False,
                    now=current_time,
                )
                return None, APPROVAL_CANCELLED, f"Approval request failed: {exc}"

            if decision == "deny":
                self.storage.record_audit(
                    slug=slug,
                    action="get",
                    outcome="denied",
                    agent_id=agent_id,
                    error_code=APPROVAL_CANCELLED,
                    reason=reason,
                    cached=False,
                    now=current_time,
                )
                return (
                    None,
                    APPROVAL_CANCELLED,
                    f"Access to secret slug '{slug}' was denied by user",
                )

            if decision == "allow_always":
                if agent_id:
                    self.storage.save_standing_grant(
                        agent_id=agent_id,
                        slug=slug,
                        grant_ttl_hours=self.config.grant_ttl_hours,
                        now=current_time,
                    )

            nonce = self.storage.create_authorization_nonce(
                agent_id=agent_id,
                slug=slug,
                ttl_seconds=MAX_APPROVAL_WAIT_SECONDS,
                now=current_time,
            )
            return nonce, None, None

        return None, POLICY_NOT_EVALUATED, "Unknown policy evaluation state"
