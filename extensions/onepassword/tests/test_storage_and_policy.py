"""Unit tests for SQLite state storage, audit logging, standing grants, and policy evaluation."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from extensions.onepassword.src.config import (
    MAX_STANDING_GRANTS,
    OnepasswordConfig,
    OnepasswordItemConfig,
)
from extensions.onepassword.src.policy import BoundedInMemoryCache, PolicyEvaluator
from extensions.onepassword.src.storage import OnepasswordStorage
from extensions.onepassword.src.types import (
    POLICY_NOT_EVALUATED,
    UNKNOWN_SLUG,
)


def test_storage_audit_log(tmp_path: Path) -> None:
    """Test recording and retrieving audit logs from SQLite."""
    db_path = tmp_path / "test.sqlite"
    storage = OnepasswordStorage(db_path=db_path)

    # Record entries
    r1 = storage.record_audit(
        slug="repo-token",
        action="get",
        outcome="allowed",
        agent_id="agent-007",
        reason="Perform git clone",
        cached=False,
    )
    assert r1.slug == "repo-token"
    assert r1.outcome == "allowed"

    r2 = storage.record_audit(
        slug="db-pass",
        action="get",
        outcome="denied",
        agent_id="agent-007",
        error_code=POLICY_NOT_EVALUATED,
        reason="Unauthorized attempt",
        cached=False,
    )
    assert r2.outcome == "denied"

    # Fetch logs
    logs = storage.get_audit_log(limit=10)
    assert len(logs) == 2
    assert logs[0].slug == "db-pass"
    assert logs[0].outcome == "denied"
    assert logs[1].slug == "repo-token"
    assert logs[1].outcome == "allowed"

    # Filter by slug
    repo_logs = storage.get_audit_log(limit=10, slug="repo-token")
    assert len(repo_logs) == 1
    assert repo_logs[0].slug == "repo-token"


def test_standing_grants_lifecycle_and_lru(tmp_path: Path) -> None:
    """Test standing grants creation, expiry, and LRU eviction."""
    db_path = tmp_path / "test_grants.sqlite"
    storage = OnepasswordStorage(db_path=db_path)

    now = 100000.0

    # 1. Save standing grant
    grant = storage.save_standing_grant(
        agent_id="agent-1",
        slug="api-key",
        grant_ttl_hours=720,
        now=now,
    )
    assert grant.agent_id == "agent-1"
    assert grant.slug == "api-key"
    assert grant.expires_at == now + (720 * 3600.0)

    # 2. Check active grant
    assert storage.has_standing_grant("agent-1", "api-key", now=now + 100) is True

    # 3. Check for different agent or slug
    assert storage.has_standing_grant("agent-2", "api-key", now=now + 100) is False
    assert storage.has_standing_grant("agent-1", "other-slug", now=now + 100) is False

    # 4. Check expired grant
    future = now + (721 * 3600.0)
    assert storage.has_standing_grant("agent-1", "api-key", now=future) is False

    # 5. Test LRU eviction at MAX_STANDING_GRANTS
    for i in range(MAX_STANDING_GRANTS):
        storage.save_standing_grant(
            agent_id=f"agent-{i}",
            slug="shared-slug",
            grant_ttl_hours=100,
            now=now + i,
        )

    # Total grants should be capped at MAX_STANDING_GRANTS
    all_grants = storage.list_standing_grants(now=now)
    assert len(all_grants) == MAX_STANDING_GRANTS

    # Adding one more should evict oldest (agent-0)
    storage.save_standing_grant(
        agent_id="agent-new",
        slug="shared-slug",
        grant_ttl_hours=100,
        now=now + MAX_STANDING_GRANTS + 10,
    )

    all_grants_after = storage.list_standing_grants(now=now)
    assert len(all_grants_after) == MAX_STANDING_GRANTS
    assert any(g.agent_id == "agent-new" for g in all_grants_after)


def test_authorization_nonces(tmp_path: Path) -> None:
    """Test single-use authorization nonces."""
    db_path = tmp_path / "test_nonces.sqlite"
    storage = OnepasswordStorage(db_path=db_path)

    now = 1000.0
    nonce = storage.create_authorization_nonce(
        agent_id="agent-1",
        slug="secret-slug",
        ttl_seconds=600,
        now=now,
    )
    assert nonce.startswith("auth-")

    # First consumption: valid
    valid, err = storage.consume_authorization_nonce(
        nonce=nonce,
        agent_id="agent-1",
        slug="secret-slug",
        now=now + 50,
    )
    assert valid is True
    assert err is None

    # Second consumption: invalid (single use)
    valid2, err2 = storage.consume_authorization_nonce(
        nonce=nonce,
        agent_id="agent-1",
        slug="secret-slug",
        now=now + 60,
    )
    assert valid2 is False
    assert err2 == POLICY_NOT_EVALUATED


@pytest.mark.asyncio
async def test_policy_evaluator_auto_and_deny(tmp_path: Path) -> None:
    """Test policy evaluation for auto and deny tiers."""
    db_path = tmp_path / "test_policy.sqlite"
    storage = OnepasswordStorage(db_path=db_path)

    config = OnepasswordConfig(
        items={
            "auto-slug": OnepasswordItemConfig(item="Auto Item", policy="auto"),
            "deny-slug": OnepasswordItemConfig(item="Deny Item", policy="deny"),
        }
    )

    evaluator = PolicyEvaluator(config=config, storage=storage)

    # 1. Unknown slug
    nonce, err, msg = await evaluator.evaluate_access(slug="unknown", reason="test")
    assert nonce is None
    assert err == UNKNOWN_SLUG

    # 2. Deny tier
    nonce, err, msg = await evaluator.evaluate_access(slug="deny-slug", reason="test")
    assert nonce is None
    assert err == POLICY_NOT_EVALUATED

    # 3. Auto tier
    nonce, err, msg = await evaluator.evaluate_access(slug="auto-slug", reason="test")
    assert nonce is not None
    assert err is None

    # Verify nonce can be consumed
    valid, _ = storage.consume_authorization_nonce(nonce, "", "auto-slug")
    assert valid is True


@pytest.mark.asyncio
async def test_policy_evaluator_approve_tier(tmp_path: Path) -> None:
    """Test approve tier with standing grant and interactive callbacks."""
    db_path = tmp_path / "test_approve.sqlite"
    storage = OnepasswordStorage(db_path=db_path)

    config = OnepasswordConfig(
        items={
            "approve-slug": OnepasswordItemConfig(item="Approve Item", policy="approve"),
        }
    )

    # Case 1: No approval hook -> denied
    evaluator1 = PolicyEvaluator(config=config, storage=storage, approval_hook=None)
    nonce, err, msg = await evaluator1.evaluate_access(slug="approve-slug", reason="test")
    assert nonce is None
    assert err == POLICY_NOT_EVALUATED

    # Case 2: Interactive hook returns allow_once
    mock_hook = AsyncMock(return_value="allow_once")
    evaluator2 = PolicyEvaluator(config=config, storage=storage, approval_hook=mock_hook)
    nonce, err, msg = await evaluator2.evaluate_access(
        slug="approve-slug",
        reason="need token",
        agent_id="agent-A",
    )
    assert nonce is not None
    assert err is None
    mock_hook.assert_called_once_with("approve-slug", "need token", "agent-A")
    # Standing grant was not saved for allow_once
    assert storage.has_standing_grant("agent-A", "approve-slug") is False

    # Case 3: Interactive hook returns allow_always
    mock_hook_always = AsyncMock(return_value="allow_always")
    evaluator3 = PolicyEvaluator(config=config, storage=storage, approval_hook=mock_hook_always)
    nonce, err, msg = await evaluator3.evaluate_access(
        slug="approve-slug",
        reason="continuous access",
        agent_id="agent-A",
    )
    assert nonce is not None
    assert err is None
    # Standing grant was saved
    assert storage.has_standing_grant("agent-A", "approve-slug") is True

    # Case 4: Subsequent access uses standing grant without calling hook
    mock_hook_unused = AsyncMock()
    evaluator4 = PolicyEvaluator(config=config, storage=storage, approval_hook=mock_hook_unused)
    nonce, err, msg = await evaluator4.evaluate_access(
        slug="approve-slug",
        reason="subsequent call",
        agent_id="agent-A",
    )
    assert nonce is not None
    assert err is None
    mock_hook_unused.assert_not_called()


def test_bounded_in_memory_cache() -> None:
    """Test in-memory cache TTL and invalidation."""
    cache = BoundedInMemoryCache(ttl_seconds=10)
    now = 1000.0

    cache.set("key-1", "val-1", now=now)
    assert cache.get("key-1", now=now + 5) == "val-1"
    # Expired
    assert cache.get("key-1", now=now + 15) is None

    # Invalidate
    cache.set("key-2", "val-2", now=now)
    cache.invalidate("key-2")
    assert cache.get("key-2", now=now) is None
