"""CI check to ensure database and config schema versions are canonical.

Enforces the AGENTS.md policy:
"Any SQLite change requiring a schema-version bump needs explicit user discussion
and acceptance before implementation. Agents must not advance SQLite schema versions
autonomously."
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
PYPROJECT_PATH = ROOT / "pyproject.toml"

CANONICAL_SCHEMA_VERSIONS: dict[str, int] = {
    "schema_state": 1,
    "schema_agent": 1,
    "schema_config": 1,
    "schema_memory": 1,
}


def check_schema_versions() -> list[str]:
    errors: list[str] = []

    if not PYPROJECT_PATH.exists():
        return ["pyproject.toml not found"]

    try:
        data = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        return [f"pyproject.toml: failed to parse TOML: {e}"]

    tool_jarvis = data.get("tool", {}).get("jarvis", {})
    if not tool_jarvis:
        return ["pyproject.toml: missing [tool.jarvis] section"]

    for key, expected_version in CANONICAL_SCHEMA_VERSIONS.items():
        actual_version = tool_jarvis.get(key)
        if actual_version is None:
            errors.append(f"pyproject.toml: missing [tool.jarvis].{key}")
        elif actual_version != expected_version:
            errors.append(
                f"pyproject.toml: [tool.jarvis].{key} = {actual_version} "
                f"(expected canonical version {expected_version}). "
                f"Autonomous schema bumps are forbidden by AGENTS.md."
            )

    # Check state_core contract
    try:
        from jarvis_state_core.contract import (
            STATE_SCHEMA_VERSION,
            STATE_STRICT_SCHEMA_VERSION,
        )

        if STATE_SCHEMA_VERSION != CANONICAL_SCHEMA_VERSIONS["schema_state"]:
            errors.append(
                f"jarvis_state_core.contract: STATE_SCHEMA_VERSION = {STATE_SCHEMA_VERSION} "
                f"(expected {CANONICAL_SCHEMA_VERSIONS['schema_state']})"
            )
        if STATE_STRICT_SCHEMA_VERSION != 1:
            errors.append(
                f"jarvis_state_core.contract: STATE_STRICT_SCHEMA_VERSION = {STATE_STRICT_SCHEMA_VERSION} (expected 1)"
            )
    except ImportError:
        # Fallback if package is not installed in current environment
        pass

    return errors


def main() -> None:
    errors = check_schema_versions()
    if errors:
        print("FAIL: schema version check failed:")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)
    print("OK: schema versions are canonical (no autonomous bumps)")


if __name__ == "__main__":
    main()
