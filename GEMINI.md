# JARVIS Workspace Rules

## Mandatory Frontend & UI/UX Standards

- **Automatic UI/UX Pro Max Intelligence:** Whenever designing, scaffolding, modifying, styling, or reviewing any frontend components, web pages, or UI/UX in JARVIS (in `frontend/`, `ui/`, `apps/desktop/`, etc.):
  - **Do NOT wait for user reminders.** Always proactively and automatically apply the `ui-ux-pro-max` skill.
  - Run the design intelligence search tool:
    ```bash
    python .agents/skills/ui-ux-pro-max/scripts/search.py "<query>" [--domain <domain>] [--stack <stack>] [--design-system]
    ```
  - Enforce WCAG AA/AAA accessibility standards (minimum 4.5:1 contrast, keyboard navigation, visible focus rings, aria-labels).
  - Adopt professional font pairings, responsive layout grids, consistent spacing tokens, and smooth motion curves from the skill's design system intelligence.
  - All new web frontend work lives in the `frontend/` directory (the new modern frontend replacing legacy `ui/`).

## Mandatory Gravitas Autonomous Execution

- **Automatic Gravitas Activation**: On **EVERY** input prompt and user request (coding, debugging, refactoring, review, planning, terminal execution, or engineering work):
  - **Do NOT wait for user reminders.** Always proactively apply the `gravitas` skill (`.agents/skills/gravitas/SKILL.md` or global `gravitas`).
  - **Foundational Standard**: Report what actually happened, not what was intended. Ground every claim in observable session output. If a check or verification was not run, explicitly state that it was not run.
  - **The 6 Gravitas Invariants**:
    1. **Ground before mutating**: Always read and verify the target, its tests, and its callers before editing. Never act on assumed file state.
    2. **Stay in declared scope**: Keep all changes strictly bounded to the intended files and requirements.
    3. **Completion needs evidence**: Never claim completion, resolution, or verification without fresh, observable execution evidence (test output, linter output, build output, or runtime proof).
    4. **Never exact-retry a failure**: If an approach fails, diagnose the root cause and alter diagnosis, context, or strategy before retrying.
    5. **Satisfy the contract**: Verify all acceptance criteria explicitly; generic affirmations do not suffice.
    6. **Say what you can't verify**: Explicitly state any unverified assumptions, missing test suites, or environmental limitations instead of fabricating certainty.

