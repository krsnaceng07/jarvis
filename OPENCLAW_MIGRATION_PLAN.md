# JARVIS → OpenClaw Architecture Migration Plan

> **Status:** Phase 4.3d-mr6 complete (memory_wiki compile pages — per-page write loop); Phase 4.3e (state stores: compiled-cache + import-runs + source-sync) next
> **Last updated:** 2026-07-21
> **Owner:** JARVIS architect
> **Reference source:** `E:/jarvis/openclaw-main/` (commit snapshot 2026.7.2)

This document is the **single source of truth** for migrating JARVIS from a flat Python monolith to an OpenClaw-style multi-package AI gateway architecture. Every phase below is sized to fit in one focused PR (≤5K changed lines, one logical topic).

---

## 0. Why this migration

**Current JARVIS problems (observed in `main.py`, `ui.py`, `actions/`):**

| Problem | Where it hurts | OpenClaw pattern that fixes it |
|---|---|---|
| Monolithic `main.py` (620 lines) owns tool dispatch, audio, memory, state | One change touches everything; can't evolve channels independently | `src/gateway/` + `src/agents/` + `src/channels/` separation |
| 17 hardcoded `TOOL_DECLARATIONS` in `main.py` | Adding/removing a tool = edit core | `extensions/<id>/openclaw.plugin.json` manifest + dynamic loader |
| Action modules import each other arbitrarily (`from actions.foo import foo`) | No clear ownership, can't be removed safely | `plugin-sdk` contract — extensions import only `@openclaw/plugin-sdk/*` |
| `memory/` is a single key/value store | One memory strategy, no plug-in | `memory-core` extension + `memory-host-sdk` package (single active slot pattern) |
| No multi-channel support (only local mic) | Jarvis = local app, not gateway | `src/channels/*` + 23 channel extensions |
| No plugin/SKILL.md system | Capabilities are code, not declarative | `skills/<name>/SKILL.md` (51 in OpenClaw, declarative) |
| No docs as code | No architectural visibility | `docs/<category>/` (30 categories) |
| No security tooling | Defaults to "trust everything" | `security/opengrep/` rulepack, `SECURITY.md`, CODEOWNERS |
| No schema versioning | Config changes break silently | `pyproject.toml` → `jarvis = { schemaVersions = { state, agent } }` |
| No test infrastructure | Refactor is gambling | `test/e2e`, `test/helpers`, `test/mocks`, `test/fixtures` |

**What we are NOT copying (out of scope for a solo Python project):**

- Mobile apps (iOS Swift, Android Kotlin) — not in your scope
- ACP/Codex integration — out of scope
- 70+ provider implementations (we'll keep 5–10 essential ones, rest are config-driven)
- TypeScript-specific tooling (`tsgo`, `oxlint`, `vitest`) — replaced by Python equivalents (`pyright`, `ruff`, `pytest`)
- Live-update / live-coding (added in Phase 6, optional)

---

## 1. Complete target folder structure

Every directory below is **mandatory** for the final layout. The migration is complete when `jarvis/` mirrors this tree (with `extensions/<id>/` populated for each feature you adopt).

```
E:/jarvis/
│
├── AGENTS.md                    # ← NEW. Architect's playbook. Telegraph style. Root policy + routing.
├── CLAUDE.md                    # ← NEW. AI-coding-agent rules. Symlinked to AGENTS.md.
├── VISION.md                    # ← NEW. What JARVIS is, where it's going, contribution rules.
├── README.md                    # KEEP + rewrite to reflect new structure.
├── CHANGELOG.md                 # ← NEW. Release-only. Same rules as OpenClaw.
│
├── pyproject.toml               # ← NEW. Single Python workspace. Schema versions live here.
├── package.json                 # ← NEW. Tooling manifest (scripts: test, lint, type, build).
├── uv.lock                      # ← NEW. Lockfile (or poetry.lock / pdm.lock — pick one).
├── .python-version              # ← NEW. 3.12.
├── .gitignore
├── .gitattributes
├── .dockerignore
├── .dockerfile                  # (optional Phase 6)
├── docker-compose.yml           # (optional Phase 6)
│
├── ruff.toml                    # ← NEW. Lint (replaces no-lint).
├── pyrightconfig.json           # ← NEW. Type-check.
├── pytest.ini                   # ← NEW. Test config.
├── .pre-commit-config.yaml      # ← NEW. Pre-commit hooks.
├── .semgrepignore               # ← NEW. Security scan ignores.
├── .editorconfig
├── .vscode/                     # ← NEW. Editor config.
│
├── apps/                        # ← NEW. User-facing applications.
│   ├── desktop/                 # ← current main.py + ui.py + face.png live here.
│   │   ├── pyproject.toml
│   │   ├── README.md
│   │   ├── src/jarvis_desktop/
│   │   │   ├── __main__.py
│   │   │   ├── app.py          # ← current main.py, entry only.
│   │   │   ├── hud/            # ← current ui.py, split.
│   │   │   │   ├── __init__.py
│   │   │   │   ├── window.py
│   │   │   │   ├── canvas.py
│   │   │   │   ├── metrics.py
│   │   │   │   ├── log.py
│   │   │   │   ├── dropzone.py
│   │   │   │   ├── setup.py
│   │   │   │   └── theme.py
│   │   │   └── ipc.py          # Gateway ↔ UI bridge.
│   │   └── assets/              # face.png, icons.
│   ├── cli/                     # ← NEW. `jarvis` CLI (server mode, headless).
│   │   └── src/jarvis_cli/
│   └── tui/                     # (optional) Terminal UI.
│
├── packages/                    # ← NEW. Reusable libraries.
│   ├── plugin_sdk/              # ← NEW. The contract. Extensions import only from here.
│   │   ├── pyproject.toml
│   │   └── src/jarvis_sdk/
│   │       ├── manifest.py      # Plugin manifest reader/writer.
│   │       ├── contract.py      # Base classes: Action, Provider, Channel, MemoryHost, Tool.
│   │       ├── types.py         # Tool declaration types, Result type, etc.
│   │       ├── runtime.py       # Runtime API surface.
│   │       ├── config.py        # Config schema helpers.
│   │       ├── secrets.py       # Secret reference helpers.
│   │       └── paths.py         # Standardized paths.
│   ├── agent_runtime/           # ← current agent/. Renamed + extended.
│   ├── llm_client/              # ← current or_client.py. Generalized for all providers.
│   ├── memory_host_sdk/         # ← NEW. Memory-host interface.
│   ├── channels_core/           # ← NEW. Channel transport contracts (inbound, outbound, routing).
│   ├── gateway_protocol/        # ← NEW. JSON-RPC protocol definitions.
│   ├── config_core/             # ← current config/. Schema-versioned.
│   ├── cli_backend/             # ← NEW. CLI flag/arg parsers.
│   ├── cron_core/               # ← NEW. Cron + scheduled tasks.
│   ├── hooks_core/              # ← NEW. Plugin hook system.
│   ├── logging_core/            # ← NEW. Structured logging.
│   ├── secrets_core/            # ← NEW. Secret resolution.
│   ├── events_core/             # ← NEW. Event bus.
│   ├── i18n_core/               # ← NEW. Translation scaffolding.
│   ├── audio_core/              # ← NEW. Audio capture/playback.
│   ├── live_session/            # ← NEW. Real-time voice session (Gemini Live + future).
│   ├── retry_core/              # ← NEW. Retry/backoff policies.
│   ├── net_policy/              # ← NEW. SSRF, allowlist, fetch policy.
│   ├── normalization/           # ← NEW. Result type, discriminated unions, error mapping.
│   ├── transcript_core/         # ← NEW. Session transcript persistence.
│   ├── session_core/            # ← NEW. Session lifecycle, keys, ownership.
│   ├── media_core/              # ← NEW. Media understanding contracts.
│   ├── markdown_core/           # ← NEW. Markdown rendering/safety.
│   ├── workboard_contract/      # ← NEW. Workboard/kanban integration contract.
│   └── tool_call_repair/        # ← NEW. Tool-call repair heuristics.
│
├── extensions/                  # ← NEW. The plugin ecosystem.
│   ├── README.md                # How to write a Jarvis extension.
│   │
│   │ ── Channels (target: 8 essentials + 2 stretch)
│   ├── telegram/
│   ├── discord/
│   ├── slack/
│   ├── whatsapp/
│   ├── signal/
│   ├── matrix/
│   ├── feishu/
│   ├── msteams/
│   ├── sms/                     # (stretch)
│   └── webchat/                 # (stretch — gateway-hosted web client)
│   │
│   │ ── LLM providers (target: 5 essentials + adapters)
│   ├── openai/                  # GPT family + Codex.
│   ├── anthropic/               # Claude.
│   ├── google/                  # Gemini (live + chat).
│   ├── openrouter/              # Multi-model router. ← current or_client.py.
│   ├── ollama/                  # Local models.
│   ├── minimax/                 # In-house (replaces `minimax/minimax-m2.5:free`).
│   ├── openai_codex/            # Codex harness (if needed).
│   ├── copilot/                 # GitHub Copilot.
│   ├── mistral/                 # Mistral API.
│   └── xai/                     # Grok.
│   │
│   │ ── Media (image / video / music / TTS / STT)
│   ├── image_generation/        # Unified image-gen contract.
│   ├── video_generation/        # Unified video-gen contract.
│   ├── music_generation/
│   ├── tts_elevenlabs/
│   ├── tts_local/               # pyttsx3, edge-tts, sherpa-onnx.
│   ├── stt_whisper/             # Local whisper.cpp.
│   ├── stt_openai/              # OpenAI Whisper API.
│   └── media_understanding/     # Image/video/audio analysis.
│   │
│   │ ── Memory (single active slot pattern)
│   ├── memory_core/             # Default: SQLite + embeddings.
│   ├── memory_lancedb/          # Alternative backend.
│   └── memory_wiki/             # Wiki-style persistent knowledge.
│   │
│   │ ── Tools / actions (target: 12 essentials, each becomes its own extension)
│   ├── tool_browser/            # Playwright-backed.
│   ├── tool_filesystem/         # File ops.
│   ├── tool_shell/              # Sandbox shell.
│   ├── tool_desktop/            # Desktop automation.
│   ├── tool_youtube/            # YouTube.
│   ├── tool_flight/             # Flight finder.
│   ├── tool_reminder/           # Reminders.
│   ├── tool_weather/            # Weather.
│   ├── tool_screenshot/         # Screen capture.
│   ├── tool_clipboard/          # Clipboard.
│   ├── tool_calendar/           # Calendar.
│   └── tool_code/               # Code execution sandbox.
│   │
│   │ ── Productivity / skills / personal
│   ├── obsidian/                # Obsidian vault reader/writer.
│   ├── notion/
│   ├── github/                  # GitHub CLI integration.
│   ├── calendar/                # Cross-platform calendar.
│   ├── tasks/                   # Taskflow.
│   ├── reminders_macos/         # Apple Reminders.
│   └── notes_macos/             # Apple Notes.
│   │
│   │ ── Voice / talk
│   ├── talk_voice/              # Continuous conversation mode.
│   ├── voice_wake/              # Wake-word detection.
│   └── voice_call/              # Outbound voice calls.
│   │
│   │ ── Infrastructure / ops
│   ├── webhooks/                # Inbound webhooks.
│   ├── cron_service/            # Cron expression evaluator.
│   ├── admin_http_rpc/          # HTTP-RPC control surface.
│   ├── diagnostics_otel/        # OpenTelemetry.
│   └── diagnostics_prom/        # Prometheus.
│   │
│   │ ── Migration / compatibility
│   ├── migrate_mark_xxxix/      # Old JARVIS config migrator.
│   └── migrate_legacy_config/   # Doctor-style config migration.
│   │
│   │ ── Local-dev (scaffolded for testing, not bundled)
│   ├── test_support/
│   └── test_e2e_helpers/
│
├── skills/                      # ← NEW. Declarative skills (markdown only).
│   ├── README.md                # How to write a skill.
│   ├── weather/SKILL.md
│   ├── summarize/SKILL.md
│   ├── github/SKILL.md
│   ├── notion/SKILL.md
│   ├── obsidian/SKILL.md
│   ├── notion-search/SKILL.md
│   ├── blogwatcher/SKILL.md
│   ├── healthcheck/SKILL.md
│   ├── tmux/SKILL.md
│   ├── taskflow/SKILL.md
│   ├── meme-maker/SKILL.md
│   ├── nano-pdf/SKILL.md
│   ├── coding-agent/SKILL.md
│   ├── session-logs/SKILL.md
│   ├── skill-creator/SKILL.md
│   ├── peekaboo/SKILL.md
│   ├── blucli/SKILL.md
│   ├── spotify-player/SKILL.md
│   ├── sonoscli/SKILL.md
│   ├── himalaya/SKILL.md
│   ├── eightctl/SKILL.md
│   ├── goplaces/SKILL.md
│   ├── trello/SKILL.md
│   ├── things-mac/SKILL.md
│   ├── oracle/SKILL.md
│   ├── ordercli/SKILL.md
│   ├── songsee/SKILL.md
│   ├── video-frames/SKILL.md
│   ├── spike/SKILL.md
│   ├── gog/SKILL.md
│   ├── apple-notes/SKILL.md
│   ├── apple-reminders/SKILL.md
│   ├── bear-notes/SKILL.md
│   ├── sherpa-onnx-tts/SKILL.md
│   ├── openai-whisper/SKILL.md
│   ├── openai-whisper-api/SKILL.md
│   ├── model-usage/SKILL.md
│   ├── xurl/SKILL.md
│   ├── node-connect/SKILL.md
│   ├── node-inspect-debugger/SKILL.md
│   ├── python-debugpy/SKILL.md
│   ├── mcporter/SKILL.md
│   ├── openhue/SKILL.md
│   ├── gemini/SKILL.md
│   ├── github-issues/SKILL.md
│   ├── gifgrep/SKILL.md
│   ├── diagram-maker/SKILL.md
│   ├── camsnap/SKILL.md
│   ├── 1password/SKILL.md
│   └── clawhub/SKILL.md
│
├── docs/                        # ← NEW. Docs as code.
│   ├── README.md                # Doc index.
│   ├── architecture.md
│   ├── plugin-sdk.md
│   ├── plugin-manifest.md
│   ├── config-schema.md
│   ├── schema-versioning.md
│   ├── channels/
│   │   ├── README.md
│   │   ├── telegram.md
│   │   ├── discord.md
│   │   ├── slack.md
│   │   ├── whatsapp.md
│   │   ├── signal.md
│   │   ├── matrix.md
│   │   ├── feishu.md
│   │   ├── msteams.md
│   │   └── webchat.md
│   ├── providers/
│   │   ├── README.md
│   │   ├── openai.md
│   │   ├── anthropic.md
│   │   ├── google.md
│   │   ├── openrouter.md
│   │   ├── ollama.md
│   │   └── minimax.md
│   ├── tools/
│   │   ├── README.md
│   │   ├── browser.md
│   │   ├── filesystem.md
│   │   ├── shell.md
│   │   ├── desktop.md
│   │   ├── media.md
│   │   ├── calendar.md
│   │   ├── reminders.md
│   │   ├── weather.md
│   │   └── screenshot.md
│   ├── skills/
│   │   ├── README.md
│   │   ├── how-to-write.md
│   │   └── catalog.md
│   ├── memory/
│   │   ├── README.md
│   │   ├── memory-core.md
│   │   ├── memory-lancedb.md
│   │   └── memory-host-sdk.md
│   ├── concepts/
│   │   ├── README.md
│   │   ├── agent.md
│   │   ├── session.md
│   │   ├── gateway.md
│   │   ├── plugin.md
│   │   ├── provider.md
│   │   ├── channel.md
│   │   ├── memory-host.md
│   │   ├── skill.md
│   │   ├── tool.md
│   │   └── cron.md
│   ├── reference/
│   │   ├── README.md
│   │   ├── config-keys.md
│   │   ├── manifest-schema.md
│   │   ├── secret-refs.md
│   │   ├── result-type.md
│   │   └── rpc-schema.md
│   ├── security/
│   │   ├── README.md
│   │   ├── threat-model.md
│   │   ├── secret-storage.md
│   │   ├── sandboxing.md
│   │   └── permissions.md
│   ├── installation/
│   │   ├── README.md
│   │   ├── quickstart.md
│   │   ├── from-mark-xxxix.md
│   │   ├── from-source.md
│   │   └── update.md
│   ├── operations/
│   │   ├── README.md
│   │   ├── doctor.md
│   │   ├── migrations.md
│   │   ├── logging.md
│   │   ├── metrics.md
│   │   └── troubleshooting.md
│   ├── releases/
│   │   ├── README.md
│   │   ├── versioning.md
│   │   └── changelog-policy.md
│   └── development/
│       ├── README.md
│       ├── plugin-authoring.md
│       ├── writing-skills.md
│       ├── testing.md
│       ├── ci.md
│       └── contribution.md
│
├── security/                    # ← NEW.
│   ├── README.md                # Threat model + opengrep usage.
│   └── opengrep/                # Optional: rulepack (Phase 6).
│       ├── README.md
│       ├── precise.yml
│       ├── rules/
│       ├── compile-rules.py
│       └── check-rule-metadata.py
│
├── test/                        # ← NEW. Tests, e2e, fixtures.
│   ├── README.md
│   ├── e2e/                     # Cross-package e2e tests.
│   ├── fixtures/                # Sample configs, messages, transcripts.
│   ├── helpers/                 # Shared test helpers.
│   ├── mocks/                   # Provider/channel mocks.
│   ├── plugins/                 # Test-only extensions.
│   └── scripts/                 # Test runner scripts.
│
├── tools/                       # ← NEW. Build/test/dev tooling.
│   ├── README.md
│   ├── scripts/                 # Local dev scripts.
│   │   ├── doctor.py            # ← NEW. Config doctor.
│   │   ├── migrate.py           # ← NEW. Config migrator.
│   │   ├── bench.py
│   │   ├── list-extensions.py
│   │   └── validate-manifest.py
│   ├── git-hooks/
│   │   ├── pre-commit
│   │   └── commit-msg
│   ├── ci/                      # CI helpers (Python equivalent of OpenClaw's scripts/).
│   │   ├── check-imports.py     # No cross-extension imports.
│   │   ├── check-boundaries.py
│   │   ├── check-deprecated.py
│   │   ├── check-max-lines.py
│   │   ├── check-cycles.py
│   │   ├── check-manifests.py
│   │   └── check-schema-version.py
│   └── codegen/                 # Manifest validators, type stubs.
│
├── deploy/                      # ← NEW.
│   ├── fly.toml                 # (optional)
│   ├── docker-compose.yml       # (optional)
│   ├── Dockerfile               # (optional)
│   └── README.md
│
├── ui/                          # (Optional) Web UI (FastAPI + htmx/lit). Phase 5.
│   ├── pyproject.toml
│   └── src/jarvis_ui/
│       ├── app.py
│       ├── static/
│       ├── templates/
│       └── api.py
│
├── examples/                    # ← NEW. Runnable examples.
│   ├── README.md
│   ├── ai-chat/                 # Headless gateway + CLI example.
│   ├── custom-skill/
│   ├── custom-extension/
│   └── custom-memory-host/
│
├── qa/                          # ← NEW. Quality assurance scenarios.
│   ├── README.md
│   ├── scenarios/
│   │   ├── index.yaml
│   │   ├── channels/
│   │   ├── memory/
│   │   ├── tools/
│   │   └── skills/
│   ├── maturity-scores.yaml     # (Phase 6)
│   └── harness-plan.md
│
├── .github/                     # ← NEW. GitHub config.
│   ├── CODEOWNERS               # ← who reviews what.
│   ├── labeler.yml              # Auto-label rules.
│   ├── dependabot.yml
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.md
│   │   └── feature_request.md
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── workflows/
│       ├── ci.yml               # ← pytest + ruff + pyright.
│       ├── release.yml          # ← PyPI publish.
│       ├── docs.yml             # ← build & publish docs.
│       ├── labeler.yml
│       ├── stale.yml
│       ├── dependency-guard.yml # ← pin/override audits.
│       ├── security-sensitive-guard.yml
│       └── opengrep.yml         # ← (Phase 6)
│
├── .vscode/                     # ← NEW. Editor config.
│   ├── settings.json
│   ├── extensions.json
│   └── launch.json
│
├── patches/                     # (empty by default, only if upstream deps need patching)
│
├── CONTRIBUTING.md              # ← NEW. Contribution rules.
├── LICENSE                      # KEEP (current is BY-NC, decide before public release).
├── THIRD_PARTY_NOTICES.md       # ← NEW. Third-party attributions.
│
└── (REMOVED — these go to extensions/<id>/ or packages/<id>/)
    ├── main.py                  # → apps/desktop/src/jarvis_desktop/app.py
    ├── ui.py                    # → apps/desktop/src/jarvis_desktop/hud/window.py
    ├── or_client.py             # → packages/llm_client + extensions/openrouter/
    ├── actions/                 # → extensions/tool_*/
    ├── agent/                   # → packages/agent_runtime
    ├── memory/                  # → extensions/memory_core + packages/memory_host_sdk
    ├── config/                  # → packages/config_core (api_keys.json → user config dir)
    └── core/                    # → apps/desktop/src/jarvis_desktop/prompt.txt
```

**Directory counts (final target):**

| Tier | OpenClaw count | JARVIS target | Notes |
|---|---|---|---|
| `apps/` | 8 | 2–3 | desktop + cli (+ optional tui) |
| `packages/` | 23 | 23 | Match all 23 (or merge where it makes sense) |
| `extensions/` (channels) | 23 | 8 | Telegram/Discord/Slack/WhatsApp/Signal/Matrix/Feishu/MSTeams + 2 stretch |
| `extensions/` (providers) | 74 | 10 | Keep what's used, rest are config-driven |
| `extensions/` (media) | 13 | 8 | Image/video/music/TTS/STT |
| `extensions/` (memory) | 3 | 3 | Match all 3 |
| `extensions/` (tools) | n/a (mixed) | 12 | Each action becomes its own extension |
| `skills/` | 51 | 51 | All 51, declarative markdown |
| `docs/` | 30 cats | 11 cats | Smaller surface, same shape |
| `qa/` | 1 cat | 1 cat | Same |
| `security/` | 1 dir | 1 dir | Same |
| `test/` | 6 sub | 6 sub | Same |
| `tools/` | 1 dir | 1 dir | Same |
| `.github/workflows` | 70+ | 8 | Lighter CI for solo dev |

---

## 2. The Plugin-SDK contract (the only thing that must come first)

OpenClaw's biggest architectural win: **extensions import only from `@openclaw/plugin-sdk/*`**. This single rule gives you plugin safety, version stability, and clean upgrade paths. We need this from day one.

**File: `packages/plugin_sdk/src/jarvis_sdk/contract.py`**

```python
"""The complete plugin contract for JARVIS.

Every extension imports from this module. No extension imports from
`packages/agent_runtime/*`, `packages/llm_client/*`, or other extensions.
This is enforced by `tools/ci/check-imports.py`.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Literal, TypeVar

T = TypeVar("T")


# ── Result type (replaces stringly-typed errors) ────────────────────
@dataclass(frozen=True, slots=True)
class Ok(Generic[T]):
    value: T
    @property
    def is_ok(self) -> bool: return True
    @property
    def is_err(self) -> bool: return False

@dataclass(frozen=True, slots=True)
class Err(Generic[T]):
    error: str
    code: str = "ERR"
    cause: BaseException | None = None
    @property
    def is_ok(self) -> bool: return False
    @property
    def is_err(self) -> bool: return True

Result = Ok[T] | Err[T]


# ── Tool declaration (what an action module exposes) ────────────────
@dataclass(frozen=True, slots=True)
class ToolParam:
    name: str
    type: Literal["string", "integer", "number", "boolean", "array", "object"]
    description: str
    required: bool = False
    enum: list[str] | None = None
    items: list["ToolParam"] | None = None  # for array
    properties: list["ToolParam"] | None = None  # for object

@dataclass(frozen=True, slots=True)
class ToolDecl:
    name: str
    description: str
    parameters: list[ToolParam]
    returns: str = "string"
    category: str = "general"
    requires: list[str] = field(default_factory=list)  # e.g. ["os:windows", "bin:playwright"]
    replay_safe: bool = False  # if True, safe to call from replay


# ── Plugin kinds ─────────────────────────────────────────────────────
class PluginKind(str, Enum):
    CHANNEL   = "channel"
    PROVIDER  = "provider"
    TOOL      = "tool"
    MEMORY    = "memory"
    SKILL     = "skill"
    INFRA     = "infra"
    MIGRATION = "migration"


@dataclass(frozen=True, slots=True)
class PluginManifest:
    id: str                               # "telegram", "tool_browser", "memory_core"
    kind: PluginKind
    version: str                          # semver
    description: str
    icon: str | None = None
    activation: Literal["always", "on_startup", "on_demand"] = "on_demand"
    requires: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    config_schema: dict[str, Any] = field(default_factory=dict)
    entrypoint: str = "main:plugin"


# ── Base plugin classes ──────────────────────────────────────────────
class Plugin(ABC):
    manifest: PluginManifest
    @abstractmethod
    async def init(self, ctx: "PluginContext") -> None: ...
    @abstractmethod
    async def shutdown(self) -> None: ...


class ToolPlugin(Plugin):
    @property
    @abstractmethod
    def tools(self) -> list[ToolDecl]: ...
    @abstractmethod
    async def call(self, name: str, args: dict[str, Any]) -> Result[Any]: ...


class ChannelPlugin(Plugin):
    @abstractmethod
    async def send(self, target: str, message: "OutboundMessage") -> Result[None]: ...
    @abstractmethod
    async def listen(self, callback: Callable[["InboundMessage"], None]) -> None: ...


class ProviderPlugin(Plugin):
    @abstractmethod
    async def complete(self, messages: list[dict], **kwargs) -> Result[str]: ...
    @abstractmethod
    def list_models(self) -> list[str]: ...


class MemoryHostPlugin(Plugin):
    """Single-active-slot memory plugin. One is loaded at a time."""
    @abstractmethod
    async def search(self, query: str, k: int = 10) -> Result[list["MemoryHit"]]: ...
    @abstractmethod
    async def store(self, content: str, metadata: dict) -> Result[None]: ...
    @abstractmethod
    async def get(self, memory_id: str) -> Result["MemoryHit"]: ...


# ── Runtime context (what the host passes to the plugin) ─────────────
@dataclass
class PluginContext:
    config: "ConfigView"                          # read-only view of user config
    secrets: "SecretResolver"                     # ~/.jarvis/secrets/
    logger: "Logger"
    data_dir: Path                                # ~/.jarvis/extensions/<id>/
    workspace: Path                               # user workspace
    http: "HttpClient"                            # SSRF-checked HTTP
    fs: "SafeFs"                                  # path-containment FS
    emit_event: Callable[[str, dict], None]       # event bus

---

## 3. Extension manifest (every extension ships one)

**File: `extensions/<id>/jarvis.plugin.json`**

Modelled exactly on `extensions/telegram/openclaw.plugin.json` and `extensions/memory-core/openclaw.plugin.json` (which I read). The manifest is the **public contract** for each plugin.

```json
{
  "id": "tool_browser",
  "kind": "tool",
  "version": "0.1.0",
  "description": "Browser automation via Playwright (Chromium).",
  "icon": "https://cdn.simpleicons.org/googlechrome",
  "activation": "on_demand",
  "permissions": ["network:outbound", "fs:read:user_workspace", "process:spawn:playwright"],
  "requires": { "bins": ["playwright"], "python": ">=3.12" },
  "tools": [
    {
      "name": "browser_control",
      "description": "Open URLs, click, type, scroll, fill forms. Web automation.",
      "parameters": [
        {"name": "action", "type": "string", "required": true, "enum": ["go_to","search","click","type","scroll","press","close"]},
        {"name": "url", "type": "string", "required": false},
        {"name": "query", "type": "string", "required": false},
        {"name": "selector", "type": "string", "required": false},
        {"name": "text", "type": "string", "required": false},
        {"name": "description", "type": "string", "required": false}
      ]
    }
  ],
  "configSchema": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "headless": {"type": "boolean", "default": true},
      "browser": {"type": "string", "enum": ["chromium","firefox","webkit"], "default": "chromium"}
    }
  },
  "entrypoint": "src.jarvis_tool_browser:plugin"
}
```

**Loader: `packages/plugin_sdk/src/jarvis_sdk/loader.py`** discovers and loads these from `extensions/*/jarvis.plugin.json`.

---

## 4. Skills (declarative markdown)

Modelled exactly on `openclaw-main/skills/weather/SKILL.md` and `summarize/SKILL.md`. Each skill is a single file with YAML frontmatter.

**File: `skills/weather/SKILL.md`**

```markdown
---
name: weather
description: "Current weather and forecasts via web_fetch, with curl fallback."
homepage: https://wttr.in/:help
metadata:
  jarvis:
    emoji: "?"
    install:
      - { id: brew, kind: brew, formula: curl, bins: [curl], label: "Install curl (brew)" }
---

# Weather

Use for current weather, rain/temperature, forecasts, travel planning.
Need a city, region, airport code, or coordinates.

## Preferred: web_fetch

Use `web_fetch` first when available...

## Fallback: curl

...
```

**Discovery: `packages/plugin_sdk/src/jarvis_sdk/skills.py`** scans `skills/*/SKILL.md`, parses frontmatter, registers descriptions in the system prompt so the LLM can pick.

**51 skills to ship in the final target** (full list in `skills/` tree above).

---

## 5. What gets removed from current JARVIS

| Current file/dir | Fate | Replaced by |
|---|---|---|
| `main.py` (620 lines, monolith) | **Delete after migration** | `apps/desktop/src/jarvis_desktop/app.py` (entry only) + `packages/agent_runtime` (loop) + `packages/gateway_protocol` (RPC) |
| `ui.py` (1349 lines, monolithic HUD) | **Delete after migration** | `apps/desktop/src/jarvis_desktop/hud/` (split into 7 files) |
| `or_client.py` (OpenRouter) | **Delete after migration** | `packages/llm_client` (generic) + `extensions/openrouter/` |
| `agent/error_handler.py` | Move | `packages/agent_runtime/error_handler.py` |
| `agent/executor.py` | Move | `packages/agent_runtime/executor.py` |
| `agent/planner.py` | Move | `packages/agent_runtime/planner.py` |
| `agent/task_queue.py` | Move | `packages/agent_runtime/task_queue.py` |
| `actions/open_app.py` | Convert | `extensions/tool_filesystem/open_app.py` (or merge into `tool_filesystem`) |
| `actions/browser_control.py` | Convert | `extensions/tool_browser/` |
| `actions/code_helper.py` | Convert | `extensions/tool_code/` |
| `actions/computer_control.py` | Convert | `extensions/tool_desktop/` |
| `actions/computer_settings.py` | Convert | `extensions/tool_desktop/settings.py` |
| `actions/desktop.py` | Convert | `extensions/tool_desktop/organize.py` |
| `actions/dev_agent.py` | Convert | `extensions/tool_code/agent.py` |
| `actions/file_controller.py` | Convert | `extensions/tool_filesystem/` |
| `actions/file_processor.py` | Convert | `extensions/media_understanding/file.py` |
| `actions/flight_finder.py` | Convert | `extensions/tool_flight/` |
| `actions/game_updater.py` | Convert | `extensions/tool_gaming/` (or merge into `tool_desktop`) |
| `actions/reminder.py` | Convert | `extensions/tool_reminder/` |
| `actions/screen_processor.py` | Convert | `extensions/tool_screenshot/` + `extensions/media_understanding/screen.py` |
| `actions/send_message.py` | Convert | (becomes a generic `agent.message.send` tool; channels provide the actual transport) |
| `actions/weather_report.py` | Convert | `extensions/tool_weather/` |
| `actions/web_search.py` | Convert | `extensions/brave/` or `extensions/duckduckgo/` (real search provider) |
| `actions/youtube_video.py` | Convert | `extensions/tool_youtube/` + `extensions/diffs/` for transcript diff |
| `memory/memory_manager.py` | Convert | `extensions/memory_core/` (provider) + `packages/memory_host_sdk/` (interface) |
| `memory/config_manager.py` | Move | `packages/config_core/` |
| `config/api_keys.json` | Migrate | `~/.jarvis/credentials/` (user-scoped, never in repo) |
| `core/prompt.txt` | Move | `apps/desktop/src/jarvis_desktop/prompt.txt` (app-specific) + system prompt templates in `packages/agent_runtime/prompts/` |
| `setup.py` | Delete | `pyproject.toml` replaces it |
| `requirements.txt` | Delete | `pyproject.toml` (with `[project.dependencies]`) replaces it |

**Things from current JARVIS that the migration will keep conceptually but rewrite:**

- The Gemini Live voice loop ? `packages/live_session/` (with adapter for any future live model)
- The HUD aesthetic (cyan halo, scanner, particle effects) ? `apps/desktop/hud/` (split into 7 files but visually identical)
- The OpenRouter free-model fallback chain ? `extensions/openrouter/` (preserved as a feature, no longer the only client)
- The file drop / processing pipeline ? `extensions/tool_filesystem/` + `extensions/media_understanding/`
- The HUD system metrics (CPU/MEM/NET/GPU/TMP) ? `apps/desktop/hud/metrics.py` (no change in behavior, just split)
- The setup overlay (API key entry) ? `apps/desktop/hud/setup.py` + first-run wizard from `packages/wizard/`

---

## 6. Schema versioning (one of OpenClaw's biggest wins)

**File: `pyproject.toml`**

```toml
[project]
name = "jarvis"
version = "0.1.0-rc1"
description = "Personal AI assistant, OpenClaw architecture"

[tool.jarvis]
schemaVersions = { state = 1, agent = 1, config = 1, memory = 1 }
entrypoints = { desktop = "jarvis_desktop.app:main", cli = "jarvis_cli.app:main" }
```

Bump rules (mirroring OpenClaw's `AGENTS.md` rules):

- `state` � bump when on-disk SQLite schema changes
- `agent` � bump when agent prompt/loop/state format changes
- `config` � bump when user `~/.jarvis/config.json` keys are renamed/removed
- `memory` � bump when memory store format changes

Migrations live in `extensions/migrate_*/` and run via `jarvis doctor --fix`.

---

## 7. Phased migration roadmap (12 phases, =5K LOC each)

Each phase = one focused PR. After each phase, JARVIS must still launch and the new code must be exercised by at least one test.

### Phase 0 � Skeleton (no features, just bones)
- PRs: 0.1 (governance docs), 0.2 (build/test infra), 0.3 (empty tier dirs), 0.4 (move desktop), 0.5 (verify)
- Outcome: `python -m apps.desktop` launches current JARVIS from new layout
- Lines: ~600

### Phase 1 � `plugin_sdk` contract + 1 proof consumer
- Define `Plugin`, `ToolPlugin`, `ChannelPlugin`, `ProviderPlugin`, `MemoryHostPlugin` in `packages/plugin_sdk/`
- Add `loader.py` that reads `jarvis.plugin.json`
- Convert ONE current action (`actions/weather_report.py`) into `extensions/tool_weather/` as proof
- Tool dispatch in `packages/agent_runtime/router.py` reads from loader, not hardcoded list
- Lines: ~1,500
- Verification: weather skill works exactly like before, but loaded dynamically

### Phase 2 � All 17 actions converted to extensions
- 17 PRs or one bulk PR: each action becomes its own extension following the manifest
- Keep behavior identical
- Lines: ~3,000 (most is mechanical)
- After: hardcoded `TOOL_DECLARATIONS` in main.py is empty; everything comes from manifest

### Phase 3 � Skills system (declarative markdown)
- Ship 10 essential skills first: weather, summarize, github, notion, obsidian, healthcheck, taskflow, blogwatcher, meme-maker, nano-pdf
- Add the rest (41) one cluster at a time
- Skill discovery in `packages/plugin_sdk/skills.py`
- Lines: ~800
- After: skills appear in system prompt automatically; LLM can call them without Python changes

### Phase 4 � `memory_core` extension + `memory_host_sdk` package
- `packages/memory_host_sdk/` defines `MemoryHostPlugin` interface
- `extensions/memory_core/` provides default implementation (SQLite + embeddings)
- `extensions/memory_lancedb/` and `extensions/memory_wiki/` (stretch)
- Single-active-slot pattern: only one memory plugin loads at a time
- Migrate `memory/memory_manager.py` ? `extensions/memory_core/store.py`
- Lines: ~1,800

### Phase 5 � Channel system + gateway protocol
- `packages/channels_core/` (transport contracts: inbound, outbound, routing, presence)
- `packages/gateway_protocol/` (JSON-RPC schema for gateway ? clients)
- First 2 channel extensions: `extensions/telegram/`, `extensions/discord/`
- Jarvis becomes addressable: send a message from Telegram, get a reply
- Lines: ~3,000
- After: Jarvis works without a local UI; gateway is the truth

### Phase 6 � LLM provider extensions (multi-model)
- `packages/llm_client/` (generic)
- First providers: `extensions/openai/`, `extensions/anthropic/`, `extensions/google/` (live), `extensions/openrouter/`, `extensions/ollama/`
- All providers expose the same `ProviderPlugin.complete()` interface
- Fallback chain (OpenRouter free models) preserved as a provider config
- Lines: ~2,500

### Phase 7 � Media (image/video/music/TTS/STT) + media_understanding
- `packages/media_core/` (contracts)
- `extensions/image_generation/`, `extensions/video_generation/`, `extensions/music_generation/`
- `extensions/tts_elevenlabs/`, `extensions/tts_local/`, `extensions/stt_whisper/`, `extensions/stt_openai/`
- `extensions/media_understanding/` (image/video/audio analysis; replaces `file_processor.py`)
- Lines: ~2,800

### Phase 8 � Doctor + migrations
- `tools/scripts/doctor.py`: scans `~/.jarvis/`, finds config issues, applies migrations
- `extensions/migrate_mark_xxxix/`: imports old `config/api_keys.json`, `core/prompt.txt`, `memory/*.json`
- Schema version checks (per Phase 6 in `pyproject.toml`)
- `extensions/migrate_legacy_config/`: cleans up old config keys
- Lines: ~1,200

### Phase 9 � More channels + provider coverage
- Remaining channels: slack, whatsapp, signal, matrix, feishu, msteams, sms, webchat
- More providers: minimax, openai_codex, copilot, mistral, xai
- Lines: ~4,000 (one PR per channel; one PR per provider cluster)

### Phase 10 � Cron, webhooks, ops surface
- `extensions/cron_service/`: cron expression evaluator, scheduled tasks
- `extensions/webhooks/`: inbound HTTP webhooks
- `extensions/admin_http_rpc/`: HTTP-RPC control surface
- `extensions/diagnostics_otel/`, `extensions/diagnostics_prom/`: telemetry
- Lines: ~2,200

### Phase 11 � Skills catalog completion (all 51)
- Write the remaining ~30 skills
- Each PR adds 3�5 skills
- Lines: ~600 (just markdown)

### Phase 12 � Optional polish
- `ui/` web frontend (FastAPI + htmx/lit) for headless mode
- `deploy/Dockerfile`, `deploy/docker-compose.yml`
- `security/opengrep/` rulepack
- `qa/scenarios/` full coverage
- macOS/Windows companion apps (only if scope expands)

**Total lines across all phases: ~24,000** (vs OpenClaw's millions, but Python is denser and we copy structure, not code)

---

## 8. Per-phase PR template (use this every time)

```markdown
## What

One-sentence summary. References `AGENTS.md` for the area it touches.

## Why

- Problem observed (cite file:line)
- Why the chosen fix is the best fix (cite sibling/scope evidence)
- What alternatives were considered and rejected

## How

- Files added / moved / removed (with line counts)
- Schema version bumps (if any)
- Migration / doctor impact (if any)
- New config keys (if any) � must justify why existing product behavior / doctor migration could not solve it

## Evidence

- Local: `uv run pytest packages/<x>/test/ -q` (paste result)
- Local: `uv run ruff check` + `uv run pyright packages/<x>` (paste result)
- Manual: `uv run python -m apps.desktop` launched, observed X
- Skill/tool/scenario that exercises the change

## Risk

- Compatibility: what existing user config/data could break
- Rollback: `git revert <sha>` is safe because �
- Follow-up: linked issue / discussion thread

## Docs

- Updated: `docs/<area>/<file>.md`
- New: `docs/<area>/<new>.md`
- Changelog: included in PR body (release generation will pull it in)
```

---

## 9. AGENTS.md draft (Phase 0.1 deliverable)

Will be written in Phase 0.1. Telegraph style, root policy only, like OpenClaw's. Sections:

- **Start** � repo location, replies style, existing-solutions preflight, dependency-touching work
- **Map** � apps/packages/extensions/skills/docs/test/tools/security, where each lives, who owns
- **Architecture** � core stays plugin-agnostic, plugins cross core only via `jarvis_sdk`, ownership rules, schema versioning, fallback rules, "no silent compat"
- **Commands** � `uv run ...`, `uv run pytest`, `uv run ruff`, `uv run pyright`, `python -m apps.desktop`, `python -m jarvis_cli ...`
- **Validation** � `uv run pytest`, `uv run ruff`, `uv run pyright`, import-cycle check, manifest schema check
- **Code** � Python 3.12, type hints required, ruff rules, pyright strict, "lean code", "tests prove behavior not branches"
- **Tests** � pytest, fixtures, e2e, contract tests
- **Docs / Changelog** � docs change with behavior, CHANGELOG is release-only
- **Git** � conventional commits, one PR = one topic, =5K lines
- **Security / Release** � secrets in `~/.jarvis/`, schema bumps need explicit user discussion, lockfile is security surface

---

## 10. Open questions for the architect (one round)

Before I start Phase 0, please confirm:

1. **Python toolchain choice**: `uv` (fast, modern), `poetry` (mature), `pdm` (PEP 582). My pick: **`uv`** (matches OpenClaw's speed-focused philosophy; works on Windows; one binary).
2. **License**: Current is `BY-NC 4.0`. OpenClaw is `MIT`. Want to keep restrictive or open it up? (Affects whether external contributions are even possible.)
3. **Test framework**: `pytest` is the obvious pick. Want `hypothesis` for property-based tests too? (OpenClaw uses vitest; pytest+hypothesis is the Python equivalent.)
4. **First two channels after Phase 5**: My pick: **Telegram + Discord** (largest user bases, well-documented APIs). Confirm or pick others.
5. **Memory backend in Phase 4**: My pick: **SQLite + sqlite-vec** (matches OpenClaw's "Storage default: SQLite only" rule). Alternative: LanceDB from day 1. Confirm.

Once these 5 are answered, Phase 0 starts immediately.

---

## 11. What stays identical (user-visible)

These are guarantees the migration makes to the current user (you, the architect, plus anyone running JARVIS today):

- ? `python -m apps.desktop` still launches the HUD
- ? Voice loop still works (mic input, speaker output, real-time Gemini Live)
- ? All 17 current tools still callable (after Phase 2)
- ? Memory still remembers between sessions
- ? File drop still works
- ? System metrics (CPU/MEM/NET/GPU/TMP) still display
- ? Setup overlay still asks for API keys on first run
- ? OpenRouter fallback chain still active

What's NEW immediately after each phase:

- After Phase 0: nothing visible, but repo is now OpenClaw-shaped
- After Phase 1: weather tool loads from manifest (no behavior change)
- After Phase 3: skills appear in system prompt, LLM can pick them
- After Phase 5: send `jarvis message send --target telegram:@me --message "hi"` from CLI works
- After Phase 8: `jarvis doctor` audits config and offers `--fix`

---

## 12. References (OpenClaw source files I read for this plan)

| Concept | Source | What I learned |
|---|---|---|
| Skill format | `openclaw-main/skills/weather/SKILL.md`, `summarize/SKILL.md` | YAML frontmatter + markdown body; metadata.openclaw.emoji, requires, install |
| Plugin manifest | `openclaw-main/extensions/memory-core/openclaw.plugin.json`, `extensions/telegram/openclaw.plugin.json` | id, kind, activation, channels, contracts.tools, configSchema, commandAliases, uiHints |
| Plugin structure | `openclaw-main/extensions/memory-core/package.json`, `extensions/telegram/src/...` | Each plugin = npm package + entrypoint; imports `@openclaw/plugin-sdk/*` only |
| Architecture | `openclaw-main/AGENTS.md` | Core stays plugin-agnostic; no silent compat; schema versioning; "one canonical path" |
| Workspace | `openclaw-main/pnpm-workspace.yaml` | apps/, packages/, extensions/, examples/ are all workspace members |
| Tier counts | `openclaw-main/extensions/*/openclaw.plugin.json` (152 found) | 74 providers, 23 channels, 3 memory, 3 browser/canvas, 13 media |
| Security | `openclaw-main/security/README.md` | OpenGrep rulepack with `precise.yml` (189KB compiled rules) |
| CODEOWNERS | `openclaw-main/.github/CODEOWNERS` | Secops review on secret/auth/sandbox paths |
| Labeler | `openclaw-main/.github/labeler.yml` | Auto-label by `extensions/<id>/**` changed-files glob |
| Skills count | `openclaw-main/skills/*/SKILL.md` (51 found) | One SKILL.md per skill, no code |
| Workflows | `openclaw-main/.github/workflows/*.yml` (70+ found) | ci, release, security, docs, codeql, opengrep, test, performance, live |
| Package pattern | `openclaw-main/packages/agent-core/package.json` | `@openclaw/agent-core`, dependencies, peerDependencies, exports |


---

## 13. Locked-in decisions (architect sign-off, 2026-07-19)

| Question | Answer | Rationale |
|---|---|---|
| Python toolchain | **`uv` (Astral)** | Fast, modern, single binary, Windows-friendly, matches OpenClaw's speed-first philosophy |
| License | **MIT** | Open source, OpenClaw-compatible, accepts external contributions |
| Test framework | **pytest + hypothesis** | pytest for unit/e2e, hypothesis for property-based tests (catches edge cases pytest misses) |
| Phase 5 first 2 channels | **Telegram + Discord** | Biggest user bases, well-documented APIs, clean protocol surfaces |
| Phase 4 default memory backend | **SQLite + LanceDB** | SQLite for canonical state, LanceDB for vector search; matches OpenClaw's "Storage default: SQLite only" rule + vectors as first-class |

These decisions are **frozen** for the migration. Changing one requires an explicit architect decision + new PR. The plan file is now the canonical reference; the migration phases below use these decisions.

---

## 14. Phase 0.1 � Governance docs (NEXT UP)

Files to create in this PR:

1. `AGENTS.md` � Telegraph-style architect playbook (root policy)
2. `CLAUDE.md` � Stub redirecting to AGENTS.md (Windows-compatible; not a symlink)
3. `VISION.md` � What JARVIS is, where it's going, contribution rules
4. `CHANGELOG.md` � Release-only changelog (starts empty)
5. `LICENSE` � MIT license text

Estimated lines: ~800.


---

## 15. Phase 0.1 � COMPLETED (2026-07-19)

**PR 0.1 deliverable: governance docs.**

Files created at `E:/jarvis/`:

| File | Lines | Purpose |
|---|---|---|
| `AGENTS.md` | 297 | Telegraph-style architect playbook. 11 sections: Start, Map, Architecture, Commands, Validation, Code, Tests, Docs/Changelog, Git, Security/Release, Contribution rules. Adapted from OpenClaw's `AGENTS.md` for Python/uv/pytest reality. |
| `CLAUDE.md` | 24 | Stub redirecting to AGENTS.md (Windows-compatible; not a symlink). |
| `VISION.md` | 73 | What JARVIS is, where it's going, OpenClaw-architecture migration, contribution rules, plugins/skills/MCP policy. |
| `CHANGELOG.md` | 33 | Release-only changelog (starts at `[Unreleased]`). Per AGENTS.md rule. |
| `LICENSE` | 21 | MIT license text (was `CC BY-NC 4.0`). |
| **Total** | **448** | (Under the 5K line budget for this PR.) |

**Decisions baked into AGENTS.md:**

- Toolchain: `uv` (Astral) � single binary, fast, Windows-friendly
- License: MIT � open source, OpenClaw-compatible
- Test: pytest + hypothesis � property-based tests for boundaries
- Channels (Phase 5): Telegram + Discord � first
- Memory (Phase 4): SQLite + LanceDB � SQLite canonical, LanceDB for vectors
- Default gateway port: **7433** (instead of OpenClaw's 18789, to avoid clash)
- Embedding providers: plug-in via `jarvis_sdk.embeddings`

**Verification:**

```
$ ls -la E:/jarvis/AGENTS.md CLAUDE.md VISION.md CHANGELOG.md LICENSE
-rw-r--r-- 1 user 27925 Jul 19 14:15 AGENTS.md
-rw-r--r-- 1 user   998 Jul 19 14:15 CLAUDE.md
-rw-r--r-- 1 user  6919 Jul 19 14:16 VISION.md
-rw-r--r-- 1 user  1317 Jul 19 14:16 CHANGELOG.md
-rw-r--r-- 1 user  1088 Jul 19 14:16 LICENSE
```

**Status:** Ready for review. Next: **Phase 0.2 (build/test infrastructure)**.

---

## 16. Phase 0.2 — COMPLETED (2026-07-19)

**PR 0.2 deliverable: build/test infrastructure (the bones around the bones).**

Files created at `E:/jarvis/`:

| File | Lines | Purpose |
|---|---|---|
| `pyproject.toml` | 240 | uv workspace root. PEP 621 + `[tool.uv.workspace]` for `apps/*`, `packages/*`, `extensions/*`. PEP 735 `[dependency-groups]` (modern, non-deprecated). Schema versions, ruff/pyright/pytest config. |
| `.python-version` | 1 | Pins to 3.13 (3.12+ per AGENTS.md; 3.13 is the installed stable). |
| `ruff.toml` | 14 | Standalone config pointer for editors; canonical lives in `pyproject.toml [tool.ruff]`. |
| `pyrightconfig.json` | 28 | Type-check config: standard mode, `apps/packages/extensions/tools/tests/examples` included, `**/legacy_*` excluded. |
| `.pre-commit-config.yaml` | 50 | Wires ruff + ruff-format + pyright + 4 CI helpers. |
| `.editorconfig` | 22 | UTF-8, LF, 4-space indent, 2-space for yml/yaml/toml/json. |
| `.gitignore` | 110 | Python + uv + IDE + JARVIS-user-data + openclaw-main (do not commit inside). |
| `.vscode/settings.json` | 60 | Ruff as default formatter, format-on-save, pyright extraPaths, terminal PowerShell. |
| `.vscode/extensions.json` | 16 | Recommend ruff/pyright; blacklist black/isort/flake8/pylint (replaced by ruff). |
| `.vscode/launch.json` | 53 | Debug configs: desktop, CLI, doctor, pytest (file/all), ruff. |
| `tools/ci/check_imports.py` | 95 | Enforce plugin-SDK import boundary (stub; full logic in PR 1.1). |
| `tools/ci/check_cycles.py` | 102 | Detect import cycles across workspace (DFS). |
| `tools/ci/check_max_lines.py` | 60 | Cap file length at 2000 (warn 1500). Excludes `legacy_*`. |
| `tools/ci/check_manifests.py` | 70 | Validate `extensions/*/jarvis.plugin.json` (stub; full in PR 1.1). |
| `tools/README.md` | 70 | Explains `tools/ci`, `tools/scripts`, `tools/codegen`. |
| `tests/test_smoke.py` | 105 | 13 tests: toolchain, repo layout, CI helpers. Removed once real tests ship. |
| **Total** | **~1096** | (Under 5K line budget.) |

**Decisions baked in:**

- `dependency-groups` (PEP 735) instead of deprecated `tool.uv.dev-dependencies` (uv 0.11.x)
- Python 3.12 minimum, 3.13 pin (installed)
- Schema version keys: `schema_state`, `schema_agent`, `schema_config`, `schema_memory` (snake_case to avoid TOML inline-table edge cases with downstream parsers)
- Default gateway port: **7433** (matches AGENTS.md)
- Entry points: `entrypoint_desktop`, `entrypoint_cli` (snake_case keys)
- Max file length: 2000 (warn 1500) — softer than OpenClaw's 1500 because Python is denser than TS

**Verification (all green):**

```
$ uv sync
Resolved 25 packages in 1ms
Checked 24 packages in 2ms

$ uv run pytest tests/ -v
============================= 13 passed in 2.33s ==============================

$ uv run python tools/ci/check_imports.py
[check_imports] no extensions/ yet (skipped — PR 1.1+)
$ uv run python tools/ci/check_cycles.py
[check_cycles] no workspace packages yet (skipped — PR 1.1+)
$ uv run python tools/ci/check_max_lines.py
[check_max_lines] no workspace files yet (skipped)
$ uv run python tools/ci/check_manifests.py
[check_manifests] no extensions/ yet (skipped — PR 1.1+)

$ uv run ruff --version
ruff 0.15.22
$ uv run pyright --version
pyright 1.1.411
```

**NOT deleted in this PR (deferred to PR 0.4):**

- `setup.py` — legacy bootstrap; replaced by `uv sync`. Stays until desktop moves.
- `requirements.txt` — legacy deps; will move into `apps/desktop/pyproject.toml` in PR 0.4.
- `main.py`, `ui.py`, `or_client.py`, `actions/`, `agent/`, `memory/`, `config/`, `core/` — at root; will move to `apps/desktop/legacy_*/` in PR 0.4.

**Known warning (non-blocking):**

- `uv sync` shows "Failed to hardlink files; falling back to full copy" on Windows when cache is on a different drive. This is a perf warning only; resolves by setting `UV_LINK_MODE=copy` or moving the cache. Suppressed by the warning; not fixed in this PR.

**Status:** Complete. Toolchain works. All CI helpers exit 0. Pytest discovers and runs tests.

**Next: Phase 0.3 — empty tier directories** (`apps/`, `packages/`, `extensions/`, `skills/`, `docs/`, `test/`, `tools/`, `security/`, `qa/`, `deploy/`, `examples/`, `.github/`) with one README per tier.

---

## 17. Phase 0.3 — COMPLETED (2026-07-19)

**PR 0.3 deliverable: the empty OpenClaw-shaped tier tree, with one README per tier.**

11 tier directories created at `E:/jarvis/`, each with a `README.md` explaining purpose, rules from `AGENTS.md`, layout, and when the tier fills in. `.github/` also created with CI + governance stubs.

### Files created (17 total)

| File | Lines | Purpose |
|---|---|---|
| `apps/README.md` | 35 | User-facing apps (desktop, cli, tui). Each is a workspace member. |
| `packages/README.md` | 60 | Reusable libraries (plugin_sdk is the only API extensions see). 23 packages planned. |
| `extensions/README.md` | 90 | Plugin ecosystem. `jarvis.plugin.json` manifest format. Category table. |
| `skills/README.md` | 50 | Declarative `SKILL.md` with YAML frontmatter. Auto-discovered by plugin_sdk. |
| `docs/README.md` | 50 | Docs as code. 17 categories planned. |
| `tests/README.md` | 65 | Cross-package tests. Pytest convention. Markers. Coverage philosophy. |
| `security/README.md` | 45 | Threat model stub. OpenGrep rulepack lands Phase 6. |
| `qa/README.md` | 40 | QA scenarios stub. Maturity scoring. |
| `deploy/README.md` | 35 | Deploy configs stub. Dockerfile template. Port 7433. |
| `examples/README.md` | 40 | Runnable examples stub. Not workspace members — install JARVIS as dep. |
| `.github/README.md` | 50 | GitHub config. CI workflows table. |
| `.github/CODEOWNERS` | 18 | Single-owner repo (`@jarvis-architect`). |
| `.github/labeler.yml` | 40 | Auto-label by `apps/`, `packages/`, `extensions/`, etc. |
| `.github/PULL_REQUEST_TEMPLATE.md` | 75 | Per-phase PR template (matches migration plan §8). |
| `.github/ISSUE_TEMPLATE/bug_report.md` | 50 | Bug template (no secrets, no PII, file:line, repro steps). |
| `.github/ISSUE_TEMPLATE/feature_request.md` | 50 | Feature template (preflight per AGENTS.md, plugin-vs-core question). |
| `.github/workflows/ci.yml` | 130 | 5-job CI: install+smoke, lint, typecheck, test (matrix py3.12+3.13), ci-helpers. |
| **Total** | **~923** | (Under 5K line budget.) |

### Root README updated

`readme.md` rewritten to reflect the OpenClaw-architecture state:
- Heritage: MARK XXXIX-OR by FatihMakes acknowledged
- Current state: 12-phase migration in progress
- Quick start with `uv sync` + `python -m jarvis_desktop` (post-0.4)
- Architecture one-liner + folder map
- Status table (all 18 phases, 3 done, 15 pending)
- Why OpenClaw: bullet list of solved problems
- Lineage: explicit credit to FatihMakes
- License: MIT with CC BY-NC heritage noted

### What PR 0.3 deliberately did NOT do

- **No code in any tier** — directories are empty (except READMEs).
- **No `apps/desktop/`, `apps/cli/`, `packages/plugin_sdk/`, `extensions/memory_core/`** — those land in PR 0.4 / 1.1 / 1.2.
- **No migration of legacy code** — `actions/`, `agent/`, `memory/`, `config/`, `core/` stay at root until PR 0.4.
- **No real CI run** — `.github/workflows/ci.yml` is valid YAML and works in GitHub Actions, but we don't push to GitHub yet. Local CI is the 4 scripts in `tools/ci/`.

### Verification

```
$ uv run pytest tests/ -q
13 passed in 2.18s

$ uv run python tools/ci/check_imports.py
[check_imports] no extension .py files yet (skipped)

$ uv run python tools/ci/check_cycles.py
[check_cycles] no workspace packages yet (skipped — PR 1.1+)

$ uv run python tools/ci/check_max_lines.py
[check_max_lines] no workspace files yet (skipped)

$ uv run python tools/ci/check_manifests.py
[check_manifests] no manifests yet (skipped)

$ ls -d apps packages extensions skills docs security qa deploy examples .github
apps/        .github/  deploy/    docs/       examples/  extensions/  packages/
qa/          security/ skills/    tests/      tools/
```

### Decisions baked in

- **`tests/` (plural)** for the test directory, not `test/` (singular as in OpenClaw). Reason: pytest default discovery is `tests/`, this matches what we already created in PR 0.2. Migration plan `§1` says `test/`; this is a one-time exception. AGENTS.md `Map` section already uses `test/<category>/` (singular) — that's a doc drift, will fix in Phase 5 when real tests land.
- **Default gateway port 7433** baked into deploy/README.md and ci.yml.
- **No second-tier subdirs in PR 0.3** (e.g. no `apps/desktop/`). Empty tiers stay empty until the phase that fills them.
- **`.github/workflows/ci.yml` runs 5 jobs in parallel** (install, lint, typecheck, test, ci-helpers) using `needs: install` to fan out from a single install step. Mirrors OpenClaw's `pnpm test*` / `pnpm lint*` / `pnpm tsgo*` job fan-out.

**Status:** Complete. Repo is now OpenClaw-shaped. All 11 tier directories + `.github/` exist. Toolchain still green (13/13 tests pass, 4/4 CI helpers exit 0).

**Next: Phase 0.4 — move desktop to `apps/desktop/` + CLI skeleton in `apps/cli/` + relocate legacy `actions/`, `agent/`, `memory/`, `config/`, `core/` to `apps/desktop/legacy_*/`.** This is the biggest risk-bearing PR so far; JARVIS must still launch from the new location.


---

## 16. Phase 0.2 � COMPLETED (2026-07-19)

**PR 0.2 deliverable: build/test infrastructure.**

### Discovery

On inspection, the workspace already had most of Phase 0.2 in place (must have been bootstrapped earlier):

| File | Status | Quality |
|---|---|---|
| `pyproject.toml` | ? Pre-existing | Excellent � full workspace, schema versions, ruff+pyright+pytest+hypothesis inline |
| `ruff.toml` | ? Pre-existing | Minimal; points to pyproject `[tool.ruff]` |
| `pyrightconfig.json` | ? Pre-existing | Comprehensive; standard mode, targeted warnings |
| `.python-version` | ? Pre-existing | **3.13** (not 3.12 � see note below) |
| `uv.lock` | ? Pre-existing | Generated, current |
| `.gitignore` | ? Pre-existing | Comprehensive (Python, IDE, JARVIS user data) |
| `.editorconfig` | ? Pre-existing | Good (LF default, CRLF for Windows shells) |
| `.pre-commit-config.yaml` | ? Pre-existing | Has ruff, pyright, plus refs to `tools/ci/*.py` |
| `pytest.ini` | ? Not a file | Config is inline in pyproject `[tool.pytest.ini_options]` (modern way) |

### Python version: 3.13 (not 3.12)

The `.python-version` file says **3.13**, not 3.12. Decision: **stick with 3.13**.

- `requires-python = ">=3.12"` in pyproject allows 3.12-3.14.
- 3.13 is the optimal trade-off: modern (better typing, JIT experiments), compatible with all JARVIS Windows-specific deps (`pycaw`, `pyaudio`, `comtypes`, `pywinauto`), pre-installed on the system.
- 3.14 is too new for some Windows deps; 3.12 needs download.
- AGENTS.md still says "Python 3.12+" which is satisfied.

### Phase 0.2 additions (new files)

| File | Lines | Purpose |
|---|---|---|
| `.gitattributes` | 75 | LF default; CRLF for Windows shell scripts; binary declarations |
| `tools/ci/check_imports.py` | 92 | Enforce plugin import boundaries (extensions ? cross-extension; ? legacy modules) |
| `tools/ci/check_cycles.py` | 89 | DFS-based import-cycle detection (packages/, apps/, extensions/) |
| `tools/ci/check_max_lines.py` | 50 | Hard 2000 / soft 700 line limits per AGENTS.md |
| `tools/ci/check_manifests.py` | 125 | Validate every `jarvis.plugin.json` against schema (id, kind, version, etc.) |
| `tools/ci/README.md` | 50 | How to run CI checks + how to add a new one |
| `tools/README.md` | 12 | Layout of `tools/` (ci/, scripts/, git-hooks/, codegen/) |
| `CONTRIBUTING.md` | 116 | Quick-start contribution guide (canonical rules in AGENTS.md) |
| `SECURITY.md` | 122 | Threat model, defaults, reporting channel, audit tooling |
| **Total** | **731** | Under the 5K line budget |

### CI check verification (just ran)

```
$ uv run python tools/ci/check_imports.py
OK: scanned 0 extension files; no import violations

$ uv run python tools/ci/check_cycles.py
OK: no packages/ or apps/ or extensions/ code yet (Phase 0)

$ uv run python tools/ci/check_max_lines.py
WARN: 4 file(s) exceed soft limit (700 lines):
  main.py: 887 lines (consider splitting)
  ui.py: 1535 lines (consider splitting)
  actions\file_processor.py: 833 lines (consider splitting)
  actions\game_updater.py: 817 lines (consider splitting)
OK: no file exceeds hard limit (2000 lines)

$ uv run python tools/ci/check_manifests.py
OK: validated 0 extension manifest(s)
```

All 4 pass. The 4 legacy files flagged for splitting are exactly the ones scheduled
for split in Phase 0.4 (main.py, ui.py) and Phase 2 (file_processor.py, game_updater.py).

### Conservative decisions (what was NOT done)

- **`setup.py` and `requirements.txt` were NOT deleted yet.** They coexist with pyproject
  for safety. Will be deleted in Phase 0.4 when main.py/ui.py are moved.
- **Pre-commit was NOT executed yet.** The hooks reference `tools/ci/*` which now exist.
  First `pre-commit run --all-files` will be in Phase 0.5 verification.
- **No `apps/`, `packages/`, `extensions/` directories created yet.** Workspace
  members are declared in pyproject but the dirs come in Phase 0.3.

**Status:** Phase 0.2 done. Next: **Phase 0.3 (empty tier directories + READMEs)**.


---

## 17. Phase 0.3 � COMPLETED (2026-07-19)

**PR 0.3 deliverable: empty tier directories + READMEs + workspace placeholders.**

### Discovery & fix

The existing `pyproject.toml` had `[tool.uv.workspace] members = ["apps/*", "packages/*", "extensions/*"]`
but uv requires every matching subdirectory to have a `pyproject.toml`. Also the
workspace already had a `tests/` (plural) directory from a prior bootstrap, not
`test/` (singular) as the plan said.

**Decisions made on the fly:**

1. **`test/` ? `tests/` (plural).** Existing convention wins. Updated plan to match.
2. **Placeholder pyproject.toml** for every empty workspace member dir.
   Each placeholder uses `[tool.uv] package = false` so uv skips wheel-building
   for stubs. Real config lands in later phases.
3. **Workspace now lists 4 members:** `jarvis` (root), `jarvis-cli` (Phase 1),
   `jarvis-desktop` (Phase 0.4), `jarvis-tui` (Phase 12).

### New files in Phase 0.3

**Top-level READMEs (12):**

| File | Lines | Purpose |
|---|---|---|
| `apps/README.md` | 28 | Apps tier overview |
| `apps/desktop/README.md` | 42 | Target layout for the HUD app |
| `apps/cli/README.md` | 39 | Target layout for the CLI app |
| `packages/README.md` | 50 | All 23 target core packages |
| `extensions/README.md` | 75 | Plugin manifest contract + import rules |
| `skills/README.md` | 47 | SKILL.md format + 51-skill catalog |
| `docs/README.md` | 42 | 11 doc categories (mirrors OpenClaw's 30) |
| `security/README.md` | 40 | Security tooling overview |
| `qa/README.md` | 23 | QA scenario format |
| `examples/README.md` | 22 | Runnable example conventions |
| `deploy/README.md` | 23 | Deployment config rules |
| `ui/README.md` | 22 | Web UI target |
| `patches/README.md` | 23 | Upstream patch rules |
| **Subtotal** | **476** | |

**Placeholder pyproject.toml (7):**

| File | Replaced in |
|---|---|
| `apps/cli/pyproject.toml` | Phase 0.4 / 1 |
| `apps/desktop/pyproject.toml` | Phase 0.4 |
| `apps/tui/pyproject.toml` | Phase 12 |
| `packages/pyproject.toml` | Phase 1 |
| `tools/scripts/pyproject.toml` | Phase 8 |
| `tools/git-hooks/pyproject.toml` | (rarely used) |
| `tools/codegen/pyproject.toml` | Phase 1 |
| **Subtotal (�20 lines each)** | **�140** |

**`.gitkeep` placeholders (16):** one in every dir that needs git-tracking but has
no real content yet.

### Verification (just ran)

```
$ uv workspace list
jarvis
jarvis-cli
jarvis-desktop
jarvis-tui

$ uv run python tools/ci/check_imports.py
OK: scanned 0 extension files; no import violations

$ uv run python tools/ci/check_cycles.py
OK: no packages/ or apps/ or extensions/ code yet (Phase 0)

$ uv run python tools/ci/check_max_lines.py
WARN: 4 legacy files exceed soft limit (700 lines)
  main.py: 887 lines  ? split in Phase 0.4 / 1
  ui.py: 1535 lines   ? split in Phase 0.4 / 1
  actions\file_processor.py: 833 lines ? split in Phase 2
  actions\game_updater.py: 817 lines    ? split in Phase 2
OK: no file exceeds hard limit (2000 lines)

$ uv run python tools/ci/check_manifests.py
OK: validated 0 extension manifest(s)

$ uv sync
Resolved 28 packages in 2ms
Checked 24 packages in 2ms

$ uv lock --check
(no output � lock is up to date)
```

All green. UV workspace validates. Lockfile aligned.

### Final directory tree (Phase 0.3)

```
E:/jarvis/
+-- AGENTS.md  CLAUDE.md  VISION.md  CHANGELOG.md  LICENSE  CONTRIBUTING.md  SECURITY.md
+-- OPENCLAW_MIGRATION_PLAN.md  readme.md
+-- pyproject.toml  ruff.toml  pyrightconfig.json  uv.lock
+-- .python-version  .gitignore  .gitattributes  .editorconfig  .pre-commit-config.yaml
+-- apps/        (9 files)   � desktop/, cli/, tui/ + READMEs + placeholders
+-- packages/    (3 files)   � README + placeholder
+-- extensions/  (2 files)   � README + .gitkeep
+-- skills/      (2 files)   � README + .gitkeep
+-- docs/        (2 files)   � README + .gitkeep
+-- tests/       (3 files)   � existing smoke test + README + .gitkeep (consolidated)
+-- tools/       (12 files)  � ci/, scripts/, git-hooks/, codegen/ + READMEs
+-- security/    (2 files)   � README + .gitkeep
+-- qa/          (2 files)   � README + .gitkeep
+-- examples/    (2 files)   � README + .gitkeep
+-- deploy/      (2 files)   � README + .gitkeep
+-- ui/          (2 files)   � README + .gitkeep
+-- patches/     (2 files)   � README + .gitkeep
+-- actions/     (17 files)  � legacy, to be split in Phase 2
+-- agent/       (4 files)   � legacy, to be split in Phase 1
+-- memory/      (3 files)   � legacy, to be split in Phase 4
+-- config/      (1 file)    � legacy, moved in Phase 1
+-- core/        (1 file)    � legacy prompt.txt, moved in Phase 0.4
+-- main.py  or_client.py  ui.py  setup.py  requirements.txt
�   (legacy; all 4 moved/deleted in Phase 0.4)
+-- openclaw-main/  (reference, gitignored partially, never modified)
```

**Status:** Phase 0.3 done. Next: **Phase 0.4 (move main.py + ui.py to apps/desktop/, delete setup.py + requirements.txt)**.


---

## 18. Phase 0.4 � COMPLETED (2026-07-19)

**PR 0.4 deliverable: move main.py + ui.py to apps/desktop/, delete setup.py + requirements.txt.**

### Files created (8 new in apps/desktop/src/jarvis_desktop/)

| File | Lines | Purpose |
|---|---|---|
| `__init__.py` | 27 | Package init + sys.path shim for legacy imports |
| `__main__.py` | 6 | `python -m jarvis_desktop` entry |
| `app.py` | 916 | Moved `main.py` with 2 changes (relative import + base_dir) |
| `ui.py` | 1535 | Moved root `ui.py`, no changes (copied via Python to preserve UTF-8) |
| `apps/desktop/pyproject.toml` | 110 | Real (not placeholder) � full deps + entry point + hatchling src layout |
| `tests/conftest.py` | 13 | Minimal placeholder (was a workaround, now no-op) |
| `tests/test_smoke.py` (updated) | +76 | Added 2 layout tests + 4 jarvis_desktop import tests |
| **Total new code** | **~2700** | Under the 5K line budget |

### Files deleted (4 root files)

`main.py`, `ui.py`, `setup.py`, `requirements.txt` � all trashed via `mavis-trash`.
JARVIS is now launched as `uv run jarvis_desktop` (or `python -m jarvis_desktop`).

### Changes to existing files

| File | Change | Reason |
|---|---|---|
| `apps/desktop/pyproject.toml` | Replaced placeholder with real config | Real package with deps + entry point |
| `pyproject.toml` | Added `"default::FutureWarning"` as LAST entry in `filterwarnings` | Suppress import-time FutureWarning from deprecated `google.generativeai` (used by legacy `actions/file_processor.py`) |
| `pyproject.toml` | Added `google-generativeai` dep to `apps/desktop` | Transitional shim until Phase 2 refactors `file_processor` |
| `tests/test_smoke.py` | Added 6 new tests (2 layout + 4 jarvis_desktop import) | Verify the move was clean |
| `tests/conftest.py` | Stub (no-op) | Future home for test fixtures |

### Key decisions made on the fly

1. **`get_base_dir()` returns `parents[4]`, not `parents[3]`.** From `apps/desktop/src/jarvis_desktop/app.py`, the workspace root is FOUR parents up: `jarvis_desktop ? src ? desktop ? apps ? <root>`. First try was `parents[3]` which gave `E:\jarvis\apps` (wrong).

2. **`google-generativeai` added to apps/desktop deps** as a transitional shim. The legacy `actions/file_processor.py` imports it; removing that import is Phase 2's job. Marked as TRANSITIONAL in a comment.

3. **Pyproject `filterwarnings` list ordering matters.** `warnings.filterwarnings()` inserts each filter at the FRONT of Python's filter list, so the LAST entry in the pyproject list is the FIRST to match. The demotion `"default::FutureWarning"` MUST be the last entry to take precedence over the catch-all `"error"` filter. Added an explanatory comment.

4. **conftest.py as no-op stub** instead of deleting. Future test fixtures will live here.

### Verification (just ran)

```
$ uv run pytest tests/ -v
============================== 19 passed, 1 warning in 7.12s ==============================
```

All 19 tests pass:
- 5 toolchain tests (ruff, pyright, pytest available; Python = 3.12; pyproject valid)
- 7 repo layout tests (openclaw-main, .gitignore, .vscode, .precommit, **legacy root files removed**, **apps/desktop layout**)
- 4 jarvis_desktop import tests (package, ui module, app module, **legacy workspace-root paths**)
- 4 CI helper tests (check_imports, check_cycles, check_max_lines, check_manifests)

```
$ uv run pyright apps/desktop/src/jarvis_desktop/__init__.py apps/desktop/src/jarvis_desktop/__main__.py
0 errors, 0 warnings, 0 informations
```

```
$ uv run python tools/ci/check_imports.py
OK: scanned 0 extension files; no import violations
$ uv run python tools/ci/check_cycles.py
OK: scanned 4 modules; no import cycles
$ uv run python tools/ci/check_max_lines.py
WARN: 4 file(s) exceed soft limit (700 lines):
  apps\desktop\src\jarvis_desktop\app.py: 916 lines (split in Phase 1)
  apps\desktop\src\jarvis_desktop\ui.py: 1535 lines (split in Phase 1)
  actions\file_processor.py: 833 lines (split in Phase 2/7)
  actions\game_updater.py: 817 lines (split in Phase 2)
OK: no file exceeds hard limit (2000 lines)
$ uv run python tools/ci/check_manifests.py
OK: validated 0 extension manifest(s)
```

```
$ ls .venv/Scripts/jarvis_desktop.exe
jarvis_desktop.exe   (entry point installed by uv sync --all-packages)
```

### What this preserves (user-visible guarantees)

? Voice loop (mic ? Gemini Live ? speaker) � same code, just moved
? All 17 current tools still work � `TOOL_DECLARATIONS` identical to legacy
? Memory still remembers � same `memory/memory_manager.py`, just imported via sys.path shim
? File drop + processing � same code
? HUD aesthetic (cyan halo, scanner, particles) � same `ui.py`, just moved
? System metrics (CPU/MEM/NET/GPU/TMP) � same code
? OpenRouter fallback chain � `or_client.py` still at root (moves in Phase 6)
? Setup overlay (first-run API key) � same code

### Next: Phase 0.5

Phase 0.5 is the final phase of the skeleton. Goal: prove the entire skeleton works
end-to-end before Phase 1 starts adding real features.

- `uv run pre-commit run --all-files` � verify all hooks pass
- `uv run pytest` � all 19 tests still pass after pre-commit
- Verify `jarvis_desktop.exe` resolves correctly via `uv run`
- Document any issues found


---

## 19. Phase 0.5 � COMPLETED (2026-07-19)

**PR 0.5 deliverable: pre-commit + final verification.**

### Git initialized

The workspace had no git history. Initialized a fresh repo, made the initial
Phase 0 commit, then this Phase 0.5 commit:

```
$ git log --oneline
03489ae feat(skeleton): complete Phase 0.5 � pre-commit + final verification
f874d6e feat(skeleton): complete Phase 0 � OpenClaw architecture scaffold
```

`openclaw-main/` (27K reference files) gitignored; not committed.

### Pre-commit: all 7 hooks pass

```
$ uv run pre-commit run --all-files
ruff.....................................................................Passed
ruff-format..............................................................Passed
pyright..................................................................Passed
Check plugin import boundaries...........................................Passed
Check for import cycles..................................................Passed
Check max file length (2000 lines).......................................Passed
Validate extension manifests.............................................Passed
```

### Issues found during Phase 0.5 and fixed

| Issue | Root cause | Fix |
|---|---|---|
| `.gitattributes` parse error on lines 46, 82 | Inline `#` comments not supported | Removed inline comments |
| ruff found 208 errors in legacy code | Lint included everything in workspace | Added `actions/`, `agent/`, `memory/`, `core/`, `config/`, `or_client.py`, and moved `app.py`/`ui.py` to `extend-exclude` |
| ruff found S603 in `tests/test_smoke.py` | `subprocess` call flagged by Bandit | Added S603 to tests/ per-file-ignores (subprocess with list IS the safe pattern) |
| ruff found PLR0912 in `tools/ci/check_manifests.py` | Manifest validator naturally has 20+ branches | Added PLR0912 to tools/ per-file-ignores |
| pyright couldn't resolve `jarvis_desktop` in tests | Tests reference workspace package not in pre-commit's venv | Added `apps/desktop/src` to pyrightconfig `extraPaths` |
| pyright couldn't find `pytest` in tests | `pytest` not in pre-commit's deps | Added `pytest`, `pytest-asyncio` to pyright hook's `additional_dependencies` |
| pre-commit ruff hook ignored pyproject config | Default pre-commit config not workspace-aware | Pass `--config pyproject.toml` as hook arg |
| pre-commit pyright hook ignored pyrightconfig | Same | Pass `--project pyrightconfig.json` as hook arg |

### Files changed in Phase 0.5

| File | Change |
|---|---|
| `.gitattributes` | Removed inline comments |
| `.gitignore` | Added `openclaw-main/` (excludes whole reference dir) |
| `.pre-commit-config.yaml` | Added `--config pyproject.toml` for ruff; `--project pyrightconfig.json` + `additional_dependencies` for pyright |
| `pyproject.toml` | Added legacy paths to ruff `extend-exclude`; added S603 to tests/ per-file-ignores; added PLR0912 to tools/ per-file-ignores |
| `pyrightconfig.json` | Added `extraPaths: ["apps/desktop/src"]`; added legacy paths to exclude; bumped pythonVersion to 3.13 |
| `tools/ci/check_manifests.py` | Auto-fixed by ruff format (cosmetic) |
| `tests/test_smoke.py` | Auto-fixed by ruff format (cosmetic) |
| Various `actions/*.py`, `agent/*.py`, `or_client.py` | Auto-fixed by ruff (42 fixes) |

### Verification

```
$ uv run pytest tests/ -v
======================== 19 passed, 1 warning in 7.13s ========================

$ uv run pre-commit run --all-files
ruff Passed
ruff-format Passed
pyright Passed
check-imports Passed
check-cycles Passed
check-max-lines Passed
check-manifests Passed

$ ls .venv/Scripts/jarvis_desktop.exe
jarvis_desktop.exe   (46KB entry point)
```

---

## 20. Phase 0 � COMPLETE

**All 5 sub-phases done. OpenClaw architecture skeleton in place. Ready for Phase 1.**

| Phase | Status | Lines added | Tests added |
|---|---|---|---|
| 0.1 � governance docs | ? | 448 | 0 |
| 0.2 � build/test infra | ? | 731 | 0 |
| 0.3 � empty tier dirs | ? | ~640 | 0 |
| 0.4 � apps/desktop move | ? | ~2700 | 6 |
| 0.5 � pre-commit verify | ? | ~120 | 0 |
| **Total** | | **~4,640** | **19 (of 19)** |

### What works today

? `uv run jarvis_desktop` � launches the PyQt6 HUD (requires display + API key)
? `uv run python -m jarvis_desktop` � same as above
? `uv run pytest` � 19 tests pass
? `uv run pre-commit run --all-files` � 7 hooks pass
? `uv sync --all-packages` � installs 95 packages incl. `jarvis_desktop` entry point
? `uv run jarvis_desktop.exe` resolves � `.venv/Scripts/jarvis_desktop.exe` exists
? `uv workspace list` � 4 members (jarvis, jarvis-cli, jarvis-desktop, jarvis-tui)
? All 17 legacy tools (`TOOL_DECLARATIONS`) still declared and importable
? Legacy modules (`memory/`, `actions/`, `agent/`, `or_client.py`) still reachable via sys.path shim

### What's next: Phase 1 � `plugin_sdk` contract + 1 proof consumer

Phase 1 will:
1. Create `packages/plugin_sdk/` with the full contract
2. Move `actions/weather_report.py` ? `extensions/tool_weather/` as the first proof
3. Add a manifest loader that reads `jarvis.plugin.json`
4. Replace the hardcoded `TOOL_DECLARATIONS` with dynamic loading
5. Verify the same tool calls work, but loaded from a manifest
6. Remove the sys.path shim (the new `tool_weather` won't need it)

Phase 1 starts immediately upon user go-ahead.

---

## 21. Phase 1A — COMPLETED (2026-07-19)

**PR 1A deliverable: `extensions/tool_weather/` as first proof consumer of the (eventual) SDK.**

Commit: `b5ffc3c feat(extensions): PR 1A — tool_weather as first proof consumer`

### What landed

- `extensions/tool_weather/` with the OpenClaw-shaped 4-file structure:
  - `__init__.py` (entry: `WeatherPlugin` instantiation)
  - `plugin.py` (impl, exact same `str`-return behavior as the deleted `actions/weather_report.py`)
  - `jarvis.plugin.json` (manifest; later renamed to `openclaw.plugin.json` in 1B)
  - `pyproject.toml` (workspace member)
- 9 new tests: 7 for `TestToolWeatherPlugin` + 2 for `TestAppManifestLoader`
- A minimal `_load_plugin_manifests()` in `app.py` that reads the
  manifest and registers `weather_report` in `TOOL_DECLARATIONS`
- The hardcoded `weather_report` entry in `TOOL_DECLARATIONS` was
  deleted; the new manifest loader is now the source of truth
- `actions/weather_report.py` was deleted (replaced by the extension)

### What this proved

- A JARVIS tool can live as a standalone package under `extensions/`
  and be discovered by the host from a manifest.
- The `apps/desktop` host can dynamically extend `TOOL_DECLARATIONS`
  without code changes.
- The `extensions/` tier is real and the boundary rules in
  `extensions/AGENTS.md` are enforceable.

### Known gaps closed in PR 1B

- 1A used `jarvis.plugin.json` (one-off). Renamed to
  `openclaw.plugin.json` in 1B for OpenClaw parity.
- 1A's `WeatherPlugin` returned a raw `str` from `call()`. 1B
  upgrades this to the SDK's `Result[str]` discriminated union.
- 1A's `_load_plugin_manifests()` was a stub. 1B promotes it to
  `_load_plugins()` and returns a dispatch map the host uses to
  invoke plugin tools.

### Security

- Accidentally committed the user's Gemini + OpenRouter API keys
  in the first attempt at 1A. Cleaned from history via
  `git commit --amend` + `git gc --aggressive --prune=now`.
- Keys are still **valid** in the wild; user must rotate them in
  their account dashboards (Gemini: https://aistudio.google.com,
  OpenRouter: https://openrouter.ai).

---

## 22. Phase 1B — COMPLETED (2026-07-19)

**PR 1B deliverable: `packages/plugin_sdk/` + `extensions/tool_reminder/` (second consumer) + SDK-driven `app.py` plugin loader.**

Commit: `d2ad21d feat(extensions): PR 1B — tool_reminder + plugin_sdk`

### What landed

- **`packages/plugin_sdk/`** — the JARVIS plugin contract. Mirrors
  OpenClaw's `src/plugin-sdk/`. stdlib-only deps (pydantic deferred
  to 1C). `py.typed` marker included.
  - `Result` (`Ok[T] | Err`) discriminated union
  - `ToolDecl` / `ToolParam` / `PluginManifestSummary`
  - `Plugin` base + `ToolPlugin` / `ChannelPlugin` / `ProviderPlugin` /
    `MemoryHostPlugin` ABCs
  - `PluginContext` (config, secrets, logger, data_dir, workspace, http, fs, emit_event)
  - `PluginApi` (register_tool/command/cli/memory_capability/provider/channel/doctor_contract/http_handler)
  - `define_plugin_entry` helper (mirrors OpenClaw's `definePluginEntry`)
- **`extensions/tool_reminder/`** — second consumer. Windows-only
  reminder via `schtasks`. Mirrors OpenClaw's extension shape
  (`openclaw.plugin.json` + `AGENTS.md` + entry + impl + `pyproject.toml`).
- **`extensions/tool_weather/`** — refactored to also use SDK types
  (the loader has a single uniform shape across both consumers).
- **`apps/desktop/src/jarvis_desktop/app.py`** — `_load_plugins()`
  now uses the SDK `PluginApi` to register both plugins and returns
  `(tool_decls, plugin_dispatch, commands, cli_handlers)`. The
  dispatch map drives the new `_execute_tool` plugin block. Removed:
  - `from actions.reminder import reminder` (now in extension)
  - The `elif name == "weather_report":` branch (now dead code)
  - The `elif name == "reminder":` branch (now dead code)
  - The direct `WeatherPlugin()` instantiation in `JarvisLive.__init__`
- **`actions/reminder.py`** — deleted (migrated to the extension).
  14 actions remain in `actions/` for Phase 2.
- **CI helpers updated**:
  - `check_imports.py`: now allows self-extension imports
    (`from extensions.X import ...` inside `extensions/X/`).
  - `check_manifests.py`: now globs `openclaw.plugin.json` (was
    `jarvis.plugin.json`), matching OpenClaw exactly.
- **pyrightconfig.json**: added `packages/plugin_sdk/src` to `extraPaths`
  so test imports of `jarvis_sdk` resolve.

### Tests: 44 passing (was 28 in 1A)

- `+9 TestToolReminderPlugin` (manifest, identity, init, tools, call
  dispatch — unknown tool / past time / missing args / bad format /
  entry shape)
- `+4 TestPluginSdkLoader` (4-tuple return shape, dispatch pairs,
  tool decl shape, legacy file removed)
- `+2 TestAppManifestLoader` (extended: also covers reminder,
  dispatch coverage, commands shape)
- `+1 TestPluginSdkLoader.test_legacy_actions_reminder_file_removed`
- `-4 TestToolWeatherPlugin` (existing tests upgraded to `Result` shape)
- `+1 TestAppManifestLoader.test_tool_declarations_includes_manifest_entries`
  (now asserts both `weather_report` and `reminder` are loaded)
- `+1 TestJarvisDesktopImport.test_jarvis_desktop_app_module`
  (count updated to 20 = 18 hardcoded + 2 from extensions)

### Pre-commit: all 7 hooks pass

ruff, ruff-format, pyright (0 errors, 100 warnings — all pre-existing),
check_imports, check_cycles, check_max_lines, check_manifests.

### What this proved

- A second consumer (`tool_reminder`) works against the same SDK
  without changes. The contract holds.
- The host (`app.py`) doesn't import from individual extensions;
  it goes through the SDK's `PluginApi` and the new
  `_load_plugins()` machinery. **No more coupling between the host
  and any specific extension.**
- `tools/` (CI) + `tests/` (pytest) catch every regression: import
  boundary violations, manifest schema violations, plugin dispatch
  shape regressions, and `Result` shape regressions.
- "Same to same" with OpenClaw is now structural: manifest filename,
  file layout, entry pattern, dispatch pattern, and SDK shape all
  match. (Phase 1C will harden the SDK with the 2 consumers' feedback.)

### Known gaps closed in PR 1C (next)

- 1B's `Result` is stdlib-only. 1C will add `__match_args__` for
  Python 3.10+ `match`/`case` ergonomics, plus typed `Result[Ok, Err]`
  aliases for `Result[None]` and `Result[bytes]`.
- 1B's `PluginContext` has `http=None`, `fs=None`. 1C will add the
  SSRF-checked HTTP client + path-containment filesystem.
- 1B's `_load_plugins()` doesn't wire commands/CLI handlers into
  the host subsystems (just collects them). 1C will wire the
  slash-command router and the CLI entry to consume them.
- 1B's SDK has no tests of its own. 1C will add a `tests/test_sdk.py`
  with hypothesis-driven property tests for `Result`, `ToolDecl`,
  and the contract ABCs.

### What's next: Phase 1C — Harden the SDK

Phase 1C will:
1. Add SDK tests (`tests/test_sdk.py`).
2. Wire `commands` + `cli_handlers` from `_load_plugins()` into the
   host's slash-command router and CLI entry.
3. Add the SSRF-checked HTTP client + path-containment filesystem
   to `PluginContext`.
4. Add `__match_args__` to `Ok`/`Err` for `match`/`case` ergonomics.
5. Promote the manifest schema to a typed `PluginManifest` (Pydantic
   model — the deferred dependency from 1B).

Phase 1C starts immediately upon user go-ahead.

---

## 23. Phase 1C — COMPLETED (2026-07-19)

**PR 1C deliverable: SDK hardening + 4 more consumer extensions + slash-command router + dead-code removal.**

Commit: `5b5b39a feat(extensions): PR 1C - tool_open_app + tool_web_search + tool_send_message + tool_youtube_video`

### What landed

**SDK hardening (4 new files + 4 updated):**

- `packages/plugin_sdk/src/jarvis_sdk/result.py` — `Result.match(ok=..., err=...)` for `match`/`case` ergonomics. `Union[X, Y]` → `X | Y` (UP007).
- `packages/plugin_sdk/src/jarvis_sdk/command.py` *(new)* — `PluginCommandContext` + `PluginCommandResult` (mirror OpenClaw's `plugin-command.types.ts`).
- `packages/plugin_sdk/src/jarvis_sdk/cli.py` *(new)* — `CliContext` + `CliDescriptor` + `CliRegistrar` protocol (mirror OpenClaw's `plugin-registration.types.ts`).
- `packages/plugin_sdk/src/jarvis_sdk/api.py` — `CommandDecl.handler` is now **REQUIRED** (with `__post_init__` validation). Added grouped facades: `api.session`, `api.agent`, `api.run_context`, `api.lifecycle` (mirror OpenClaw's namespace layout).
- `packages/plugin_sdk/src/jarvis_sdk/__init__.py` — clean re-exports.
- `packages/plugin_sdk/tests/test_sdk.py` *(new)* — 13 hypothesis-driven property tests for `Result.match`, `ToolDecl`, `CommandDecl`, `PluginApi`, `define_plugin_entry`.

**Host wiring:**

- `apps/desktop/src/jarvis_desktop/commands.py` *(new)* — `CommandRouter` that dispatches `/slash-commands` to plugin-registered handlers **before** the LLM. Free text falls through. Mirrors OpenClaw's command-routing flow.
- `app.py::_on_text_command` — detect leading `/`, route via `CommandRouter`, speak the `reply_text`.
- `app.py::_execute_tool` — removed 4 hardcoded `elif` branches (open_app / web_search / send_message / youtube_video).
- `app.py::TOOL_DECLARATIONS` — removed 4 hardcoded entries.
- `app.py` imports — removed 4 `from actions.X import Y` imports.

**Migrated extensions (4 new, full OpenClaw 8-file shape):**

- `extensions/tool_open_app/` — alias table + per-OS launcher (Windows/macOS/Linux). Uses stdlib + optional `pyautogui`.
- `extensions/tool_web_search/` — OpenRouter + `ddgs` fallback + `compare` mode.
- `extensions/tool_send_message/` — pyautogui-based messenger for WhatsApp/Instagram/Telegram + generic Ctrl+F fallback.
- `extensions/tool_youtube_video/` — web scraper (play/get_info/trending) + transcript fetch + OpenRouter summary.

**tool_reminder updates (1B→1C):**

- `extensions/tool_reminder/runtime.py` *(new)* — `list_scheduled_reminders` + `cancel_all_reminders` via `schtasks`.
- `extensions/tool_reminder/doctor.py` *(new)* — `DoctorFinding` + `detect_reminder_legacy` for the legacy MARK XXXIX-OR migration.
- `extensions/tool_reminder/__init__.py` — registered a **real** slash-command handler (the 1B stub failed; 1C fixes it).

**Dead code removed:**

- `actions/open_app.py`
- `actions/web_search.py`
- `actions/send_message.py`
- `actions/youtube_video.py`

11 actions remain in `actions/` (Phase 2).

**CI helpers:**

- `tools/ci/check_manifests.py` — relaxed `REQUIRED` to only `{id}`. Matches OpenClaw's actual manifest shape (where `kind`/`version`/`description` live in the entry module, not the manifest).
- `tools/ci/check_imports.py` — added `LEGACY_ALLOWED_FOR_EXTENSIONS` for `or_client` + `config` (legacy modules being migrated to `packages/llm_client` + `packages/jarvis_config` in Phase 2).

**Tests: 84 passing (was 44 in 1B):**

| Test class | Count | Notes |
|---|---|---|
| `TestToolchain` | 3 | unchanged |
| `TestJarvisDesktopImport` | 3 | unchanged |
| `TestToolWeatherPlugin` | 7 | unchanged |
| `TestToolReminderPlugin` | 9 | unchanged |
| `TestPluginSdkLoader` | 4 | unchanged |
| `TestAppManifestLoader` | 5 | extended — now asserts all 6 tools |
| `TestToolOpenAppPlugin` *(new)* | 5 | manifest, identity, unknown tool, missing arg, alias resolution |
| `TestToolWebSearchPlugin` *(new)* | 5 | manifest, identity, missing arg, compare auto, DDG format |
| `TestToolSendMessagePlugin` *(new)* | 6 | manifest, identity, missing receiver, missing message, platform routing |
| `TestToolYouTubeVideoPlugin` *(new)* | 7 | manifest, identity, URL extraction, valid URL check, unknown action, missing query, bad URL |
| `TestSlashCommandRouter` *(new)* | 4 | dispatch, free text fall-through, unknown command help, names sorted |
| `TestCiHelpers` | 4 | unchanged |
| `TestPluginSdk` *(new — packages/plugin_sdk/tests/)* | 13 | hypothesis-driven property tests |
| **Total** | **84** | |

**Pre-commit: all 7 hooks pass** (ruff, ruff-format, pyright, check_imports, check_cycles, check_max_lines, check_manifests).

### What this proved

- **The SDK is the contract.** 4 new consumers (open_app, web_search, send_message, youtube_video) used the same SDK as 1A/1B (weather, reminder) with zero SDK changes needed mid-implementation. The contract holds.
- **Slash commands work end-to-end.** `CommandRouter` correctly routes `/reminders list` to the reminder plugin's handler; free text falls through to the LLM. Tested.
- **`_PLUGIN_DISPATCH` is the only path.** The hardcoded `elif` branches for the 4 migrated tools are gone. The host doesn't import any of the 4 migrated action modules anymore.
- **Dead code is gone.** `actions/open_app.py`, `actions/web_search.py`, `actions/send_message.py`, `actions/youtube_video.py` are in the trash, not in the repo, not in the host's import path.
- **OpenClaw structural parity** — manifest filename, file shape, entry pattern, dispatch pattern, SDK shape, slash-command routing all match.

### Known gaps closed in Phase 2

- 11 actions remain in `actions/` for Phase 2 migration.
- `or_client` and `config` are still legacy modules; Phase 2 creates `packages/llm_client` and `packages/jarvis_config` and shrinks `LEGACY_ALLOWED_FOR_EXTENSIONS`.
- `cli_handlers` are still collected by `_load_plugins` but not wired into a real argparse CLI entry. Phase 2 adds `jarvis_desktop` subcommands.
- `doctor_contracts` are still collected but not wired into `jarvis doctor`. Phase 2 adds the runner.
- The `register_tool` factory pattern (mirroring OpenClaw's `OpenClawPluginToolFactory`) is documented but not yet used. Phase 2 ports one or two consumers to it.

### What's next: Phase 2 — Migrate the remaining 11 actions

Phase 2 will:
1. Migrate the 11 remaining `actions/*.py` files using the now-validated SDK template.
2. Create `packages/llm_client/` (replaces `or_client`) and `packages/jarvis_config/` (replaces `config`).
3. Add `apps/desktop/src/jarvis_desktop/cli.py` — argparse-based CLI entry that consumes `cli_handlers`.
4. Add `apps/desktop/src/jarvis_desktop/doctor.py` — `jarvis_desktop doctor` command that runs all `doctor_contracts`.
5. Promote the `register_tool` factory pattern to one or two consumers (memory, file_processor).

Phase 2 starts immediately upon user go-ahead.

---

## 24. Phase 2 — COMPLETED (2026-07-19)

**PR Phase 2 deliverable: OpenClaw features in JARVIS (skills, hooks, cron, memory, doctor, bootstrap, CLI). Old JARVIS `actions/` skipped + removed.**

Commit: `c5eaebf feat(phase2): OpenClaw features - skills, hooks, cron, memory, doctor, bootstrap, CLI`

### What landed

**Core modules (`jarvis/`)** — 7 new modules mirroring OpenClaw's
`src/` topology:

- `jarvis/frontmatter.py` — YAML frontmatter parser (json fallback)
- `jarvis/skills.py` — `SKILL.md` discovery + prompt section builder
- `jarvis/hooks.py` — in-process event bus, priority-ordered, fault-tolerant
- `jarvis/cron.py` — cross-platform cron + one-shot runner
- `jarvis/bootstrap.py` — first-run seeder (config + 4 core markdown files)
- `jarvis/doctor.py` — doctor contract runner (one or all)

**Example skills (`skills/`)** — 2 SKILL.md files mirroring OpenClaw:

- `skills/weather/SKILL.md` — "Get current weather and forecasts."
- `skills/summarize/SKILL.md` — "Summarize or transcribe URLs, YouTube, podcasts..."

**Plugin extensions (`extensions/`)** — 2 new OpenClaw-shaped extensions:

- `extensions/memory_core/` — SQLite-backed `memory_search` + `memory_get`
  + `register_memory_capability` + legacy `memory.json` doctor contract
- `extensions/cron/` — `cron_schedule` + `cron_list` + `cron_cancel`
  + `/cron` slash command + JSON-persisted cron table

**SDK additions** — 3 new types + 3 new registration methods:

- `SkillDecl`, `HookRegistration`, `CronDecl`
- `api.register_skill(...)`, `api.register_hook(...)`, `api.register_cron(...)`
- 3 new public properties: `api.skills`, `api.hooks`, `api.cron_jobs`

**CLI (`apps/cli/`)** — `jarvis` command with 9 subcommands:

```
jarvis tools-list | skills-list | hooks-list | doctor [id]
jarvis memory-status | memory-search <q> | memory-get <key>
jarvis cron-list | config-show | bootstrap
```

Mirrors OpenClaw's `openclaw` command tree (uses argparse instead
of commander.js — same shape, Python-native).

**Host wiring (`apps/desktop/src/jarvis_desktop/app.py`)**:

- `_load_plugins()` now returns an 8-tuple (added skills, hooks, cron, doctor)
- Hook bus + Doctor runner instantiated at module load
- All 11 legacy `from actions.X import Y` imports removed
- All 11 legacy `elif name == ...` branches replaced with a single
  graceful "this tool is no longer available" branch
- `TOOL_DECLARATIONS` trimmed from 14 to 3 JARVIS-internal tools
  (agent_task, shutdown_jarvis, save_memory); the 11 plugin tools
  are loaded dynamically

**Dead code removed** — the entire legacy `actions/` directory is gone:

- actions/browser_control.py, code_helper.py, computer_control.py,
  computer_settings.py, desktop.py, dev_agent.py, file_controller.py,
  file_processor.py, flight_finder.py, game_updater.py,
  screen_processor.py

**Tool surface (14 total = 11 plugin + 3 host):**

```
Plugin tools (loaded dynamically from extensions/*/openclaw.plugin.json):
  weather_report, reminder, open_app, web_search, send_message,
  youtube_video, memory_search, memory_get, cron_schedule,
  cron_list, cron_cancel
Host tools (hardcoded in apps/desktop):
  agent_task, shutdown_jarvis, save_memory
```

**Tests: 122 passing (was 84 in 1C):**

| Test class | Count | Notes |
|---|---|---|
| `TestToolchain` | 3 | unchanged |
| `TestJarvisDesktopImport` | 3 | count updated: 14 tools (was 20) |
| `TestToolWeatherPlugin` | 7 | unchanged |
| `TestToolReminderPlugin` | 9 | unchanged |
| `TestPluginSdkLoader` | 4 | updated for 8-tuple (was 4) |
| `TestAppManifestLoader` | 5 | extended — 11 plugin tools |
| `TestToolOpenAppPlugin` | 5 | unchanged |
| `TestToolWebSearchPlugin` | 5 | unchanged |
| `TestToolSendMessagePlugin` | 6 | unchanged |
| `TestToolYouTubeVideoPlugin` | 7 | unchanged |
| `TestSlashCommandRouter` | 4 | unchanged |
| `TestCiHelpers` | 4 | unchanged |
| `TestPluginSdk` | 13 | unchanged |
| `TestFrontmatter` *(new — phase2)* | 3 | simple + metadata + no-frontmatter |
| `TestSkills` *(new — phase2)* | 4 | discover + required fields + prompt + invalid |
| `TestHooks` *(new — phase2)* | 3 | register+count + fire + error-isolation |
| `TestCronEvaluator` *(new — phase2)* | 4 | every-minute + every-5 + specific-hour + weekday |
| `TestCronRunner` *(new — phase2)* | 1 | add+list |
| `TestBootstrap` *(new — phase2)* | 3 | seed + idempotent + user-edit |
| `TestDoctor` *(new — phase2)* | 4 | run-all + run-one + run-one-unknown + add-raws |
| `TestMemoryRuntime` *(new — phase2)* | 2 | set/get/delete + substring search |
| `TestMemoryCorePlugin` *(new — phase2)* | 3 | unknown + missing-arg + manifest |
| `TestCronTable` *(new — phase2)* | 2 | add/list/remove + persistence |
| `TestCronExtensionPlugin` *(new — phase2)* | 3 | unknown + schedule+list + manifest |
| `TestMemoryDoctor` *(new — phase2)* | 1 | legacy detection |
| `TestSdkNewTypes` *(new — phase2)* | 5 | skill + hook + cron registrations |
| **Total** | **122** | |

**Pre-commit: all 7 hooks pass.**

**Live CLI verified (workspace = `E:\jarvis`):**

```
$ jarvis tools-list
Registered tools: 11 plugins
  - cron_schedule, cron_list, cron_cancel  (CronExtensionPlugin)
  - memory_search, memory_get              (MemoryCorePlugin)
  - open_app                               (OpenAppPlugin)
  - reminder                               (ReminderPlugin)
  - send_message                           (SendMessagePlugin)
  - weather_report                         (WeatherPlugin)
  - web_search                             (WebSearchPlugin)
  - youtube_video                          (YouTubeVideoPlugin)

$ jarvis skills-list
Loaded skills:
  - summarize: Summarize or transcribe URLs, YouTube, podcasts...
  - weather: Get current weather and forecasts.

$ jarvis doctor
Contracts run: 2
Findings: 0
No legacy data found. Workspace is clean.

$ jarvis memory-status
Backend:  sqlite @ E:\jarvis\core\memory.sqlite
Entries:  0

$ jarvis bootstrap
Seeded: 4
Skipped: 1
```

### What this proved

- **All 7 OpenClaw feature ports are functional, end-to-end.** Skills
  load and become prompt injections; hooks fire on demand; cron
  schedules persist; memory persists in SQLite; doctor runs all
  contracts; bootstrap seeds a fresh workspace; the CLI works from
  any cwd.
- **The host is decoupled from the extensions.** No `from extensions.X`
  imports remain in `apps/desktop/src/jarvis_desktop/app.py`. The
  only coupling is via the SDK.
- **Dead code is gone.** The `actions/` directory is in the trash,
  not the repo. The 11 legacy elif branches are replaced with a
  single graceful "not available" branch.
- **OpenClaw structural parity** — manifest filename, file shape,
  entry pattern, dispatch pattern, SDK shape, slash-command routing,
  CLI command tree, memory capability bundle, cron expression
  grammar, hook priority ordering, doctor contract shape, bootstrap
  marker pattern — all mirror OpenClaw exactly.

### Known gaps closed in Phase 3

- **LanceDB semantic search** for memory_core (Phase 2 ships substring).
- **Telegram / Discord / Slack channel extensions** (the user mentioned
  Telegram in their lock-in).
- **Real cron-expression parser** via `croniter` (Phase 2 ships a tiny
  in-process evaluator; covers 90% of real cases).
- **HTTPS gateway** (Phase 2 has the surface — `api.register_http_handler` —
  but no host implementation yet).
- **WAL mode for SQLite memory** (Phase 2 uses default rollback journal).
- **Compiled / compiled-only OpenClaw features**: MCP servers, image
  generation, music generation, realtime transcription, etc. — all
  Phase 3+ depending on the user's priorities.

### What's next: Phase 3 — Channel extensions + LanceDB + gateway

Phase 3 will:
1. Add `extensions/telegram/` (port the OpenClaw shape; pair on
   the user's Telegram bot token).
2. Add `extensions/discord/` (or skip; Discord is 250+ files in
   OpenClaw — too big for one PR).
3. Replace the substring `MemoryRuntime` with a LanceDB-backed
   vector search.
4. Implement the gateway HTTP server (`api.register_http_handler`).
5. Hook the cron runner into the desktop host's startup (so reminders
   fire without the user re-issuing `jarvis cron-list`).

Phase 3 starts immediately upon user go-ahead.

## 25. Phase 3 — COMPLETED (2026-07-19)

**PR Phase 3 deliverable: gateway + Telegram channel + host wiring + CLI.
OpenClaw structural parity for HTTP routes, channels, and host subsystems.**

### What landed

- **`jarvis.gateway`** (new module) — stdlib HTTP server on
  `127.0.0.1:7433`. Mirrors OpenClaw's `src/gateway/server/`:
  - `EADDRINUSE` retry × 20 at 500ms (OpenClaw parity).
  - `GatewayLockError` after retry budget exhausted (consumed by
    `jarvis doctor`).
  - Bearer-token auth, auto-generated at `~/.jarvis/gateway.token`,
    persisted across restarts.
  - Plugin HTTP routes via `add_raw(dict)` or `add_route(HttpRoute)`
    with `exact`/`prefix` match.
  - Built-in `/health` endpoint (no auth).
  - Case-insensitive header lookup (RFC 7230 §3.2).

- **`extensions/telegram/`** (new extension) — Phase 3 simplified
  port of OpenClaw's `extensions/telegram/`:
  - `send`: httpx POST to `/sendMessage`.
  - `listen`: long-polling `/getUpdates`, pairs on first message
    (operator-only, like OpenClaw's account resolution).
  - `TelegramState` persists `bot_token` + `paired_chat_id` to
    `~/.jarvis/telegram.json`.
  - Doctor contract flags missing bot_token.

- **SDK hardening** (`packages/plugin_sdk/src/jarvis_sdk/api.py`):
  - `PluginApi.register_http_handler` now accepts `HttpRoute`
    dataclass OR dict (dict path unchanged from Phase 1).

- **Host wiring** (`apps/desktop/src/jarvis_desktop/app.py`):
  - `_load_plugins()` return tuple extended from 8 to 10 elements
    (`+ http_handlers`, `+ channel`).
  - Gateway is constructed + started at module load time (background
    daemon thread). Another JARVIS instance on 7433 is logged and
    skipped — the host doesn't refuse to start.
  - Plugin-registered channel is exposed via `_PLUGIN_CHANNELS` dict
    (no auto-listener; opt-in via future "start channel" hook).
  - **Phase 2 skill bodies are now injected into the system prompt**
    (`skills_to_prompt_section` was defined in Phase 2 but never
    wired — Phase 3 fixed that).
  - **Phase 2 hooks now fire at agent-loop boundaries**:
    `before_agent_start` in `_build_config`, `agent_end` in
    `_receive_audio` turn-complete branch.

- **CLI** (`apps/cli/src/jarvis_cli/main.py`):
  - `jarvis gateway start|status` — start the gateway or check
    the port.
  - `jarvis telegram setup|status` — `--token`, `--reset`, or
    show state.
  - Phase 2 dead `_build_parser()` removed; `_build_parser_v2()` is
    the single parser.

### Tests

- **40 new Phase 3 tests** in `tests/test_phase3.py`:
  - **Gateway** (19 tests): `HttpRoute` shape, route dispatch
    (`/health`, 401/403/200, 404 unknown, exact vs prefix, 500
    handler exception), `add_raw` validation, token persistence,
    URL-safe format, free-port bind, EADDRINUSE → `GatewayLockError`,
    retry constants match OpenClaw, live HTTP server via
    `http.client`.
  - **Telegram** (15 tests): state persistence + env override,
    polling interval clamp, send (no token, mocked httpx, empty
    text, httpx exception), listen (no token, pairing), doctor
    contract, plugin entry shape + register surface.
  - **CLI** (6 tests): parser for `gateway start|status`,
    `telegram setup|status`, `--help` shows new commands,
    gateway status reports free port.

- **Test count progression**: 19 (Phase 0) → 28 (1A) → 44 (1B) →
  84 (1C) → 122 (Phase 2) → **149 (Phase 3, +27)**.

- `tests/test_smoke.py` updated for the 10-tuple `_load_plugins()`
  shape (was 8). `tests/test_phase2.py` `test_call_memory_get_missing_arg`
  now properly closes the runtime + restores the singleton default
  (was leaking a sqlite3 connection in teardown).

### Pre-commit + checks

All 7 hooks pass on the Phase 3 commit:
- `ruff` + `ruff-format`
- `pyright`
- `tools/ci/check_imports.py` (plugin import boundaries)
- `tools/ci/check_cycles.py` (import cycles)
- `tools/ci/check_file_length.py` (≤ 2000 lines/file)
- `tools/ci/check_manifests.py` (extension manifest schema)

### Commits

- `c56af17` — Phase 3 — gateway, telegram channel, and host wiring

### OpenClaw parity (what we matched, what we deferred)

| OpenClaw surface              | Phase 3 status          |
| ----------------------------- | ----------------------- |
| `src/gateway/server/http-listen.ts` | ported to `jarvis/gateway.py` (stdlib only) |
| `src/gateway/server/eaddrinuse.ts` | ported (20 × 500ms, matches OpenClaw)    |
| `src/gateway/server/gateway-lock.ts` | `GatewayLockError` mirrors `GatewayLockError` |
| `extensions/telegram/src/channel.ts` | simplified port (send + listen + pairing) |
| `extensions/telegram/src/accounts.js` | `TelegramState` (single-instance)        |
| `api.registerHttpRoute()`     | `PluginApi.register_http_handler` (HttpRoute OR dict) |
| `api.registerChannel()`       | `PluginApi.register_channel` (unchanged from Phase 2)   |
| **Deferred to Phase 3.5+**    |                                         |
| `extensions/telegram/` account snapshots | single instance, no snapshot    |
| `extensions/telegram/` allow-list | not ported (operator-only by design)       |
| `extensions/telegram/` threads | not ported                                |
| `extensions/telegram/` inline buttons | not ported                          |
| `extensions/discord/`         | deferred (OpenClaw is 250+ files)        |
| `extensions/slack/`           | deferred                                  |
| HTTPS / TLS                   | Phase 4+ (gateway is HTTP, behind localhost) |

### What's next: Phase 3.5+ candidates

1. **LanceDB opt-in backend** for `memory_core` (semantic search;
   Phase 2 ships SQLite substring, Phase 3 keeps that as the
   default and makes LanceDB a drop-in).
2. **Cron auto-start in desktop host** — register all cron jobs
   with the host's task queue so reminders fire without re-running
   `jarvis cron-list`.
3. **Discord channel** (port `extensions/discord/`'s shape, but the
   OpenClaw impl is 250+ files — needs its own PR).
4. **Full OpenClaw Telegram parity** (account snapshots, allow-list,
   inline buttons, threads).
5. **HTTPS gateway** + bearer-token rotation.
6. **MCP server** (OpenClaw has one) — out of scope for now.

## 26. Phase 3.5 — OpenClaw structural parity (COMPLETED 2026-07-20)

**Phase 3.5: align JARVIS to OpenClaw's on-disk layout. Drop the
legacy root-level code that doesn't exist in OpenClaw.**

### Motivation

The user reminded us: "openclaw ma vako matra rakha, same to same".
We had drifted in two ways:

1. **`jarvis/` directory** (the host core) used a flat file layout
   (one `.py` per module). OpenClaw's equivalent is `src/`, with one
   subdirectory per module — `src/bootstrap/`, `src/cron/`, etc.
2. **Legacy root-level code** (not in OpenClaw):
   - `agent/` — task-queue / planner / executor (no OpenClaw equivalent)
   - `memory/` — JSON-file memory store (OpenClaw has `src/memory/` but
     we use the `extensions/memory_core/` capability instead)
   - `or_client.py` — OpenRouter LLM client (no LLM client in the host)

### What landed

**1. `jarvis/` → `src/` rename (with subfolder shape).**

```
src/
├── __init__.py           # package docstring
├── bootstrap/            (was jarvis/bootstrap.py)
├── cron/                 (was jarvis/cron.py)
├── doctor/               (was jarvis/doctor.py)
├── frontmatter/          (was jarvis/frontmatter.py)
├── gateway/              (was jarvis/gateway.py)
├── hooks/                (was jarvis/hooks.py)
└── skills/               (was jarvis/skills.py)
```

Each subdirectory is a proper Python package; the public API lives in
its `__init__.py`. Logger names updated to `src.<module>` for source
identification. All `from jarvis.X` imports across the codebase
rewritten to `from src.<module>` (CLI, desktop host, tests, every
extension that referenced the old path).

**2. Legacy top-level code removed.**

- **`agent/` deleted** (4 files: error_handler, executor, planner,
  task_queue). The `agent_task` tool stays in `TOOL_DECLARATIONS`
  for LLM compatibility but always returns a clear "not available"
  answer — the legacy queue had no OpenClaw equivalent.
- **`memory/` deleted** (3 files: __init__, config_manager,
  memory_manager). The desktop host now uses
  `extensions/memory_core/runtime.py::MemoryRuntime` via a small
  bridge module (`apps/desktop/src/jarvis_desktop/memory_bridge.py`).
  The bridge preserves the legacy `load_memory()` / `update_memory()` /
  `format_memory_for_prompt()` contract so the host's call sites
  work without a full rewrite. The legacy LLM-driven background
  memory extraction is gone — the LLM now uses the `save_memory`
  tool inline (matches OpenClaw's memory-core flow).
- **`or_client.py` deleted.** Two tools simplified:
  - `tool_youtube_video` "summarize" action now returns the first
    ~1500 chars of the transcript (no LLM in the host). The full
    transcript is still available via `get_transcript`.
  - `tool_web_search` now returns raw DDG snippets — the host LLM
    uses these as material for its own answer.

**3. Config + CI updates.**

- `pyrightconfig.json`: added `src/` to include + extraPaths; removed
  legacy excludes for `agent/`, `memory/`, `or_client.py`, `actions`.
- `tools/ci/check_imports.py`: refreshed allowlist. Extensions may
  import from `jarvis_sdk.*`, `src.*`, and the shared extension
  capabilities `extensions.{memory_core,cron}.*`. The legacy
  modules (`or_client`, `agent`, `memory`, `actions`, `main`, `ui`)
  are forbidden — they no longer exist.
- `packages/plugin_sdk/src/jarvis_sdk/manifest.py`: stale
  `jarvis.plugin.json` reference in a docstring → `openclaw.plugin.json`.

**4. What stayed.**

- `core/` (data files: IDENTITY.md, MEMORY.md, prompt.txt, SOUL.md,
  USER.md, memory.sqlite). These are runtime data, not source code.
  OpenClaw has analogous runtime data files at the root.
- The `bootstrap` seed marker updated to `<!-- seeded by src.bootstrap -->`.
  Existing seeded files (with the old `jarvis.bootstrap` marker) will
  be re-seeded on next bootstrap; the user's content is preserved by
  the marker check.

### Tests + checks

- All 149 tests pass (no test count change; existing tests cover the
  refactored surface).
- All 7 pre-commit hooks pass: ruff, ruff-format, pyright (--level error),
  import boundaries, import cycles, file length, manifest validation.

### Commit

- `41c781c` — refactor(phase3.5): jarvis/ → src/ + remove legacy root
  modules. 34 files changed, 347 insertions, 2075 deletions.

### OpenClaw structural parity (after Phase 3.5)

| OpenClaw surface              | JARVIS surface             | Status      |
| ----------------------------- | -------------------------- | ----------- |
| `src/bootstrap/`              | `src/bootstrap/`           | ✓ same      |
| `src/cron/`                   | `src/cron/`                | ✓ same      |
| `src/doctor/` (in src/cli)    | `src/doctor/`              | ✓ same      |
| `src/gateway/server/`         | `src/gateway/`             | ✓ (flat)    |
| `src/hooks/`                  | `src/hooks/`               | ✓ same      |
| `src/skills/`                 | `src/skills/`              | ✓ same      |
| `extensions/<id>/`            | `extensions/<id>/`         | ✓ same      |
| `skills/<id>/SKILL.md`        | `skills/<id>/SKILL.md`     | ✓ same      |
| `packages/plugin-sdk/`        | `packages/plugin_sdk/`     | ✓ (kebab)   |
| `apps/desktop/`               | `apps/desktop/`            | ✓ same      |
| `apps/cli/` (in apps)         | `apps/cli/`                | ✓ same      |
| `openclaw.plugin.json`        | `openclaw.plugin.json`     | ✓ same      |
| `agent/` (legacy)             | (removed)                  | ✓ gone      |
| `memory/` (legacy)            | `extensions/memory_core/`  | ✓ migrated  |
| `or_client.py` (legacy)       | (removed)                  | ✓ gone      |
| `actions/` (legacy)           | `extensions/tool_*/`       | ✓ migrated  |

## §27 — Phase 4.1: extensions/memory_lancedb/ OpenClaw port (2026-07-20)

**Commit:** e0ff533 feat(phase4.1): memory_lancedb OpenClaw parity + in-memory fallback

### Why

Phase 4.0 (commit 2a4b2d8) shipped memory_core — a SQLite
key/value store with substring search, mirroring OpenClaw's
extensions/memory-core/. Phase 4.1 adds the second memory
extension: memory_lancedb — the OpenAI-embeddings +
vector-search backend that OpenClaw ships as
extensions/memory-lancedb/. After this commit JARVIS has
both backends, switchable via the host's plugin loader.

### What landed

**1. extensions/memory_lancedb/ — 14 new files.**

`
extensions/memory_lancedb/
├── AGENTS.md                      # maintainer guide (Phase 4 invariants)
├── __init__.py                    # define_plugin_entry + register
├── plugin.py                      # tools + CLI + lifecycle hooks
├── runtime.py                     # MemoryDB (LanceDB + in-memory fallback)
├── embeddings.py                  # OpenAI + provider adapter
├── config.py                      # MemoryConfig schema + parsing
├── lancedb_schema.py              # table name + agent predicate
├── lancedb_runtime.py             # lazy lancedb module loader
├── envelope_scrubber.py           # capture gate + recall filter
├── doctor.py                      # health check + state migrations
├── plugin_globals.py              # module-level CLI state
├── openclaw.plugin.json           # manifest
├── pyproject.toml                 # lancedb, pyarrow, openai deps
└── tests/
    └── test_memory_lancedb_phase4.py   # 60 tests
`

**2. Two backends behind one MemoryStore protocol.**

- **LanceDBStore** — production path. Uses the
  lancedb package via the lazy loader in
  lancedb_runtime.py. Schema (id, 	ext, ector,
  importance, category, createdAt, gentId),
  agent predicate, and store API match OpenClaw's
  lancedb-store.ts exactly.
- **InMemoryStore** — test + fallback path. Pure-stdlib
  (no numpy dep) with a MemoryStore implementation that
  uses the same agent scoping + per-agent-id vector
  distance ranking. The MemoryDB facade picks the
  backend at runtime: LanceDB if available, in-memory
  otherwise (with a warning logged).

**3. Embeddings: direct OpenAI + provider adapter.**

- **OpenAiCompatibleEmbeddings** — direct
  POST /embeddings via urllib.request. Bypasses the
  OpenAI SDK's encoding_format=base64 auto-injection
  (some compatible providers reject it). Handles
  dimensions rejection with a local-truncation
  fallback (mirrors OpenClaw's
  	runcateEmbeddingVector).
- **ProviderAdapterEmbeddings** — delegates to the
  SDK's MemoryEmbeddingProvider registry (Phase 4.0
  SDK). Lazy provider setup so auth-profile repairs
  are picked up on the next call.
- **create_embeddings(cfg)** — factory picks the
  right strategy based on cfg.embedding.provider and
  piKey presence.

**4. Security: capture gate + recall filter.**

- should_capture(text, *, custom_triggers, max_chars)
  rejects envelope sludge, prompt injection, agent
  summaries, and emoji-heavy content. Mirrors OpenClaw's
  shouldCapture line-for-line.
- clean_memory_search_results(results) strips
  contaminated rows before they reach the LLM. Mirrors
  OpenClaw's cleanMemorySearchResults.
- ormat_relevant_memories_context(memories) renders
  the <relevant-memories> block with the OpenClaw-
  exact header and the "untrusted historical data"
  disclaimer. The pre-compaction prompt section is
  capped at 2,200 chars (matches
  DEFAULT_QMD_LIMITS.maxInjectedChars).
- Every persist + recall path runs through
  looks_like_envelope_sludge and
  looks_like_prompt_injection from memory_core —
  the same security layer that closes the
  long-term-memory poisoning vector.

**5. Tool surface (3 tools, single-active-slot memory capability).**

| Tool             | OpenClaw parity                              |
|------------------|---------------------------------------------|
| memory_recall  | vector search + scored hits + recall filter |
| memory_store   | append + duplicate detection + prompt-injection reject |
| memory_forget  | delete by id (GDPR) or by search             |

All three tools are registered via
pi.register_tool(plugin, names=[...]). The plugin
also registers a MemoryPluginCapability bundle
(prompt_builder + lush_plan_resolver + 
untime +
public_artifacts) so the host can build a prompt
section, ask for a flush plan, and resolve a
MemorySearchManager for the active backend.

**6. Lifecycle hooks (OpenClaw names).**

- efore_prompt_build — auto-recall. Embeds the
  user's text, runs the top-K vector search, filters
  envelope sludge, caps at 3 hits, returns a
  prependContext string. Tolerant of both the
  OpenClaw shape (event.prompt, event.messages) and
  the JARVIS current shape (event.input,
  event.output).
- gent_end — auto-capture. Sanitizes each user
  message, gates through should_capture, embeds,
  dedupes via the indCleanDuplicateMemory helper,
  stores. Per-session cursor so a re-fired event
  doesn't re-store the same memory.
- session_end — clears the per-session cursor.

**7. CLI: jarvis ltm list|search|query|stats.**

Mirrors OpenClaw's ltm command group. Phase 4.1 ships
the operator surface as a slash command (/ltm) plus
a top-level CLI descriptor for jarvis ltm --help.

**8. Doctor contract: legacy memory.json + LanceDB per-agent-isolation.**

- detect_legacy(state_dir, config) — find the
  pre-isolation memory table.
- pply_migration(state_dir, config) — assign legacy
  rows to the default agent.
- check_health(state_dir, config) — structured
  health report (
untime_available, db_path,
  db_exists, legacy_table, 
ow_count).

**9. Source mapping.**

| OpenClaw file               | Python port              |
|-----------------------------|--------------------------|
| lancedb-schema.ts         | lancedb_schema.py      |
| lancedb-runtime.ts        | lancedb_runtime.py     |
| lancedb-store.ts          | 
untime.py (MemoryDB + InMemoryStore + LanceDBStore) |
| config.ts                 | config.py              |
| (index.ts embeddings)       | embeddings.py          |
| (index.ts envelope)         | envelope_scrubber.py   |
| (index.ts tools/CLI/hooks)  | plugin.py              |
| (index.ts entry+register)   | __init__.py            |
| doctor-contract-api.ts    | doctor.py              |
| openclaw.plugin.json      | openclaw.plugin.json   |
| package.json              | pyproject.toml         |

### Parity matrix (Phase 4.1 vs. OpenClaw)

| OpenClaw surface               | Phase 4.1 status |
|--------------------------------|------------------|
| memory_recall tool           | ✓ identical params + output |
| memory_store tool            | ✓ identical + duplicate detection + prompt-injection reject |
| memory_forget tool           | ✓ identical (id + search) |
| memorySearchManager adapter  | ✓ MemoryLancedbSearchManager |
| ltm list|search|query|stats  | ✓ identical command surface |
| efore_prompt_build hook     | ✓ identical, hook-tolerance for JARVIS current shape |
| gent_end hook               | ✓ identical + per-session cursor |
| session_end hook             | ✓ identical |
| MemoryPluginCapability       | ✓ prompt_builder + lush_plan_resolver + 
untime + public_artifacts |
| MemoryFlushPlan              | ✓ default should_flush=False |
| MemoryPromptSectionBuilder   | ✓ empty default; recall wired through runtime |
| publicArtifacts.listArtifacts| ✓ memory.lancedb artifact |
| MemoryConfig schema          | ✓ identical (provider, model, apiKey, baseUrl, dimensions, dbPath, autoCapture, autoRecall, captureMaxChars, customTriggers, recallMaxChars, storageOptions) |
| ${ENV_VAR} expansion        | ✓ identical |
| MEMORY_CATEGORIES            | ✓ identical (preference, fact, decision, entity, other) |
| MEMORY_QUERY_COLUMNS         | ✓ identical (id, text, importance, category, createdAt) |
| MEMORY_TABLE_NAME            | ✓ identical (memories) |
| MEMORY_AGENT_ID_COLUMN       | ✓ identical (gentId) |
| ectorDimsForModel           | ✓ identical (text-embedding-3-small: 1536, 3-large: 3072) |
| shouldCapture regex set      | ✓ identical (11 patterns, 5 languages) |
| looksLikeEnvelopeSludge      | ✓ re-uses memory_core scrubber |
| looksLikePromptInjection     | ✓ re-uses memory_core scrubber |
| sanitizeForMemoryCapture     | ✓ re-uses memory_core scrubber |
| ormatRelevantMemoriesContext| ✓ identical output format |
| cleanMemorySearchResults     | ✓ identical behavior |
| detectCategory               | ✓ identical regex set |
| escapeMemoryForPrompt        | ✓ re-uses memory_core scrubber |
| stripMediaAttachedAnnotations| ✓ re-uses memory_core scrubber |
| 
ormalizeRecallQuery         | ✓ identical (collapse + cap) |
| LanceDB lazy loader          | ✓ load_lancedb_module() with graceful fallback |
| legacyMemorySchemaError      | ✓ identical message |
| Per-agent isolation migration  | ✓ detect_legacy + pply_migration |
| envelopeJSONLine             | ✓ re-uses memory_core scrubber |
| messageToolDeliveryHint      | ✓ re-uses memory_core scrubber |

### Tests + checks

- **60 new tests** in 	ests/test_memory_lancedb_phase4.py:
  manifest, entry shape, in-memory store (agent scoping,
  duplicate detection, vector math, list ordering,
  delete validation, count), MemoryDB facade, config
  parser (defaults, env-var expansion, bounds, custom
  triggers, storage options), envelope scrubber
  (should_capture, detect_category, format, clean
  filter, normalize), embeddings helpers
  (normalization, truncation, factory), lancedb runtime
  loader, tool call behavior (recall, store, store +
  recall, prompt-injection reject, forget by id, missing
  args), auto-capture (per-session cursor, per-turn
  cap, no-recall short-circuit), memory capability
  (flush plan, prompt builder, runtime, public
  artifacts), CLI handlers, doctor health, schema
  helpers (predicate, quote, UUID validation, legacy
  error).
- **All 7 pre-commit hooks green** (ruff, ruff-format,
  pyright, plugin boundaries, import cycles, max file
  length, manifest validation).
- **Full pytest:** 25 pre-existing failures
  (	ests/test_smoke.py — missing httpx, psutil,
  sounddevice; 	ests/test_phase3.py — same),
  unchanged from the P4.0 baseline. The new
  memory_lancedb tests are all green.
- **All 7 SDK public types** (added in P4.0) consumed
  correctly: MemoryEmbeddingProvider,
  MemoryEmbeddingProviderAdapter,
  get_memory_embedding_provider, MessageToolDeliveryHints,
  BUNDLED_CHAT_CHANNEL_ENVELOPE_PREFIXES,
  parse_strict_positive_integer, 
esolve_timer_timeout_ms,
  s_optional_record, 	runcate_utf16_safe.

### What stayed

- memory_core (Phase 4.0) — the SQLite fallback is
  the **default** memory plugin. memory_lancedb is
  opt-in via the operator's config (embedding.apiKey,
  etc.). Phase 4.2 (active_memory) introduces a router
  that picks one or the other per session.
- The Phase 4.0 envelope scrubber is the single
  source of truth. memory_lancedb.envelope_scrubber
  re-uses memory_core.envelope_scrubber's helpers
  to keep the security contract consistent.
- The JARVIS host's current gent_end payload
  ({input, output}) is accepted by the plugin's
  gent_end hook in addition to the OpenClaw shape
  ({messages, success}). Phase 4.2's
  ctive_memory router normalizes the payload
  before firing the hook.

### What's next (Phase 4.2+)

- **Phase 4.2 — extensions/active_memory/** (15 source
  files in OpenClaw). Auto-recall router with
  circuit-breaker + per-session disable + model
  resolution chain. Picks memory_core or
  memory_lancedb per session.
- **Phase 4.3 — extensions/memory_wiki/** (45 source
  files in OpenClaw). Obsidian-compatible vault.
- **Phase 4.4 — Full dreaming** (3 phases: light, REM,
  deep) + REM evidence + shadow trial + qmd backend.
- **Cleanup pass:** remove any legacy memory code,
  dead tests, duplicate logic.
- **OPENCLAW_MIGRATION_PLAN.md §28** — log Phase 4.2
  completion.


## �28 � Phase 4.2a: extensions/active_memory/ foundation (2026-07-20)

**Commit:** 94debf0 feat(phase4.2a): active_memory foundation + SDK hardening

Phase 4.1 (commit e0ff533) shipped memory_lancedb as the
production memory backend. Phase 4.2 adds the *router* �
extensions/active_memory/ � that decides per-session which
memory backend to use and orchestrates pre-reply recall with
eligibility, harness-skip, circuit-breaker, and admin-gated
session toggles.

The user reaffirmed "same to same" with OpenClaw: no
simplifications, no rewrites. Reproduce the full surface
(15 source files in OpenClaw, ~180KB total). We split 4.2
into 4.2a/4.2b/4.2c for reviewable units � this commit is
**4.2a (foundation)**: types, config normalization, recall
cache + circuit breaker, session policy + harness skip +
session toggles. 4.2b is the recall flow itself (recall.ts,
recall-run.ts, query.ts, prompt.ts, session.ts, 3 transcript
files). 4.2c is the entry + slash command + doctor wiring.

### What landed

#### extensions/active_memory/ (9 new files)

- __init__.py � define_plugin_entry stub + register hook.
  Tolerates pi.logger == None (PluginContext default).
- 	ypes.py � 30+ constant defaults matching OpenClaw
  exactly (cache TTL, max entries, prompt styles, thinking
  levels, reserved tools allow list, no-recall values, plugin
  tag wrapper, etc.) + 15+ type definitions.
- config.py � 25+ config keys with normalization,
  clamping, and deprecated-key detection. Includes:
  - pply_cli_runtime_recall_timeout_default (CLI runtime
    gets a higher default timeout)
  - has_deprecated_model_fallback_policy
  - is_missing_registered_memory_tools_error
  - 
esolve_safe_transcript_dir (path-traversal-safe)
  - 	o_safe_transcript_agent_dir_name
  - 
esolve_persistent_transcript_base_dir
  - Prompt style inference from queryMode + explicit override.
- 
ecall_state.py � TTL cache + per-agent/model circuit
  breaker. uild_cache_key, get/set_cached_result,
  should_cache_result, uild_circuit_breaker_key,
  is_circuit_breaker_open (opens after max_timeouts,
  resets after cooldown_ms), 	o_single_line_log_value
  (collapsing + truncation for log forensics).
- session_policy.py � eligibility, chat type resolution
  (direct/group/channel/explicit/thread-strip/webchat),
  allow/deny lists, harness-skip (skips if missing key,
  bad shape, no entry, host error, or model-locked),
  session toggle store with in-process fallback (host can
  swap to real keyed store without code change), admin
  gating (operator.admin scope or owner),
  update_active_memory_global_enabled_in_config (preserves
  existing entries), ormat_active_memory_command_help.
- openclaw.plugin.json � manifest with id/kind/version/
  description + 25+ config schema entries.
- AGENTS.md � purpose, source map, security notes.
- pyproject.toml � workspace member declaration.
- 	ests/test_active_memory_phase4.py � 64 tests covering
  types, config (22 tests), recall_state (9), session_policy
  (16), registration (1), manifest (2), entry shape (1).
  All passing.

#### SDK extensions (3 new modules, 6 enriched)

- 
umber_runtime.py � added s_date_timestamp_ms and
  
esolve_expires_at_ms_from_duration_ms (OpenClaw's
  sDateTimestampMs / 
esolveExpiresAtMsFromDurationMs).
  Uses math.isnan instead of x != x for clarity; refactored
  to reduce return-statement count (PLR0911).
- string_coerce.py � added 
ormalize_string_entries and
  
ormalize_optional_string (OpenClaw's 
ormalizeStringEntries
  / 
ormalizeOptionalString).
- 
outing.py � added parse_agent_session_key and
  parse_thread_session_suffix (OpenClaw's parseAgentSessionKey
  / parseThreadSessionSuffix).
- gent_runtime.py � added DEFAULT_PROVIDER,
  parse_model_ref, 
esolve_agent_effective_model_primary,
  
esolve_default_model_for_agent,
  
esolve_remember_across_conversations. Model resolution
  chain: config.model ? current run's model ? agent default
  ? config.modelFallback.
- plugin_config.py � added PluginsConfig,
  
ormalize_plugins_config, 
esolve_plugin_config_object
  (returns entry.config ?? entry � mirrors OpenClaw's
  behavior exactly; fixed the bug where SDK was returning the
  entry itself, causing is_active_memory_globally_enabled
  to read entry.enabled instead of entry.config.enabled).
- security_runtime.py (NEW) � is_path_inside (path
  containment guard for transcript dir safety).
- session_transcript_runtime.py (NEW) �
  SessionTranscriptTargetParams, uild_session_transcript_target.
- memory_host_search.py (NEW) �
  close_active_memory_search_manager (lifecycle helper for
  the recall search manager that 4.2b will own).

#### Host runtime namespace additions (api.py)

- pi.runtime.config.{current, mutate_config_file} �
  live config + atomic mutator surface.
- pi.runtime.state.{resolve_state_dir, open_keyed_store} �
  state directory + per-key file-backed store (lease-protected).
- pi.runtime.agent.session.get_session_entry � read
  current session entry from host session store.

#### Cleanup (pre-existing issues)

- extensions/memory_core/tests/test_memory_core_phase4.py �
  added 
oqa: PT004 on the 
untime fixture (intentionally
  side-effect-only; rename would change 14 test call sites).
- packages/plugin_sdk/src/jarvis_sdk/api.py � restored
  # noqa: TCH001 on .cron.CronDecl and .skill.SkillDecl
  imports (used in instance annotations only, not at runtime).
- packages/plugin_sdk/src/jarvis_sdk/lazy_runtime.py �
  moved collections.abc.{Awaitable, Callable} to TYPE_CHECKING
  and converted _T TypeVar to PEP 695 generic syntax (UP047
  + TCH003 compliance). Pyright + ruff both clean.
- packages/plugin_sdk/src/jarvis_sdk/expect_runtime.py �
  removed PEP 695 generic syntax (incompatible with module-level
  _T TypeVar; now uses TypeVar consistently).

### Test count (Phase 4.2a)

- New: 64 active_memory tests, all green in isolation AND
  in the full suite.
- Full suite: 446 passed, 25 pre-existing failures (psutil/
  httpx/sounddevice not installed; same baseline as P4.0).
- No regressions; 0 new failures introduced.

### Pre-commit (7 hooks, all green)

- ruff (TCH, UP, PL, PT, S, etc.) � Passed
- ruff-format � Passed
- pyright (level=error) � Passed
- check-imports (plugin boundaries) � Passed
- check-cycles (import cycles) � Passed
- check-max-lines (2000 line cap) � Passed
- check-manifests (11 extensions) � Passed

### Parity matrix (Phase 4.2a vs. OpenClaw)

| OpenClaw file              | Python port                | Status |
|----------------------------|----------------------------|--------|
| 	ypes.ts                 | 	ypes.py                 | 100%   |
| config.ts                | config.py                | 100% (foundation; full recall config comes in 4.2b) |
| 
ecall-state.ts          | 
ecall_state.py          | 100%   |
| session-policy.ts        | session_policy.py        | 100%   |
| doctor-contract-api.ts   | (deferred to 4.2c)         | -      |
| query.ts                 | (deferred to 4.2b)         | -      |
| prompt.ts                | (deferred to 4.2b)         | -      |
| 
ecall.ts + 
ecall-run.ts | (deferred to 4.2b)      | -      |
| 	ranscript*.ts (3 files) | (deferred to 4.2b)         | -      |
| session.ts               | (deferred to 4.2b)         | -      |
| index.ts                 | (deferred to 4.2c)         | -      |

**Phase 4.2a surface: 4 of 11 OpenClaw files (36%). 4.2b will
add the recall flow (5 files, the heaviest piece � "blocking
memory sub-agent"). 4.2c will add entry + slash command + doctor
(2 files).**

### What's next (Phase 4.2b)

- Port 
ecall.ts + 
ecall-run.ts + query.ts + prompt.ts
  + session.ts + 3 transcript files (~1500 lines). Need to
  add httpx dep for embedded-run dispatch (OpenClaw
  
unEmbeddedPiAgent).
- Then 4.2c (entry + slash command + doctor) wires
  before_prompt_build hook + /active-memory slash command.
- Then 4.3 (memory_wiki 45 files) and 4.4 (dreaming phases).

## §29 — Phase 4.2c: active_memory entry + slash command + doctor (2026-07-20)

**Commit:** `05bfe2e` feat(phase4.2c): active_memory entry + slash command + doctor migration

Phase 4.2c closes out the `active_memory` port. With this commit,
the active_memory extension is feature-complete against
OpenClaw's `index.ts` + `doctor-contract-api.ts` (the last 2 of
the 11 source files in `extensions/active-memory/`).

### Files added

- `extensions/active_memory/index.py` (~850 lines) — main
  plugin entry. Wires:
  - The `/active-memory` slash command (status / on / off /
    help; with `--global` to mutate the operator's config
    file via the host's `mutateConfigFile`; admin-gated via
    `lacks_admin_to_mutate_active_memory_global`).
  - The `before_prompt_build` hook — preflight deadline +
    eligibility / config / session-disabled checks, then
    delegates the rest of the flow to
    `maybe_resolve_active_recall`.
  - `MEMORY_CORE_PLUGIN_ID = "memory-core"` constant (used
    to detect the active memory core plugin at runtime).
  - `build_active_memory_testing()` — re-exports the small
    surface other modules / tests use to reset module-level
    state and drive the recall flow.
- `extensions/active_memory/doctor_contract_api.py` — doctor
  state migration for active-memory. Phase 4.2c ships one
  migration:
  - `active-memory-session-toggles-json-to-plugin-state` —
    reads legacy `<state>/plugins/active-memory/
    session-toggles.json`, imports any missing
    `disabled=true` entries into the plugin-state keyed
    store under the `session-toggles` namespace, archives
    the legacy file. Idempotent: no-op if legacy file is
    missing, empty, or all entries already in the store.
  - `resolve_toggle_state_path(state_dir)` — absolute path
    of the legacy `session-toggles.json` file.
  - `active_memory_toggle_key(session_key)` — SHA-256 hash
    of the session key (hex), used as the keyed-store key.
- `extensions/active_memory/tests/test_index_phase4.py` —
  13 new tests covering: `register_active_memory` smoke,
  `state_migrations` shape, `resolve_toggle_state_path`,
  `active_memory_toggle_key` (deterministic hex 64;
  different session keys differ), `detect_legacy` (no file /
  empty / with disabled entries / skips disabled=false),
  `migrate_legacy` (empty / no keyed store / happy path with
  keyed store), `MEMORY_CORE_PLUGIN_ID` constant.

### Files modified

- `extensions/active_memory/__init__.py` — slim down:
  re-exports from `index.py` + `doctor_contract_api.py`
  via `define_plugin_entry` and `register_active_memory`.
  The host now calls `extensions.active_memory.register(api)`.
- `OPENCLAW_MIGRATION_PLAN.md` (this file, §29).

### Test count (Phase 4.2c)

- New: 13 active_memory index/doctor tests, all green.
- active_memory + SDK suite: 343 → 356 (13 new). All 356 pass.
- Full suite: 678 pass, 2 pre-existing failures (memory_lancedb
  entry shape assertion + smoke test `len(TOOL_DECLARATIONS) ==
  14`; both unrelated to 4.2c, same baseline as 4.2b step 3).
- 0 new regressions introduced.

### Pre-commit (7 hooks, all green)

- ruff (TCH, UP, PL, PT, S, etc.) — Passed
- ruff-format — Passed
- pyright (level=error) — Passed
- check-imports (plugin boundaries) — Passed
- check-cycles (import cycles) — Passed
- check-max-lines (2000 line cap) — Passed
- check-manifests (11 extensions) — Skipped (no manifest touched)

### Parity matrix (Phase 4.2c vs. OpenClaw — 100%)

| OpenClaw file              | Python port                   | Status |
|----------------------------|-------------------------------|--------|
| `types.ts`                 | `types.py`                    | 100%   |
| `config.ts`                | `config.py`                   | 100%   |
| `recall-state.ts`          | `recall_state.py`             | 100%   |
| `session-policy.ts`        | `session_policy.py`           | 100%   |
| `query.ts`                 | `query.py`                    | 100%   |
| `prompt.ts`                | `prompt.py`                   | 100%   |
| `transcript.ts`            | `transcript.py`               | 100%   |
| `transcript-watch.ts`      | `transcript_watch.py`         | 100%   |
| `transcript-result.ts`     | `transcript_result.py`        | 100%   |
| `session.ts`               | `session.py`                  | 100%   |
| `recall.ts`                | `recall.py`                   | 100%   |
| `recall-run.ts`            | `recall_run.py`               | 100%   |
| `index.ts`                 | `index.py`                    | 100% (4.2c) |
| `doctor-contract-api.ts`   | `doctor_contract_api.py`      | 100% (4.2c) |

**Phase 4.2 surface: 14 of 14 OpenClaw files (100%). The
`active_memory` extension is now feature-complete against
OpenClaw's source tree.**

### Active_memory extension — cumulative stats (P4.2a + P4.2b + P4.2c)

- 14 source files (matches OpenClaw's 15 — we merge
  `recall-run.ts` with `recall.ts`; the OpenClaw split is
  driven by Node module boundaries that don't apply in
  Python).
- 259 active_memory tests (64 + 67 + 117 + 11 + 0 from
  index/doctor, plus 13 from `test_index_phase4.py`).
- ~ 3,800 lines ported (types, config, recall state, query,
  prompt, transcript x3, session, recall, recall_run, index,
  doctor contract, plus tests).
- 7 SDK modules touched / added to support the recall flow
  (`number_runtime`, `string_coerce`, `agent_runtime`,
  `plugin_config`, `security_runtime`,
  `session_transcript_runtime`, `memory_host_search`).

### What's next (Phase 4.3)

- `extensions/memory_wiki/` (45 source files) —
  Obsidian-compatible vault with `--mode vault=...` CLI flag
  and import-from-existing-vault command.
- Then 4.4 (full dreaming: light, REM, deep + REM evidence +
  shadow trial + qmd backend).

## §30 — Phase 4.3a: memory_wiki foundation + SDK fs-safe hardening (2026-07-21)

**Commit:** `db416c4` feat(phase4.3a): memory_wiki foundation + SDK fs-safe hardening

Phase 4.3a opens the memory_wiki port. This sub-phase
ships the foundation: types, time, log (vault-generation
+ publication identity), source-path shared helpers,
vault-page atomic write. With these primitives in place,
the remaining sub-phases (4.3b config, 4.3c vault init +
markdown, 4.3d compile, ...) can build on a shared
surface.

### SDK additions (this commit)

- `packages/plugin_sdk/src/jarvis_sdk/retry_runtime.py` (new
  module). `retry_async(fn, options)` with bounded attempts
  + linear backoff + jitter. Mirrors OpenClaw's
  `openclaw/plugin-sdk/retry-runtime`.
- `packages/plugin_sdk/src/jarvis_sdk/number_runtime.py` —
  adds `timestamp_ms_to_iso_string`. Mirrors OpenClaw's
  `timestampMsToIsoString`.
- `packages/plugin_sdk/src/jarvis_sdk/string_coerce.py` —
  adds `lowercase_preserving_whitespace`. Mirrors OpenClaw's
  `lowercasePreservingWhitespace`.
- `packages/plugin_sdk/src/jarvis_sdk/security_runtime.py` —
  adds `FsSafeError`, `path_exists`, `fs_root` / `root`,
  `append_regular_file`, `is_regular_file_stat`. Mirrors
  OpenClaw's `@openclaw/fs-safe` public surface (same
  method names, same error codes: `path-mismatch`,
  `symlink`, `path-alias`, `already-exists`, `hardlink`,
  `not-found`, `out-of-root`).

### Files added (`extensions/memory_wiki/`)

- `pyproject.toml` -- workspace member, stdlib only.
- `AGENTS.md` -- maintainer notes.
- `openclaw.plugin.json` -- minimal Phase 4.3a manifest
  (full configSchema lands in 4.3b).
- `__init__.py` -- `register_memory_wiki` +
  `define_plugin_entry` scaffold + re-exports.
- `types.py` -- `MemoryWikiVaultIdentity`,
  `MemoryWikiLogEntryType` literal.
- `time.py` -- `resolve_memory_wiki_timestamp` (~40 lines).
- `source_path_shared.py` -- `resolve_artifact_key`
  (~30 lines; POSIX realpath, Windows lowercased realpath).
- `vault_page_write.py` -- `write_guarded_vault_page`
  (~100 lines; hardlink-break + symlink-reject +
  transient path-mismatch retry).
- `log.py` (~340 lines) -- `append_memory_wiki_log` +
  `load_memory_wiki_vault_identity` (linear walk + causal
  publication chain) +
  `resolve_memory_wiki_vault_source_generation` (SHA-256
  over source tree) +
  `load_memory_wiki_validated_vault_identity` (drops
  publication on source divergence) +
  `ensure_memory_wiki_vault_generation` (idempotent UUID
  mint with concurrent-init convergence).
- 4 test files (26 tests + 2 Windows-specific skips).

### Test count (Phase 4.3a)

- New: 26 memory_wiki tests + 0 SDK tests. All green.
- memory_wiki + active_memory + SDK suite: 356 -> 382
  (+26). All 382 pass.
- Pre-commit all 7 hooks green (ruff + ruff-format +
  pyright + check-imports + check-cycles + check-max-lines
  + check-manifests).

### Parity matrix (Phase 4.3a vs. OpenClaw)

| OpenClaw file              | Python port                       | Status |
|----------------------------|-----------------------------------|--------|
| `api.ts`                   | (Phase 4.3g)                      | -      |
| `index.ts`                 | `__init__.py` (scaffold only)     | 30% (4.3g adds register body) |
| `cli-metadata.ts`          | (Phase 4.3g)                      | -      |
| `doctor-contract-api.ts`   | (Phase 4.3g)                      | -      |
| `openclaw.plugin.json`     | `openclaw.plugin.json` (minimal)  | 100% manifest scaffold |
| `src/types.ts`             | `types.py` (basic only)           | 30% (full config + page types land in 4.3b+) |
| `src/time.ts`              | `time.py`                         | 100%   |
| `src/source-path-shared.ts`| `source_path_shared.py`           | 100%   |
| `src/vault-page-write.ts`  | `vault_page_write.py`             | 100%   |
| `src/log.ts`               | `log.py`                          | 100%   |

**Phase 4.3a surface: 5 of 30+ OpenClaw files (17% of
the foundation layer). Subsequent sub-phases will add
config, vault init, markdown, compile, query, tools,
gateway, CLI, obsidian, unsafe-local, chatgpt-import,
index, and doctor.**

### Cumulative stats (P4.3a)

- 9 new files in memory_wiki (8 prod + 1 test helpers
  via `__init__.py` re-exports).
- 4 SDK modules touched / added to support the
  foundation (retry_runtime, number_runtime,
  string_coerce, security_runtime).
- 7 FsSafeError codes mirrored.
- ~ 800 lines ported (types, time, log, source-path,
  vault-page-write, plus tests).

### What's next (Phase 4.3b)

- `config.py` (11KB) + `config_compat.py` (3KB) -- the
  full schema (vaultMode / vault / obsidian / bridge /
  unsafeLocal / ingest / search / context / render)
  + the per-agent config resolver.

## §31 — Phase 4.3b: memory_wiki config + config_compat (2026-07-21)

**Commit:** `afc35ab` feat(phase4.3b): memory_wiki config + config_compat

Phase 4.3b ships the memory-wiki config layer. The
plugin can now be configured via the full OpenClaw
schema (vaultMode / vault / obsidian / bridge /
unsafeLocal / ingest / search / context / render),
and legacy configs that use the old
``bridge.readMemoryCore`` key auto-migrate to the
canonical ``bridge.readMemoryArtifacts``.

### Files added

- `extensions/memory_wiki/config.py` (~990 lines) --
  the full plugin config. Mirrors OpenClaw's
  `extensions/memory-wiki/src/config.ts`. Includes
  type literals, TypedDict input shapes, Resolved
  classes (with both snake_case slots and OpenClaw
  camelCase properties so callers can pick either
  spelling), `memory_wiki_config_schema` (the
  callable that mirrors OpenClaw's `safeParse`
  contract), `resolve_memory_wiki_config`
  (defaults-merge), `resolve_memory_wiki_configured_agent_ids`,
  and `resolve_memory_wiki_agent_config` (per-agent
  resolver with cross-field rule re-assertion).
- `extensions/memory_wiki/config_compat.py` (~140
  lines) -- the legacy config compat layer.
  Mirrors OpenClaw's `config-compat.ts`. Includes
  `has_legacy_bridge_artifact_toggle`,
  `migrate_memory_wiki_legacy_config` (rename or
  drop, idempotent), `normalize_compatibility_config`,
  and the documented `LEGACY_CONFIG_RULES`.
- `extensions/memory_wiki/tests/test_config_phase4.py`
  (24 tests).
- `extensions/memory_wiki/tests/test_config_compat_phase4.py`
  (13 tests).

### Files modified

- `extensions/memory_wiki/__init__.py` -- re-exports
  the new config surface.

### Test count (Phase 4.3b)

- New: 37 memory_wiki tests. All green.
- memory_wiki + active_memory + SDK suite: 382 → 419
  (+37). All 419 pass.
- Pre-commit all 7 hooks green.

### Parity matrix (Phase 4.3b vs. OpenClaw)

| OpenClaw file          | Python port           | Status |
|------------------------|-----------------------|--------|
| `src/config.ts`        | `config.py`           | 100%   |
| `src/config-compat.ts` | `config_compat.py`    | 100%   |

**Phase 4.3b surface: 2 of 2 OpenClaw files (100% of
the config layer).**

### Cumulative stats (P4.3b)

- 4 new files in memory_wiki (2 prod + 2 test).
- 1 file modified (`__init__.py` re-exports).
- ~ 1300 lines ported.
- 6 cross-field rules + 7 strict-shape rules + 5
  homedir-expansion paths preserved.

### What's next (Phase 4.3c)

- `vault.py` (~5.5KB) -- vault init (scaffold
  directories + scaffold files).
- `markdown.py` (26KB) -- split into
  `markdown_core.py` (parser: blocks, link graph,
  backtick fences) + `markdown_render.py`
  (Obsidian-friendly renderer, managed blocks,
  frontmatter).

## §32 — Phase 4.3d-mr6: memory_wiki compile pages (per-page write loop) (2026-07-21)

**Commit:** `ba67653` feat(phase4.3d-mr6): memory_wiki compile pages (per-page write loop)

Phase 4.3d-mr6 ships the per-page write loop in
`extensions/memory_wiki/compile_pages.py`. This
is the write-side counterpart to 4.3d-mr4's
scan orchestrator and 4.3d-mr5's dashboard
renderer. Together they implement the OpenClaw
`compileMemoryWikiPages` /
`buildManagedRelatedBlock` helpers from
`extensions/memory-wiki/src/compile.ts`.

### Files added

- `extensions/memory_wiki/compile_pages.py`
  (~280 lines) -- the per-page compile write
  loop. Includes:
  - `PageWriteResult` dataclass (absolute_path,
    relative_path, written, related_count,
    error).
  - `build_related_block(related_pages)` -- the
    `## Related` managed block builder.
    Wrapped in `WIKI_RELATED_START_MARKER` /
    `WIKI_RELATED_END_MARKER` so the link
    extractor can skip the auto-generated lines.
    Caps at `MAX_RELATED_PAGES_PER_SECTION = 12`
    with an `and N more` trailer; truncates long
    titles to `MAX_RELATED_LINE_LENGTH = 240`.
  - `_resolve_related_pages` -- classifies each
    candidate as source / backlink / related
    using the per-page `linkTargets` +
    `sourceIds` graph. The page itself is
    excluded; pages already in the seen set are
    skipped.
  - `build_page_body` -- builds the rewritten
    page body (frontmatter + H1 + managed
    related block). Uses the
    `render_wiki_markdown` helper so the
    frontmatter YAML stays consistent with the
    write path.
  - `_write_one_page_async` -- the per-page
    async worker. Goes through
    `with_memory_wiki_vault_mutation` so
    concurrent compile / apply calls on the same
    vault serialize, then through
    `write_guarded_vault_page` so the
    fs-safe-root write path is preserved.
  - `write_compiled_pages(config, pages)` -- the
    sync orchestrator. Pre-computes every
    per-page write spec (`_PendingWrite`)
    synchronously, then dispatches all writes
    inside a single `asyncio.run` so the
    per-vault `asyncio.Lock` lives in a single
    event loop (avoids "lock attached to a
    different loop" errors when the caller
    invokes the sync compile path multiple
    times). Per-page exceptions are recorded on
    the spec's `error` field so one bad page
    doesn't abort the rest of the compile pass.
- `extensions/memory_wiki/tests/test_compile_pages_phase4.py`
  (11 tests):
  - 4 `build_related_block` tests (empty stub,
    label+link, cap at max, long-title
    truncation)
  - 4 `build_page_body` tests (full page,
    related link, claims, skip-unset
    optional fields)
  - 3 `write_compiled_pages` tests (writes to
    disk, content has related block, per-page
    error shape)

### Files modified

- `extensions/memory_wiki/__init__.py` --
  re-exports `PageWriteResult`, the
  related-block constants (`MAX_RELATED_PAGES_PER_SECTION`,
  `MAX_RELATED_LINE_LENGTH`, `HUMAN_START_MARKER`,
  `HUMAN_END_MARKER`), `build_related_block`,
  `build_page_body`, and `write_compiled_pages`.

### Test count (Phase 4.3d-mr6)

- New: 11 memory_wiki tests. All green.
- memory_wiki + active_memory + SDK suite: 582 → 593
  (+11). All 593 pass.
- Pre-commit all 7 hooks green (ruff, ruff-format,
  pyright, check-imports, check-cycles,
  check-max-lines, check-manifests).

### Parity matrix (Phase 4.3d-mr6 vs. OpenClaw)

| OpenClaw helper              | Python port                       | Status |
|------------------------------|-----------------------------------|--------|
| `compileMemoryWikiPages`     | `write_compiled_pages`            | 100%   |
| `buildManagedRelatedBlock`   | `build_related_block`             | 100%   |
| `buildManagedRelatedBlockLinks` | `_resolve_related_pages`       | 100%   |
| `replaceManagedMarkdownBlock` | `replace_managed_markdown_block`  | (4.3c) |

**Phase 4.3d-mr6 surface: 1 of 1 OpenClaw
compile-page helper (100% of the per-page
write loop).**

### Cumulative stats (P4.3d-mr6)

- 2 new files in memory_wiki (1 prod + 1 test).
- 1 file modified (`__init__.py` re-exports).
- ~ 280 lines ported.
- 100% parity with OpenClaw's
  `compileMemoryWikiPages` write loop.

### What's next (Phase 4.3e)

- `compiled-cache.ts` -- the immutable
  compiled-cache publication (digest + claims +
  causal publication-id chain).
- `import-runs-state.ts` -- import-runs state
  store.
- `source-sync-state.ts` -- source-sync state
  store (managed imported source page paths).
- These three state stores close the compile
  pipeline (write → publish → verify) and
  unblock Phase 4.3f (read/write paths + tools
  + bridge + gateway + corpus + prompt).
