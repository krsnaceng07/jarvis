"""jarvis.plugins.webhooks — Webhooks plugin & TaskFlow HTTP bridge configuration.

OpenClaw parity: mirrors
``openclaw-main/extensions/webhooks/src/config.ts`` and
``openclaw-main/extensions/webhooks/src/http.ts``.

Features:
- `WEBHOOK_ACTIONS`: List of 13 supported Webhook HTTP actions.
- `WebhookRouteConfig`: Resolved route dataclass (`route_id`, `path`, `session_key`, `secret`, `controller_id`, `description`).
- `normalize_webhook_path()`: Ensures path starts with `/` and strips trailing `/`.
- `resolve_webhooks_plugin_config()`: Parses `webhooks.routes` dictionary and enforces unique path constraint.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

WEBHOOK_ACTIONS: list[str] = [
    "create_flow",
    "get_flow",
    "list_flows",
    "find_latest_flow",
    "resolve_flow",
    "get_task_summary",
    "set_waiting",
    "resume_flow",
    "finish_flow",
    "fail_flow",
    "request_cancel",
    "cancel_flow",
    "run_task",
]


@dataclass
class WebhookRouteConfig:
    route_id: str
    path: str
    session_key: str
    secret: Any
    controller_id: str
    description: str | None = None


def normalize_webhook_path(path: str) -> str:
    """Normalize a webhook route path string."""
    p = path.strip()
    if not p.startswith("/"):
        p = "/" + p
    if len(p) > 1 and p.endswith("/"):
        p = p[:-1]
    return p


def resolve_webhooks_plugin_config(plugin_cfg: dict[str, Any] | None) -> list[WebhookRouteConfig]:
    """Resolve and validate Webhook plugin route configurations."""
    val = plugin_cfg if isinstance(plugin_cfg, dict) else {}
    routes_map = val.get("routes")
    if not isinstance(routes_map, dict):
        return []

    configured: list[WebhookRouteConfig] = []
    seen_paths: dict[str, str] = {}

    for route_id, raw_route in routes_map.items():
        if not isinstance(raw_route, dict):
            continue
        if raw_route.get("enabled") is False:
            continue

        session_key = str(raw_route.get("sessionKey") or "").strip()
        secret = raw_route.get("secret")
        if not session_key or secret is None:
            continue

        raw_path = str(raw_route.get("path") or f"/plugins/webhooks/{route_id}")
        norm_path = normalize_webhook_path(raw_path)

        if norm_path in seen_paths:
            existing = seen_paths[norm_path]
            raise ValueError(
                f"webhooks.routes.{route_id}.path conflicts with routes.{existing}.path ({norm_path})."
            )

        seen_paths[norm_path] = route_id

        ctrl_id = str(raw_route.get("controllerId") or f"webhooks/{route_id}").strip()
        desc = str(raw_route.get("description")).strip() if raw_route.get("description") else None

        configured.append(
            WebhookRouteConfig(
                route_id=route_id,
                path=norm_path,
                session_key=session_key,
                secret=secret,
                controller_id=ctrl_id,
                description=desc,
            )
        )

    return configured


__all__ = [
    "WEBHOOK_ACTIONS",
    "WebhookRouteConfig",
    "normalize_webhook_path",
    "resolve_webhooks_plugin_config",
]
