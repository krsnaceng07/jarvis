"""Gateway RPC handlers for models operations — mirrors OpenClaw server-methods/models.ts."""

from __future__ import annotations

import logging
from typing import Any

from jarvis_config_core import load_config

_log = logging.getLogger("jarvis.gateway.models_handlers")

_DEFAULT_MODELS = [
    {
        "id": "gemini-2.0-flash",
        "name": "Gemini 2.0 Flash",
        "provider": "google",
        "contextWindow": 1048576,
        "maxOutputTokens": 8192,
        "reasoning": False,
    },
    {
        "id": "gemini-2.0-pro-exp-0205",
        "name": "Gemini 2.0 Pro Experimental",
        "provider": "google",
        "contextWindow": 2097152,
        "maxOutputTokens": 8192,
        "reasoning": True,
    },
    {
        "id": "gemini-1.5-pro",
        "name": "Gemini 1.5 Pro",
        "provider": "google",
        "contextWindow": 2097152,
        "maxOutputTokens": 8192,
        "reasoning": False,
    },
    {
        "id": "gemini-1.5-flash",
        "name": "Gemini 1.5 Flash",
        "provider": "google",
        "contextWindow": 1048576,
        "maxOutputTokens": 8192,
        "reasoning": False,
    },
]


def models_list_handler(params: dict[str, Any]) -> dict[str, Any]:
    """Handle models.list RPC request."""
    cfg = load_config()
    configured_model = getattr(cfg, "model", "gemini-2.0-flash")

    models = [dict(m) for m in _DEFAULT_MODELS]
    # Mark the configured default
    for m in models:
        m["isDefault"] = m["id"] == configured_model

    return {
        "ok": True,
        "defaultModel": configured_model,
        "models": models,
    }


def make_models_handlers() -> dict[str, Any]:
    """Return all models-related gateway RPC handlers."""
    return {
        "models.list": models_list_handler,
    }


__all__ = ["make_models_handlers"]
