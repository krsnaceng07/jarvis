"""Enforce JARVIS plugin import boundaries.

Rules (mirrors OpenClaw's check-extension-import-boundary):

- Extensions may import only from:
    * `jarvis_sdk.*` (the plugin SDK)
    * their own package (self-imports)
    * `extensions.memory_core.*` (the OpenClaw memory capability)
    * `extensions.cron.*` (the OpenClaw cron capability)
    * `src.*` (host core modules — bootstrap, skills, hooks, etc.)
- No cross-extension imports.
- No imports from `packages/*/src/**` (except `packages/plugin_sdk/src/jarvis_sdk/`).
- No imports of bare `main`, `ui`, `or_client`, `agent`, `memory`, `actions`
  (legacy modules removed in Phase 3.5).

Phase 3.5: `jarvis.*` imports are gone — extensions use `src.<module>` now.
The `extensions.memory_core` and `extensions.cron` allowlists are
intentional (extensions commonly read these capabilities).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
EXTENSIONS = ROOT / "extensions"
PACKAGES = ROOT / "packages"

# ── Forbidden top-level module names (legacy JARVIS modules removed in Phase 3.5) ──
FORBIDDEN_TOP_LEVEL = {
    "main",
    "ui",
    "actions",
    "agent",
    "memory",
    "or_client",
}

# ── Allowed legacy imports ─
# (empty in Phase 3.5: no legacy allowed; everything goes through
# jarvis_sdk, src, or extensions.<memory_core|cron>)
LEGACY_ALLOWED_FOR_EXTENSIONS: set[str] = set()

# ── Allowed SDK imports (anything else in jarvis_* is suspicious in extensions) ──
SDK_ROOT = "jarvis_sdk"

# Pattern: `from X import Y` or `import X`
IMPORT_RE = re.compile(
    r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))",
    re.MULTILINE,
)

# Extensions that other extensions may depend on (the OpenClaw
# "shared capabilities" pattern). Currently: memory_core, cron.
EXTENSION_ALLOWLIST = {"memory_core", "cron"}


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
                    f"{rel}:{line_no}: imports removed/legacy module `{top}` "
                    f"(Phase 3.5 removed all root-level legacy code)"
                )
            # Cross-extension: `from extensions.<other> import ...`
            if mod.startswith("extensions.") and self_ext is not None:
                ext_name = mod.split(".", 2)[1] if mod.count(".") >= 2 else ""
                norm_ext = ext_name.replace("-", "_")
                norm_self = self_ext.replace("-", "_")
                if norm_ext and norm_ext != norm_self and norm_ext not in EXTENSION_ALLOWLIST:
                    violations.append(
                        f"{rel}:{line_no}: cross-extension import `{mod}` "
                        f"(extensions may only import from `jarvis_sdk.*`, "
                        f"`src.*`, and the shared capabilities: "
                        f"{sorted(EXTENSION_ALLOWLIST)})"
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
