# JARVIS packages

Core libraries. Each package is a workspace member with its own `pyproject.toml` and
a stable, narrow API surface.

Mirrors OpenClaw's `packages/` (23 core packages). JARVIS targets all 23, condensed
where it makes sense.

## Layout

| Package | Purpose | Phase |
|---|---|---|
| `plugin_sdk/` | **The contract.** Plugins import only from here. | 1 |
| `agent_runtime/` | Agent loop, executor, planner, task queue. | 1 |
| `llm_client/` | Generic LLM client (provider-agnostic). | 6 |
| `memory_host_sdk/` | Memory host interface. | 4 |
| `channels_core/` | Channel transport contracts (inbound/outbound/routing). | 5 |
| `gateway_protocol/` | JSON-RPC schema for gateway ↔ clients. | 5 |
| `config_core/` | Config schema helpers, schema-version aware. | 1 |
| `cron_core/` | Cron expression evaluator, scheduled tasks. | 10 |
| `hooks_core/` | Plugin hook system. | 1 |
| `logging_core/` | Structured logging. | 1 |
| `secrets_core/` | Secret resolution. | 1 |
| `events_core/` | Event bus. | 1 |
| `i18n_core/` | Translation scaffolding. | 6 |
| `audio_core/` | Audio capture / playback. | 1 |
| `live_session/` | Real-time voice session (Gemini Live + future). | 1 |
| `retry_core/` | Retry / backoff policies. | 1 |
| `net_policy/` | SSRF, allowlist, fetch policy. | 1 |
| `normalization/` | Result type, discriminated unions, error mapping. | 1 |
| `transcript_core/` | Session transcript persistence. | 1 |
| `session_core/` | Session lifecycle, keys, ownership. | 1 |
| `media_core/` | Media understanding contracts. | 7 |
| `markdown_core/` | Markdown rendering / safety. | 1 |
| `workboard_contract/` | Workboard / kanban integration contract. | 1 |
| `tool_call_repair/` | Tool-call repair heuristics. | 1 |

## Rules

- Each package has its own `pyproject.toml` and tests colocated.
- Plugins (extensions) may import **only from `plugin_sdk`**. All other packages
  are private to the host and to apps.
- Apps (desktop, CLI) may import any package.
- No circular imports between packages (enforced by `tools/ci/check_cycles.py`).
- No package depends on an extension.
