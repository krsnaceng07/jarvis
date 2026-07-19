# Security Policy

JARVIS treats security as a deliberate tradeoff: **strong defaults without killing capability.**
The goal is to stay powerful for real work while making risky paths explicit and operator-controlled.

## Reporting a vulnerability

**Do not file a public issue for security bugs.** Open a private security advisory
on the repository (GitHub → Security → Advisories → "New draft security advisory")
or email the maintainer directly (see `git log` for the active maintainer email).

Include in your report:

- Description of the vulnerability and impact
- Reproduction steps / proof of concept
- Affected versions
- Suggested fix (if any)
- Your name/handle for credit in the advisory (or "anonymous")

We aim to acknowledge within 72 hours and ship a fix within 30 days for critical issues.

## Threat model

JARVIS is a **local-first, single-user** personal AI assistant. The trust boundaries:

| Boundary | Trust | Default posture |
|---|---|---|
| Local user (operator) | High | Full host access for the `main` session |
| Remote user (channel peer) | Low | DM pairing; untrusted input treated as data, never as instructions |
| Plugin | Variable | Imports only `jarvis_sdk.*`; declared permissions in manifest |
| External API | Low | Credentials in `~/.jarvis/credentials/`; SSRF policy enforced |
| LLM output | Low | Treat as untrusted data; never auto-execute tool calls without user confirmation in sensitive paths |

## Security defaults (mirrors OpenClaw's posture)

- **DM pairing** on every channel (Telegram, Discord, Slack, WhatsApp, Signal, etc.).
  Unknown senders receive a short pairing code; the bot does not process their message
  until the operator approves (`jarvis pairing approve <channel> <code>`).
- **Public inbound DMs require explicit opt-in:** set `dmPolicy="open"` AND include `"*"`
  in the channel allowlist.
- **Sandbox by default** for non-`main` sessions: `agents.defaults.sandbox.mode: "non-main"`.
  Docker is the default sandbox backend; SSH and OpenShell backends are also available.
- **No silent config compat:** `jarvis doctor --fix` is the only path for legacy config.
  Runtime reads canonical shape only.
- **Secret storage:** channel/provider creds live in `~/.jarvis/credentials/`. Model
  auth profiles live in `~/.jarvis/agents/<agentId>/auth-profiles.json`. **Never in repo.**
- **No environment variable smuggling:** all env-driven paths must be listed in `AGENTS.md`.
- **SQLite only** for runtime state. No JSON/JSONL/TXT sidecar files for caches,
  queues, registries, indexes, cursors, or plugin scratch data.

## Plugin isolation

- Extensions may import **only from `jarvis_sdk.*`** and their own package.
- Cross-extension imports are forbidden (enforced by `tools/ci/check_imports.py`).
- Extensions declare permissions in `jarvis.plugin.json` (e.g. `network:outbound`,
  `fs:read:user_workspace`, `process:spawn:playwright`).
- Core refuses to load an extension that declares unknown permissions or fails
  the manifest schema check.

## Secret reference failures

Per `AGENTS.md`:

- **Proven-inactive surfaces skip the failure.**
- **Unknown ownership fails closed** (the gateway refuses to start).
- **Otherwise start, mark the exact capability/account/route configured-unavailable,**
  emit a typed redacted diagnostic, and forbid implicit credential fallback.
- **`jarvis doctor` and `jarvis status` must list every degraded owner.**

## Audit tooling

- **`tools/ci/check_imports.py`** — enforces plugin boundary invariants on every commit.
- **`tools/ci/check_cycles.py`** — detects import cycles that could leak internal symbols.
- **`tools/ci/check_max_lines.py`** — caps file length (2000 lines hard limit) to limit
  the blast radius of any single change.
- **`tools/ci/check_manifests.py`** — validates every `extensions/*/jarvis.plugin.json`
  against the manifest schema.
- **`security/opengrep/` rulepack** (Phase 12) — OpenGrep-based security scanner with
  precise rules for known dangerous patterns.
- **`.github/CODEOWNERS`** — gates security-sensitive paths on `secops` review.
  See the current `CODEOWNERS` file for the exact paths.

## What JARVIS does NOT do

- ❌ No telemetry, no analytics, no "phone home" by default.
- ❌ No automatic updates without explicit operator approval.
- ❌ No cloud sync of session transcripts (they live in local SQLite).
- ❌ No auto-execution of tool calls derived from LLM output in non-`main` sessions.
- ❌ No environment variable passthrough to plugins (plugins must declare required env vars).

## Out of scope

- Vulnerabilities in third-party dependencies — please report upstream first.
  JARVIS will mirror the fix as soon as a patched version is available.
- Issues in the **OpenClaw reference** at `openclaw-main/` — that is a vendored
  snapshot, not actively maintained. Report issues against the upstream OpenClaw repo.
- Best-practice suggestions without a concrete vulnerability.

## Acknowledgements

We credit security researchers who report valid issues in the release notes
(see `CHANGELOG.md`) unless they request anonymity.
