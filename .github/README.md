# .github/

GitHub-specific configuration. CI workflows, issue/PR templates,
CODEOWNERS, labeler rules. None of this affects JARVIS runtime; it's
purely for the GitHub repo UI and automation.

## Layout

```
.github/
├── README.md                       # this file
├── CODEOWNERS                      # who reviews what
├── labeler.yml                     # auto-label rules
├── dependabot.yml                  # dependency update PRs
├── ISSUE_TEMPLATE/
│   ├── bug_report.md
│   └── feature_request.md
├── PULL_REQUEST_TEMPLATE.md
└── workflows/
    └── ci.yml                      # PR + push CI
```

## Workflows (PR 0.3 ships only `ci.yml`)

| Workflow | Trigger | What it does | Lands in |
|---|---|---|---|
| `ci.yml` | push, PR | pytest + ruff + pyright | PR 0.3 (this PR) |
| `release.yml` | tag | Build sdist + wheel, publish to PyPI | Phase 0.5+ |
| `docs.yml` | push to main | Build & publish docs | Phase 5+ |
| `labeler.yml` | PR | Auto-label by `apps/*`, `packages/*`, `extensions/*` | PR 0.3 |
| `stale.yml` | schedule | Mark stale issues/PRs | Phase 0.5+ |
| `dependency-guard.yml` | schedule | Pin/override audits | Phase 6+ |
| `security-sensitive-guard.yml` | PR | Require security review on secret/auth/sandbox paths | Phase 6+ |
| `opengrep.yml` | PR | OpenGrep precise rulepack | Phase 6+ (stretch) |

## Templates (PR 0.3)

- `ISSUE_TEMPLATE/bug_report.md` — what you saw, what you expected, repro steps.
- `ISSUE_TEMPLATE/feature_request.md` — user story, alternatives considered.
- `PULL_REQUEST_TEMPLATE.md` — What, Why, How, Evidence, Risk, Docs
  (matches the per-phase PR template in `OPENCLAW_MIGRATION_PLAN.md` §8).

## CODEOWNERS

Single-owner repo right now (the JARVIS architect). Add reviewers as
extensions and packages gain owners.

## labeler.yml

Auto-labels PRs by what files they touch:
- `apps/<x>/**` → label `app/<x>`
- `packages/<x>/**` → label `package/<x>`
- `extensions/<x>/**` → label `extension/<x>`
- `docs/**` → label `docs`
- `tests/**` → label `tests`
- `tools/**` → label `tools`

See `OPENCLAW_MIGRATION_PLAN.md` §1, §7, §8.
