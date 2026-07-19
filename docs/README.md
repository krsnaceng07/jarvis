# JARVIS docs

Documentation as code. Mirrors OpenClaw's `docs/` (30 categories). JARVIS targets
11 categories — same shape, smaller surface.

## Layout

| Category | Purpose | Phase |
|---|---|---|
| `architecture/` | How the pieces fit together. | 1 |
| `concepts/` | Domain concepts (agent, session, gateway, plugin, provider, channel, memory-host, skill, tool, cron). | 1 |
| `installation/` | Quickstart, from-source, from-MARK-XXXIX, update. | 0.4 |
| `channels/` | Per-channel setup (telegram, discord, slack, whatsapp, signal, matrix, feishu, msteams, webchat). | 5+ |
| `providers/` | Per-provider setup. | 6+ |
| `tools/` | Per-tool docs (browser, filesystem, shell, desktop, media, calendar, reminders, weather, screenshot). | 2 |
| `skills/` | How to write + catalog. | 3 |
| `memory/` | Memory hosts (memory-core, memory-lancedb, memory-host-sdk). | 4 |
| `security/` | Threat model, secret storage, sandboxing, permissions. | 0.3 (this dir) + 12 |
| `reference/` | Config keys, manifest schema, secret refs, result type, RPC schema. | 1+ |
| `development/` | Plugin authoring, writing skills, testing, CI, contribution. | 1+ |
| `operations/` | Doctor, migrations, logging, metrics, troubleshooting. | 8 |
| `releases/` | Versioning, changelog policy. | 0.3 (this dir) |

## Rules

- Docs change with code. Every behavior/API change has a corresponding doc update
  in the same PR.
- Use the `$technical-documentation` skill (when available) for reviews.
- Docs final answers should include the local file path: `docs/<area>/<file>.md`.
- The `docs/concepts/` files are the canonical place for domain vocabulary.
- `docs/reference/` is for machine-readable contracts (schemas, key lists).
