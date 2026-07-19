---
name: Bug report
about: Something is broken, throwing, or behaving wrong
title: "bug: "
labels: bug
assignees: jarvis-architect
---

## What happened

A clear, concise description of the bug.

## What you expected

A clear, concise description of what you expected to happen.

## Repro steps

1. `python -m jarvis_desktop` (or `jarvis ...`)
2. Send message "..."
3. Observe: ...
4. Expected: ...

## Environment

- JARVIS version: `jarvis --version` (when CLI lands in PR 0.4)
- OS: [Windows 11 / macOS 14 / Ubuntu 24.04 / ...]
- Python: `python --version`
- Active extensions: list from `~/.jarvis/config.json` (when lands)
- LLM provider: [openai / anthropic / openrouter / ...]

## Logs / screenshots

Paste the relevant output. **Never paste API keys, tokens, or session
secrets.** Per AGENTS.md: live-verify when feasible, but never print
secrets.

## Possible cause (optional)

If you have a guess, link the file:line in the codebase you think is
involved. AGENTS.md review rules: high confidence required, read
siblings and callers before saying "the bug is here".

## Affected

- [ ] desktop UI
- [ ] CLI
- [ ] voice / audio
- [ ] memory
- [ ] specific tool (which?)
- [ ] specific channel (which?)
