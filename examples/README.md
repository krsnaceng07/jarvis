# JARVIS examples

Runnable examples showing how to use JARVIS or extend it.

Mirrors OpenClaw's `examples/` (currently `ai-chat` — a headless gateway + CLI example).

## Layout

```
examples/
├── README.md
├── ai_chat/             # Headless gateway + CLI example
├── custom_skill/        # "How to write a skill" example
├── custom_extension/    # "How to write an extension" example
└── custom_memory_host/  # "How to write a memory host" example
```

## Phasing

- **Phase 0.3 (now):** empty placeholder.
- **Phase 12:** examples land as documentation-driven tutorials.

## Rules

- Examples are **runnable** (not just code snippets).
- Examples use real (mocked) JARVIS APIs and can be tested in CI.
- Each example has its own `pyproject.toml` so it can be installed standalone.
