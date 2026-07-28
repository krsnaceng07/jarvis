# RAFT Channel Extension (JARVIS)

Minimum scaffold matching the OpenClaw `extensions/raft/`
shape. The OpenClaw source is 18 files; this
Python port ships a focused subset.

## Parity status (vs `openclaw-main/extensions/raft/`)

| OpenClaw | JARVIS | Notes |
|---|---|---|
| `index.ts` (entrypoint) | `__init__.py` + `plugin.py` | stub entry |
| `ChannelPlugin` descriptor | `RAFTPlugin` dataclass | shape equivalent |
| Send / listen | `send()` + `listen()` abstract stubs | Phase 5.16 |
| Doctor contract | `doctor.py` returns healthy stub | Phase 5.16 |
| Runtime singleton | `runtime.py` `set/get/reset` | shape equivalent |

## Auth

Env vars: `RAFT_NODE_ID` (read at init time).

## Base URL

`raft://localhost:7000`

The minimum-scaffold is loadable + discoverable; the full
send + listen + media surface lands in Phase 5.16.
