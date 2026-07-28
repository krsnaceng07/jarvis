# GitHub Copilot 2 Provider Extension (JARVIS)

Minimum scaffold matching the OpenClaw `extensions/github-copilot-2/`
shape. The OpenClaw source is 33 files; this
Python port ships a focused subset.

## Parity status (vs `openclaw-main/extensions/github-copilot-2/`)

| OpenClaw | JARVIS | Notes |
|---|---|---|
| `index.ts` (entrypoint) | `__init__.py` + `plugin.py` | stub entry |
| `ProviderPlugin` descriptor | `GitHubCopilot2Provider` dataclass | shape equivalent |
| Streaming client | deferred | Phase 5.16 |
| Model catalog | `default_model` + `list_models()` stub | Phase 5.16 |

## Auth

API key: `GITHUB_COPILOT_2_KEY` (read at provider init time).

## Base URL

`https://api.githubcopilot.com/v1` (OpenAI-compatible).

The minimum-scaffold is loadable + discoverable; the full
streaming + tool-use surface lands in Phase 5.16.
