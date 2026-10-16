"""Webhooks infra plugin for JARVIS / OpenClaw."""

from __future__ import annotations

from .plugin import WebhooksPlugin, entry, webhooks_plugin
from .src.config import normalize_webhook_path, resolve_webhooks_plugin_config
from .src.doctor import run_webhooks_doctor_checks
from .src.http import (
    TaskFlowWebhookHandler,
    WebhookRateLimiter,
    extract_request_secret,
    resolve_secret_value,
)
from .src.http_request_schema import validate_webhook_action
from .src.types import (
    ConfiguredWebhookRoute,
    FlowView,
    TaskFlowWebhookTarget,
    TaskView,
    WebhookRouteConfig,
    WebhookSecretInput,
)

__all__ = [
    "ConfiguredWebhookRoute",
    "FlowView",
    "TaskFlowWebhookHandler",
    "TaskFlowWebhookTarget",
    "TaskView",
    "WebhookRateLimiter",
    "WebhookRouteConfig",
    "WebhookSecretInput",
    "WebhooksPlugin",
    "entry",
    "extract_request_secret",
    "normalize_webhook_path",
    "resolve_secret_value",
    "resolve_webhooks_plugin_config",
    "run_webhooks_doctor_checks",
    "validate_webhook_action",
    "webhooks_plugin",
]
