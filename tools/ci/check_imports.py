"""Enforce JARVIS plugin import boundaries.

Rules (mirrors OpenClaw's check-extension-import-boundary):

- Extensions may import only from `jarvis_sdk.*` (the plugin SDK) and their own package.
- No cross-extension imports (`from extensions.X.Y import ...`).
- No imports from `packages/*/src/**` (except `packages/plugin_sdk/src/jarvis_sdk/`).
- No imports of bare `main`, `ui`, `or_client` (those modules are being migrated).

Full rule enforcement is added in Phase 1 (after `plugin_sdk` exists).
This Phase 0.2 version is a stub that validates the structure and flags
violations of the rules above that are already enforceable today.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
EXTENSIONS = ROOT / "extensions"
PACKAGES = ROOT / "packages"

# ── Forbidden top-level module names (legacy JARVIS modules being migrated) ──
FORBIDDEN_TOP_LEVEL = {
    "main",                # current monolithic main.py
    "ui",                  # current monolithic ui.py
    "or_client",           # current or_client.py (becomes packages/llm_client)
    "actions",             # current flat actions/ (becomes extensions/tool_*)
    "agent",               # current agent/ (becomes packages/agent_runtime)
    "memory",              # current memory/ (becomes extensions/memory_core)
}

# ── Allowed SDK imports (anything else in jarvis_* is suspicious in extensions) ──
SDK_ROOT = "jarvis_sdk"

# Pattern: `from X import Y` or `import X`
IMPORT_RE = re.compile(
    r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))",
    re.MULTILINE,
)


def find_violations() -> list[str]:
    """Scan every .py file under extensions/ for import violations."""
    if not EXTENSIONS.exists():
        return []

    violations: list[str] = []
    for py_file in EXTENSIONS.rglob("*.py"):
        if "__pycache__" in py_file.parts:
            continue
        try:
            text = py_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        rel = py_file.relative_to(ROOT)
        for m in IMPORT_RE.finditer(text):
            mod = m.group(1) or m.group(2)
            if not mod:
                continue
            top = mod.split(".", 1)[0]
            line_no = text[: m.start()].count("\n") + 1

            if top in FORBIDDEN_TOP_LEVEL:
                violations.append(
                    f"{rel}:{line_no}: imports legacy module `{top}` "
                    f"(being migrated per OPENCLAW_MIGRATION_PLAN.md)"
                )
            # Cross-extension: `from extensions.X import ...` or
            # `from X.Y import ...` where X is a sibling extension dir
            if mod.startswith("extensions."):
                violations.append(
                    f"{rel}:{line_no}: cross-extension import `{mod}` "
                    f"(extensions may only import from `jarvis_sdk.*` and self)"
                )

    return violations


def main() -> int:
    violations = find_violations()
    if violations:
        for v in violations:
            print(f"FAIL: {v}")
        print(f"\n{len(violations)} import violation(s) found.")
        return 1
    if not EXTENSIONS.exists():
        print("OK: extensions/ not yet created (Phase 0) — nothing to check")
    else:
        n = sum(1 for _ in EXTENSIONS.rglob("*.py") if "__pycache__" not in _.parts)
        print(f"OK: scanned {n} extension files; no import violations")
    return 0


if __name__ == "__main__":
    sys.exit(main())
