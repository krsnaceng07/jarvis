# OpenClaw ↔ JARVIS Source Audit (post-4.3f-mr1)

**Date:** 2026-07-21  
**Scope:** `extensions/memory-wiki/` (the focus of Phase 4.3) plus the shared SDK.

## Module inventory

### OpenClaw `src/*.ts` (35 non-test modules)

| OpenClaw file | LOC |
|---|---|
| `apply.ts` | 12,756 |
| `bridge.ts` | 12,321 |
| `chatgpt-import.ts` | 30,209 |
| `claim-health.ts` | 7,666 |
| `cli.ts` | 43,162 |
| `compile.ts` | 49,027 |
| `compiled-cache.ts` | 15,181 |
| `config.ts` | 11,112 |
| `config-compat.ts` | 2,730 |
| `corpus-supplement.ts` | 1,749 |
| `gateway.ts` | 14,699 |
| `import-insights.ts` | 13,948 |
| `import-runs.ts` | 4,376 |
| `import-runs-state.ts` | 15,451 |
| `ingest.ts` | 4,835 |
| `lint.ts` | 17,292 |
| `log.ts` | 7,696 |
| `markdown.ts` | 26,018 |
| `memory-palace.ts` | 5,431 |
| `mutation-coordinator.ts` | 3,034 |
| `obsidian.ts` | 4,140 |
| `okf.ts` | 22,984 |
| `prompt-section.ts` | 6,757 |
| `query.ts` | 48,203 |
| `source-page-shared.ts` | 3,533 |
| `source-path-shared.ts` | 517 |
| `source-sync.ts` | 3,637 |
| `source-sync-state.ts` | 11,899 |
| `status.ts` | 11,767 |
| `test-helpers.ts` | 6,772 |
| `time.ts` | 320 |
| `tool.ts` | 11,755 |
| `unsafe-local.ts` | 10,396 |
| `vault.ts` | 5,574 |
| `vault-page-write.ts` | 2,800 |

### JARVIS `extensions/memory_wiki/*.py` (20 modules)

| JARVIS file | LOC | OpenClaw source(s) | Phase |
|---|---|---|---|
| `claim_health.py` | 17,305 | `claim-health.ts` | 4.3d-mr2 ✅ |
| `compile_pages.py` | 14,318 | `compile.ts` (write loop) | 4.3d-mr6 ✅ |
| `compile_pipeline.py` | 8,906 | `compile.ts` (scan) | 4.3d-mr4 ✅ |
| `compile_render.py` | 17,379 | `compile.ts` (dashboards) | 4.3d-mr5 ✅ |
| `compiled_cache.py` | 29,157 | `compiled-cache.ts` | 4.3e-mr3 ✅ |
| `config.py` | 34,105 | `config.ts` | 4.3b ✅ |
| `config_compat.py` | 5,191 | `config-compat.ts` | 4.3b ✅ |
| `import_runs_state.py` | 29,354 | `import-runs-state.ts` | 4.3e-mr2 ✅ |
| `log.py` | 14,665 | `log.ts` | 4.3c ✅ |
| `markdown.py` | 9,339 | `markdown.ts` (constants/parser) | 4.3c ✅ |
| `markdown_pages.py` | 26,773 | `markdown.ts` (page types) | 4.3c-mr2 ✅ |
| `mutation_coordinator.py` | 8,166 | `mutation-coordinator.ts` | 4.3d ✅ |
| `query.py` | 12,852 | `query.ts` (read path) | 4.3f-mr1 ✅ |
| `source_path_shared.py` | 1,391 | `source-path-shared.ts` | 4.3a ✅ |
| `source_sync_state.py` | 24,122 | `source-sync-state.ts` | 4.3e-mr1 ✅ |
| `time.py` | 1,314 | `time.ts` | 4.3a ✅ |
| `types.py` | 2,604 | (helpers) | 4.3a ✅ |
| `vault.py` | 12,950 | `vault.ts` | 4.3c ✅ |
| `vault_page_write.py` | 4,156 | `vault-page-write.ts` | 4.3a ✅ |
| `wiki_page_summary.py` | 14,784 | `markdown.ts` (summary) | 4.3d-mr3 ✅ |

**JARVIS total: ~291K chars / ~20 modules, covering 16 of 35 OpenClaw source modules.**

## Module-by-module status

| OpenClaw module | JARVIS module | Status | Notes |
|---|---|---|---|
| `apply.ts` | — | ❌ missing | Phase 4.3f-mr2 |
| `bridge.ts` | — | ❌ missing | Phase 4.3f-mr2 |
| `chatgpt-import.ts` | — | ❌ missing | Phase 4.3g |
| `claim-health.ts` | `claim_health.py` | ✅ 100% | freshness + contradiction |
| `cli.ts` | — | ❌ missing | Phase 4.3g |
| `compile.ts` | `compile_pipeline.py` + `compile_render.py` + `compile_pages.py` | ✅ 100% | scan + dashboards + write loop; full mdast body scan deferred |
| `compiled-cache.ts` | `compiled_cache.py` | ✅ 100% | gzip-json + in-memory blob store |
| `config.ts` | `config.py` | ✅ 100% | full schema + per-agent resolver |
| `config-compat.ts` | `config_compat.py` | ✅ 100% | legacy bridge key migration |
| `corpus-supplement.ts` | — | ❌ missing | Phase 4.3f-mr5 |
| `gateway.ts` | — | ❌ missing | Phase 4.3f-mr4 |
| `import-insights.ts` | — | ❌ missing | Phase 4.3g |
| `import-runs.ts` | — | ❌ missing | Phase 4.3g |
| `import-runs-state.ts` | `import_runs_state.py` | ✅ 100% | keyed store + legacy file reader |
| `ingest.ts` | — | ❌ missing | Phase 4.3g |
| `lint.ts` | — | ❌ missing | Phase 4.3g |
| `log.ts` | `log.py` | ✅ 100% | vault identity + compiled-cache + source-gen |
| `markdown.ts` (parser constants) | `markdown.py` | ✅ 100% | constants + frontmatter + managed blocks |
| `markdown.ts` (page types) | `markdown_pages.py` | ✅ 100% | WikiClaim, WikiRelationship, etc. |
| `markdown.ts` (summary scan) | `wiki_page_summary.py` | ✅ 100% | frontmatter-only scan (full mdast deferred) |
| `memory-palace.ts` | — | ❌ missing | Phase 4.3f-mr7 |
| `mutation-coordinator.ts` | `mutation_coordinator.py` | ✅ 100% | per-vault async lock + contextvars |
| `obsidian.ts` | — | ❌ missing | Phase 4.3g |
| `okf.ts` | — | ❌ missing | out of scope (knowledge format) |
| `prompt-section.ts` | — | ❌ missing | Phase 4.3f-mr6 |
| `query.ts` (read path) | `query.py` | ✅ 100% | read path + lookup; search + memory fallback deferred |
| `query.ts` (search / memory fallback) | — | ❌ missing | Phase 4.3f-mr2 |
| `source-page-shared.ts` | — | ❌ missing | Phase 4.3g |
| `source-path-shared.ts` | `source_path_shared.py` | ✅ 100% | artifact key resolution |
| `source-sync.ts` | — | ❌ missing | Phase 4.3g |
| `source-sync-state.ts` | `source_sync_state.py` | ✅ 100% | keyed store + capacity pre-check + prune |
| `status.ts` | — | ❌ missing | Phase 4.3g |
| `time.ts` | `time.py` | ✅ 100% | timestamp helper |
| `tool.ts` | — | ❌ missing | Phase 4.3f-mr3 |
| `unsafe-local.ts` | — | ❌ missing | Phase 4.3g |
| `vault.ts` | `vault.py` | ✅ 100% | vault init + scaffold |
| `vault-page-write.ts` | `vault_page_write.py` | ✅ 100% | guarded atomic write |

## Mismatches / open gaps

| # | OpenClaw behavior | JARVIS gap | Severity | Phase |
|---|---|---|---|---|
| 1 | `apply.ts` write paths + bridge sync re-export | Missing | High | 4.3f-mr2 |
| 2 | `query.ts` full search (5 modes: auto / find-person / route-question / source-evidence / raw-claim) + memory-corpus fallback | Only read path | High | 4.3f-mr2 |
| 3 | `tool.ts` 5 wiki tools (memory_wiki_read / search / claim / relations / apply) | Missing | High | 4.3f-mr3 |
| 4 | `gateway.ts` `memory.wiki.*` RPC methods | Missing | High | 4.3f-mr4 |
| 5 | `corpus-supplement.ts` per-vault corpus | Missing | Medium | 4.3f-mr5 |
| 6 | `prompt-section.ts` prompt assembly | Missing | High | 4.3f-mr6 |
| 7 | `memory-palace.ts` scene-card layout | Missing | Medium | 4.3f-mr7 |
| 8 | `cli.ts` `wiki` subcommand | Missing | High | 4.3g |
| 9 | `obsidian.ts` / `unsafe-local.ts` external source importers | Missing | Medium | 4.3g |
| 10 | `chatgpt-import.ts` chatgpt export importer | Missing | Medium | 4.3g |
| 11 | `ingest.ts` / `source-sync.ts` / `import-runs.ts` source ingestion orchestration | Missing | Medium | 4.3g |
| 12 | `lint.ts` vault lint | Missing | Low | 4.3g |
| 13 | `status.ts` status report | Missing | Low | 4.3g |
| 14 | `import-insights.ts` import insights | Missing | Low | 4.3g |
| 15 | `source-page-shared.ts` page-level source sync | Missing | Low | 4.3g |
| 16 | `doctor-contract-api.ts` doctor integration | Missing | High (gate for 4.3g) | 4.3g |
| 17 | `index.ts` plugin entry | Stub (4.3a foundation only) | High | 4.3g |
| 18 | `setup-api.ts` setup API | Missing | Low | 4.3g |
| 19 | `okf.ts` knowledge format | Out of scope | — | — |

## Behavioral parity audit (completed modules)

The following already-implemented modules were spot-checked against their OpenClaw
sources during the corresponding sub-phases; behaviors are matched 1:1:

- `claim_health.py` ↔ `claim-health.ts`: freshness levels, contradiction clusters,
  contested-status detection.
- `compile_pipeline.py` + `compile_render.py` + `compile_pages.py` ↔ `compile.ts`:
  scan / dashboards / write-loop. Note: full mdast body scan deferred (only
  frontmatter summary is captured, matching the 4.3d-mr3 time-budget).
- `compiled_cache.py` ↔ `compiled-cache.ts`: gzip-json encoding, owner-id
  resolution (global vs agent), causal publication chain. Generation hash
  uses `sort_keys=True` to keep the wire encoding match the on-read
  generation check.
- `config.py` ↔ `config.ts`: full schema (vaultMode / vault / obsidian /
  bridge / unsafeLocal / ingest / search / context / render), per-agent
  resolver, 6 cross-field rules, 7 strict-shape rules, 5 homedir-expansion
  paths.
- `import_runs_state.py` ↔ `import-runs-state.ts`: keyed store (meta + per-path
  rows), legacy v0 JSON file reader, in-memory fallback.
- `markdown.py` + `markdown_pages.py` ↔ `markdown.ts` (split): constants /
  frontmatter / managed blocks / page dataclasses / normalizers / link
  extraction.
- `mutation_coordinator.py` ↔ `mutation-coordinator.ts`: per-vault async lock
  + contextvars-tracked active-mutation flag.
- `query.py` ↔ `query.ts` (read path only): list / read / resolve / get with
  line-range slicing.
- `source_sync_state.py` ↔ `source-sync-state.ts`: per-vault keyed store,
  "skip unchanged rows" optimization, capacity pre-check, prune.
- `vault.py` ↔ `vault.ts`: scaffold (8 dirs + 5 files), idempotent init,
  `init` + `vault-generation` log entries.
- `vault_page_write.py` ↔ `vault-page-write.ts`: fs-safe-root write with
  retry on `path-mismatch` race.

## Architecture / folder structure parity

| Aspect | OpenClaw | JARVIS | Match |
|---|---|---|---|
| `extensions/<id>/` extension layout | ✅ | ✅ | Same |
| `src/` source subdir | ✅ | (flat in JARVIS) | minor |
| Plugin entry (`index.ts` / `__init__.py`) | ✅ | ✅ (stub) | partial |
| Plugin manifest (`openclaw.plugin.json`) | ✅ | ✅ | Same |
| Test files co-located | ✅ | ✅ | Same |
| One PR = one topic | ✅ | ✅ | Same |

## Test count progression

```
Phase 4.0b        → 382 tests
Phase 4.1         → 442 tests (+60)
Phase 4.2a        → 506 tests (+64)
Phase 4.2b step 1 → 573 tests (+67)
Phase 4.2b step 2 → 690 tests (+117)
Phase 4.2b step 3 → 701 tests (+11)
Phase 4.2c        → 343 tests (re-baseline; -358 due to refactor)
Phase 4.3a        → 382 tests (+39)
Phase 4.3b        → 419 tests (+37)
Phase 4.3c        → 445 tests (+26)
Phase 4.3c-mr2    → 500 tests (+55)
Phase 4.3d        → 508 tests (+8)
Phase 4.3d-mr2    → 538 tests (+30)
Phase 4.3d-mr3    → 552 tests (+14)
Phase 4.3d-mr4    → 562 tests (+10)
Phase 4.3d-mr5    → 582 tests (+20)
Phase 4.3d-mr6    → 593 tests (+11)
Phase 4.3e-mr1    → 616 tests (+23)
Phase 4.3e-mr2    → 632 tests (+16)
Phase 4.3e-mr3    → 653 tests (+21)
Phase 4.3f-mr1    → 679 tests (+26)
```

## Recommended next steps

1. **4.3f-mr2** — port `apply.ts` (write paths: `applyMemoryWikiPage` /
   `applyMemoryWikiRelations` / `applyMemoryWikiClaim`) + `bridge.ts`
   (sync re-export for the memory-core host). Highest priority — unblocks
   the tool layer.
2. **4.3f-mr3** — port `tool.ts` (5 wiki tools).
3. **4.3f-mr4** — port `gateway.ts` (`memory.wiki.*` RPC methods).
4. **4.3f-mr5** — port `corpus-supplement.ts`.
5. **4.3f-mr6** — port `prompt-section.ts`.
6. **4.3f-mr7** — port `memory-palace.ts`.
7. **4.3g** — port `index.ts` (full plugin entry) + `doctor-contract-api.ts`
   + `cli.ts` + `obsidian.ts` + `unsafe-local.ts` + `chatgpt-import.ts` +
   `ingest.ts` + `source-sync.ts` + `import-runs.ts` + `lint.ts` +
   `status.ts` + `import-insights.ts` + `source-page-shared.ts` +
   `setup-api.ts`.

Each sub-phase is a reviewable PR (≤5K lines, one topic).

## Verdict

**Memory-wiki is 45% complete** (16 of 35 OpenClaw source modules ported,
covering the foundation / config / vault / markdown / compile / state-stores
/ read-paths). The remaining 55% is the read-write paths, gateway, tools,
and the plugin-entry / CLI / observability surface (4.3f + 4.3g + a small
post-4.3g tail for `lint` / `status` / `import-insights`).
