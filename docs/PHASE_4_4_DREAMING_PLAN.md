# Phase 4.4 — Dreaming Pipeline Port Plan

**Date:** 2026-07-23
**Source of truth:** `openclaw-main/extensions/memory-core/`
**Architect rule:** Same to same — match OpenClaw's architecture, structure,
workflow, style, logic exactly. No JARVIS-original additions.
**Verification:** `docs/OPENCLAW_VERIFICATION_4.4.md` at the end.

---

## OpenClaw Source Inventory

### Root-level files (3)

| File | LOC | Purpose |
|---|---|---|
| `openclaw.plugin.json` | 156 | Plugin manifest: `id: "memory-core"`, 2 tools, 1 alias, uiHints, full `configSchema` |
| `index.ts` | 228 | Plugin entry: registers tools, command, CLI, memory capability, dreaming state + cron |
| `cli.ts` | 261 | Re-export of `registerMemoryCli` from `src/cli.js` |
| `cli-metadata.ts` | n/a | TS-only metadata (skip per Phase 4.3g decision) |

### `src/*.ts` (10 dreaming + 1 CLI = 11 files)

| File | LOC | OpenClaw exports |
|---|---|---|
| `dreaming-state.ts` | 143 | 7 namespace constants + `configureMemoryCoreDreamingState`, `openMemoryCoreStateStore`, workspace key normalizers, `readMemoryCoreWorkspaceEntries`, `writeMemoryCoreWorkspaceEntries` |
| `dreaming-shared.ts` | 31 | Shared helpers between dreaming files |
| `dreaming-events.ts` | 32 | Failed-dreaming event helpers + paths |
| `dreaming-dreams-file.ts` | 140 | Dreams file persistence (DREAMS.md + per-session) |
| `dreaming-markdown.ts` | 145 | Phase block writers (`writeDailyDreamingPhaseBlock`, `writeDeepDreamingReport`) |
| `dreaming-narrative.ts` | 943 | Narrative generation via LLM subagent (with fallback path) |
| `dreaming-repair.ts` | 310 | `auditDreamingArtifacts`, `repairDreamingArtifacts` |
| `dreaming-shadow-trial.ts` | 227 | Shadow trial (preview without writing) |
| `dreaming-phases.ts` | 1861 | Light + REM + Deep phases + `runDreamingSweepPhases` |
| `dreaming-command.ts` | 121 | `/dreaming` slash command handler |
| `dreaming.ts` | 926 | `registerShortTermPromotionDreaming` (cron registration, lifecycle, reconciliation) |
| `cli.ts` | n/a | `registerMemoryCli` (CLI subcommands: status/index/search/promote/promote-explain/rem-harness/rem-backfill) |

**Total: ~5,140 LOC** to port.

---

## Plugin Entry Flow (from `index.ts`)

```
register(api):
  1. configureMemoryCoreDreamingState(<T>(opts) => state.openKeyedStore<T>(opts))
     → sets up the global keyed store factory for dreaming state

  2. registerShortTermPromotionDreaming(api)
     → registers cron job for the dreaming sweep
     → sets up start-of-life reconciliation
     → schedules a "shadow trial" (dry-run) at startup

  3. api.registerMemoryCapability({
       promptBuilder: buildPromptSection,
       flushPlanResolver: buildMemoryFlushPlan,
       runtime: createLazyMemoryRuntime(host),
       publicArtifacts: ...
     })

  4. api.registerTool((ctx) => createLazyMemorySearchTool(...), {names: ["memory_search"]})
     api.registerTool((ctx) => createLazyMemoryGetTool(...),    {names: ["memory_get"]})

  5. api.registerCommand({
       name: "dreaming",
       description: "Enable or disable memory dreaming.",
       acceptsArgs: true,
       exposeSenderIsOwner: true,
       handler: async (ctx) => handleDreamingCommand(api, ctx),
     })

  6. api.registerCli(async ({program}) => { registerMemoryCli(program, host) })
     → wires up `memory status/index/search/promote/...` subcommand tree
```

---

## Port Mapping

| OpenClaw file | JARVIS port | Sub-phase |
|---|---|---|
| `dreaming-state.ts` | `extensions/memory_core/dreaming_state.py` | 4.4a |
| `dreaming-shared.ts` | `extensions/memory_core/dreaming_shared.py` | 4.4b |
| `dreaming-events.ts` | `extensions/memory_core/dreaming_events.py` | 4.4b |
| `dreaming-dreams-file.ts` | `extensions/memory_core/dreaming_dreams_file.py` | 4.4c |
| `dreaming-markdown.ts` | `extensions/memory_core/dreaming_markdown.py` | 4.4d |
| `dreaming-narrative.ts` | `extensions/memory_core/dreaming_narrative.py` | 4.4e |
| `dreaming-repair.ts` | `extensions/memory_core/dreaming_repair.py` | 4.4f |
| `dreaming-shadow-trial.ts` | `extensions/memory_core/dreaming_shadow_trial.py` | 4.4g |
| `dreaming-phases.ts` | `extensions/memory_core/dreaming_phases.py` | 4.4h |
| `dreaming-command.ts` | `extensions/memory_core/dreaming_command.py` | 4.4i |
| `dreaming.ts` | `extensions/memory_core/dreaming.py` | 4.4j |
| `cli.ts` (src) | `extensions/memory_core/cli.py` | 4.4l |
| `cli.ts` (root) | (re-export from `cli.py`) | 4.4l |
| `index.ts` | `extensions/memory_core/__init__.py` (update) | 4.4k |
| `openclaw.plugin.json` | (update) | 4.4l |

---

## Porting Rules (enforced across all sub-phases)

1. **Same function names** — `registerShortTermPromotionDreaming` becomes
   `register_short_term_promotion_dreaming` (snake_case only).
2. **Same public API surface** — every public OpenClaw export has a
   corresponding Python export in the matching file.
3. **Same config schema** — `configSchema` in manifest matches OpenClaw 1:1.
4. **Same state namespace constants** — 7 namespaces with same names.
5. **Same error contract** — failure events, log format, append paths.
6. **Same async pattern** — subagent is async; sweep is async; state I/O is sync.
7. **Same docstring format** — first line: OpenClaw purpose, second line: Python port.

---

## Sub-phase Details

### 4.4a — dreaming-state (143 LOC, ~150 LOC Python)
**File:** `extensions/memory_core/dreaming_state.py`
**Exports:**
- 7 namespace constants (`DREAMING_DAILY_INGESTION_NAMESPACE` etc.)
- `configure_memory_core_dreaming_state(open_keyed_store)`
- `open_memory_core_state_store(namespace, open_keyed_store)`
- `normalize_memory_core_workspace_key(workspace_dir)`
- `memory_core_workspace_state_key(workspace_dir)`
- `memory_core_workspace_entry_key(workspace_dir, logical_key)`
- `memory_core_state_reference(namespace, workspace_dir)`
- `read_memory_core_workspace_entries(namespace, workspace_dir)`
- `write_memory_core_workspace_entries(namespace, workspace_dir, entries)`
**Notes:**
- 7 namespace constants → module-level `str` constants
- `OpenKeyedStoreOptions` async → Python sync keyed store
- TypeBox `TSchema` → use `dataclass` for `WorkspaceValue`
- 4,096 entries max per namespace

### 4.4b — dreaming-shared (31 LOC) + dreaming-events (32 LOC)
**Files:** `extensions/memory_core/dreaming_shared.py`, `dreaming_events.py`
**Exports (shared):**
- `resolve_memory_core_dreaming_logger(api)` — type helper
- `format_dreaming_error_message(err)` — string formatter
**Exports (events):**
- `DREAMING_FAILED_EVENTS_PATH` constant
- `append_failed_dreaming_event({workspaceDir, phase, error, storageMode, nowMs, logger})`
- `list_failed_dreaming_events(workspace_dir)`
- `normalize_failed_dreaming_events(raw)`

### 4.4c — dreaming-dreams-file (140 LOC)
**File:** `extensions/memory_core/dreaming_dreams_file.py`
**Exports:**
- `DREAMS_FILE_RELATIVE_PATH` constant
- `resolve_dreams_file_path(workspace_dir)`
- `read_dreams_file(workspace_dir) -> str`
- `write_dreams_file(workspace_dir, content)`
- `append_dream_entry(workspace_dir, entry_md)`
- `parse_dream_entry(text) -> dict`

### 4.4d — dreaming-markdown (145 LOC)
**File:** `extensions/memory_core/dreaming_markdown.py`
**Exports:**
- `DAILY_DREAMING_PHASE_MARKERS`, `DEEP_DREAMING_REPORT_MARKERS` constants
- `resolve_phase_markers(phase)` — "light" | "rem" → markers
- `resolve_daily_memory_path(workspace_dir, epoch_ms, timezone)`
- `resolve_separate_report_path(workspace_dir, phase, epoch_ms)`
- `should_write_inline(storage)` / `should_write_separate(storage)` predicates
- `write_daily_dreaming_phase_block({workspaceDir, day, phase, block, cfg})`
- `write_deep_dreaming_report({workspaceDir, report, cfg})`

### 4.4e — dreaming-narrative (943 LOC)
**File:** `extensions/memory_core/dreaming_narrative.py`
**Exports (28 functions):**
- `NarrativePhaseData` dataclass
- `append_fallback_narrative_entry({nowMs, timezone, logger, reason})`
- `read_recent_dream_diary_entries({workspaceDir, limit})`
- `generate_and_append_dream_narrative({subagent, workspaceDir, data, nowMs, timezone, model, logger})`
- `run_detached_dream_narrative(...)` — non-blocking variant
- ~20 internal helpers (diary section mgmt, narrative session keys, prompt builders)
**Notes:**
- Subagent integration via `subagent.run({idempotencyKey, sessionKey, message})`
- Python: stub the subagent surface as a `SubagentSurface` protocol
- LLM call → use existing `jarvis_sdk.acquire_local_service` interface

### 4.4f — dreaming-repair (310 LOC)
**File:** `extensions/memory_core/dreaming_repair.py`
**Exports:**
- `DreamingArtifactsAuditSummary` dataclass
- `RepairDreamingArtifactsResult` dataclass
- `audit_dreaming_artifacts({workspaceDir, logger}) -> AuditSummary`
- `repair_dreaming_artifacts({workspaceDir, audit, logger, nowMs}) -> RepairResult`

### 4.4g — dreaming-shadow-trial (227 LOC)
**File:** `extensions/memory_core/dreaming_shadow_trial.py`
**Exports:**
- `DreamingShadowTrialVerdict` Literal type ("helpful"|"neutral"|"harmful")
- `DreamingShadowTrialRecommendation` Literal type ("promote"|"defer"|"reject")
- `DreamingShadowTrialInput` dataclass
- `DreamingShadowTrialReport` dataclass
- `resolve_dreaming_shadow_trial_recommendation(report) -> Recommendation`
- `default_dreaming_shadow_trial_report_path({workspaceDir, nowMs}) -> Path`
- `build_dreaming_shadow_trial_report({input, verdict, helpfulSnippets, harmfulSnippets, ...})`
- `write_dreaming_shadow_trial_report({report, path, logger})`

### 4.4h — dreaming-phases (1861 LOC) — THE BIG ONE
**File:** `extensions/memory_core/dreaming_phases.py`
**Exports (12 functions + types):**
- `DAILY_INGESTION_STATE_RELATIVE_PATH`, `SESSION_INGESTION_STATE_RELATIVE_PATH` paths
- `RemDreamingPreview` dataclass
- `preview_rem_dreaming({workspaceDir, cfg, logger, nowMs}) -> RemDreamingPreview`
- `seed_historical_daily_memory_signals({workspaceDir, logger, cfg, nowMs})`
- `filter_recall_entries_within_lookback({entries, nowMs, lookbackDays})`
- `normalize_daily_ingestion_state(raw)`, `normalize_session_ingestion_state(raw)`
- `run_dreaming_sweep_phases({workspaceDir, pluginConfig, cfg, logger, subagent, detachNarratives, nowMs})`
  - **This is the orchestrator** — runs light, REM, then deep in sequence
- Internal: `run_light_dreaming`, `run_rem_dreaming`, `run_deep_dreaming`
- Internal: 30+ helper functions (snippet builders, heading parsers, daily file readers, etc.)
**Notes:**
- `run_dreaming_sweep_phases` must catch errors per-phase and continue
- Each phase has its own `appendFailedDreamingEvent` call on failure
- Light/REM phases write inline + separate report; deep phase writes separate report

### 4.4i — dreaming-command (121 LOC)
**File:** `extensions/memory_core/dreaming_command.py`
**Exports:**
- `handle_dreaming_command(api, ctx) -> PluginCommandResult`
  - Implements `/dreaming on|off|status|help` (admin-gated)
**Notes:**
- Admin gating: `lacks_admin_or_owner_for_dreaming_mutation` check
- `update_dreaming_enabled_in_config` mutates config (admin-only)
- `format_status`, `format_phase_guide`, `format_usage` helpers

### 4.4j — dreaming.ts main (926 LOC)
**File:** `extensions/memory_core/dreaming.py`
**Exports (3 main + many helpers):**
- `resolve_short_term_promotion_dreaming_config({pluginConfig, appConfig, agentId, cfg, nowMs})` — config resolver
- `register_short_term_promotion_dreaming(api)` — the registration function called from `index.ts`
- `reconcile_short_term_dreaming_cron_job({...})` — cron lifecycle
- Internal: managed-cron job builder, legacy migration, error formatter
**Notes:**
- Cron uses `RUNTIME_CRON_RECONCILE_INTERVAL_MS = 60_000`
- Handles race condition in startup: retry 12 times at 5s intervals
- Migrates legacy phase jobs to managed jobs

### 4.4k — index.ts plugin entry (228 LOC)
**File:** `extensions/memory_core/__init__.py` (UPDATE)
**Changes:**
- Add imports for new dreaming exports
- Add `configure_memory_core_dreaming_state(...)` call
- Add `register_short_term_promotion_dreaming(api)` call
- Add `/dreaming` command registration
- Add `memory` CLI subcommand registration
- Keep existing tool registrations (memory_search, memory_get)

### 4.4l — cli.ts (261 LOC) + manifest update
**File:** `extensions/memory_core/cli.py` + manifest update
**cli.py exports:**
- `register_memory_cli(program, host_options)` — registers 7 subcommands
- All subcommands: `memory status`, `memory index`, `memory search`,
  `memory promote`, `memory promote-explain`, `memory rem-harness`,
  `memory rem-backfill`
**manifest updates:**
- `id: "memory-core"` (with hyphen, not underscore — Python identifier constraint applies differently here since this is the manifest)
- `kind: "memory"`
- `contracts.tools: ["memory_get", "memory_search"]`
- `commandAliases: [{name: "dreaming", kind: "runtime-slash", cliCommand: "memory"}]`
- `toolMetadata: {memory_get: {replaySafe: true}}`
- Full `uiHints: {dreaming.frequency, dreaming.model}`
- Full `configSchema.dreaming.{...}` (8 sections)
- `activation.onStartup: false` (per OpenClaw)

### 4.4m — Live test + pre-commit + tests
- Run `jarvis --help` and confirm new `memory` subcommand appears
- Run `jarvis memory --help` to confirm 7 subcommands
- Run `jarvis dreaming status` to confirm slash command
- Run all 935 unit tests
- Run pre-commit 7/7
- Live `jarvis memory search`, `jarvis memory promote --help` etc.

### 4.4 verification
- Re-run side-by-side comparison
- Update `docs/OPENCLAW_VERIFICATION_4.4.md`

---

## Dependencies Between Sub-phases

```
4.4a (state)         ← base for all other phases
4.4b (shared+events) ← needed by 4.4c
4.4c (dreams-file)   ← needed by 4.4d, 4.4e
4.4d (markdown)      ← needed by 4.4h
4.4e (narrative)     ← needed by 4.4h, 4.4g
4.4f (repair)        ← independent
4.4g (shadow-trial)  ← depends on 4.4e
4.4h (phases)        ← depends on 4.4a, 4.4b, 4.4c, 4.4d, 4.4e
4.4i (command)       ← independent
4.4j (orchestrator)  ← depends on 4.4a, 4.4b, 4.4h
4.4k (entry)         ← depends on all above
4.4l (cli+manifest)  ← depends on 4.4k
```

Parallel-safe pairs: (4.4a, 4.4b), (4.4f, 4.4i), (4.4c, 4.4d)

---

## Public API Surface (what `extensions/memory_core/__init__.py` must export)

```python
# Existing (4.0a)
MemoryRuntime, build_prompt_section, MemoryCorePlugin, ... (Phase 4.0)

# New (4.4)
# dreaming-state
DREAMING_DAILY_INGESTION_NAMESPACE
DREAMING_SESSION_INGESTION_FILES_NAMESPACE
DREAMING_SESSION_INGESTION_SEEN_NAMESPACE
SHORT_TERM_RECALL_NAMESPACE
SHORT_TERM_PHASE_SIGNAL_NAMESPACE
SHORT_TERM_META_NAMESPACE
SHORT_TERM_LOCK_NAMESPACE
SHORT_TERM_LOCK_MAX_ENTRIES
SESSION_SEEN_HASHES_PER_CHUNK
configure_memory_core_dreaming_state, open_memory_core_state_store
normalize_memory_core_workspace_key, memory_core_workspace_state_key
memory_core_workspace_entry_key, memory_core_state_reference
read_memory_core_workspace_entries, write_memory_core_workspace_entries

# dreaming-shared + events
append_failed_dreaming_event, list_failed_dreaming_events

# dreaming-dreams-file
resolve_dreams_file_path, read_dreams_file, write_dreams_file, append_dream_entry

# dreaming-markdown
write_daily_dreaming_phase_block, write_deep_dreaming_report

# dreaming-narrative
generate_and_append_dream_narrative, read_recent_dream_diary_entries

# dreaming-repair
audit_dreaming_artifacts, repair_dreaming_artifacts

# dreaming-shadow-trial
build_dreaming_shadow_trial_report, write_dreaming_shadow_trial_report
default_dreaming_shadow_trial_report_path
resolve_dreaming_shadow_trial_recommendation

# dreaming-phases
run_dreaming_sweep_phases, preview_rem_dreaming
seed_historical_daily_memory_signals, filter_recall_entries_within_lookback
normalize_daily_ingestion_state, normalize_session_ingestion_state
DAILY_INGESTION_STATE_RELATIVE_PATH, SESSION_INGESTION_STATE_RELATIVE_PATH

# dreaming-command
handle_dreaming_command

# dreaming main
register_short_term_promotion_dreaming
resolve_short_term_promotion_dreaming_config

# cli
register_memory_cli
```

Total: ~60 new exports. Matches OpenClaw's public surface.

---

## Estimated Effort

| Sub-phase | LOC | Est. complexity |
|---|---|---|
| 4.4a (state) | 150 | Low (mostly constants + CRUD) |
| 4.4b (shared+events) | 70 | Low |
| 4.4c (dreams-file) | 150 | Low |
| 4.4d (markdown) | 160 | Low |
| 4.4e (narrative) | 1000 | High (LLM subagent integration) |
| 4.4f (repair) | 330 | Medium |
| 4.4g (shadow-trial) | 240 | Medium |
| 4.4h (phases) | 2000 | High (orchestrator + 3 phases) |
| 4.4i (command) | 130 | Low |
| 4.4j (orchestrator) | 1000 | High (cron lifecycle) |
| 4.4k (entry) | 250 | Medium |
| 4.4l (cli+manifest) | 280 | Medium |
| 4.4m (test) | - | Tests |

**Total ~5,760 LOC Python** (vs OpenClaw ~5,140 LOC TS) — small expansion
due to Python's explicit type annotations and dataclasses.

**Risk areas:**
- LLM subagent integration (4.4e) — JARVIS doesn't have a real subagent surface yet; need to mock
- Cron lifecycle (4.4j) — JARVIS has `extensions/cron/` but it's separate
- `WorkspaceValue` type — TypeBox to dataclass conversion

**Mitigation:** each sub-phase ships with unit tests + live smoke test before
moving on. If something can't be ported 1:1, document the deviation in
`docs/OPENCLAW_VERIFICATION_4.4.md` and surface it for the architect.
