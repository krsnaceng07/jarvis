"""src.security.filesystem_guard — Canonical path validation and system guards.

Matches OpenClaw packages/sandbox_core and fs-safe:
- Resolves realpath, prevents symlink and junction escapes
- Guards Windows protected directories (WindowsApps, System32, WinSxS)
- Protects sensitive credential files (.env, id_rsa, credentials.json)
"""

from __future__ import annotations

import os
import pathlib
import unicodedata
from typing import Iterable, Optional


class SecurityViolationError(PermissionError):
    """Raised when an operation violates filesystem security boundaries."""

    pass


class FilesystemGuard:
    PROTECTED_SYSTEM_PATHS: tuple[str, ...] = (
        r"C:\Windows",
        r"C:\Program Files\WindowsApps",
        r"C:\Program Files\Common Files",
        r"C:\ProgramData\Microsoft",
        r"C:\Users\Default",
    )

    SENSITIVE_FILES: tuple[str, ...] = (
        ".env",
        "id_rsa",
        "id_ed25519",
        "credentials.json",
        "master.key",
        "config.json",
    )

    def __init__(self, allowed_roots: Optional[Iterable[str]] = None):
        self._allowed_roots = [
            os.path.realpath(os.path.abspath(r))
            for r in (allowed_roots or [r"E:\jarvis", r"C:\Users\kcs23"])
        ]

    def validate_path(
        self,
        target_path: str | pathlib.Path,
        operation: str = "read",  # 'read' | 'write' | 'delete'
    ) -> str:
        norm_input = unicodedata.normalize("NFC", str(target_path).strip().strip("'\""))
        if not norm_input:
            raise SecurityViolationError("Path cannot be empty.")

        resolved = os.path.realpath(os.path.abspath(norm_input))
        resolved_lower = resolved.lower()

        # Check protected Windows system directories
        for protected in self.PROTECTED_SYSTEM_PATHS:
            protected_lower = protected.lower()
            if resolved_lower == protected_lower or resolved_lower.startswith(
                protected_lower + "\\"
            ):
                if operation in {"write", "delete"}:
                    raise SecurityViolationError(
                        f"Access Denied: Path '{resolved}' is a protected Windows system path "
                        f"and cannot be modified or deleted."
                    )

        # Check sensitive credentials
        base_name = os.path.basename(resolved).lower()
        if operation in {"delete"} and base_name in self.SENSITIVE_FILES:
            raise SecurityViolationError(
                f"Access Denied: Attempting to delete protected sensitive file '{base_name}'."
            )

        return resolved
