"""jarvis_i18n — mirrors OpenClaw ``src/i18n/``."""

from __future__ import annotations

import locale
import logging
from typing import Any

_log = logging.getLogger("jarvis.i18n")

_TRANSLATIONS: dict[str, dict[str, str]] = {
    "en-US": {
        "welcome": "Welcome to JARVIS",
        "agent.started": "Agent turn started",
        "agent.completed": "Agent turn completed",
        "error.generic": "An error occurred",
    },
    "np": {
        "welcome": "JARVIS मा स्वागत छ",
        "agent.started": "एजेन्टको काम सुरु भयो",
        "agent.completed": "एजेन्टको काम सम्पन्न भयो",
        "error.generic": "समस्या आयो",
    },
}


def resolve_locale(config: dict[str, Any] | None = None) -> str:
    """Resolve locale string from config or system default."""
    if config and isinstance(config, dict):
        cfg_loc = config.get("locale") or config.get("language")
        if cfg_loc and isinstance(cfg_loc, str):
            return cfg_loc.strip()

    try:
        sys_loc, _ = locale.getdefaultlocale()
        if sys_loc:
            return sys_loc.replace("_", "-")
    except Exception:
        pass

    return "en-US"


def t(key: str, loc: str | None = None, default: str | None = None) -> str:
    """Translate key for given locale."""
    active_loc = loc or "en-US"
    translations = _TRANSLATIONS.get(active_loc) or _TRANSLATIONS.get("en-US", {})
    return translations.get(key) or default or key


__all__ = ["resolve_locale", "t"]
