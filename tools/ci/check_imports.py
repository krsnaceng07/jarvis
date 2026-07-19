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
    "main",  # current monolithic main.py
    "ui",  # current monolithic ui.py
    "actions",  # current flat actions/ (becomes extensions/tool_*)
    "agent",  # current agent/ (becomes packages/agent_runtime)
    "memory",  # current memory/ (becomes extensions/memory_core)
}

# ── Allowed legacy imports (Phase 1C exception; migrate in Phase 2) ─
# These are top-level modules extensions may use today. They will be
# replaced by proper `packages/*` modules in Phase 2 — at that point
# this allowlist shrinks and the import-boundary rule tightens.
LEGACY_ALLOWED_FOR_EXTENSIONS = {
    "or_client",  # becomes packages/llm_client (Phase 2)
    "config",  # becomes packages/jarvis_config (Phase 2)
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
        # Identify this file's own extension id (the directory directly
        # under ``extensions/``). Self-imports like
        # ``from extensions.tool_weather.plugin import WeatherPlugin``
        # are allowed; cross-extension imports are not.
        parts = rel.parts
        self_ext = parts[1] if len(parts) >= 2 and parts[0] == "extensions" else None

        for m in IMPORT_RE.finditer(text):
            mod = m.group(1) or m.group(2)
            if not mod:
                continue
            top = mod.split(".", 1)[0]
            line_no = text[: m.start()].count("\n") + 1

            if top in FORBIDDEN_TOP_LEVEL and top not in LEGACY_ALLOWED_FOR_EXTENSIONS:
                violations.append(
                    f"{rel}:{line_no}: imports legacy module `{top}` "
                    f"(being migrated per OPENCLAW_MIGRATION_PLAN.md)"
                )
            # Cross-extension: `from extensions.<other> import ...`
            # (imports of self are permitted).
            if mod.startswith("extensions.") and self_ext is not None:
                # `extensions.tool_weather.plugin` lives in `tool_weather/`.
                ext_name = mod.split(".", 2)[1] if mod.count(".") >= 2 else ""
                if ext_name and ext_name != self_ext:
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
