"""jarvis.config.io_invalid_config — invalid-config formatting + error helpers.

OpenClaw parity: mirrors
``openclaw-main/src/config/io.invalid-config.ts``.

Focused minimal port: the public surface accepts a ``DedupeCache``-like
object (anything exposing ``.check``/``.add``) for log dedup; terminal
sanitization is delegated to a caller-provided callable.
"""
from __future__ import annotations

from typing import Callable, List, Optional


def _sanitize(value: str) -> str:
    """Default sanitizer that strips control characters."""
    if not isinstance(value, str):
        return ""
    return "".join(ch for ch in value if ch == "\n" or ch == "\t" or ord(ch) >= 0x20)


def format_invalid_config_details(issues: List[dict], *, sanitize_fn: Optional[Callable] = None) -> str:
    """Format validation issues as terminal-safe bullet lines.

    Mirrors :func:`formatInvalidConfigDetails`
    (``shared/config/io.invalid-config.ts`).
    """
    sanitize = sanitize_fn or _sanitize
    if not issues:
        return ""
    lines = []
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        path = sanitize(issue.get("path") or "<root>")
        msg = sanitize(issue.get("message") or "")
        lines.append(f"- {path}: {msg}")
    return "\n".join(lines)


def _format_log_message(config_path: str, details: str) -> str:
    return f"Invalid config at {config_path}:\n{details}"


def log_invalid_config_once(params: dict) -> None:
    """Log an invalid config message once per path during a load sequence.

    Mirrors :func:`logInvalidConfigOnce`
    (``shared/config/io.invalid-config.ts`).
    """
    config_path = params.get("configPath") or ""
    details = params.get("details") or ""
    logger = params.get("logger")
    logged_paths = params.get("loggedConfigPaths")
    if logged_paths is not None and hasattr(logged_paths, "check"):
        try:
            if logged_paths.check(config_path):
                return
        except Exception:
            pass
    if logger is not None and hasattr(logger, "error"):
        logger.error(_format_log_message(config_path, details))


def create_invalid_config_error(
    config_path: str,
    details: str,
    options: Optional[dict] = None,
) -> Exception:
    """Create the tagged invalid-config error shape.

    Mirrors :func:`createInvalidConfigError`
    (``shared/config/io.invalid-config.ts`).
    """
    options = options or {}
    error = Exception(f"Invalid config at {config_path}:\n{details}")
    error.name = "InvalidConfigError"
    setattr(error, "code", "INVALID_CONFIG")
    setattr(error, "details", details)
    setattr(error, "recovery", options.get("recovery") or "doctor")
    return error


def is_invalid_config_error(err) -> bool:
    """Return whether ``err`` is a tagged invalid-config error."""
    return bool(err) and getattr(err, "code", None) == "INVALID_CONFIG"


def is_doctor_recoverable_invalid_config_error(err) -> bool:
    """Return whether the invalid-config error is doctor-recoverable."""
    return is_invalid_config_error(err) and getattr(err, "recovery", None) != "manual"


def throw_invalid_config(params: dict) -> None:
    """Log and throw the standard invalid-config error for a validation result.

    Mirrors :func:`throwInvalidConfig`
    (``shared/config/io.invalid-config.ts`).
    """
    config_path = params.get("configPath") or ""
    issues = params.get("issues") or []
    logger = params.get("logger")
    logged_paths = params.get("loggedConfigPaths")
    details = format_invalid_config_details(issues, sanitize_fn=params.get("sanitize_fn"))
    log_invalid_config_once({
        "configPath": config_path,
        "details": details,
        "logger": logger,
        "loggedConfigPaths": logged_paths,
    })
    raise create_invalid_config_error(config_path, details)


__all__ = [
    "format_invalid_config_details",
    "log_invalid_config_once",
    "create_invalid_config_error",
    "is_invalid_config_error",
    "is_doctor_recoverable_invalid_config_error",
    "throw_invalid_config",
]
