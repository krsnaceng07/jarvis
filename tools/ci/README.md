# JARVIS CI tools

These are the local-equivalent of OpenClaw's `scripts/check-*.mjs` family. They run
as pre-commit hooks (see `.pre-commit-config.yaml`) and on every push via CI.

## Available checks

| Script | Purpose | Phase added |
|---|---|---|
| `check_imports.py` | Enforce plugin import boundaries. Extensions may only import from `jarvis_sdk.*` and their own package. | 0.2 |
| `check_cycles.py` | Detect import cycles in `packages/`, `apps/`, `extensions/`. | 0.2 |
| `check_max_lines.py` | Hard limit 2000 lines/file (soft 700 per AGENTS.md). | 0.2 |
| `check_manifests.py` | Validate every `extensions/*/jarvis.plugin.json` against the manifest schema. | 0.2 |

## Running locally

```bash
uv run python tools/ci/check_imports.py
uv run python tools/ci/check_cycles.py
uv run python tools/ci/check_max_lines.py
uv run python tools/ci/check_manifests.py
```

Or all at once via pre-commit:

```bash
uv run pre-commit run --all-files
```

## Adding a new check

1. Add the script under `tools/ci/`.
2. Make it exit 0 on success, 1 on failure.
3. Print `OK: ...` on success, `FAIL: ...` on failure (so pre-commit output is readable).
4. Add a hook entry in `.pre-commit-config.yaml`.
5. Update this README's table.
6. Update `OPENCLAW_MIGRATION_PLAN.md` with the new check.

All checks are pure Python (no compiled deps) so they work on every platform.
