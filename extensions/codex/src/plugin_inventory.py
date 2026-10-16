"""Read-only Codex plugin and app inventory preflight."""

from __future__ import annotations

import inspect
from typing import Any, Callable

from extensions.codex.src.plugin_policy import CodexPluginsPolicy


async def read_codex_plugin_app_inventory(
    request: Callable[[str, dict[str, Any] | None], Any],
    policy: CodexPluginsPolicy,
) -> list[dict[str, Any]]:
    """Resolve configured plugin-owned apps against current Codex inventory."""
    if not policy.enabled:
        return []
    installed = await _call(request, "plugin/installed", {})
    installed_plugins = _records(installed, "plugins")
    app_snapshot = await _call(request, "app/installed", {})
    installed_apps = _records(app_snapshot, "apps")
    app_ids = {_string(record.get("id")) for record in installed_apps}
    app_ids.discard(None)
    result: list[dict[str, Any]] = []
    for entry in policy.plugins:
        if not entry.enabled:
            continue
        summary = _find_plugin(installed_plugins, entry.plugin_name, entry.marketplace_name)
        if summary is None:
            continue
        detail = await _call(
            request,
            "plugin/read",
            {
                "pluginName": entry.plugin_name,
                **(
                    {"remoteMarketplaceName": entry.marketplace_name}
                    if entry.marketplace_name
                    else {}
                ),
            },
        )
        plugin = detail.get("plugin") if isinstance(detail, dict) else detail
        apps = plugin.get("apps", []) if isinstance(plugin, dict) else []
        for app in apps if isinstance(apps, list) else []:
            if not isinstance(app, dict):
                continue
            app_id = _string(app.get("id"))
            if app_id and app_id in app_ids:
                result.append({"appId": app_id, "configKey": entry.config_key, "owned": True})
    if policy.allow_all_plugins:
        for app in installed_apps:
            app_id = _string(app.get("id"))
            if (
                app_id
                and app.get("accessible") is not False
                and app.get("enabled") is not False
                and app.get("callable") is not False
            ):
                result.append({"appId": app_id, "configKey": None, "owned": True})
    return result


async def _call(request: Callable[..., Any], method: str, params: dict[str, Any]) -> Any:
    response = request(method, params)
    return await response if inspect.isawaitable(response) else response


def _records(response: Any, key: str) -> list[dict[str, Any]]:
    if not isinstance(response, dict):
        return []
    records = response.get(key)
    return [item for item in records if isinstance(item, dict)] if isinstance(records, list) else []


def _find_plugin(
    records: list[dict[str, Any]], name: str, marketplace: str | None
) -> dict[str, Any] | None:
    for record in records:
        if record.get("name") != name and record.get("pluginName") != name:
            continue
        record_marketplace = record.get("marketplaceName") or record.get("marketplace")
        if marketplace is None or record_marketplace == marketplace:
            return record
    return None


def _string(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


__all__ = ["read_codex_plugin_app_inventory"]
