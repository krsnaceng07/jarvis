from __future__ import annotations

import asyncio

from extensions.codex.src.plugin_inventory import read_codex_plugin_app_inventory
from extensions.codex.src.plugin_policy import (
    build_codex_plugin_apps_config,
    resolve_codex_plugins_policy,
)


def test_plugin_policy_normalizes_qualified_identity_and_overrides():
    policy = resolve_codex_plugins_policy(
        {
            "codexPlugins": {
                "enabled": True,
                "allow_destructive_actions": "ask",
                "plugins": {
                    "security-review@company-tools": {"enabled": True},
                    "calendar": {
                        "pluginName": "google-calendar",
                        "marketplaceName": "openai-curated",
                        "allow_destructive_actions": False,
                    },
                },
            }
        }
    )
    assert policy.enabled is True
    assert policy.plugins[0].plugin_name == "security-review"
    assert policy.plugins[0].marketplace_name == "company-tools"
    assert policy.plugins[1].allow_destructive_actions is False


def test_plugin_apps_are_denied_without_verified_inventory():
    policy = resolve_codex_plugins_policy(
        {"codexPlugins": {"enabled": True, "plugins": {"review@official": {}}}}
    )
    assert build_codex_plugin_apps_config(policy) == {
        "apps": {"_default": {"enabled": False, "open_world_enabled": False}}
    }


def test_plugin_apps_require_owned_inventory_and_apply_destructive_policy():
    policy = resolve_codex_plugins_policy(
        {
            "codexPlugins": {
                "enabled": True,
                "plugins": {"review@official": {"allow_destructive_actions": "ask"}},
            }
        }
    )
    config = build_codex_plugin_apps_config(
        policy,
        inventory=[
            {"appId": "review-app", "configKey": "review@official", "owned": True},
            {"appId": "unverified", "configKey": "review@official", "owned": False},
        ],
    )
    assert config["apps"]["review-app"]["destructive_enabled"] is True
    assert "unverified" not in config["apps"]


def test_inventory_preflight_requires_installed_plugin_and_app():
    policy = resolve_codex_plugins_policy(
        {"codexPlugins": {"enabled": True, "plugins": {"review@official": {}}}}
    )
    calls: list[str] = []

    def request(method, _params):
        calls.append(method)
        return {
            "plugin/installed": {"plugins": [{"name": "review", "marketplaceName": "official"}]},
            "app/installed": {"apps": [{"id": "review-app"}]},
            "plugin/read": {"plugin": {"apps": [{"id": "review-app"}]}},
        }.get(method, {})

    inventory = asyncio.run(read_codex_plugin_app_inventory(request, policy))
    assert inventory == [{"appId": "review-app", "configKey": "review@official", "owned": True}]
    assert calls == ["plugin/installed", "app/installed", "plugin/read"]


def test_allow_all_admits_only_accessible_enabled_callable_account_apps():
    policy = resolve_codex_plugins_policy(
        {"codexPlugins": {"enabled": True, "allow_all_plugins": True}}
    )

    def request(method, _params):
        return {
            "plugin/installed": {"plugins": []},
            "app/installed": {
                "apps": [
                    {"id": "ready", "accessible": True, "enabled": True, "callable": True},
                    {"id": "needs-auth", "accessible": False, "enabled": True, "callable": True},
                    {"id": "disabled", "accessible": True, "enabled": False, "callable": True},
                    {"id": "not-callable", "accessible": True, "enabled": True, "callable": False},
                ]
            },
        }.get(method, {})

    inventory = asyncio.run(read_codex_plugin_app_inventory(request, policy))
    assert inventory == [{"appId": "ready", "configKey": None, "owned": True}]
