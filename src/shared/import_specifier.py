"""jarvis.shared.import_specifier — safe ESM import specifier conversion.

OpenClaw parity: mirrors ``openclaw-main/src/shared/import-specifier.ts``.
"""
from __future__ import annotations

import pathlib
import sys


def to_safe_import_path(specifier: str) -> str:
    """Convert an absolute path to a file:// URL on Windows for ESM loaders.

    On Windows, Node's ESM loader requires absolute paths to be expressed as
    file:// URLs. Raw drive-letter paths like C:\\... are parsed as URL schemes.

    Mirrors :func:`toSafeImportPath` (``shared/import-specifier.ts``).
    """
    if sys.platform != "win32":
        return specifier
    if specifier.startswith("file://"):
        return specifier
    # pathlib.PureWindowsPath.isAbsolute is the cross-platform check.
    if pathlib.PureWindowsPath(specifier).is_absolute():
        return pathlib.Path(specifier).as_uri()
    return specifier


__all__ = ["to_safe_import_path"]
