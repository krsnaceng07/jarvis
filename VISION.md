# JARVIS Vision

JARVIS is the AI that actually does things. It runs on your devices, in your channels, with your rules.

This document explains the current state and direction of the project. We are still early, so iteration is fast.

Project overview and developer docs: [`README.md`](README.md)
Architect rules: [`AGENTS.md`](AGENTS.md)
Migration plan (from old flat layout to OpenClaw architecture): [`OPENCLAW_MIGRATION_PLAN.md`](OPENCLAW_MIGRATION_PLAN.md)
Contribution guide: [`CONTRIBUTING.md`](CONTRIBUTING.md)

## Origin

JARVIS started as a personal playground to learn AI and build something genuinely useful: an assistant that can run real tasks on a real computer. It evolved through several names and shells — Mark I through Mark XXXIX (39) — and was always tightly focused on the **desktop voice-assistant** use case: real-time Gemini Live mic-in, speaker-out, hardcoded Python tool dispatch, PyQt6 HUD.

The 2026.7 release marks a turning point. JARVIS adopts the **OpenClaw architecture**: a multi-package Python workspace with extensions, declarative skills, schema versioning, and a strict plugin contract. JARVIS keeps its iconic desktop HUD and real-time voice loop, but the foundation underneath becomes the same battle-tested architecture that powers OpenClaw (the AI gateway by the same name).

The goal: a personal assistant that is easy to use, supports a wide range of platforms, and respects privacy and security.

## Current focus

**Priority:**

- Migration to OpenClaw architecture (12 phases, see [`OPENCLAW_MIGRATION_PLAN.md`](OPENCLAW_MIGRATION_PLAN.md))
- Security and safe defaults
- Bug fixes and stability
- Setup reliability and first-run UX

**Next priorities:**

- Supporting all major model providers (OpenAI, Anthropic, Google Gemini, OpenRouter, Ollama)
- Multi-channel: Telegram, Discord, Slack, WhatsApp, Signal, Matrix, Feishu, Microsoft Teams
- Performance and test infrastructure
- Better agent harness capabilities (process isolation, ACP, harness plugins)
- Ergonomics across CLI and web frontend
- Companion apps on macOS, iOS, Android, Windows, and Linux

## Architecture principles (summary)

The full rules live in [`AGENTS.md`](AGENTS.md). The non-negotiables:

1. **Core stays plugin-agnostic.** No bundled ids/defaults/policy in core when manifest/registry/capability contracts work.
2. **Plugins cross into core only via `jarvis_sdk.*`.** No extension imports from another extension, from `packages/*` (except `plugin_sdk`), or from anywhere else outside itself.
3. **Schema versioning is mandatory.** State, agent, config, and memory each have a version; bumps need explicit architect approval.
4. **Storage is SQLite only.** No JSON/JSONL/TXT sidecar files for runtime state.
5. **Skills are declarative markdown.** No Python code in `skills/<id>/`, just `SKILL.md` with YAML frontmatter.
6. **One PR = one topic.** ≤5K changed lines per PR. Bounded behavior-neutral refactors don't need full gates.
7. **Lean code wins.** No shims, aliases, or fallback paths just to reduce diff. Delete before adding.
8. **Doctor owns migrations.** Runtime assumes canonical shape; only `jarvis doctor --fix` translates legacy data.

## Configuration compatibility

JARVIS runtime code reads the current configuration schema only. We do not keep long-lived aliases or compatibility branches that silently accept old, renamed, or malformed config keys.

When a config change makes existing user config invalid, the same change needs a doctor migration.

`jarvis doctor --fix` should detect the old shape, explain it, back it up when needed, and rewrite it to the canonical format. Core-owned config and auth state are repaired in core doctor code; plugin-owned config is repaired by that plugin's doctor contract.

## Security

Security in JARVIS is a deliberate tradeoff: strong defaults without killing capability. The goal is to stay powerful for real work while making risky paths explicit and operator-controlled.

Canonical security policy and reporting:

- [`SECURITY.md`](SECURITY.md) (Phase 6)
- `security/opengrep/` rulepack (Phase 12)

We prioritize secure defaults, but also expose clear knobs for trusted high-power workflows.

## Plugins & Memory

JARVIS has a plugin API. Core stays lean; optional capabilities should usually ship as plugins. We are generally slimming down core while expanding what plugins can do.

There are two broad plugin styles:

- **Code plugins** run JARVIS plugin code and are appropriate for deeper runtime extension (custom tool, custom channel, custom provider).
- **Bundle-style plugins** package stable external surfaces such as skills, MCP servers, and related configuration.

Prefer bundle-style plugins when they can express the capability. They have a smaller, more stable interface and better security boundaries. Use code plugins when the capability needs runtime hooks, providers, channels, tools, or other in-process extension points.

Preferred plugin path is `pip`/`uv` package distribution plus local extension loading for development. If you build a plugin, host and maintain it in your own repository. The bar for adding optional plugins to core is intentionally high.

Plugin discovery, official publisher status, provenance, and security review will live in **JARVIS Hub** (TBD, Phase 12). JARVIS docs should document core extension points; plugin promotion belongs in JARVIS Hub, preferably under vetted org publishers for official plugins.

Memory is a special plugin slot where only one memory plugin can be active at a time. Today we ship two memory options (`memory_core` for SQLite, `memory_lancedb` for vector-first). Over time we plan to converge on one recommended default path.

### Skills

We ship skills for baseline UX. New skills should be published as `SKILL.md` files in the `skills/` tree. Each skill is a single markdown file with YAML frontmatter — no code, just the description, when to use it, and how to invoke it. The LLM picks the right skill from the frontmatter description; the runtime executes the tool calls the skill describes.

Official or bundled promotion should require a clear product, security, or maintainer-ownership reason.

### MCP Support

JARVIS supports MCP as both a server and a runtime integration surface. MCP details will live in `docs/cli/mcp.md` (Phase 6).

The project goal is pragmatic MCP support without duplicating existing agent, tool, plugin, or JARVIS Hub paths.

## Contribution rules (one-liner)

One PR = one issue/topic. PRs over ~5,000 changed lines are reviewed only in exceptional circumstances. Do not open large batches of tiny PRs at once; each PR has review cost. For very small related fixes, grouping into one focused PR is encouraged.

---

JARVIS is a labor of love by a developer building a real-world personal AI assistant. The migration to OpenClaw architecture is the foundation for everything that comes next. Welcome aboard.
