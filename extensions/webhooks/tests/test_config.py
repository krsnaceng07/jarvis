"""Unit tests for Webhooks configuration parsing and path normalization."""

import pytest
from extensions.webhooks.src.config import (
    normalize_webhook_path,
    resolve_webhooks_plugin_config,
)


def test_normalize_webhook_path() -> None:
    """Test path normalization rules."""
    assert normalize_webhook_path("api/webhook") == "/api/webhook"
    assert normalize_webhook_path("/api/webhook/") == "/api/webhook"
    assert normalize_webhook_path("//plugins///webhooks//route1/") == "/plugins/webhooks/route1"
    assert normalize_webhook_path("/") == "/"
    assert normalize_webhook_path("") == "/plugins/webhooks"


def test_resolve_routes_success() -> None:
    """Test parsing valid webhook routes."""
    raw = {
        "routes": {
            "github": {
                "sessionKey": "session-gh",
                "secret": "gh-webhook-secret-123",
                "description": "GitHub CI Webhook",
            },
            "jira": {
                "path": "/custom/jira/hook",
                "sessionKey": "session-jira",
                "secret": {"source": "env", "provider": "default", "id": "JIRA_SECRET"},
                "controllerId": "jira-controller",
            },
            "disabled-route": {
                "enabled": False,
                "sessionKey": "session-disabled",
                "secret": "dummy",
            },
        }
    }

    routes = resolve_webhooks_plugin_config(raw)
    assert len(routes) == 2

    r1 = next(r for r in routes if r.route_id == "github")
    assert r1.path == "/plugins/webhooks/github"
    assert r1.session_key == "session-gh"
    assert r1.secret == "gh-webhook-secret-123"
    assert r1.controller_id == "webhooks/github"
    assert r1.description == "GitHub CI Webhook"

    r2 = next(r for r in routes if r.route_id == "jira")
    assert r2.path == "/custom/jira/hook"
    assert r2.session_key == "session-jira"
    assert isinstance(r2.secret, dict)
    assert r2.controller_id == "jira-controller"


def test_resolve_routes_validation_errors() -> None:
    """Test validation errors for missing sessionKey, secret, or path conflicts."""
    # 1. Missing sessionKey
    with pytest.raises(ValueError, match="sessionKey is required"):
        resolve_webhooks_plugin_config({"routes": {"r1": {"secret": "secret"}}})

    # 2. Missing secret
    with pytest.raises(ValueError, match="secret is required"):
        resolve_webhooks_plugin_config({"routes": {"r1": {"sessionKey": "session-1"}}})

    # 3. Path collision
    with pytest.raises(ValueError, match="conflicts with"):
        resolve_webhooks_plugin_config(
            {
                "routes": {
                    "route1": {
                        "path": "/shared/hook",
                        "sessionKey": "session-1",
                        "secret": "s1",
                    },
                    "route2": {
                        "path": "/shared/hook/",
                        "sessionKey": "session-2",
                        "secret": "s2",
                    },
                }
            }
        )
