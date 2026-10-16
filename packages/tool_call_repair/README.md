# jarvis-tool-call-repair

Repair for model-emitted plain-text tool calls (`[tool:name]{...}`,
`[name]` + JSON, Harmony `to=name` blocks, `<function=name>` XML-ish
spans), ported from OpenClaw's `packages/tool-call-repair/`.

This package ships the deterministic core: parser limits/options
(`contracts`), the structural scanner (`grammar`), block parsing and
user-text stripping (`payload`), assistant-message promotion
(`promote`), and the incremental Markdown-protection fast path
(`protection_fast_path`). The streaming state machine
(`stream-normalizer.ts`) lands as a follow-up slice and wires the
agent loop; until then nothing calls these paths at runtime.
