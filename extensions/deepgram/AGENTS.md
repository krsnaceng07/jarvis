# Deepgram Infra Extension (JARVIS)

Minimum scaffold matching the OpenClaw `extensions/deepgram/`
shape. The OpenClaw source is 11 files; this
Python port ships a focused subset.

## Parity status (vs `openclaw-main/extensions/deepgram/`)

| OpenClaw | JARVIS | Notes |
|---|---|---|
| `index.ts` (entrypoint) | `__init__.py` + `plugin.py` | stub entry |
| `Plugin` (generic) | `DeepgramPlugin` dataclass | shape equivalent |
| Full infra surface | deferred | Phase 5.16 |

The minimum-scaffold is loadable + discoverable; the full
infra surface lands in Phase 5.16.
