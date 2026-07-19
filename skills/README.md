# JARVIS skills

Declarative skills. Each skill is a **single markdown file** with YAML frontmatter —
no Python code.

Mirrors OpenClaw's `skills/` (51 skills). JARVIS targets all 51.

## Format

`skills/<id>/SKILL.md`:

```markdown
---
name: <id>
description: "<one-sentence description used by the LLM to pick this skill>"
homepage: <optional URL>
metadata:
  jarvis:
    emoji: "☔"
    requires: { bins: ["curl"] }
    install:
      - { id: brew, kind: brew, formula: curl, bins: [curl], label: "Install curl (brew)" }
---

# <Human Title>

<Usage instructions, trigger phrases, examples, fallback paths, etc.>
```

## Discovery

The runtime scans `skills/*/SKILL.md` and includes the frontmatter `description`
in the system prompt. The LLM picks the right skill from the description; the
runtime executes the tool calls the skill describes.

See `docs/skills/how-to-write.md` (Phase 3) for the full authoring guide.

## Catalog (51 target skills)

weather, summarize, github, notion, obsidian, notion-search, blogwatcher,
healthcheck, tmux, taskflow, meme-maker, nano-pdf, coding-agent, session-logs,
skill-creator, peekaboo, blucli, spotify-player, sonoscli, himalaya, eightctl,
goplaces, trello, things-mac, oracle, ordercli, songsee, video-frames, spike,
gog, apple-notes, apple-reminders, bear-notes, sherpa-onnx-tts,
openai-whisper, openai-whisper-api, model-usage, xurl, node-connect,
node-inspect-debugger, python-debugpy, mcporter, openhue, gemini, github-issues,
gifgrep, diagram-maker, camsnap, 1password, clawhub.

## Phasing

| Phase | What fills in |
|---|---|
| 3 | First 10 essentials (weather, summarize, github, notion, obsidian, healthcheck, taskflow, blogwatcher, meme-maker, nano-pdf) |
| 11 | Remaining 41 |
