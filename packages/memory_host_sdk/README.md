# `jarvis-memory-host-sdk`

Public memory API surface for JARVIS. Mirrors OpenClaw's
`packages/memory-host-sdk/` package (60+ files: the public
memory API used by both the host runtime and by plugin
authors). Plugins import only from this package; never from
`src/...` or other extensions.

## Public surface

The current slice (Phase 5.1–5.5) re-exports the 34
`memory_host_*.py` modules from `jarvis_sdk` while the
physical move is in progress. The re-export shim is
temporary; the physical move (Phase 2 of the V2 refactor
plan) will rewrite the modules to live here natively.

## Test surface

`packages/memory_host_sdk/tests/` will house the
`test_memory_host_*.py` files in the follow-up phase that
moves the modules here. The 60+ test files in the OpenClaw
`packages/memory-host-sdk/src/host/*.test.ts` are the
reference.

## Migration status

| Phase | Status | Notes |
|---|---|---|
| 5.1 event types / store / export | ✅ re-exported from `jarvis_sdk` | 43 tests |
| 5.2 hash / status / secret | ✅ re-exported | 61 tests |
| 5.3 query expansion / multimodal | ✅ re-exported | 71 tests |
| 5.4 read retry / read file / internal | ✅ re-exported | 105 tests |
| 5.5 error utils (18 SECRET_PATTERNS preserved verbatim) | ✅ re-exported | 30 tests |
| Physical move (Wave 6 of refactor Step 2) | ⏸ deferred | barrel re-exports create circular imports |
