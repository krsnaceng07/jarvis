# JARVIS desktop app

The PyQt6 HUD — the iconic MARK XXXIX-OR visual interface. Entry point: `jarvis_desktop` (declared in root `pyproject.toml`).

## Status

**Phase 0.3 placeholder.** The current `main.py` and `ui.py` live at the workspace root. They will be moved here in **Phase 0.4** and split into smaller modules in **Phase 1**.

## Target layout (after Phase 1)

```
apps/desktop/
├── pyproject.toml
├── README.md
├── src/jarvis_desktop/
│   ├── __init__.py
│   ├── __main__.py
│   ├── app.py              # entry point (was main.py)
│   ├── ipc.py              # gateway ↔ UI bridge
│   ├── prompt.txt          # system prompt
│   └── hud/
│       ├── __init__.py
│       ├── window.py       # main window (was ui.py MainWindow)
│       ├── canvas.py       # HudCanvas (face + halos)
│       ├── metrics.py      # CPU/MEM/NET/GPU/TMP bars
│       ├── log.py          # LogWidget (animated log)
│       ├── dropzone.py     # FileDropZone
│       ├── setup.py        # SetupOverlay (first-run API key)
│       └── theme.py        # color constants
├── assets/
│   ├── face.png            # user avatar (gitignored, runtime asset)
│   └── icons/
└── tests/
    └── test_window.py
```

## Rules

- Desktop-specific deps (PyQt6, platform shims) live in this app's `pyproject.toml`,
  not the root.
- Imports from `packages/agent_runtime/`, `packages/plugin_sdk/`, etc. are allowed.
- Imports from `extensions/*` are NOT allowed; use the plugin loader.
- Face image is per-user; `assets/face.png` is gitignored.

See [`OPENCLAW_MIGRATION_PLAN.md`](../../OPENCLAW_MIGRATION_PLAN.md) for the full migration roadmap.
