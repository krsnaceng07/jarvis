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
