"""src.security.exec_guard — Command execution policy and AST security.

Matches OpenClaw packages/exec_policy/src/validator.py:
- Strict tokenization
- Safe executable allowlist
- Blocks shell injection and metacharacter chaining
"""

from __future__ import annotations

import re
import shlex
from typing import NamedTuple


class CommandValidationResult(NamedTuple):
    is_safe: bool
    reason: str
    executable: str
    arguments: list[str]


class ExecGuard:
    ALLOWED_BINARIES: frozenset[str] = frozenset(
        {
            "git",
            "uv",
            "python",
            "pytest",
            "ruff",
            "node",
            "npm",
            "tasklist",
            "explorer",
            "where",
            "powershell",
            "cmd",
            "notepad",
        }
    )

    DANGEROUS_PATTERNS: tuple[re.Pattern, ...] = (
        re.compile(r"[;&|`$><]"),
        re.compile(r"(\$\([^)]*\))", re.DOTALL),
        re.compile(r"(Format-Volume|Clear-Disk)", re.I),
        re.compile(r"(Remove-Item\s+-Path\s+[CDE]:[\\/]\s+-Recurse)", re.I),
        re.compile(r"(Invoke-WebRequest|Invoke-RestMethod).*\.ps1", re.I),
    )

    @classmethod
    def validate_command(cls, command_str: str) -> CommandValidationResult:
        cmd_clean = command_str.strip()
        if not cmd_clean:
            return CommandValidationResult(False, "Empty command.", "", [])

        for pattern in cls.DANGEROUS_PATTERNS:
            if pattern.search(cmd_clean):
                return CommandValidationResult(
                    False,
                    f"Command rejected: contains dangerous shell metacharacters or destructive command patterns ({pattern.pattern}).",
                    "",
                    [],
                )

        try:
            tokens = shlex.split(cmd_clean, posix=False)
        except ValueError as e:
            return CommandValidationResult(False, f"Command parsing error: {e}", "", [])

        if not tokens:
            return CommandValidationResult(False, "No executable specified.", "", [])

        raw_bin = tokens[0].rstrip(".exe").lower()
        exe_name = raw_bin.replace("/", "\\").split("\\")[-1]

        if exe_name not in cls.ALLOWED_BINARIES:
            return CommandValidationResult(
                False,
                f"Binary '{exe_name}' is not in the safe executable allowlist.",
                exe_name,
                tokens[1:],
            )

        return CommandValidationResult(True, "Command verified safe.", exe_name, tokens[1:])
