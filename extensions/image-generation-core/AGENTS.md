# image-generation-core (JARVIS)

Shared core package matching the OpenClaw `extensions/image-generation-core/`
shape. **Not a plugin** — OpenClaw ships this as a runtime
package (no `openclaw.plugin.json`), so JARVIS mirrors that:
just `pyproject.toml` + `__init__.py` re-exports.

## Parity status (vs `openclaw-main/extensions/image-generation-core/`)

| OpenClaw | JARVIS | Notes |
|---|---|---|
| `runtime-api.ts` re-exports | `__init__.py` re-exports | SDK surface passthrough |
| `src/runtime.ts` impl | deferred | Phase 5.16+ |
| `package.json` only (no plugin manifest) | `pyproject.toml` only | mirrors "core" not "plugin" |

The full runtime lands in Phase 5.16+ alongside the
``jarvis_sdk.image_generation_core`` module exports.
