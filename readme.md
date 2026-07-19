# JARVIS

> Personal AI assistant, OpenClaw architecture.
> Heritage: the MARK XXXIX series by FatihMakes (CC BY-NC 4.0) — see [Lineage](#lineage).

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Built with uv](https://img.shields.io/badge/built%20with-uv-purple.svg)](https://docs.astral.sh/uv/)

---

## What is JARVIS?

A personal AI assistant that runs on your machine, talks in real time,
remembers across sessions, controls your computer, and connects to
your messaging channels. PyQt6 HUD + headless gateway CLI, plugin
ecosystem, declarative skills, schema-versioned config, single-active
memory slot. Local execution; your data, your rules.

This is the OpenClaw-architecture port: a multi-package Python
workspace modeled on [OpenClaw](https://github.com/openclaw/openclaw),
adapted to Python idioms (uv workspace, ruff, pyright, pytest, hypothesis)
instead of TypeScript (pnpm, tsgo, oxlint, vitest).

---

## Quick start (after PR 0.4 lands)

```bash
# 1. Install uv (one-time)
#    Windows: winget install astral-sh.uv
#    macOS/Linux: curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Clone + sync
git clone <repo-url> jarvis
cd jarvis
uv sync

# 3. Launch the HUD
uv run python -m jarvis_desktop

# 4. Or use the CLI
uv run jarvis --help
```

> **Pre-migration:** JARVIS still runs from the root layout (the
> original `python main.py` works). After PR 0.4, the entry point
> becomes `uv run python -m jarvis_desktop`.

---

## Architecture (one-liner)

Multi-package Python workspace, plugin-SDK-bounded extensions,
schema-versioned SQLite, declarative skills, single-active memory slot.
**Extensions import only from `jarvis_sdk.*`** — the rule that
keeps the ecosystem safe.

```
jarvis/
├── apps/        user-facing (desktop, cli, tui)
├── packages/    reusable libraries (plugin_sdk, agent_runtime, llm_client, ...)
├── extensions/  plugin ecosystem (channels, providers, media, memory, tools, ...)
├── skills/      declarative SKILL.md (LLM picks from descriptions)
├── docs/        architecture, concepts, reference, security
├── test(s)/     cross-package tests
├── tools/       ci, scripts, git-hooks, codegen
├── security/    opengrep rulepack (Phase 6+)
├── qa/          scenario tests (Phase 6+)
├── deploy/      Dockerfile, fly.toml (Phase 5+)
├── examples/    runnable examples (Phase 5+)
└── .github/     CI, issue/PR templates, CODEOWNERS, labeler
```

See [`OPENCLAW_MIGRATION_PLAN.md`](OPENCLAW_MIGRATION_PLAN.md) for the
12-phase migration roadmap, [`AGENTS.md`](AGENTS.md) for the
architect rules, [`VISION.md`](VISION.md) for the project direction.

---

## Status

| Phase | Scope | Status |
|---|---|---|
| 0.1 | Governance docs (AGENTS/CLAUDE/VISION/CHANGELOG/LICENSE) | ✅ done |
| 0.2 | Build/test infra (pyproject, uv, ruff, pyright, pytest, pre-commit) | ✅ done |
| 0.3 | Empty tier directories + per-tier READMEs + .github/ | ✅ done |
| 0.4 | Move desktop to `apps/desktop/` + CLI skeleton | ⏳ next |
| 1.1 | `plugin_sdk` package (the contract) | ⏳ pending |
| 1.2 | `memory_host_sdk` + `memory_core` (first proof — SQLite + sqlite-vec + FTS5) | ⏳ pending |
| 1.3 | `extensions/tool_weather/` (second proof) | ⏳ pending |
| 2.x  | All 17 current tools → extensions | ⏳ pending |
| 3.x  | Skills system (10 essential skills) | ⏳ pending |
| 4.x  | More memory backends (lancedb, wiki) | ⏳ pending |
| 5.x  | Channel system (Telegram, Discord first) | ⏳ pending |
| 6.x  | LLM provider extensions (OpenAI, Anthropic, Google, OpenRouter) | ⏳ pending |
| 7.x  | Media (image/video/music/TTS/STT) | ⏳ pending |
| 8.x  | Doctor + migrations (config migrator) | ⏳ pending |
| 9.x  | More channels + provider coverage | ⏳ pending |
| 10.x | Cron, webhooks, ops surface | ⏳ pending |
| 11.x | Skills catalog completion (all 51) | ⏳ pending |
| 12.x | Optional polish (web UI, deploy, security rulepack) | ⏳ pending |

Total target: ~24,000 lines across 12+ phases.

---

## Why OpenClaw architecture?

The original JARVIS (MARK XXXIX-OR) was a monolith: 620-line `main.py`
hardcoded 17 tools, `actions/` modules imported each other
arbitrarily, memory was a single key/value store, no plugin system,
no schema versioning, no test infrastructure, no security tooling.

OpenClaw solves all of these:
- **Plugin SDK** — every extension imports only from `jarvis_sdk.*`,
  enforced by `tools/ci/check_imports.py`.
- **Schema versioning** — `state`, `agent`, `config`, `memory` versions
  live in `pyproject.toml`; bumps require explicit owner approval.
- **Storage** — SQLite only (no JSON sidecars for runtime state).
- **Skills** — declarative `SKILL.md` files; LLM picks from descriptions.
- **Single-active memory** — only one memory plugin loaded at a time.
- **Result type** — fallible operations return `Ok | Err`, not
  stringly-typed errors.
- **Channels** — `src/channels_core/` + extensions for Telegram,
  Discord, Slack, etc. Gateway protocol via JSON-RPC.

We copy **structure, not code**. The patterns transfer; the
TypeScript idioms translate to Python equivalents.

---

## Lineage

JARVIS descends from [MARK XXXIX-OR](https://youtu.be/ldvDNzwnM8k)
by [FatihMakes](https://www.youtube.com/@FatihMakes), a series
documenting the build of a real-time voice AI assistant with screen
awareness, file handling, and computer control. The original
implementation was a Python monolith under CC BY-NC 4.0.

This project picks up the codebase, keeps the user-visible behavior
(HUD, voice loop, 17 tools, memory, file drop, system metrics), and
rebuilds the architecture from the ground up using OpenClaw's
patterns. License has been upgraded from CC BY-NC 4.0 to **MIT** with
the goal of accepting external contributions.

If you came from the original MARK XXXIX series — thank you. The
migration preserves everything you used; the code just lives in new
places now.

---

## License

[MIT](LICENSE) — Copyright (c) 2026 JARVIS contributors.
Original MARK XXXIX-OR series © FatihMakes, used with permission
under the original CC BY-NC 4.0 license terms (see [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)
when it lands in Phase 5+).

---

## Contributing

Read [`AGENTS.md`](AGENTS.md) first. The architect rules are
non-negotiable. Per the per-phase PR template in
[`OPENCLAW_MIGRATION_PLAN.md`](OPENCLAW_MIGRATION_PLAN.md) §8:

- One PR = one topic
- ≤5,000 changed lines per PR
- No silent compat — if a config change invalidates existing files,
  add a matching `jarvis doctor --fix` migration
- Tests prove behavior, not branches
- All extensions import only from `jarvis_sdk.*`
- All `jarvis.plugin.json` files pass `tools/ci/check_manifests.py`

Open an issue first for anything beyond a small refactor.
