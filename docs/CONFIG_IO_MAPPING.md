OpenClaw → JARVIS Config IO Mapping

Purpose
- Capture high-level mapping of OpenClaw `src/config/*.ts` functions used by `io.factory.ts` into JARVIS `src/config/*.py` counterparts. Guide incremental parity work.

Status snapshot (2026-08-10)
- `create_config_io` minimal facade: implemented and safe for import-time use.
- `read_config_file_snapshot` family: implemented with path/hash/source-config metadata.
- `read_config_file_snapshot_with_plugin_metadata`: implemented with a conservative empty plugin metadata payload.
- `read_config_file_snapshot_for_write`: implemented with stable write-preflight metadata.
- `write_config_file`: implemented with JSON serialization and parent-dir creation.
- Runtime-only hooks that depend on a fully ported app runtime remain intentionally `NotImplementedError` stubs.

Mapping
- createConfigIO (openclaw-main/src/config/io.factory.ts)
  -> `src.config.io.create_config_io` (minimal facade implemented)

- io.read-helpers.ts
  -> `src.config.io` helpers (some implemented: `parse_config_json5`, `resolve_config_snapshot_hash`, `restore_env_changes_if_unchanged`)

- io.snapshot.ts
  -> `src.config.io` snapshot facades (to implement):
    - `read_config_file_snapshot_from_context` -> `read_config_file_snapshot` / `read_config_file_snapshot_with_plugin_metadata`
    - `read_best_effort_config_snapshot` -> `read_best_effort_config_snapshot` (partial minimal impl exists)
    - `read_config_file_snapshot_for_write` -> `read_config_file_snapshot_for_write` (placeholder/implemented)

- io.write.ts
  -> `src.config.io` write facades (to implement gradually):
    - `writeConfigFile` -> `write_config_file` (minimal implemented)
    - `readConfigFileSnapshotForWrite` helpers -> `read_config_file_snapshot_for_write`
    - `promote/preserve/recover` flows -> placeholders until full logic ported

- observe / recovery
  -> high-level functions such as `promoteConfigSnapshotToLastKnownGood`, `preserveConfigSnapshotAsClobbered`, `recoverConfigFromLastKnownGood` should remain NotImplemented until recovery subsystem ported.

Next steps
1. Implement `read_config_file_snapshot_with_plugin_metadata` to return `{'snapshot': ..., 'pluginMetadataSnapshot': ...}` shape used by callers.
2. Implement a minimal `read_config_file_snapshot_for_write` that returns `{'snapshot': ..., 'writeOptions': {...}}` with conservative safe defaults to allow caller tests that exercise write plumbing.
3. Add unit tests in `tests/test_config_io_snapshot.py` covering basic snapshot shapes and read-for-write metadata.
4. Iterate on write flow (`write_config_file`) to support a minimal preflight/atomic-write pattern used by tests.

Notes
- Keep `get_runtime_config` and `load_config` unimplemented (raise NotImplementedError) until runtime contract is ported; tests assert this behavior.
- Avoid importing extension modules or heavy dependencies at import time; prefer lazy imports inside functions to keep cold-start behavior.

