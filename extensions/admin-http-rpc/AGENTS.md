# Admin HTTP RPC Infra Extension (JARVIS)

Minimum scaffold matching the OpenClaw `extensions/admin-http-rpc/`
shape. The OpenClaw source is 8 files; this
Python port ships a focused subset.

## Parity status (vs `openclaw-main/extensions/admin-http-rpc/`)

| OpenClaw | JARVIS | Notes |
|---|---|---|
| `index.ts` (entrypoint) | `__init__.py` + `plugin.py` | stub entry |
| `Plugin` (generic) | `AdminHTTPRPCPlugin` dataclass | shape equivalent |
| Full infra surface | deferred | Phase 5.16 |

The minimum-scaffold is loadable + discoverable; the full
infra surface lands in Phase 5.16.
