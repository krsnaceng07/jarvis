# memory_core Plugin Guide

Read this before any change under `extensions/memory_core/`. These
are intentional maintainer decisions. Also read `extensions/AGENTS.md`
for the plugin boundary rules.

## Scope

- **Phase 2 (shipped).** Long-term memory via SQLite. Substring
  search; key/value get; slash command; prompt section. Mirrors
  OpenClaw's `extensions/memory-core/` exactly.
- **Phase 2.5 (target).** LanceDB semantic-search backend behind
  a feature flag; FTS5 index; legacy `memory.json` apply path.
- **Phase 3+ (target).** Dreaming (auto-summarize at low-traffic
  hours); cross-session recall; vector compression.

## Reliability Invariants

- **One SQLite file per workspace.** Default path
  ``$JARVIS_DATA_DIR/core/memory.sqlite`` (or
  ``~/.jarvis/core/memory.sqlite``). Never write to multiple DBs.
- **WAL is OFF.** Phase 2 uses default rollback journal (not WAL)
  to keep the `sqlite3.connect(...)` API simple. WAL is a Phase
  2.5 improvement (concurrent reads + writes from the cron runner).
- **Threading.** `check_same_thread=False` because plugins call us
  from the async event loop. ALL access goes through `_conn_lock`.
- **Substring search is bounded.** `limit` defaults to 20, max
  enforced at 100. Don't let the LLM ask for `limit=10000`.
- **No exceptions in `runtime.recent()` / `runtime.search_substring()`.**
  They return an empty list on any DB error (the plugin layer
  surfaces the error in its `Result`).

## Security Invariants

- **No network.** Memory is local SQLite. We never phone home.
- **No shell injection.** All SQL is parameterized (`?` placeholders).
- **Write paths are scoped to the data dir.** The plugin never
  builds absolute paths from user input.

## Context And Authorization

- **Single-active-slot.** The `api.register_memory_capability`
  call fails loudly if another plugin already registered a memory
  capability. JARVIS has one memory, period.
- **The slash command is operator-only.** ``expose_sender_is_owner=True``.

## Review Standard

- Schema changes (new columns, new tables) need a migration plan.
  Phase 2 uses `CREATE TABLE IF NOT EXISTS`; future versions add
  a versioned migration table.
- Performance changes (FTS5, vector index) need a benchmark
  against the legacy `memory/memory.json` path.
- Cross-platform issues (Windows path separators, macOS file
  permissions) need a real OS test before merging.

## Dependencies

- `sqlite3` (stdlib).
- No third-party packages. Phase 2.5 adds `lancedb` for semantic
  search and optional `croniter` for scheduled `set` jobs.
