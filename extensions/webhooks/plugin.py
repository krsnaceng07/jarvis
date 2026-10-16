"""Webhooks infra plugin definition and route registration.

OpenClaw parity: mirrors @openclaw/webhooks infra plugin:
- Registers authenticated inbound routes on Gateway HTTP router
- Binds routes to TaskFlow sessions
- Doctor diagnostics
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin

from .src.config import resolve_webhooks_plugin_config
from .src.doctor import run_webhooks_doctor_checks
from .src.http import TaskFlowWebhookHandler
from .src.types import ConfiguredWebhookRoute, TaskFlowWebhookTarget


@dataclass(frozen=True, slots=True)
class WebhooksPlugin(Plugin):
    """Webhooks infra plugin descriptor."""

    id: str = "webhooks"
    name: str = "Webhooks"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = (
        "Authenticated inbound webhooks that bind external automation to OpenClaw TaskFlows."
    )
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any = None) -> None:
        """Initialize plugin runtime, resolve routes, and register HTTP handlers."""
        raw_config = getattr(ctx, "config", {}) if ctx else {}
        if isinstance(raw_config, dict) and "plugins" in raw_config:
            raw_config = (
                raw_config.get("plugins", {})
                .get("entries", {})
                .get("webhooks", {})
                .get("config", {})
            )
        elif isinstance(raw_config, dict) and "webhooks" in raw_config:
            raw_config = raw_config["webhooks"]

        routes: list[ConfiguredWebhookRoute] = resolve_webhooks_plugin_config(raw_config)
        targets_by_path: dict[str, list[TaskFlowWebhookTarget]] = {}

        tasks_runtime = getattr(getattr(ctx, "runtime", None), "tasks", None)
        managed_flows = getattr(tasks_runtime, "managed_flows", None) or getattr(
            tasks_runtime, "managedFlows", None
        )

        for route in routes:
            task_flow = None
            if managed_flows and hasattr(managed_flows, "bind_session"):
                task_flow = managed_flows.bind_session(session_key=route.session_key)
            elif managed_flows and hasattr(managed_flows, "bindSession"):
                task_flow = managed_flows.bindSession(session_key=route.session_key)

            target = TaskFlowWebhookTarget(
                route_id=route.route_id,
                path=route.path,
                secret_input=route.secret,
                default_controller_id=route.controller_id,
                task_flow=task_flow,
            )
            targets_by_path.setdefault(target.path, []).append(target)

        handler = TaskFlowWebhookHandler(targets_by_path=targets_by_path)

        self.metadata["routes"] = routes
        self.metadata["targets_by_path"] = targets_by_path
        self.metadata["handler"] = handler

        # Register HTTP routes on Gateway router
        if hasattr(ctx, "register_http_route"):
            for path in targets_by_path:
                ctx.register_http_route(
                    path=path,
                    auth="plugin",
                    match="exact",
                    replace_existing=True,
                    handler=handler.handle_request,
                )

        # Register doctor contract
        if hasattr(ctx, "register_doctor_contract"):
            ctx.register_doctor_contract(
                "webhooks",
                lambda raw_cfg, fix=False: run_webhooks_doctor_checks(
                    raw_config=raw_cfg,
                ),
            )

    def get_handler(self) -> TaskFlowWebhookHandler:
        """Get the instantiated webhook HTTP request handler."""
        return self.metadata.get("handler") or TaskFlowWebhookHandler(targets_by_path={})


webhooks_plugin = WebhooksPlugin()
entry = webhooks_plugin
