<!--
This template follows the per-phase PR template from OPENCLAW_MIGRATION_PLAN.md §8.
Fill every section. Cross-link the migration plan phase this PR implements.
-->

## What

One-sentence summary. References `AGENTS.md` for the area it touches.

## Why

- Problem observed (cite `file:line`)
- Why the chosen fix is the best fix (cite sibling/scope evidence)
- What alternatives were considered and rejected

## How

- Files added / moved / removed (with line counts)
- Schema version bumps (if any)
- Migration / doctor impact (if any)
- New config keys (if any) — must justify why existing product
  behavior / doctor migration could not solve it (per AGENTS.md
  "Config/env surface bar is high")

## Evidence

- Local: `uv run pytest tests/ -q` (paste result)
- Local: `uv run ruff check` (paste result)
- Local: `uv run pyright packages/<x> extensions/<x>` (paste result)
- Local: `uv run python tools/ci/check_imports.py` (paste result)
- Manual: `uv run python -m jarvis_desktop` launched, observed X
- Skill/tool/scenario that exercises the change

## Risk

- Compatibility: what existing user config/data could break
- Rollback: `git revert <sha>` is safe because …
- Follow-up: linked issue / discussion thread

## Docs

- Updated: `docs/<area>/<file>.md`
- New: `docs/<area>/<new>.md`
- Changelog: included in PR body (release generation pulls it in;
  CHANGELOG.md is release-only per AGENTS.md)

## Migration plan link

This PR implements phase: [link to OPENCLAW_MIGRATION_PLAN.md §N]

## Self-review checklist

- [ ] One PR = one topic (per AGENTS.md)
- [ ] Lines changed < 5,000 (per AGENTS.md)
- [ ] No silent compat (per AGENTS.md)
- [ ] No new config keys without justification
- [ ] Tests prove behavior, not branches
- [ ] `tools/ci/check_imports.py` passes (extensions import only from `jarvis_sdk.*`)
- [ ] `tools/ci/check_cycles.py` passes (no import cycles)
- [ ] `tools/ci/check_max_lines.py` passes (no file > 2000 lines)
- [ ] `tools/ci/check_manifests.py` passes (all `jarvis.plugin.json` valid)
