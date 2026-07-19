---
name: Feature request
about: Suggest a new capability, tool, or behavior
title: "feat: "
labels: enhancement
assignees: jarvis-architect
---

## Problem / motivation

What user need does this address? What is the workflow today, and what
is it missing?

## Proposed solution

A clear, concise description of what you want JARVIS to do.

## Existing alternatives (preflight per AGENTS.md)

Before requesting, check:
- Existing JARVIS extensions in `extensions/`
- OpenClaw equivalent (see `openclaw-main/extensions/`)
- Open-source libraries that already solve this

If something already exists, prefer it. Build custom only when existing
options are unsuitable, too expensive, unmaintained, unsafe, non-
compliant, or the user explicitly asks for custom.

## Plugin vs core

Should this be:
- A new `extensions/<id>/` (preferred — most features belong here)
- A new `skills/<name>/SKILL.md` (declarative, no code)
- A new `packages/<name>/` (only if multiple extensions need it)
- A change to core (rare; needs strong justification)

## User story (optional)

> As a [persona], I want to [action] so that [outcome].

## Acceptance criteria

- [ ] criterion 1
- [ ] criterion 2
- [ ] criterion 3

## Priority

How urgent? What breaks if we don't do this?
