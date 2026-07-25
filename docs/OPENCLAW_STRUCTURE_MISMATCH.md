# OpenClaw Structure Mismatch — JARVIS Brain Port Review

**Date:** 2026-07-25
**Reviewer:** JARVIS architect (user)
**Verdict:** Structural mismatch between JARVIS's `packages/plugin_sdk/` and OpenClaw's package layout. **Refactor required** before continuing brain port.

---

## 1. OpenClaw layout (the target)

### 1a. `packages/` (24 SDK packages)

| Package | Role | Why separate |
|---|---|---|
| `agent-core` | the brain loop (5119 LOC, no OpenClaw imports) | Pure, headless-testable |
| `llm-core` | LLM types + validation (683 + 375 LOC) | Wire contract, used by every provider |
| `memory-host-sdk` | Public memory API for host + plugins | OpenClaw's Phase 5.1 — already 100% ported |
| `normalization-core` | Shared string / result / utf16-slice utilities | Used across all packages |
| `retry` | `retryAsync` helper | Used by all I/O paths |
| `plugin-sdk` | Public Plugin API (444 files) | What plugins import |
| `plugin-package-contract` | Plugin packaging manifest contract | |
| `model-catalog-core` | Catalog types | |
| `media-core`, `media-generation-core`, `media-understanding-common` | Media framework | |
| `speech-core`, `markdown-core`, `terminal-core` | Domain cores | |
| `web-content-core`, `tool-call-repair`, `net-policy` | Domain cores | |
| `acp-core`, `gateway-client`, `gateway-protocol` | Wire protocols | |
| `workboard-contract`, `media-understanding-common` | Contracts | |
| `sdk`, `ai` | Higher-level meta-packages | |

### 1b. `src/` (~80 sub-systems, runtime)

| Directory | Role | Notes |
|---|---|---|
| `plugins/` (424 files) | Plugin loader, registry, registrars, lifecycle | Includes `registry.ts`, `registrars/*.ts` |
| `agents/` (627 files) | AgentSession family, runner, harness | `agent-command.ts`, `embedded-agent-runner/` |
| `gateway/` (374 files) | HTTP RPC, discovery, chat, cron | `server.ts` + `server.impl.ts` |
| `cli/` (165 files) | Operator CLI | |
| `channels/` (61 files) | Channel framework | |
| `cron/` (57 files) | Cron scheduling | |
| `context-engine/` (~2.2K) | Context engine | |
| `routing/` (~1.4K) | Tiered route resolution | |
| `sessions/`, `sessions-store/` | Session persistence | |
| `llm/` (29 files) | LLM facade (providers live in extensions) | |
| `memory/`, `memory-host-sdk/` | Memory SDK | |
| `plugin-sdk/` | Plugin SDK (separate from `packages/plugin-sdk/`) | |
| `plugin-state/`, `plugin-runtime/` | Plugin state + runtime | |
| `provider-runtime/` | Provider runtime | |
| `tools/`, `hooks/`, `secrets/`, `config/`, `cli/`, `commands/`, `chat/`, `media/`, `tts/`, `image-generation/`, `video-generation/`, `music-generation/`, `web-search/`, `web-fetch/`, `realtime-transcription/`, `transcripts/`, `trajectory/`, `skills/`, `wizard/`, `worker/`, `daemon/`, `audit/`, `bindings/`, `commitments/`, `compat/`, `flows/`, `interactive/`, `link-understanding/`, `meeting-bot/`, `mcp/`, `model-catalog/`, `node-host/`, `pairing/`, `process/`, `proxy-capture/`, `security/`, `shared/`, `snapshot/`, `state/`, `status/`, `system-agent/`, `talk/`, `tasks/`, `tui/`, `types/`, `utils/` | All the rest |

---

## 2. JARVIS layout today (the current state)

### 2a. `packages/` (3 packages)

| Package | State |
|---|---|
| `agent_runtime/` | exists but empty (no `src/`) |
| `llm_client/` | exists but empty (no `src/`) |
| `plugin_sdk/` | **the dumping ground** — 80+ modules, all in `src/jarvis_sdk/` |

### 2b. `src/` (7 sub-systems)

`bootstrap/`, `cron/`, `doctor/`, `frontmatter/`, `gateway/`, `hooks/`, `skills/`

### 2c. `apps/` (3 apps)

`cli/`, `desktop/`, `tui/`

### 2d. Inside `packages/plugin_sdk/src/jarvis_sdk/` (80+ modules in one flat namespace)

| Group | Files | OpenClaw home |
|---|---|---|
| Memory host SDK | 34 `memory_host_*.py` modules | `packages/memory-host-sdk/src/` |
| Plugin registry | 7 `plugin_registry_*.py` modules | `src/plugins/` |
| Plugin SDK | `api.py`, `plugin_config.py`, `manifest.py`, `context.py`, `entry.py`, `contract.py`, `command.py`, `cli.py`, `hook.py`, `skill.py`, `chat_channel_ids.py`, `message_tool_delivery_hints.py`, `plugin_state*.py` | `packages/plugin-sdk/` + `src/plugin-sdk/` |
| LLM | `agent_runtime.py`, `memory_embeddings.py`, `expect_runtime.py`, `lazy_runtime.py`, `number_runtime.py`, `runtime_env.py` | `packages/llm-core/` + `src/llm/` + `packages/agent-core/src/` |
| Routing | `routing.py` | `src/routing/` |
| Cron | `cron.py` | `src/cron/` |
| Retry | `retry_runtime.py` | `packages/retry/` |
| Normalization | `string_coerce.py`, `text_utility.py`, `result.py`, `json_store.py` | `packages/normalization-core/src/` |
| Security | `security_runtime.py` | `src/security/` |
| Session | `session_transcript_runtime.py` | `src/sessions/` |
| Memory | `memory_runtime.py`, `memory_storage.py` | `src/memory/` |

---

## 3. Mismatch summary

| Aspect | OpenClaw | JARVIS today | Verdict |
|---|---|---|---|
| Number of packages | 24 | 3 (1 active) | **MISMATCH** |
| `packages/plugin-sdk/` scope | public Plugin API only | everything | **MISMATCH** |
| Memory host SDK location | `packages/memory-host-sdk/` | `packages/plugin_sdk/src/jarvis_sdk/memory_host_*.py` | **MISMATCH** |
| LLM core location | `packages/llm-core/` | not ported (the only `llm_client/` is empty) | **MISSING** |
| Agent core location | `packages/agent-core/src/` | not ported (the only `agent_runtime/` is empty) | **MISSING** |
| Retry location | `packages/retry/` | `plugin_sdk/src/jarvis_sdk/retry_runtime.py` | **MISMATCH** |
| Normalization core location | `packages/normalization-core/` | `plugin_sdk/src/jarvis_sdk/{string_coerce,text_utility,result}.py` | **MISMATCH** |
| Routing location | `src/routing/` | `plugin_sdk/src/jarvis_sdk/routing.py` | **MISMATCH** |
| Cron location | `src/cron/` | both `src/cron/` AND `plugin_sdk/src/jarvis_sdk/cron.py` | **DUPLICATE** |
| Plugin registry location | `src/plugins/` | `plugin_sdk/src/jarvis_sdk/plugin_registry_*.py` | **MISMATCH** |

**Root cause:** The 5.1–5.6 phases ported everything into the existing `packages/plugin_sdk/` instead of creating new OpenClaw-shaped packages. Phase 4.x's `plugin_sdk` predated the brain port and was used as a convenient "home" rather than the architecturally correct one.

---

## 4. Refactor plan

The correct JARVIS structure (matching OpenClaw exactly):

```
E:\jarvis\
├── apps\
│   ├── cli\
│   ├── desktop\
│   └── tui\
├── src\
│   ├── agents\          (NEW — port 5.7+ lives here)
│   ├── channels\        (NEW — port Phase 6.2)
│   ├── cli\             (NEW — port Phase 5.19)
│   ├── context-engine\  (NEW — port Phase 5.12)
│   ├── cron\            (exists, keep)
│   ├── gateway\         (exists, port Phase 5.16)
│   ├── llm\             (NEW — port Phase 5.7)
│   ├── memory\          (NEW — port Phase 5.7+)
│   ├── plugins\         (NEW — port Phase 5.6)
│   ├── routing\         (NEW — port Phase 5.13)
│   ├── security\        (NEW — extract from plugin_sdk)
│   ├── sessions\        (NEW — port Phase 5.14)
│   ├── context-engine\  (NEW — port Phase 5.12)
│   ├── hooks\           (exists)
│   └── ... (other OpenClaw src dirs)
└── packages\
    ├── agent-core\                  (NEW — Phase 5.8–5.11, the brain)
    ├── llm-core\                    (NEW — Phase 5.7)
    ├── memory-host-sdk\             (move from plugin_sdk — 34 modules)
    ├── normalization-core\          (NEW — extract string_coerce/text_utility/result/json_store)
    ├── plugin-sdk\                  (KEEP — public Plugin API)
    ├── plugin-package-contract\     (NEW — manifest contracts)
    ├── retry\                       (NEW — extract retry_runtime)
    ├── model-catalog-core\          (NEW — Phase 5.7+)
    ├── media-core\                  (NEW — Phase 5.7+)
    ├── speech-core\                 (NEW — Phase 5.7+)
    ├── ...                          (port as needed per phase)
    └── plugin_sdk\                  (DELETE after migration — content moves to packages above)
```

### 4a. Module-to-package mapping

| Current `packages/plugin_sdk/src/jarvis_sdk/` module | New location |
|---|---|
| `memory_host_*.py` (34 modules) | `packages/memory_host_sdk/src/jarvis_memory_host_sdk/` |
| `plugin_registry_*.py` (7) | `src/plugins/` (re-organize into `jarvis_plugins/`) |
| `agent_runtime.py`, `memory_embeddings.py`, `expect_runtime.py`, `lazy_runtime.py`, `number_runtime.py`, `runtime_env.py` | `packages/llm_client/src/jarvis_llm_client/` (existing empty package) |
| `routing.py` | `src/routing/` (NEW directory) |
| `cron.py` | `src/cron/` (existing — keep one canonical) |
| `retry_runtime.py` | `packages/retry/src/jarvis_retry/` (NEW package) |
| `string_coerce.py`, `text_utility.py`, `result.py`, `json_store.py` | `packages/normalization_core/src/jarvis_normalization_core/` (NEW package) |
| `security_runtime.py` | `src/security/` (NEW) |
| `session_transcript_runtime.py` | `src/sessions/` (NEW) |
| `memory_runtime.py`, `memory_storage.py` | `src/memory/` (NEW) |
| `api.py`, `plugin_config.py`, `manifest.py`, `context.py`, `entry.py`, `contract.py`, `command.py`, `cli.py`, `hook.py`, `skill.py`, `chat_channel_ids.py`, `message_tool_delivery_hints.py`, `plugin_state*.py` | KEEP in `packages/plugin_sdk/src/jarvis_sdk/` (these are the public Plugin SDK surface) |

### 4b. Refactor steps (incremental, each ≤5K LOC per PR)

1. **Step 1 (no behavior change):** Create the new package directories with `pyproject.toml`s; re-export the old `jarvis_sdk.*` modules from the new locations; keep all imports working. ~1 PR.
2. **Step 2 (move + delete old):** Physically move the modules to their new homes; update `packages/plugin_sdk/pyproject.toml` to remove the moved modules; verify tests still pass. ~1-2 PRs.
3. **Step 3 (per OpenClaw):** Continue with the V2 plan (Phase 5.7+) into the correctly-shaped packages.

### 4c. Risk

- ~80 import statements need to be updated across the codebase (extensions, apps, etc.) when modules move.
- The `extensions/memory_core/` and `extensions/memory_lancedb/` extensions import many of the `memory_host_*` modules. They will need updated imports after the move.
- Pre-commit hooks (check-imports) will catch any missed references; the move is safe to land incrementally.

---

## 5. Decision

The refactor is **mandatory** before Phase 5.7+ — the V2 plan explicitly says the brain lives in `packages/agent-core/`, the LLM contracts in `packages/llm-core/`, the routing in `src/routing/`, etc. Porting the brain into `packages/plugin_sdk/` would violate OpenClaw's architecture.

**Recommendation:** approve the refactor (Step 1 + Step 2) before resuming Phase 5.
