# JARVIS security

Security policy and tooling. The full policy lives in [`../SECURITY.md`](../SECURITY.md)
(threat model, defaults, reporting channel). This directory holds the tooling.

## Layout

```
security/
├── README.md           # this file
└── opengrep/           # OpenGrep rulepack (Phase 12)
    ├── README.md
    ├── precise.yml     # compiled super-config
    ├── rules/          # source rule YAMLs
    ├── compile_rules.py
    └── check_rule_metadata.py
```

## Audit tooling

- **`tools/ci/check_imports.py`** — enforces plugin import boundaries.
- **`tools/ci/check_cycles.py`** — detects import cycles.
- **`tools/ci/check_max_lines.py`** — caps file length.
- **`tools/ci/check_manifests.py`** — validates extension manifests.
- **`.github/CODEOWNERS`** — gates security-sensitive paths on `secops` review.
- **`security/opengrep/`** (Phase 12) — OpenGrep rulepack with precise rules for
  known dangerous patterns.

## Phasing

- **Phase 0.3 (now):** empty placeholder.
- **Phase 12:** OpenGrep rulepack lands; CI runs precise rules on every PR diff
  + full scan as manual dispatch.

## What JARVIS does NOT do

- ❌ No telemetry, no analytics, no "phone home" by default.
- ❌ No automatic updates without explicit operator approval.
- ❌ No cloud sync of session transcripts.
- ❌ No environment variable passthrough to plugins.

See [`../SECURITY.md`](../SECURITY.md) for the full list.
