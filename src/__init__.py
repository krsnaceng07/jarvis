"""jarvis host core — mirrors OpenClaw's ``src/`` topology.

Each subdirectory holds a focused system that the host
(``apps/desktop``) and CLI (``apps/cli``) consume:

  - ``src.skills``       — SKILL.md loader + registry
  - ``src.hooks``        — event bus for ``api.register_hook(...)``
  - ``src.cron``         — cross-platform scheduled-job runner
  - ``src.bootstrap``    — first-run seeder (config, MEMORY.md, IDENTITY.md, SOUL.md)
  - ``src.doctor``       — runs every plugin's ``doctor_contracts.detect(...)``
  - ``src.frontmatter``  — YAML frontmatter parser for SKILL.md / HOOK.md
  - ``src.gateway``      — stdlib HTTP server (Phase 3) for plugin routes

The shape mirrors OpenClaw's ``src/`` directory one-to-one
(``src/bootstrap/``, ``src/cron/``, ``src/gateway/``, ``src/hooks/``,
``src/skills/``, etc.) so the JARVIS Python port has the same
on-disk layout as the OpenClaw TypeScript source. Each subdir is
a Python package with its public API in its ``__init__.py``.
"""
