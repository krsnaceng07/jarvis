# Plugin SDK Boundary

This package is the public contract between plugins and core. Changes here
can affect every extension. Mirrors OpenClaw's `src/plugin-sdk/AGENTS.md`.

## Source of truth

- `extensions/AGENTS.md` — extension boundary rules (the *user* of this SDK)
- `packages/plugin_sdk/src/jarvis_sdk/entry.py` — `define_plugin_entry` (the entry shape)
- `packages/plugin_sdk/src/jarvis_sdk/api.py` — `PluginApi` (the registration surface)
- `packages/plugin_sdk/src/jarvis_sdk/contract.py` — base classes (Plugin, ToolPlugin, ...)
- `packages/plugin_sdk/src/jarvis_sdk/result.py` — `Result = Ok[T] | Err[T]` discriminated union

## Boundary rules

- **Plugins import ONLY from `jarvis_sdk.*`.** Never from `src/...`, other extensions, or other packages.
- **Host loads plugins; plugins do not reach into host internals.** Prefer narrow, versioned SDK entrypoints over broad convenience re-exports.
- **Plugins use `api.registerX(...)` to register capabilities.** The host defines what extension points exist (`register_tool`, `register_command`, `register_cli`, `register_memory_capability`, `register_provider`, `register_channel`, `register_doctor_contract`, `register_http_handler`).
- **SDK subpaths are narrow.** A plugin importing `jarvis_sdk.api` does not pay the cost of every other subpath. Heavy subpaths land in `*.runtime` subpaths.
- **No import-time side effects.** Plugin availability comes from manifest ownership plus explicit activation, not eager global registry seeding.
- **Tool return type is `Result`.** A tool returns `Ok(value)` for success, `Err(error_str, code=...)` for known failure. The host maps `Result` to the LLM's tool response shape.
- **Tool manifests live in `openclaw.plugin.json`.** The SDK is for runtime contracts; the manifest is for discovery and config.

## Verifying the boundary

- `tools/ci/check_imports.py` enforces the `jarvis_sdk` import boundary.
- `tools/ci/check_manifests.py` validates every `extensions/*/openclaw.plugin.json`.

## Expanding the boundary

- If a plugin needs a new seam, add a typed subpath. Don't reach into core.
- When adding an export, keep these aligned:
  - this file (rules)
  - `src/jarvis_sdk/__init__.py` (re-export)
  - the relevant subpath module
  - tests under `packages/plugin_sdk/tests/`
- Breaking changes are major-version work, not drive-by cleanup.
