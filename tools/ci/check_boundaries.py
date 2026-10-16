"""Run the canonical JARVIS architecture boundary checks.

This module preserves the module-style command documented in AGENTS.md:
``uv run python -m tools.ci.check_boundaries``.
"""

from __future__ import annotations

import sys

from .check_imports import main as check_imports_main


def main() -> int:
    return check_imports_main()


if __name__ == "__main__":
    sys.exit(main())
