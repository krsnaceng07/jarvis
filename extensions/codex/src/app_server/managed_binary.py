"""Managed Codex app-server binary resolution and desktop bundle inspection.

OpenClaw parity: ``extensions/codex/src/app-server/managed-binary.ts`` and
``extensions/codex/src/app-server/desktop-app-paths.ts``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Literal

_REGISTERED_PLUGIN_ROOT: str | None = None
NATIVE_CODEX_COMMAND_NAMES: frozenset[str] = frozenset({"codex", "codex.exe", "codex.cmd"})


def set_managed_codex_plugin_root(plugin_root: str | None) -> None:
    """Record the process-stable plugin root prepared by JARVIS's plugin loader."""
    global _REGISTERED_PLUGIN_ROOT
    _REGISTERED_PLUGIN_ROOT = plugin_root


def get_managed_codex_plugin_root() -> str | None:
    """Retrieve the process-stable plugin root."""
    return _REGISTERED_PLUGIN_ROOT


def resolve_desktop_codex_command_candidates(
    platform: str | None = None,
) -> list[str]:
    """Return standard desktop app executable candidates by platform preference order."""
    plat = platform or sys.platform

    if plat == "darwin":
        return [
            "/Applications/ChatGPT.app/Contents/Resources/codex",
            "/Applications/Codex.app/Contents/Resources/codex",
        ]
    elif plat == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA", r"C:\Users\Public")
        return [
            os.path.join(local_app_data, "Programs", "ChatGPT", "resources", "codex.exe"),
            os.path.join(local_app_data, "Programs", "Codex", "resources", "codex.exe"),
        ]
    else:  # linux or other posix
        return [
            "/usr/local/bin/codex",
            "/usr/bin/codex",
        ]


def is_managed_codex_desktop_command(command: str, platform: str | None = None) -> bool:
    """Return whether a command is one of the standard desktop app executables."""
    candidates = resolve_desktop_codex_command_candidates(platform)
    normalized = str(Path(command).resolve()) if Path(command).exists() else command
    for candidate in candidates:
        if candidate == command or candidate == normalized:
            return True
    return False


def attest_codex_launcher(
    command: str,
    *,
    plugin_root: str | None = None,
    platform: str | None = None,
) -> dict[str, Any]:
    """Verify that a launcher is native Codex or the official npm package.

    Wrapper scripts are rejected because their native target cannot be proven
    before launch. PATH-native ``codex`` names remain valid for operator-managed
    installations; concrete paths must resolve to a desktop binary or the
    official ``@openai/codex`` package tree.
    """
    import shutil

    raw = str(command).strip()
    if not raw:
        return {"ok": False, "reason": "launcher path is empty"}
    name = Path(raw).name.lower()
    if not Path(raw).is_absolute() and name in NATIVE_CODEX_COMMAND_NAMES:
        return {"ok": True, "kind": "path-native"}
    resolved_text = shutil.which(raw) if not Path(raw).exists() else raw
    if not resolved_text:
        return {"ok": False, "reason": "launcher does not exist"}
    resolved = Path(resolved_text).resolve()
    if is_managed_codex_desktop_command(str(resolved), platform):
        return {"ok": True, "kind": "desktop"}
    root = Path(plugin_root or get_managed_codex_plugin_root() or os.getcwd()).resolve()
    managed_roots = [
        root / "node_modules" / "@openai" / "codex",
        root / "vendor",
        root / "bin",
    ]
    is_in_managed_root = any(
        _is_relative_to(resolved, managed_root) for managed_root in managed_roots
    )
    if not is_in_managed_root:
        return {
            "ok": False,
            "reason": "launcher is outside the official @openai/codex package or managed vendor/bin tree",
        }
    if resolved.name.lower() not in {"codex", "codex.exe", "codex.cmd", "codex.js"}:
        return {"ok": False, "reason": "launcher is not an official Codex entrypoint"}
    if _looks_like_text_wrapper(resolved):
        return {
            "ok": False,
            "reason": "launcher is a text wrapper, not an official Codex binary entrypoint",
        }
    return {"ok": True, "kind": "official-npm"}


def _looks_like_text_wrapper(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            prefix = handle.read(128)
    except OSError:
        return False
    if not prefix:
        return False
    text = prefix.decode("utf-8", errors="ignore")
    return (
        text.startswith("#!")
        or text.lstrip().startswith("#!/")
        or text.lstrip().lower().startswith("echo ")
    )


def _is_relative_to(path: Path, other: Path) -> bool:
    try:
        path.relative_to(other)
        return True
    except ValueError:
        return False


def resolve_managed_codex_command_candidates(
    plugin_root: str | None = None,
    platform: str | None = None,
    order: Literal["package-first", "desktop-first"] = "package-first",
) -> list[str]:
    """Resolve ordered candidate executable paths for stdio managed startup."""
    plat = platform or sys.platform
    root = plugin_root or get_managed_codex_plugin_root() or os.getcwd()

    binary_name = "codex.exe" if plat == "win32" else "codex"

    # Package-pinned node_modules / vendor path candidates
    package_candidates = [
        os.path.join(root, "node_modules", "@openai", "codex", "bin", "codex.js"),
        os.path.join(root, "vendor", binary_name),
        os.path.join(root, "bin", binary_name),
    ]

    desktop_candidates = resolve_desktop_codex_command_candidates(plat)

    if order == "desktop-first":
        return desktop_candidates + package_candidates
    return package_candidates + desktop_candidates


def find_managed_codex_app_server_command_path(
    plugin_root: str | None = None,
    platform: str | None = None,
    order: Literal["package-first", "desktop-first"] = "package-first",
) -> str | None:
    """Return the first existing executable command path among managed candidates."""
    candidates = resolve_managed_codex_command_candidates(plugin_root, platform, order)
    for path_str in candidates:
        if os.path.exists(path_str):
            return path_str
    # Fallback to system 'codex' executable if present on PATH
    from shutil import which

    system_codex = which("codex.exe" if (platform or sys.platform) == "win32" else "codex")
    if system_codex:
        return system_codex

    return candidates[0] if candidates else None


__all__ = [
    "attest_codex_launcher",
    "find_managed_codex_app_server_command_path",
    "get_managed_codex_plugin_root",
    "is_managed_codex_desktop_command",
    "resolve_desktop_codex_command_candidates",
    "resolve_managed_codex_command_candidates",
    "set_managed_codex_plugin_root",
]
