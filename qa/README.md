# JARVIS quality assurance

QA scenarios. YAML only — per AGENTS.md, no fenced `qa-scenario` / `qa-flow`
Markdown files under `qa/scenarios/`.

Mirrors OpenClaw's `qa/` (scenarios, maturity-scores, convex-credential-broker).

## Layout

```
qa/
├── README.md
├── scenarios/
│   ├── index.yaml
│   ├── channels/
│   ├── memory/
│   ├── tools/
│   └── skills/
├── maturity_scores.yaml     # per-extension maturity grade (Phase 12)
├── frontier_harness_plan.md # how frontier models are evaluated (Phase 12)
└── harness_plan.md
```

## Phasing

- **Phase 0.3 (now):** empty placeholder.
- **Phase 12:** scenarios + maturity scores + harness plan.

## Rules

- Scenarios are YAML only. Markdown narratives live in `docs/` not `qa/`.
- Each scenario declares: goal, preconditions, steps, expected outcomes, cleanup.
- Maturity scores are per-extension (alpha / beta / stable / core).
