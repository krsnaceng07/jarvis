# JARVIS tools

Local development tooling, parallel to OpenClaw's `scripts/`, `tools/`, `git-hooks/`.

## Layout

```
tools/
├── ci/             # CI checks (pre-commit hooks + GitHub Actions steps)
├── scripts/        # Local dev scripts (doctor, migrate, list-extensions, etc.) — Phase 8
├── git-hooks/      # Git hook scripts (if pre-commit doesn't cover them) — Phase 6
└── codegen/        # Code generators (manifest validators, type stubs) — Phase 1
```

## Phase 0.2 scope

Only `tools/ci/` exists. The other subdirs come in later phases per `OPENCLAW_MIGRATION_PLAN.md`.
