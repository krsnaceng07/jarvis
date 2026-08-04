"""jarvis.config.io_warnings — config-IO warning emitters.

OpenClaw parity: mirrors ``openclaw-main/src/config/io.warnings.ts``.

Focused minimal port: thin facade that delegates terminal-text
sanitization, version comparison, raw hashing, and bounded state
mutation to caller-provided callables.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from src.config.io_state import (
    logged_config_warning_fingerprints,
    set_bounded_config_io_warning_entry,
    warned_future_touched_versions,
)


def warn_on_config_miskeys(raw: Any, logger) -> None:
    """Warn when the deprecated ``gateway.token`` key is used.

    Mirrors :func:`warnOnConfigMiskeys`
    (``shared/config/io.warnings.ts`).
    """
    if not raw or not isinstance(raw, dict):
        return
    gateway = raw.get("gateway")
    if not gateway or not isinstance(gateway, dict):
        return
    if "token" in gateway:
        logger.warn(
            'Config uses "gateway.token". This key is ignored; use "gateway.auth.token" instead.',
        )


def log_config_warnings_once(params: dict) -> None:
    """Log a list of config warnings once per fingerprint.

    Mirrors :func:`logConfigWarningsOnce`
    (``shared/config/io.warnings.ts`).
    """
    config_path = params.get("configPath") or ""
    warnings = params.get("warnings") or []
    logger = params.get("logger")
    sanitize: Optional[Callable[[str], str]] = params.get("sanitize_terminal_text_fn")
    hash_raw: Optional[Callable[[str], str]] = params.get("hash_config_raw_fn")
    if not warnings:
        logged_config_warning_fingerprints.pop(config_path, None)
        return
    sanitize_fn = sanitize or (lambda s: s)
    details = "\n".join(
        f"- {sanitize_fn(w.get('path') or '<root>')}: {sanitize_fn(w.get('message') or '')}"
        for w in warnings
    )
    fingerprint = hash_raw(details) if callable(hash_raw) else details
    if logged_config_warning_fingerprints.get(config_path) == fingerprint:
        set_bounded_config_io_warning_entry(
            logged_config_warning_fingerprints, config_path, fingerprint,
        )
        return
    set_bounded_config_io_warning_entry(
        logged_config_warning_fingerprints, config_path, fingerprint,
    )
    if logger is not None:
        logger.warn(f"Config warnings:\n{details}")


def warn_if_config_from_future(
    cfg: Any,
    logger,
    *,
    version: Optional[str] = None,
    should_warn_on_touched_version_fn: Optional[Callable] = None,
) -> None:
    """Warn when the config was last touched by a future binary version.

    Mirrors :func:`warnIfConfigFromFuture`
    (``shared/config/io.warnings.ts`).
    """
    touched = (((cfg or {}).get("meta") or {}).get("lastTouchedVersion")) if isinstance(cfg, dict) else None
    if not touched:
        return
    if not callable(should_warn_on_touched_version_fn):
        return
    if not should_warn_on_touched_version_fn(version, touched):
        return
    warned = warned_future_touched_versions
    if hasattr(warned, "check") and warned.check(touched):
        return
    if logger is not None:
        logger.warn(
            "\n".join([
                f"Your OpenClaw config was written by version {touched}, but this command is running {version}.",
                "Check: `openclaw --version`, `which openclaw`, and `openclaw gateway status --deep`.",
                "If unexpected, update PATH so `openclaw` points to the version you want, or reinstall the Gateway service from that same OpenClaw install.",
            ])
        )


__all__ = [
    "warn_on_config_miskeys",
    "log_config_warnings_once",
    "warn_if_config_from_future",
]
