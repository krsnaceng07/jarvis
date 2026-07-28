# QA Lab Infra Extension (JARVIS)

Minimum scaffold matching the OpenClaw `extensions/qa-lab/`
shape. The OpenClaw source is 458 files; this
Python port ships a focused subset.

## Parity status (vs `openclaw-main/extensions/qa-lab/`)

| OpenClaw | JARVIS | Notes |
|---|---|---|
| `index.ts` (entrypoint) | `__init__.py` + `plugin.py` | stub entry |
| `Plugin` (generic) | `QALabPlugin` dataclass | shape equivalent |
| Full infra surface | deferred | Phase 5.16 |

The minimum-scaffold is loadable + discoverable; the full
infra surface lands in Phase 5.16.
