# JARVIS apps

User-facing applications. Each app is a workspace member with its own `pyproject.toml` and an entry point declared in the root `pyproject.toml` (`[tool.jarvis] entrypoint_*`).

Mirrors OpenClaw's `apps/` (8 apps: macos, ios, android, linux, macos-mlx-tts, shared, swabble). JARVIS targets a tighter surface for a solo project.

## Layout

| App | Purpose | Phase |
|---|---|---|
| `desktop/` | PyQt6 HUD (the current MARK XXXIX-OR UI). Entry: `jarvis_desktop`. | 0.4 |
| `cli/` | Headless gateway CLI. Entry: `jarvis`. | 0.4 / 1 |
| `tui/` | Terminal UI (optional). | 12 |

## Rules

- Each app has its own `pyproject.toml`.
- Apps import freely from `packages/*` (core libraries).
- Apps may NOT import from `extensions/*` directly; they use the plugin loader
  from `packages/plugin_sdk/`.
- App-specific code (UI widgets, CLI commands) stays in the app, not in `packages/`.

See [`OPENCLAW_MIGRATION_PLAN.md`](../OPENCLAW_MIGRATION_PLAN.md) for the full migration roadmap.
