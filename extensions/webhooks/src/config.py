"""Configuration resolution and path normalization for Webhooks plugin.

OpenClaw parity: mirrors @openclaw/webhooks config parsing, route resolution,
path normalization, and conflict detection.
"""

from __future__ import annotations

import re
from typing import Any

from .types import ConfiguredWebhookRoute, WebhookSecretInput


def normalize_webhook_path(path: str) -> str:
    """Normalize route path: ensure leading slash, no trailing slash, collapse duplicate slashes."""
    trimmed = path.strip()
    if not trimmed:
        return "/plugins/webhooks"
    if not trimmed.startswith("/"):
        trimmed = "/" + trimmed
    # Collapse multiple slashes
    collapsed = re.sub(r"/+", "/", trimmed)
    if len(collapsed) > 1 and collapsed.endswith("/"):
        collapsed = collapsed[:-1]
    return collapsed


def resolve_webhooks_plugin_config(
    plugin_config: dict[str, Any] | None = None,
) -> list[ConfiguredWebhookRoute]:
    """Resolve and validate webhook routes from raw plugin configuration."""
    if not plugin_config or not isinstance(plugin_config, dict):
        return []

    routes_raw = plugin_config.get("routes") or {}
    if not isinstance(routes_raw, dict):
        return []

    configured_routes: list[ConfiguredWebhookRoute] = []
    seen_paths: dict[str, str] = {}

    for route_id, route_dict in routes_raw.items():
        if not isinstance(route_dict, dict):
            continue

        enabled = route_dict.get("enabled", True)
        if not enabled:
            continue

        session_key = str(
            route_dict.get("sessionKey") or route_dict.get("session_key") or ""
        ).strip()
        if not session_key:
            raise ValueError(
                f"webhooks.routes.{route_id}.sessionKey is required and cannot be empty"
            )

        secret_raw = route_dict.get("secret")
        if not secret_raw:
            raise ValueError(f"webhooks.routes.{route_id}.secret is required and cannot be empty")

        secret: WebhookSecretInput
        if isinstance(secret_raw, str):
            secret_str = secret_raw.strip()
            if not secret_str:
                raise ValueError(f"webhooks.routes.{route_id}.secret cannot be empty string")
            secret = secret_str
        elif isinstance(secret_raw, dict):
            secret = secret_raw
        else:
            raise ValueError(
                f"webhooks.routes.{route_id}.secret must be a string or SecretRef object"
            )

        raw_path = route_dict.get("path")
        path_to_norm = str(raw_path) if raw_path else f"/plugins/webhooks/{route_id}"
        normalized_path = normalize_webhook_path(path_to_norm)

        existing_route_id = seen_paths.get(normalized_path)
        if existing_route_id:
            raise ValueError(
                f"webhooks.routes.{route_id}.path conflicts with routes.{existing_route_id}.path ({normalized_path})."
            )

        seen_paths[normalized_path] = route_id

        raw_controller_id = route_dict.get("controllerId") or route_dict.get("controller_id")
        controller_id = (
            str(raw_controller_id).strip() if raw_controller_id else f"webhooks/{route_id}"
        )

        description = (
            str(route_dict.get("description")).strip() if route_dict.get("description") else None
        )

        configured_routes.append(
            ConfiguredWebhookRoute(
                route_id=route_id,
                path=normalized_path,
                session_key=session_key,
                secret=secret,
                controller_id=controller_id,
                description=description,
            )
        )

    return configured_routes
