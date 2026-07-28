# Anthropic Provider Extension (JARVIS)

Minimum scaffold matching the OpenClaw `extensions/anthropic/`
shape. The OpenClaw source is 50 files; this Python port
ships a focused subset:

- `openclaw.plugin.json` — manifest with `kind: provider` +
  `contracts.provider: true` + config schema for
  `api_key` + `default_model` + `max_output_tokens`.
- `pyproject.toml` — `jarvis-anthropic` workspace member.
- `__init__.py` — public re-exports.
- `plugin.py` — `AnthropicProvider(ProviderPlugin)`
  descriptor with id, name, default_model, max_output_tokens.

## Parity status (vs `openclaw-main/extensions/anthropic/`)

| OpenClaw | JARVIS | Notes |
|---|---|---|
| `index.ts` (entrypoint) | `__init__.py` + `plugin.py` | stub entry |
| `ProviderPlugin` descriptor | `AnthropicProvider` dataclass | shape equivalent |
| Streaming client | deferred | Phase 5.16 |
| Tool-use adapter | deferred | Phase 5.16 |
| Multi-account surface | deferred | Phase 5.16 |
| Image input adapter | deferred | Phase 5.16 |
| Vertex routing | deferred | Phase 5.16 |

The minimum-scaffold is loadable + discoverable; the full
streaming + tool-use surface lands in Phase 5.16.
