"""Gateway RPC handlers for config operations — mirrors OpenClaw server-methods/config.ts."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from jarvis_config_core import (
    _parse,
    load_config,
    patch_config,
    save_config,
)

_log = logging.getLogger("jarvis.gateway.config_handlers")


def _compute_hash(data: dict[str, Any]) -> str:
    serialized = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


def config_get_handler(params: dict[str, Any]) -> dict[str, Any]:
    """Handle config.get RPC request."""
    cfg = load_config()
    cfg_dict = cfg.to_dict()
    h = _compute_hash(cfg_dict)
    issues = cfg.validate()
    return {
        "ok": True,
        "config": cfg_dict,
        "hash": h,
        "issues": issues,
    }


def config_set_handler(params: dict[str, Any]) -> dict[str, Any]:
    """Handle config.set RPC request."""
    raw = params.get("config")
    if not isinstance(raw, dict):
        return {"ok": False, "error": "Missing or invalid 'config' object parameter"}

    try:
        cfg = _parse(raw)
        issues = cfg.validate()
        save_config(cfg)
        cfg_dict = cfg.to_dict()
        return {
            "ok": True,
            "config": cfg_dict,
            "hash": _compute_hash(cfg_dict),
            "issues": issues,
        }
    except Exception as e:
        _log.exception("config.set failed")
        return {"ok": False, "error": str(e)}


def config_patch_handler(params: dict[str, Any]) -> dict[str, Any]:
    """Handle config.patch RPC request."""
    patch = params.get("patch")
    if not isinstance(patch, dict):
        return {"ok": False, "error": "Missing or invalid 'patch' object parameter"}

    try:
        cfg = patch_config(patch)
        issues = cfg.validate()
        cfg_dict = cfg.to_dict()
        return {
            "ok": True,
            "config": cfg_dict,
            "hash": _compute_hash(cfg_dict),
            "issues": issues,
        }
    except Exception as e:
        _log.exception("config.patch failed")
        return {"ok": False, "error": str(e)}


def config_schema_handler(params: dict[str, Any]) -> dict[str, Any]:
    """Handle config.schema RPC request."""
    return {
        "ok": True,
        "schema": {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "gemini_api_key": {"type": "string", "description": "Google Gemini API key"},
                "model": {"type": "string", "description": "Default LLM model identifier"},
                "gateway_port": {"type": "integer", "description": "Gateway port"},
                "log_level": {"type": "string", "description": "Logging level"},
                "extensions_dir": {"type": ["string", "null"], "description": "Extensions directory path"},
                "state_dir": {"type": ["string", "null"], "description": "State directory path"},
                "agent": {"type": "object", "description": "Agent configuration"},
                "tools": {"type": "object", "description": "Tools settings"},
            },
        },
    }


def make_config_handlers() -> dict[str, Any]:
    """Return all config-related gateway RPC handlers."""
    return {
        "config.get": config_get_handler,
        "config.set": config_set_handler,
        "config.patch": config_patch_handler,
        "config.schema": config_schema_handler,
    }


__all__ = ["make_config_handlers"]
