"""Unit tests for the `onepassword` agent tool and transcript redaction."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from extensions.onepassword.src.config import OnepasswordConfig, OnepasswordItemConfig
from extensions.onepassword.src.op_cli import OpCliRunner
from extensions.onepassword.src.policy import PolicyEvaluator
from extensions.onepassword.src.storage import OnepasswordStorage
from extensions.onepassword.src.tool import (
    OnepasswordTool,
    redact_transcript_result,
)
from extensions.onepassword.src.types import (
    INVALID_ACTION,
    INVALID_REASON,
    INVALID_SLUG,
    UNKNOWN_SLUG,
    SecretItemResult,
)


@pytest.fixture
def test_setup(tmp_path: Path) -> tuple[OnepasswordTool, OnepasswordStorage, AsyncMock]:
    """Fixture to set up tool with mock OpCliRunner and SQLite storage."""
    db_path = tmp_path / "tool_test.sqlite"
    storage = OnepasswordStorage(db_path=db_path)

    config = OnepasswordConfig(
        vault="Automation",
        items={
            "repo-token": OnepasswordItemConfig(
                item="Repository automation token",
                field="credential",
                policy="auto",
                description="Token for repo tasks",
            ),
            "db-pass": OnepasswordItemConfig(
                item="Database Password",
                field="password",
                policy="deny",
            ),
        },
    )

    mock_op_runner = AsyncMock(spec=OpCliRunner)
    mock_op_runner.get_item_field.return_value = (
        SecretItemResult(
            slug="repo-token",
            item="Repository automation token",
            field="credential",
            value="ghp_super_secret_token_12345",
        ),
        None,
        None,
    )

    policy_eval = PolicyEvaluator(config=config, storage=storage)
    tool = OnepasswordTool(
        config=config,
        storage=storage,
        op_runner=mock_op_runner,
        policy_evaluator=policy_eval,
    )

    return tool, storage, mock_op_runner


@pytest.mark.asyncio
async def test_tool_list_action(
    test_setup: tuple[OnepasswordTool, OnepasswordStorage, AsyncMock],
) -> None:
    """Test `list` action never calls op or leaks secrets."""
    tool, storage, mock_op = test_setup

    res = await tool.execute({"action": "list"}, agent_id="agent-1")
    assert "items" in res
    items = res["items"]
    assert len(items) == 2

    repo_item = next(i for i in items if i["slug"] == "repo-token")
    assert repo_item["description"] == "Token for repo tasks"
    assert repo_item["policy"] == "auto"
    assert repo_item["hasStandingGrant"] is False
    assert "value" not in repo_item

    mock_op.get_item_field.assert_not_called()


@pytest.mark.asyncio
async def test_tool_get_validations(
    test_setup: tuple[OnepasswordTool, OnepasswordStorage, AsyncMock],
) -> None:
    """Test input validations for action `get`."""
    tool, storage, mock_op = test_setup

    # Invalid action
    res = await tool.execute({"action": "invalid"})
    assert res.get("errorCode") == INVALID_ACTION

    # Missing slug
    res = await tool.execute({"action": "get", "reason": "test"})
    assert res.get("errorCode") == INVALID_SLUG

    # Invalid slug regex
    res = await tool.execute({"action": "get", "slug": "Invalid_Slug!", "reason": "test"})
    assert res.get("errorCode") == INVALID_SLUG

    # Missing reason
    res = await tool.execute({"action": "get", "slug": "repo-token", "reason": ""})
    assert res.get("errorCode") == INVALID_REASON

    # Reason > 300 chars
    long_reason = "r" * 301
    res = await tool.execute({"action": "get", "slug": "repo-token", "reason": long_reason})
    assert res.get("errorCode") == INVALID_REASON

    # Unknown slug
    res = await tool.execute({"action": "get", "slug": "unknown-slug", "reason": "test"})
    assert res.get("errorCode") == UNKNOWN_SLUG


@pytest.mark.asyncio
async def test_tool_get_success_and_cache(
    test_setup: tuple[OnepasswordTool, OnepasswordStorage, AsyncMock],
) -> None:
    """Test successful `get` and subsequent cache hit."""
    tool, storage, mock_op = test_setup

    # First fetch (cache miss)
    res = await tool.execute(
        {
            "action": "get",
            "slug": "repo-token",
            "reason": "Clone private repository",
        },
        agent_id="agent-main",
    )

    assert res.get("value") == "ghp_super_secret_token_12345"
    assert res.get("slug") == "repo-token"
    assert res.get("field") == "credential"
    assert mock_op.get_item_field.call_count == 1

    # Audit log check
    logs = storage.get_audit_log(limit=5)
    assert len(logs) == 1
    assert logs[0].outcome == "allowed"
    assert logs[0].cached is False
    assert logs[0].reason == "Clone private repository"

    # Second fetch (cache hit)
    res2 = await tool.execute(
        {
            "action": "get",
            "slug": "repo-token",
            "reason": "Push commits",
        },
        agent_id="agent-main",
    )
    assert res2.get("value") == "ghp_super_secret_token_12345"
    assert mock_op.get_item_field.call_count == 1  # Not called again

    logs2 = storage.get_audit_log(limit=5)
    assert len(logs2) == 2
    assert logs2[0].cached is True
    assert logs2[0].reason == "Push commits"


def test_transcript_redaction() -> None:
    """Test redaction of secret value before transcript persistence."""
    raw_result = {
        "slug": "repo-token",
        "item": "Repository automation token",
        "field": "credential",
        "value": "super-secret-password",
    }

    redacted = redact_transcript_result(raw_result)
    assert redacted["value"] == "[REDACTED: 1Password secret for slug 'repo-token']"
    assert redacted["_redacted"] is True
    assert redacted["slug"] == "repo-token"
    # Original dict unchanged
    assert raw_result["value"] == "super-secret-password"
