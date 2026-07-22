"""Validate every extension manifest against the JARVIS plugin manifest schema.

Mirrors OpenClaw's manifest validation (extensions/<id>/openclaw.plugin.json).

Required fields (Phase 0.2 minimum):
- id: str (kebab-case, must match directory name)
- kind: one of {channel, provider, tool, memory, skill, infra, migration}
- version: str (semver)
- description: str

Optional fields (validated when present):
- icon: str (URL)
- activation: one of {always, on_startup, on_demand}
- requires: dict with optional keys (bins, python, env, services)
- permissions: list[str]
- configSchema: dict (JSON Schema subset)
- tools: list of tool declarations
- channels: list[str]
- entrypoint: str
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
EXTENSIONS = ROOT / "extensions"

# Phase 1C: relaxed to match OpenClaw's actual manifest shape.
# OpenClaw's `openclaw.plugin.json` only requires `id` (must match the
# directory name). `kind` / `version` / `description` live in the
# entry module's `definePluginEntry(...)` call, not the manifest.
# See openclaw-main/extensions/memory-core/openclaw.plugin.json for
# the canonical shape.
REQUIRED = {"id"}
ALLOWED_KINDS = {"channel", "provider", "tool", "memory", "skill", "infra", "migration"}
ALLOWED_ACTIVATION = {"always", "on_startup", "on_demand"}
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?$")
# Python extensions use snake_case (since `from extensions.<id> import X`
# requires a valid Python identifier). OpenClaw uses kebab-case because Node
# imports tolerate hyphens. We allow both.
ID_RE = re.compile(r"^[a-z][a-z0-9_-]*[a-z0-9]$")


def validate_manifest(ext_dir: Path) -> list[str]:
    errors: list[str] = []
    # Canonical manifest name is ``openclaw.plugin.json`` (matches
    # OpenClaw's `extensions/<id>/openclaw.plugin.json`). Python's
    # identifier rules force the directory name to be snake_case, but
    # the manifest file name follows OpenClaw exactly.
    manifest_path = ext_dir / "openclaw.plugin.json"
    if not manifest_path.exists():
        return [f"{ext_dir.name}: openclaw.plugin.json not found"]

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [f"{ext_dir.name}/openclaw.plugin.json: invalid JSON: {e}"]

    if not isinstance(manifest, dict):
        return [f"{ext_dir.name}/openclaw.plugin.json: must be a JSON object"]

    # Required fields
    missing = REQUIRED - manifest.keys()
    if missing:
        errors.append(f"{ext_dir.name}: missing required fields: {sorted(missing)}")

    # id must match directory name (kebab-case)
    if "id" in manifest:
        mid = manifest["id"]
        if not isinstance(mid, str):
            errors.append(f"{ext_dir.name}: 'id' must be a string")
        elif mid != ext_dir.name:
            errors.append(f"{ext_dir.name}: 'id' ({mid}) must match directory name")
        elif not ID_RE.match(mid):
            errors.append(
                f"{ext_dir.name}: 'id' ({mid}) must be snake/kebab-case "
                f"(lowercase letters, digits, underscore or hyphen)"
            )

    # kind
    if "kind" in manifest:
        kind = manifest["kind"]
        if kind not in ALLOWED_KINDS:
            errors.append(f"{ext_dir.name}: 'kind' ({kind}) must be one of {sorted(ALLOWED_KINDS)}")

    # version
    if "version" in manifest:
        version = manifest["version"]
        if not isinstance(version, str) or not SEMVER_RE.match(version):
            errors.append(f"{ext_dir.name}: 'version' ({version!r}) must be semver (e.g. '0.1.0')")

    # activation (optional)
    if "activation" in manifest and manifest["activation"] not in ALLOWED_ACTIVATION:
        errors.append(
            f"{ext_dir.name}: 'activation' ({manifest['activation']}) "
            f"must be one of {sorted(ALLOWED_ACTIVATION)}"
        )

    # tools (optional, list of dicts)
    if "tools" in manifest:
        tools = manifest["tools"]
        if not isinstance(tools, list):
            errors.append(f"{ext_dir.name}: 'tools' must be a list")
        else:
            for i, t in enumerate(tools):
                if not isinstance(t, dict):
                    errors.append(f"{ext_dir.name}: tools[{i}] must be an object")
                    continue
                if "name" not in t or not isinstance(t["name"], str):
                    errors.append(f"{ext_dir.name}: tools[{i}].name must be a string")
                if "description" not in t or not isinstance(t["description"], str):
                    errors.append(f"{ext_dir.name}: tools[{i}].description must be a string")

    return errors


def main() -> int:
    if not EXTENSIONS.exists():
        print("OK: extensions/ not yet created (Phase 0) — nothing to check")
        return 0

    all_errors: list[str] = []
    n_manifests = 0
    for ext_dir in sorted(EXTENSIONS.iterdir()):
        if not ext_dir.is_dir():
            continue
        n_manifests += 1
        all_errors.extend(validate_manifest(ext_dir))

    if all_errors:
        for e in all_errors:
            print(f"FAIL: {e}")
        print(f"\n{len(all_errors)} manifest error(s) across {n_manifests} extension(s).")
        return 1
    print(f"OK: validated {n_manifests} extension manifest(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
