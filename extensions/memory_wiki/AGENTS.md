# memory_wiki Plugin Guide

Read this before any change under `extensions/memory_wiki/`.
These are intentional maintainer decisions. Also read
`extensions/AGENTS.md` for the plugin boundary rules.

## Scope

The memory_wiki extension is OpenClaw's persistent wiki
compiler and Obsidian-friendly knowledge vault. It is
**separate from the active_memory plugin** — the active
memory plugin still handles recall, promotion, and
dreaming. memory_wiki compiles durable knowledge into a
navigable markdown vault with deterministic indexes,
provenance, structured claim/evidence metadata, and
optional Obsidian CLI workflows.

- **Phase 4.3a (this PR).** Foundation: types, time, log
  (vault-generation + publication identity), source-path
  shared helpers, vault-page atomic write.
- **Phase 4.3b (next).** Config: `config.ts` (11KB) +
  `config-compat.ts` (3KB) — the full zod-style schema
  (vaultMode / vault / obsidian / bridge / unsafeLocal /
  ingest / search / context / render) and the per-agent
  config resolver.
- **Phase 4.3c (planned).** Vault init + Markdown:
  `vault.ts` (scaffold directories + scaffold files),
  `markdown.ts` (split into core + render + pages; 26KB).
- **Phase 4.3d (planned).** Compile + claim-health +
  memory-palace + mutation-coordinator (`compile.ts` is
  the largest single file at 49KB; we split it into
  `compile_pipeline` + `compile_render` + `compile_pages`).
- **Phase 4.3e (planned).** State stores: `compiled-cache.ts`
  + `import-runs.ts` + `import-runs-state.ts` +
  `source-sync.ts` + `source-sync-state.ts`.
- **Phase 4.3f (planned).** Read path + write path:
  `query.ts` (48KB; split into search + get) + `okf.ts` +
  `lint.ts` + `apply.ts` + `tool.ts` + `bridge.ts` +
  `gateway.ts` + `corpus-supplement.ts` +
  `prompt-section.ts` + `source-page-shared.ts`.
- **Phase 4.3g (planned).** CLI + obsidian + unsafe-local
  + chatgpt-import + index + doctor-contract-api.

## Reliability Invariants

- **Vault identity is a UUID generation.** A new vault
  gets a fresh `vaultGeneration` UUID on first
  initialization (`ensureMemoryWikiVaultGeneration`).
  Concurrent initialization can append two candidates;
  the first durable entry wins.
- **Causal publication chain.** `loadMemoryWikiValidated
  VaultIdentity` re-hashes the source tree on every load
  and invalidates the cached publication id if the
  source-tree hash diverges from the recorded
  `compiledCacheSourceGeneration`. This guards against
  restored-vault divergence.
- **Atomic page writes.** `writeGuardedVaultPage` writes
  through the fs-safe root; a transient "concurrent
  rewrite race" (path-mismatch) is retried briefly.
  Symlink/path-alias swaps and persistent guard
  failures hard-fail.
- **Log entries are JSONL.** A partial final line after
  an interrupted append is silently ignored by the
  identity loader.

## Security Invariants

- **Symlink rejection.** The fs-safe root refuses any
  write that traverses a symlink in the parent chain
  (`FsSafeError("symlink")`).
- **Path-traversal guard.** `resolveArtifactKey` uses
  `lowercase_preserving_whitespace` on Windows (case-
  insensitive FS) and the canonical realpath on
  POSIX. Plugin code that resolves untrusted paths
  MUST go through this helper.
- **Hardlink detection.** `isRegularFileStat` +
  `writeGuardedVaultPage` breaks a hardlink (nlink > 1)
  before the atomic write to prevent an in-place
  rewrite from poisoning a separate file the user
  linked.
- **No `await` outside the test surface.** The
  foundation is sync-only. The async path lives in
  `vault.py` (Phase 4.3c) and `compile.py`
  (Phase 4.3d).

## Review Standard

- New `FsSafeError` codes must be added to the
  `_FS_SAFE_ERROR_CODES` set in
  `packages/plugin_sdk/src/jarvis_sdk/security_runtime.py`
  AND mirrored in the OpenClaw `@openclaw/fs-safe/errors`
  `FsSafeErrorCode` union. Phase 4.3a ships seven codes:
  `path-mismatch`, `symlink`, `path-alias`,
  `already-exists`, `hardlink`, `not-found`,
  `out-of-root`.
- New log entry types must be added to the
  `MemoryWikiLogEntry` literal in `log.py` AND to the
  OpenClaw `log.ts` `type` union. The loader walks the
  log linearly; a malformed JSON line is silently
  skipped.
- The `vaultGeneration` field is the durable identity
  anchor. Sub-phases that introduce a new identity
  (e.g. `compiledCacheReservationId`) MUST extend the
  `MemoryWikiVaultIdentity` dataclass and the
  `loadMemoryWikiVaultIdentity` walker.

## Dependencies

- Stdlib only (Phase 4.3a).
- The `jarvis_sdk` package is the only allowed import
  boundary (no cross-extension imports; no cross-package
  imports outside `jarvis_sdk`).
- Phase 4.3c may need `pathspec` or a small glob helper
  for the markdown source-tree walker; stdlib
  `pathlib.Path.glob` is preferred if it is fast enough.
- Phase 4.3d (`compile.ts`) will likely need an FTS5
  binding; the search-side of the Python port uses
  in-memory filtering + LanceDB FTS for the
  `searchMode=local` backend.
- `lancedb` is NOT a dependency — the wiki's search
  is a consumer of whichever `search.backend` the
  config selects.
