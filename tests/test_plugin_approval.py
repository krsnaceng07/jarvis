"""Tests for packages/plugin_sdk/src/jarvis_sdk/plugin_approval.py.

Mirrors tests of docs/plugins/plugin-permission-requests.md and src/infra/approval-errors.ts in OpenClaw.
"""

from __future__ import annotations


from jarvis_sdk.plugin_approval import (
    APPROVAL_NOT_FOUND,
    PluginApprovalError,
    create_plugin_approval_request,
)


def test_create_plugin_approval_request_defaults():
    req = create_plugin_approval_request(
        title="Deploy service",
        description="Deploy service to staging environment.",
    )
    assert req.title == "Deploy service"
    assert req.severity == "warning"
    assert req.allowedDecisions == ["allow-once", "allow-always", "deny"]
    assert req.timeoutMs == 120000


def test_plugin_approval_request_caps():
    long_title = "A" * 100
    long_desc = "B" * 600

    req = create_plugin_approval_request(
        title=long_title,
        description=long_desc,
        timeout_ms=1000000,
    )

    assert len(req.title) == 80
    assert len(req.description) == 512
    assert req.timeoutMs == 600000  # Capped at 10 minutes


def test_plugin_approval_error():
    err = PluginApprovalError("Unknown or expired approval id", code=APPROVAL_NOT_FOUND)
    assert err.code == APPROVAL_NOT_FOUND
    assert "Unknown or expired" in str(err)
