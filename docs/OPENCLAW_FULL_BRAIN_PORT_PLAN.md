# OpenClaw Full Brain Port Plan

**Date:** 2026-07-23
**Source of truth:** `openclaw-main/`
**Goal:** JARVIS = OpenClaw (A to Z, same-to-same)
**Architect rule:** Match OpenClaw's architecture, structure, workflow, logic, style exactly. No JARVIS-original additions. Remove all legacy JARVIS code that doesn't match OpenClaw.

---

## OpenClaw Inventory

### Source code volume

| Path | Files | Purpose |
|---|---|---|
| `src/plugin-sdk` | 444 (non-test) | Public API surface plugins use |
| `src/plugins` | 424 | Plugin loader, registry, types, registrars |
| `src/agents` | 627 | Agent runtime, turn execution, tool calls |
| `src/gateway` | 374 | HTTP RPC, discovery, chat, cron integration |
| `src/cli` | 165 | Operator CLI surface |
| `src/memory-host-sdk` | 14 | Public memory API (host + plugins) |
| `src/llm` | 29 | LLM integration (providers live in extensions) |
| `src/channels` | 61 | Channel plugins (Telegram, Discord, etc.) |
| `src/cron` | 57 | Scheduling system |
| `src/memory` | 1 (root only) | Memory SDK root file |
| `src/tools` | 1 (types) | Tool types |
| **src total** | **11448** | Includes tests + everything |
| `extensions/` | 152 plugins | Per-feature implementations |
| `packages/` | 23 | Shared SDK packages |

### Key files already studied

- `src/plugin-sdk/plugin-entry.ts` (367 LOC) — public Plugin API surface
- `src/plugins/types.ts` (251 LOC) — PluginApi + PluginRecord + state types
- `src/plugins/registry.ts` (94 LOC) — `createPluginRegistry` factory
- `src/gateway/server.ts` (42 LOC) + `server.impl.ts` (2431 LOC) — main HTTP server
- `src/plugins/loader.ts` (14 LOC) — top-level loader entry

---

## JARVIS Current State (vs. OpenClaw target)

### ✅ Already at 100% OpenClaw parity (Phase 4.0–4.4)

- `extensions/memory_core/` — memory plugin (full OpenClaw parity, 5K LOC)
  - State CRUD (7 namespaces)
  - DREAMS.md persistence
  - Markdown phase blocks
  - Dream diary (narrative scaffold)
  - Repair + audit
  - Shadow trial
  - Phases (light/REM/deep scaffold)
  - /dreaming command
  - Short-term promotion + cron scaffold
  - Plugin entry wiring
  - 7-subcommand CLI
- `extensions/memory_wiki/` — 100% OpenClaw parity (Phase 4.3)
- `extensions/active_memory/` — 100% OpenClaw parity (Phase 4.2)
- `extensions/memory_lancedb/` — Phase 4.1
- `extensions/cron/` — 100% OpenClaw parity
- `extensions/telegram/` — 100% OpenClaw parity
- `packages/plugin_sdk/` (Python) — full OpenClaw SDK surface

### ⚠️ Partial / scaffold

- `src/memory` (JARVIS) — only `runtime.py`; needs full port
- `src/llm` (JARVIS) — only the `memory_embeddings` module
- `src/channels` (JARVIS) — missing
- `src/gateway` (JARVIS) — partial (only `server.py` basics)
- `src/agents` (JARVIS) — missing entirely
- `src/cli` (JARVIS) — has CLI app, but not the OpenClaw shape

### ❌ Missing entirely

- `src/agents/` — turn executor, tool runner, model call
- `src/gateway/server.impl.ts` equivalent — chat, RPC, discovery, cron
- `src/cli/` — operator surface (status, doctor, wizard, etc.)
- `src/memory-host-sdk/` — public memory SDK
- `src/memory/root-memory-files.ts` equivalent
- All 152 OpenClaw extensions (we only have 6)

---

## Port Strategy

The full port is 20000+ files and cannot be done in one session.
A **phased approach** is required. Each phase is a vertical slice
that brings a coherent chunk of OpenClaw's brain to JARVIS.

### Phase 5 — Brain Core (Plugin System + Agent Runtime + Gateway + CLI + Memory Host SDK)

**Estimated scope:** 30-50 OpenClaw files ported; ~3000-5000 LOC
**Goal:** JARVIS has the same plugin/agent/gateway/CLI surface as
OpenClaw, and the 6 existing extensions still work.

| Sub | Files | Description |
|---|---|---|
| 5.1 | `src/memory-host-sdk/*.ts` (14 files) | Public memory SDK for host + plugins |
| 5.2 | `src/memory/root-memory-files.ts` (1 file) | Memory SDK root file |
| 5.3 | `src/plugins/registry.ts` + state + types | Plugin registry core (replaces JARVIS plugin loader) |
| 5.4 | `src/plugins/loader.ts` | Top-level plugin loader |
| 5.5 | `src/plugins/registrars/*.ts` | Domain registrars (tools, channels, providers, etc.) |
| 5.6 | `src/agents/turn-executor.ts` | Turn execution engine |
| 5.7 | `src/agents/tool-runner.ts` | Tool call + result handling |
| 5.8 | `src/agents/model-caller.ts` | LLM call + streaming |
| 5.9 | `src/gateway/server.ts` + `server.impl.ts` | HTTP gateway (chat, RPC, discovery) |
| 5.10 | `src/cli/index.ts` | CLI surface (status, doctor, wizard, etc.) |
| 5.11 | integration tests | End-to-end: gateway + agent + tools + memory |
| 5.12 | verification | `docs/OPENCLAW_VERIFICATION_5.md` + `OPENCLAW_MIGRATION_PLAN.md` update |

### Phase 6 — Cron + Channels + LLM providers

**Estimated scope:** 60+ OpenClaw files
**Goal:** Cron scheduling, channel integration, and LLM provider
registry all match OpenClaw.

| Sub | Files | Description |
|---|---|---|
| 6.1 | `src/cron/*` (57 files) | Cron system — schedule, reconcile, notify |
| 6.2 | `src/channels/*` (61 files) | Channel framework (Telegram, Discord, etc.) |
| 6.3 | `src/llm/*` (29 files) | LLM integration + provider catalog |
| 6.4 | integration tests + verification | |

### Phase 7 — Memory plugin rewrites (using new memory-host-sdk)

**Goal:** The 6 existing extensions migrate to the new
memory-host-sdk surface (replacing the JARVIS-original surface).

| Sub | Files | Description |
|---|---|---|
| 7.1 | `extensions/memory_core/` migrate to new SDK | Use new `jarvis_sdk.memory_host_sdk` |
| 7.2 | `extensions/memory_lancedb/` migrate | Use new search manager surface |
| 7.3 | `extensions/memory_wiki/` migrate | Use new public_artifacts surface |
| 7.4 | `extensions/active_memory/` migrate | Use new short-term-recall surface |
| 7.5 | integration tests + verification | |

### Phase 8 — Provider extensions (Anthropic, OpenAI, etc.)

**Estimated scope:** 100+ extensions
**Goal:** Port the provider extensions (most are small — 50-300 LOC
each). Focus on the most-used: Anthropic, OpenAI, Gemini, etc.

| Sub | Files | Description |
|---|---|---|
| 8.1 | `extensions/anthropic/` | Anthropic provider |
| 8.2 | `extensions/openai/` | OpenAI provider |
| 8.3 | `extensions/google/` | Google provider |
| 8.4 | `extensions/ollama/` | Ollama provider |
| 8.5 | `extensions/mistral/`, `groq/`, `cohere/`, etc. | Other providers |
| 8.6 | integration tests + verification | |

### Phase 9 — Memory + search + media extensions

**Goal:** Port the memory and media extensions (the non-provider ones).

| Sub | Files | Description |
|---|---|---|
| 9.1 | `extensions/memory-qmd/` | QMD memory engine |
| 9.2 | `extensions/brave/`, `tavily/`, etc. | Search providers |
| 9.3 | `extensions/elevenlabs/`, `openai-tts/`, etc. | TTS providers |
| 9.4 | integration tests + verification | |

### Phase 10 — Cleanup

**Goal:** Remove all JARVIS-original code that doesn't match OpenClaw.
Verify parity end-to-end.

| Sub | Files | Description |
|---|---|---|
| 10.1 | Find + remove JARVIS-original code | Anything not in OpenClaw |
| 10.2 | Update all references | Use the new SDK surface |
| 10.3 | Final verification + audit | `docs/OPENCLAW_FULL_BRAIN_AUDIT.md` |

---

## Phase 5 Detailed Plan (immediate next phase)

### 5.1 — `src/memory-host-sdk/*.ts` (14 files)

**OpenClaw files:**
- `dreaming.ts` — already ported in 4.4 (status/health)
- `engine-qmd.ts` — QMD search engine
- `engine-storage.ts` — QMD storage
- `event-export.ts` — event log export
- `event-store.ts` — event log SQLite store
- `event-types.ts` — event types
- `events.ts` — event helpers
- `multimodal.ts` — multimodal content types
- `query.ts` — memory query helpers
- `secret.ts` — memory secret storage
- `status.ts` — memory status reporting

**JARVIS equivalents:** None. `extensions/memory_core/runtime.py` has
partial logic but doesn't match OpenClaw's memory-host-sdk.

**Estimated LOC:** ~1500-2000

### 5.2 — `src/memory/root-memory-files.ts` (1 file)

**Purpose:** Root memory file helpers (MEMORY.md, daily memory).
~50 LOC.

### 5.3 — `src/plugins/registry.ts` + state + types

**Purpose:** Replaces JARVIS's plugin loader with OpenClaw's
`createPluginRegistry` factory.
**Estimated LOC:** ~2000-3000

**Key types to port:**
- `OpenClawPluginApi` — the brain's API to plugins
- `PluginRecord` — per-plugin state
- `PluginRegistry` — the registry singleton
- `createPluginRegistry(params)` — factory

**Key registrars:**
- `registerTool`, `registerChannel`, `registerProvider`
- `registerCli`, `registerCommand`
- `registerMemoryCapability`
- `registerLifecycle`, `registerReload`
- etc. (per registry.ts)

### 5.4 — `src/plugins/loader.ts`

**Purpose:** Top-level plugin loader (reads manifest, instantiates
entries, calls `register()`).
**Estimated LOC:** ~500

### 5.5 — `src/plugins/registrars/*.ts`

**Purpose:** Domain registrars split out of registry.ts.
**Estimated LOC:** ~3000-4000

### 5.6 — `src/agents/turn-executor.ts`

**Purpose:** The brain's turn-execution engine. Reads prompt,
calls model, runs tools, emits events.
**Estimated LOC:** ~2000-3000

### 5.7 — `src/agents/tool-runner.ts`

**Purpose:** Tool call + result handling with middleware support.
**Estimated LOC:** ~1500-2000

### 5.8 — `src/agents/model-caller.ts`

**Purpose:** LLM call + streaming + retry + failover.
**Estimated LOC:** ~1500-2000

### 5.9 — `src/gateway/server.ts` + `server.impl.ts`

**Purpose:** HTTP gateway — chat, RPC, discovery, cron integration.
**Estimated LOC:** ~5000-7000

### 5.10 — `src/cli/index.ts`

**Purpose:** Operator CLI surface (status, doctor, wizard, etc.)
**Estimated LOC:** ~2000-3000

---

## Estimated Total Effort

| Phase | Sub | LOC | Sessions |
|---|---|---|---|
| 5 | 12 | 15-25K | 4-6 |
| 6 | 4 | 10-15K | 3-4 |
| 7 | 5 | 5-10K | 2-3 |
| 8 | 6 | 20-30K | 5-7 |
| 9 | 4 | 15-20K | 4-5 |
| 10 | 3 | 5-10K | 1-2 |
| **Total** | **34** | **70-110K** | **19-27** |

---

## Immediate Next Step: 5.1

Read `openclaw-main/src/memory-host-sdk/*.ts` in full, then port each
file to `packages/plugin_sdk/src/jarvis_sdk/memory_host_sdk.py`.

After 5.1, the memory-host-sdk surface is fully wired, the 6 existing
JARVIS extensions can migrate to it, and the gateway + agent layers
can use it.

---

## Architectural Decisions

1. **Python port of TS source** — every OpenClaw TS file is ported
   to a corresponding Python file in the same logical directory.
2. **snake_case at the function level**; **camelCase preserved at
   the JSON / data level** (matches OpenClaw's TS conventions).
3. **Pydantic v2 deferred** — `dataclasses.dataclass(frozen=True)`
   for SDK value types (per the prior Phase 4.x decision).
4. **Subprocess > in-process** — JARVIS's plugins run in-process
   for the operator surface, but the gateway can spawn sub-processes
   for chat/rpc per OpenClaw's design.
5. **Sync-first** — JARVIS's existing CLI + tool layer is sync.
   The agent runtime is async internally but exposes sync wrappers
   for CLI compatibility (per 4.4c/4.4d pattern).
6. **`uv` workspace** — every package has a `pyproject.toml`,
   matches the existing JARVIS layout.
7. **One PR = one topic**; **≤5K lines per PR** (per the JARVIS
   architect rule).

---

## Verification

After each sub-phase, run the OpenClaw↔JARVIS side-by-side comparison:
- Type-shape parity (TypedDict ↔ Python dataclass)
- Function signature parity
- Default values parity
- Error handling parity
- Docstring / comments preserve OpenClaw's intent

End of phase: a fresh `docs/OPENCLAW_VERIFICATION_<N>.md` + an
updated `OPENCLAW_MIGRATION_PLAN.md` entry.

---

## Risk / Scope Notes

- **MCP / streaming / WebSocket layers** — OpenClaw has deep
  WebSocket / streaming / ACP integration. The Python port will use
  the same wire protocol but the in-process runtime is simpler.
- **TS type guards** — `as Record<>`, `asPluginId` etc. need
  explicit Python `isinstance` checks.
- **TypeBox JSON schema** — OpenClaw uses `typebox` for tool
  parameter schemas. JARVIS uses `pydantic` for the same purpose
  (planned for Phase 11+).
- **`@openclaw/*` internal packages** — JARVIS will port these to
  Python as separate `jarvis_sdk` submodules (already partially done).

---

## Status

**Current:** Phase 4.4 (dreaming pipeline) port-complete. 13/13
sub-phases. 0 regressions introduced. See
`docs/OPENCLAW_VERIFICATION_4.4.md`.

**Next:** Phase 5.1 — memory-host-sdk port. Start by reading all 14
`src/memory-host-sdk/*.ts` files in full, then port each to
`packages/plugin_sdk/src/jarvis_sdk/memory_host_sdk.py`.
