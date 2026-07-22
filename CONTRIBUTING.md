# Contributing to JARVIS

Read [`AGENTS.md`](AGENTS.md) first. It is the **single source of truth** for all
contribution policy, code style, architecture, and PR rules. This file is a quick-start
summary; the canonical rules live in `AGENTS.md`.

## TL;DR

- **One PR = one topic.** ≤5,000 changed lines. Do not bundle unrelated fixes.
- **Conventional commit messages** (`feat(scope): ...`, `fix(scope): ...`, etc.).
- **Schema version bumps need explicit architect approval** (per `AGENTS.md`).
- **Plugins cross into core only via `jarvis_sdk.*`.** No cross-extension imports.
- **No silent config compat.** Doctor migration is the only path for legacy data.
- **Tests required for new code.** `pytest` + `hypothesis` for property-based tests.
- **Run pre-commit before pushing:** `uv run pre-commit run --all-files`.

## Quick start

1. **Pick an issue** (or open one for bugs/features/architecture changes).
2. **Branch from `main`:**
   ```bash
   git checkout -b fix/short-topic-name
   ```
3. **Make focused changes.** Read the relevant scoped `AGENTS.md` first
   (e.g. `extensions/AGENTS.md` when touching an extension).
4. **Run locally:**
   ```bash
   uv sync                                    # install deps
   uv run pre-commit run --all-files          # lint + type-check + boundary checks
   uv run pytest                              # tests
   ```
5. **Push and open a PR.** Use the PR template (`docs/development/contribution.md`).
6. **Wait for review.** CODEOWNERS will auto-assign based on touched paths.
7. **Architect merges** with `scripts/ship` (or via the PR button if you have rights).

## Architecture rules (cheat sheet)

| Rule | Why |
|---|---|
| Core stays plugin-agnostic | Plugins ship fast; core stays lean |
| Plugins import only from `jarvis_sdk.*` | Enforces plugin boundary; no `src/spaghetti` |
| Storage is SQLite only | Single source of truth; doctor migrates legacy files |
| Skills are declarative markdown | No code in `skills/<id>/`, just `SKILL.md` |
| Schema versioning is mandatory | Bumps need explicit user discussion; agents can't bump autonomously |
| One canonical path | Delete the old path unless user wants compat or shipped contract is cited |
| Lean code wins | No shims, aliases, fallback paths just to reduce diff |

## PR template (use this every time)

```markdown
## What
One-sentence summary.

## Why
- Problem observed (cite file:line)
- Why this fix is the best fix (cite sibling/scope evidence)
- Alternatives considered and rejected

## How
- Files added / moved / removed (with line counts)
- Schema version bumps (if any)
- Migration / doctor impact (if any)
- New config keys (if any) — must justify why existing product could not solve it

## Evidence
- Local: `uv run pytest packages/<x>/test/ -q` (paste result)
- Local: `uv run ruff check` + `uv run pyright packages/<x>` (paste result)
- Manual: `python -m jarvis_desktop` launched, observed X

## Risk
- Compatibility: what existing user config/data could break
- Rollback: `git revert <sha>` is safe because …
- Follow-up: linked issue / discussion

## Docs
- Updated: `docs/<area>/<file>.md`
- New: `docs/<area>/<new>.md`
```

## Commit message format

```
<type>(<scope>): <short summary>

<optional body — wrap at 72 chars>

<optional footer>
```

Common types: `feat`, `fix`, `refactor`, `perf`, `test`, `docs`, `chore`, `ci`.
Common scopes: `desktop`, `cli`, `gateway`, `plugins`, `skills`, `memory`, `tools`, `core`.

Examples:
- `feat(skills): add weather SKILL.md`
- `fix(memory): handle empty query in memory_core.search`
- `refactor(plugins): split weather_report into extensions/tool_weather/` _(historical — `tool_weather` removed Phase 4.3h)_

## License

By contributing, you agree that your contributions will be licensed under the
project's [MIT License](LICENSE).
