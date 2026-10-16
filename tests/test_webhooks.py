"""Tests for src/plugins/webhooks.py.

Mirrors tests of extensions/webhooks/src/config.ts in OpenClaw.
"""

from __future__ import annotations

import pytest

from src.plugins.webhooks import (
    WEBHOOK_ACTIONS,
    normalize_webhook_path,
    resolve_webhooks_plugin_config,
)


def test_webhook_actions():
    assert "create_flow" in WEBHOOK_ACTIONS
    assert "run_task" in WEBHOOK_ACTIONS
    assert "cancel_flow" in WEBHOOK_ACTIONS
    assert len(WEBHOOK_ACTIONS) == 13


def test_normalize_webhook_path():
    assert normalize_webhook_path("plugins/webhooks/zapier") == "/plugins/webhooks/zapier"
    assert normalize_webhook_path("/plugins/webhooks/zapier/") == "/plugins/webhooks/zapier"
    assert normalize_webhook_path("/") == "/"


def test_resolve_webhooks_plugin_config():
    raw_cfg = {
        "routes": {
            "zapier": {
                "sessionKey": "agent:main:main",
                "secret": "my_secret_token",
                "description": "Zapier route",
            }
        }
    }
    routes = resolve_webhooks_plugin_config(raw_cfg)
    assert len(routes) == 1
    r = routes[0]
    assert r.route_id == "zapier"
    assert r.path == "/plugins/webhooks/zapier"
    assert r.session_key == "agent:main:main"
    assert r.secret == "my_secret_token"
    assert r.controller_id == "webhooks/zapier"
    assert r.description == "Zapier route"


def test_resolve_webhooks_plugin_config_conflict():
    raw_cfg = {
        "routes": {
            "routeA": {
                "path": "/plugins/webhooks/common",
                "sessionKey": "agent:main:main",
                "secret": "secA",
            },
            "routeB": {
                "path": "/plugins/webhooks/common/",
                "sessionKey": "agent:main:main",
                "secret": "secB",
            },
        }
    }
    with pytest.raises(ValueError, match="conflicts with"):
        resolve_webhooks_plugin_config(raw_cfg)
