"""src.infra.exec_safe_builtins - POSIX shell builtins classification.

OpenClaw parity: mirrors ``openclaw-main/src/infra/exec-safe-builtins.ts``
"""

import sys
from typing import TypedDict

# Import ExecCommandSegment from wherever it's defined (usually analysis)
# We will just define a generic structure compatible with it
class ExecCommandSegmentLike(TypedDict, total=False):
    argv: list[str]
    raw: str


DEFAULT_SAFE_BUILTINS = frozenset([
    ":",
    "cd",
    "false",
    "pwd",
    "test",
    "true",
])


def is_windows_platform(platform_str: str | None = None) -> bool:
    if platform_str is not None:
        return platform_str.lower().startswith("win")
    return sys.platform == "win32"


def is_safe_builtin_segment(segment: ExecCommandSegmentLike, platform_str: str | None = None) -> bool:
    """Returns true when a parsed POSIX shell segment is one of the closed safe builtin forms."""
    # Builtin semantics here are POSIX shell. On Windows the host shell is PowerShell, where
    # these tokens have different meaning (cd is an alias to Set-Location, etc.); defer.
    if is_windows_platform(platform_str):
        return False

    argv = segment.get("argv", [])
    head = argv[0].strip().lower() if argv and argv[0] else None
    if not head:
        return False
        
    if head == "[":
        raw = segment.get("raw", "")
        return argv[-1] == "]" or raw.strip().endswith("]")
        
    return head in DEFAULT_SAFE_BUILTINS
