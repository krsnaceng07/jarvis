# OpenAI Provider Extension (JARVIS)

Minimum scaffold matching the OpenClaw `extensions/openai/`
shape. The OpenClaw source is 85 files; this Python port
ships a focused subset.

## Parity status (vs `openclaw-main/extensions/openai/`)

| OpenClaw | JARVIS | Notes |
|---|---|---|
| `index.ts` (entrypoint) | `__init__.py` + `plugin.py` | stub entry |
| `ProviderPlugin` descriptor | `OpenAIProvider` dataclass | shape equivalent |
| `provider-policy-api.ts` (route core) + `base-url.ts` + route membership | `route_policy.py` | ported; stdlib-only cold artifact consumed by `src/agents/openai_model_routes.py` |
| Streaming client | deferred | Phase 5.16 |
| Tool-use adapter | deferred | Phase 5.16 |
| Multi-account surface | deferred | Phase 5.16 |
| Image input adapter | deferred | Phase 5.16 |
| Reasoning / o-series | deferred | Phase 5.16 |
| Audio + Realtime | deferred | Phase 5.16 |

## Route-policy ownership

`route_policy.py` is provider-owned policy (auth/catalog/runtime hooks stay
with the owner; core owns the generic loop). Core calls it only through
`src/agents/openai_model_routes.py`. Do not move route facts into core;
if a second provider needs the merged-model/override helpers, extract one
shared helper and migrate both call sites in the same change.

## Thinking-policy ownership

`thinking_policy.py` is the provider-owned thinking surface
(`thinking-policy.ts`: unified + Codex profiles, reasoning-effort table).
Core reaches it only through `src/plugins/provider_thinking.py`
(`resolveThinkingProfile` surface, lazy import — same pattern as the route
cold path). The host default (`resolve_host_thinking_policy`) feeds
`api.runtime.agent.resolve_thinking_policy` (llm-task validation).

The minimum-scaffold is loadable + discoverable; the full
streaming + tool-use surface lands in Phase 5.16.
