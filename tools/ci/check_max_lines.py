"""Enforce max file length.

Per AGENTS.md:
- "Split files around ~700 LOC when clarity/testability improves."
- "Never add a `max-lines` suppression."

This check enforces a hard 2000-line ceiling (twice the soft 700 target).
Files over 700 should be split; files over 2000 must be split.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SOFT_LIMIT = 700
HARD_LIMIT = 2000


def main() -> int:
    over_soft: list[tuple[Path, int]] = []
    over_hard: list[tuple[Path, int]] = []

    for py_file in ROOT.rglob("*.py"):
        if any(p.startswith(".") for p in py_file.parts):
            continue
        if "__pycache__" in py_file.parts:
            continue
        if "openclaw-main" in py_file.parts:
            continue
        if "node_modules" in py_file.parts:
            continue
        if "legacy_" in py_file.name:
            continue
        try:
            n = sum(1 for _ in py_file.open("r", encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
        rel = py_file.relative_to(ROOT)
        if n > HARD_LIMIT:
            over_hard.append((rel, n))
        elif n > SOFT_LIMIT:
            over_soft.append((rel, n))

    if over_hard:
        print(f"FAIL: {len(over_hard)} file(s) exceed hard limit ({HARD_LIMIT} lines):")
        for path, n in over_hard:
            print(f"  {path}: {n} lines (split required)")
        return 1

    if over_soft:
        print(f"WARN: {len(over_soft)} file(s) exceed soft limit ({SOFT_LIMIT} lines):")
        for path, n in over_soft:
            print(f"  {path}: {n} lines (consider splitting)")
        # Soft limit is a warning, not a failure.

    print(f"OK: no file exceeds hard limit ({HARD_LIMIT} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
