# memory_lancedb Plugin Guide

Read this before any change under `extensions/memory_lancedb/`.
These are intentional maintainer decisions.

## Scope

- **Phase 4.1 (shipped).** Vector-search long-term memory
  via LanceDB. Mirrors OpenClaw's
  `extensions/memory-lancedb/` exactly. Two backends: real
  LanceDB and an in-memory numpy fallback for tests.
- **Phase 4.2 (target).** `active_memory` router picks
  memory_lancedb vs memory_core per process; per-session
  enable/disable; recall cache + circuit breaker.
- **Phase 4.3+ (target).** QMD backend as an alternative to
  LanceDB; dreaming phases (light/REM/deep) land here.

## Reliability Invariants

- **One plugin per process.** `api.register_memory_capability`
  is single-active-slot. The host refuses to register a
  second memory plugin. Phase 4.0's `memory_core` and Phase
  4.1's `memory_lancedb` cannot coexist in the same
  process; the operator picks one in config.
- **LanceDB is best-effort.** If the native package can't
  load (Windows + Python 3.13, no wheel), the plugin falls
  back to the in-memory store. Operators get a warning in
  the log; tools still work for the current process.
- **Backends share the same `MemoryStore` protocol.**
  Tests use the in-memory backend. Production uses
  LanceDB. The plugin's public surface never depends on
  the backend choice.
- **Cooldown on embedding failure.** A failed embedding
  call sets a 60s per-agent cooldown so we don't hammer
  the API on every recall. The tool returns an
  "unavailable" message instead of a 5xx-style error.

## Security Invariants

- **Recall filter refuses envelope sludge + prompt
  injection.** Same as `memory_core`: every recalled
  memory is run through `looks_like_envelope_sludge` and
  `looks_like_prompt_injection` before being returned to
  the LLM. A poisoned long-term memory that tries to
  re-inject attack payload on every recall is the primary
  attack vector and is closed at the recall filter.
- **Capture gate refuses prompt injection.** A user
  message that contains "ignore all previous instructions
  ..." is rejected by `should_capture` before it ever hits
  the embed API. Same as `memory_core`.
- **No secrets in the SQLite metadata table.** The
  `agentId` column is the only agent identifier. The
  `embedding.apiKey` is held in memory only (and never
  round-trips through the store).

## Context And Authorization

- **The slash command is operator-only.**
  `expose_sender_is_owner=True`.
- **Tools are gated on `agentId`.** Each tool requires a
  valid (non-empty) agentId; missing/empty values
  surface as `AGENT_DISABLED` rather than storing
  cross-agent data.
- **Auto-recall/capture are config-gated.** The plugin
  honors `autoCapture` and `autoRecall` from the
  operator's config. Default: `autoCapture=false`,
  `autoRecall=true`.

## Review Standard

- New embedding providers must go through the SDK
  `register_memory_embedding_provider` registry, not a
  custom hard-coded import.
- New memory categories need a corresponding entry in
  `MEMORY_CATEGORIES` and a `detect_category` regex update.
- The in-memory backend must stay in lockstep with the
  LanceDB backend's public surface; drift is a bug.

## Dependencies

- `lancedb>=0.20.0` (hard dep; runtime loader tries
  `import lancedb` and falls back to in-memory on failure).
- `pyarrow>=15.0.0` (transitive via lancedb).
- `openai>=1.30.0` (only used by the direct HTTP path;
  the provider-adapter path uses the SDK registry).
- No `lancedb` import at module top — `lancedb_runtime.py`
  is the only place the import lives.
