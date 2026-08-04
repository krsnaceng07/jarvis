"""jarvis.config.zod_schema_hooks — hook-related Zod schema fragments.

OpenClaw parity: mirrors ``openclaw-main/src/config/zod-schema.hooks.ts``.
"""
from __future__ import annotations

import os
from typing import Any


def is_safe_relative_module_path(raw: str) -> bool:
    """Return whether ``raw`` is a safe relative module path (no traversal, no URL).

    Mirrors :func:`isSafeRelativeModulePath`
    (``shared/config/zod-schema.hooks.ts`).
    """
    if not isinstance(raw, str):
        return False
    value = raw.strip()
    if not value:
        return False
    if os.path.isabs(value):
        return False
    # Reject POSIX- and Windows-style rooted paths that ``os.path.isabs``
    # does not flag on the current platform (e.g. ``/etc/passwd`` on Windows).
    if value.startswith(("/", "\\")):
        return False
    if value.startswith("~"):
        return False
    # Disallow URL-ish and drive-relative forms.
    if ":" in value:
        return False
    # Reject any ".." path component.
    for part in value.replace("\\", "/").split("/"):
        if part == "..":
            return False
    return True


#: Safe relative module-path schema (zod facade).
SafeRelativeModulePathSchema: Any = None  # z.string().refine(isSafeRelativeModulePath, ...)


#: Hook mapping schema (zod facade).
HookMappingSchema: Any = None  # z.object({...}).strict().optional()

#: Internal hooks config schema.
InternalHooksSchema: Any = None  # z.object({...}).strict().optional()

#: Gmail hooks config schema.
HooksGmailSchema: Any = None  # z.object({...}).strict().optional()


def validate_hook_module_path(raw: str) -> bool:
    """Convenience wrapper for the :func:`is_safe_relative_module_path` helper."""
    return is_safe_relative_module_path(raw)


__all__ = [
    "is_safe_relative_module_path",
    "validate_hook_module_path",
    "SafeRelativeModulePathSchema",
    "HookMappingSchema",
    "InternalHooksSchema",
    "HooksGmailSchema",
]
