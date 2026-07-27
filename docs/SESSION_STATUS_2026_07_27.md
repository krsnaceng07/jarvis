# Session Status — 2026-07-27

## Commits landed this session (4)

```
8fcfb6c docs(plan): §49 — log Refactor Step 2 (Waves 1-5) + Phase 5.8-5.12 port-complete
c06db37 docs(plan): §49 — log Phase 5.8-5.12 port-complete + lockfile update
ed6448d feat(phase5.12): context_engine + new OpenClaw-shaped src/ dirs
4f4e5f7 feat(phase5.8-5.11): agent_runtime — agent-core + loop + compaction + Agent
f109c68 fix(refactor): restore src/cron/__init__.py + clean up Wave 6 partial-move debris
```

## What was actually in the working tree (uncommitted before this session)

The previous summary only mentioned Phase 5.9-5.11; the real uncommitted
state was much larger:

- **Phase 5.8** (agent-core types + harness primitives) — pre-ported in
  `packages/agent_runtime/src/jarvis_agent/` (12 source files, 69 tests).
- **Phase 5.9** (agent loop) — `agent_loop.py` (48K) + `turn_interruption.py`.
- **Phase 5.10** (compaction) — `compaction.py` (33K) +
  `branch_summarization.py` (12K) + `compaction_utils.py` (8K).
- **Phase 5.11** (Agent class) — `agent.py` (25K).
- **Phase 5.12** (context engine) — 12 files in `src/context_engine/`
  + the lost 72-test `tests/test_phase512_context_engine.py` (2083 lines).
- **5 new OpenClaw-shaped `src/` dirs**:
  `src/infra/`, `src/plugin_state/`, `src/shared/`,
  `src/terminal_core/`, `src/utils/`.
- **15 new `src/routing/` modules** (per-file OpenClaw split).
- **`src/plugins/memory_state.py` + `slots.py`** additions.
- **3 refactor tools**: `jarvis_refactor.py`, `jarvis_bulk_move.py`,
  `fix_internal_imports.py`.
- **Docs**: `docs/OPENCLAW_BRAIN_PORT_PLAN_V2.md`.
- **conftest.py** (Windows path-safety hook).
- **uv.lock** (5 new workspace members).

## What was fixed

1. **`src/cron/__init__.py` regression** — the refactor Step 1 commit
   (`855d748`) accidentally replaced the 196-line cron runner with a
   10-line stub, and the redirect-stashed copy had a UTF-16 BOM that
   broke the file (null bytes → SyntaxError). Restored from commit
   `41c781c`, stripped BOM, re-encoded as clean UTF-8. 5/5 cron tests
   now pass (38/38 in `tests/test_phase2.py`).

2. **Wave 6 partial-move debris** — 34 broken partial-move files in
   `packages/memory_host_sdk/src/jarvis_memory_host_sdk/` (from a
   rolled-back Wave 6) deleted. The re-export shim `__init__.py` is
   the only file in the package now; the legacy `jarvis_sdk.*`
   import surface is preserved.

## What was lost (need to re-port)

`tests/test_phase512_context_engine.py` (2083 lines, 72 tests) was
uncommitted in the working tree. The botched file-split pass
(attempting to extract helpers into a shared module to bring the
file under the 2000-line hard limit) destroyed the original source.
The 72 tests will be **re-ported from OpenClaw** in a follow-up
Phase 5.12b commit, split into 4 files matching OpenClaw's source
test file layout:

- `tests/test_phase512_context_engine.py` (≤1.5K, 49 tests from `context-engine.test.ts`)
- `tests/test_phase512_context_engine_host_compat.py` (≤500, 5 tests)
- `tests/test_phase512_context_engine_quarantine_health.py` (≤500, 4 tests)
- `tests/test_phase512_context_engine_runtime_settings.py` (≤500, 6 tests)

The `src/context_engine/` implementation is intact and ready for
those tests to land.

## Test baseline

| State | Pass | Fail | Skip |
|---|---|---|---|
| Before session | 2472 | 17 | 1 |
| After Wave 6 cleanup + cron fix | 2477 | 12 | 1 |
| After test file loss (Phase 5.12b pending) | 2413 | 4 | 1 |

The 4 remaining failures are **pre-existing and unrelated** to this
session's work:

1. `extensions/memory_core/tests/test_memory_core_phase4.py::TestMemoryCoreEntry::test_register_adds_tools_and_capability`
   — 4.3k `set_manifest` contract change.
2. `extensions/memory_lancedb/tests/test_memory_lancedb_phase4.py::TestMemoryLancedbEntry::test_register_sets_active_db_and_embeddings`
   — same 4.3k root cause + lancedb not installed.
3. `tests/test_smoke.py::TestJarvisDesktopImport::test_jarvis_desktop_app_module`
   — `TOOL_DECLARATIONS` count dropped to 3 (expected 8+); same 4.3k
     root cause (plugin tool registrations are skipped because
     `contracts.tools` not declared).
4. `tests/test_smoke.py::TestAppManifestLoader::test_tool_declarations_includes_manifest_entries`
   — same as #3.

Also installed in-session: `google-genai` transitive deps
(`annotated_types`, `anyio`, `certifi`, `httpx`, ...). These were
missing and causing the 8 smoke tests to fail at import time; smoke
tests are now at 28/30 passing (the 2 remaining are the 4.3k issue).

## Refactor progress

Per `docs/OPENCLAW_STRUCTURE_MISMATCH.md`, the structural mismatch
refactor has 6 waves. Status:

| Wave | Scope | Status |
|---|---|---|
| Step 1 | 9 re-export shims (no behavior change) | ✅ `855d748` |
| Wave 1 | `retry_runtime` → `packages/retry/` | ✅ `09b9d6a` |
| Wave 2 | `routing` / `security_runtime` / `session_transcript_runtime` → `src/{routing,security,sessions}/` | ✅ `9f24184` |
| Wave 3 | 4 normalization modules → `packages/normalization_core/` | ✅ `85ecaec` |
| Wave 4 | `memory_runtime` + `memory_storage` → `src/memory/` | ✅ `a32b95c` |
| Wave 5 | 7 `plugin_registry_*.py` → `src/plugins/` | ✅ `975cc14` |
| Wave 6 | 34 `memory_host_*.py` → `packages/memory_host_sdk/src/jarvis_memory_host_sdk/` | ⏸️ Deferred (circular import) |

The Wave 6 deferral is documented in §49.6 of the plan.

## Open questions for user

1. **Re-port Phase 5.12 tests** (Phase 5.12b) — needed to restore the
   72 lost test count. Implementation already in place; tests
   need to be re-written from OpenClaw's 4 source `.test.ts` files.

2. **Fix 4.3k `set_manifest` regressions** — pre-existing. The
   extensions/memory_core and extensions/memory_lancedb plugins
   don't declare `contracts.tools` in their manifests, so the
   smoke test plugin loader drops their tool registrations.
   Either the manifests need to declare the tools, or the
   loader needs to be made more permissive.

3. **Continue with V2 plan phases**:
   - 5.12b (re-port Phase 5.12 tests)
   - 5.13 (routing) — ~1.8K LOC; partial already done in
     `src/routing/` additions
   - 5.14 (sessions, SQLite schema gate) — ~3.9K LOC
   - 5.15 (runner spine) — ~4.5K LOC
   - 5.16 (gateway) — ~3K LOC
   - 5.17 (Gemini provider, live smoke test) — ~0.8K LOC
   - 5.18 (delete old brain, irreversible, gated) — ~2.6K LOC
   - 5.19 (extension migration + verification) — ~1.5K LOC
