# active_memory Plugin Guide

Read this before any change under `extensions/active_memory/`.
These are intentional maintainer decisions. Also read
`extensions/AGENTS.md` for the plugin boundary rules.

## Scope

- **Phase 4.2a (shipped).** Foundation: types, config,
  recall-state (cache + circuit breaker), session-policy
  (eligibility, harness skip, chat-type resolution, allow/
  deny lists, session toggle store, admin gating).
- **Phase 4.2b (target).** Recall flow: `recall.ts` +
  `recall-run.ts` + `query.ts` + `prompt.ts` + `session.ts`
  + `transcript*.ts`. The "blocking memory sub-agent" is
  the heaviest piece — OpenClaw spawns a separate CLI
  process via `api.runtime.agent.resolveCliBackendDispatchEligibility`.
- **Phase 4.2c (target).** Entry + slash command + doctor:
  `index.ts` + `doctor-contract-api.ts`. Wires the
  foundation into the host's `before_prompt_build` hook
  bus.

## Reliability Invariants

- **One plugin per process.** `api.register_memory_capability`
  is single-active-slot; the recall flow uses the *active*
  memory slot, not a separate capability.
- **Process-wide state.** The recall cache and circuit
  breaker are module-level (per-process) singletons.
  Tests reset them via `reset_active_recall_state_for_tests`.
- **TTL-based cache eviction.** The cache sweeps expired
  entries on every Nth write and caps at
  `DEFAULT_MAX_CACHE_ENTRIES` (1000). Bounded LRU-ish
  without an explicit access-recency map.
- **Per-agent/model circuit breaker.** Opens after
  `circuitBreakerMaxTimeouts` consecutive timeouts; resets
  after `circuitBreakerCooldownMs`; one attempt is
  allowed through after the cooldown expires.
- **Recall is optional.** When the host can't read the
  session row, the harness-skip check returns `True`
  (skip recall). Crossing a harness/model boundary with an
  independently selected model is unsafe.

## Security Invariants

- **No prompt-injection amplification.** `looksLikeEnvelopeSludge`
  / `looksLikePromptInjection` (re-used from `memory_core`)
  must be consulted before any recall result is rendered
  into the system prompt (Phase 4.2c).
- **No envelope sludge in prompt prefix.** The
  `buildPromptPrefix` helper wraps the summary in an
  `<active_memory_plugin>` tag so the answering model
  can identify the source AND a future active_memory call
  can strip it before re-feeding history.
- **Per-session disable.** `setSessionActiveMemoryDisabled`
  writes to a keyed store; the absence of an entry is the
  "enabled" default (matches OpenClaw).
- **Admin gating.** `lacksAdminToMutateActiveMemoryGlobal`
  refuses the `--global` slash command unless the caller
  holds `operator.admin` scope (gateway) or is the operator
  (local).
- **No path traversal.** `resolveSafeTranscriptDir` refuses
  absolute paths, paths containing `:`, and paths that
  escape the base sessions dir (uses `isPathInside`).

## Context And Authorization

- **Per-agent enable.** `isEnabledForAgent(config, agentId)`
  returns `True` only when the operator pinned the
  `config.agents` list to include `agentId`. An empty
  list means "all agents" (matches OpenClaw).
- **Per-agent `Remember across conversations`.** Read via
  `resolveRememberAcrossConversations` (Phase 4.0 SDK).
  Active_memory treats this as a per-agent capability, not
  a plugin config — the host tracks it.
- **Dreaming-narrative sessions are skipped.** The
  eligibility helper blocks session keys shaped like
  `dreaming-narrative-{light,rem,deep}-...` so the recall
  sub-agent never runs during a dreaming pass.

## Review Standard

- New config keys need a `uiHints` entry in the manifest
  AND a default in `config.py`. Phase 4.2a ships the
  full OpenClaw parity surface; new keys in subsequent
  phases need the same dual update.
- New chat types (e.g. a new IM channel) need both a
  `ActiveMemoryChatType` literal AND a `resolveChatType`
  regex update.
- The `isPathInside` helper must be used for any
  filesystem boundary the plugin introduces (transcript
  dir, log file, etc.). Don't roll your own.

## Dependencies

- Stdlib only (Phase 4.2a).
- Phase 4.2b will add `httpx` for the embedded-run
  dispatch (OpenClaw spawns a CLI process for the recall
  sub-agent).
- The `lancedb` and `memory_core` extensions are NOT
  dependencies — active_memory is a *consumer* of whichever
  memory plugin owns the slot.
