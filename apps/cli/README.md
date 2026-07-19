# JARVIS CLI

Headless gateway CLI. Entry point: `jarvis` (declared in root `pyproject.toml`).

## Status

**Phase 0.3 placeholder.** Created in **Phase 0.4 / 1** alongside the desktop app.

## Target layout (after Phase 1)

```
apps/cli/
├── pyproject.toml
├── README.md
├── src/jarvis_cli/
│   ├── __init__.py
│   ├── __main__.py
│   ├── app.py              # typer/argparse entry
│   ├── commands/
│   │   ├── __init__.py
│   │   ├── start.py        # `jarvis gateway start`
│   │   ├── stop.py
│   │   ├── status.py
│   │   ├── message.py      # `jarvis message send --target ...`
│   │   ├── doctor.py       # `jarvis doctor` (Phase 8)
│   │   ├── migrate.py      # `jarvis doctor --fix` (Phase 8)
│   │   ├── pairing.py      # `jarvis pairing approve ...`
│   │   ├── extensions.py   # `jarvis extensions list/install/remove`
│   │   └── skills.py       # `jarvis skills list/show`
│   └── output/
│       ├── formatters.py   # text/json/yaml
│       └── prompts.py      # interactive prompts
└── tests/
    └── test_commands.py
```

## Rules

- CLI commands dispatch into the gateway via `packages/gateway_protocol/` (JSON-RPC).
- CLI never imports from `extensions/*`; uses the plugin loader.
- First-class command: `jarvis doctor` (Phase 8) runs the doctor contract.
