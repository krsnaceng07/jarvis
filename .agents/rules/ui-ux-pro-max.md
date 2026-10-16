# Rule: Automatic UI/UX Pro Max Usage for Frontend & Interfaces

Whenever working on any frontend, user interface, web app, or visual components in JARVIS (specifically in `frontend/`, `ui/`, `apps/desktop/`, etc.):
- You MUST automatically activate and apply the `ui-ux-pro-max` skill.
- Do NOT ask the user if you should use UI/UX Pro Max or wait for instructions.
- Proactively run the design intelligence search tool:
  ```bash
  python .agents/skills/ui-ux-pro-max/scripts/search.py "<product_type> <keywords>" --design-system
  ```
- Always adhere to:
  - WCAG AAA/AA accessibility (minimum 4.5:1 contrast, touch targets >= 44x44px, keyboard navigation).
  - Cohesive color palettes and typography pairings.
  - Consistent layout spacing and responsive patterns.
  - Micro-interactions and smooth motion with reduced-motion support.
