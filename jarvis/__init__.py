"""jarvis — Phase 2 OpenClaw port modules.

Mirrors OpenClaw's `src/` topology. Each subdirectory holds a focused
system that the host (`apps/desktop`) and CLI (`apps/cli`) consume:

  - `jarvis.skills` — SKILL.md loader + registry
  - `jarvis.hooks`  — event bus for `api.register_hook(...)`
  - `jarvis.cron`   — cross-platform scheduled-job runner
  - `jarvis.bootstrap` — first-run seeder (config, MEMORY.md, IDENTITY.md, SOUL.md)
  - `jarvis.doctor` — runs every plugin's `doctor_contracts.detect(...)`
  - `jarvis.frontmatter` — YAML frontmatter parser for SKILL.md / HOOK.md
"""
