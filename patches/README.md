# JARVIS patches

Upstream dependency patches. Used when a transitive dependency has a bug we can't
wait for upstream to fix and can't easily monkey-patch in our own code.

Mirrors OpenClaw's `patches/` directory.

## Layout

```
patches/
├── README.md
└── <dep-name>@<version>.patch
```

## Rules

- Patches are **last resort**. Prefer: upgrade, monkey-patch, fork, replace.
- Each patch must have a `patches/<dep>@<version>.patch` filename and a comment
  in the patch file explaining the upstream issue (link to issue/PR).
- Patches are applied via `uv` (PEP 660) or the `patches/` mechanism in `pyproject.toml`.
- A patch lands in the same PR that needs it. Do not carry forward without
  re-evaluating on each release.

## Phasing

- **Phase 0.3 (now):** empty placeholder.
- **Future:** only if a dep needs an emergency fix.
