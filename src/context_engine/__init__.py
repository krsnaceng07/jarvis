"""JARVIS context engine — OpenClaw ``src/context-engine/`` parity (Phase 5.12).

No barrel re-exports: OpenClaw's package has no ``index.ts``; import
submodules directly.

Parity map (Phase 5.12 slice, docs/OPENCLAW_BRAIN_PORT_PLAN_V2.md):
  - ``src/context-engine/types.ts``               -> types.py
  - ``src/context-engine/registry.ts``            -> registry.py
  - ``src/context-engine/registry.test-support.ts`` -> registry_test_support.py
  - ``src/context-engine/delegate.ts``            -> delegate.py
  - ``src/context-engine/host-compat.ts``         -> host_compat.py
  - ``src/context-engine/runtime-settings.ts``    -> runtime_settings.py
  - ``src/context-engine/quarantine-health.ts``   -> quarantine_health.py
  - ``src/context-engine/legacy.ts``              -> legacy.py
  - ``src/context-engine/legacy.registration.ts`` -> legacy_registration.py
  - ``src/context-engine/init.ts``                -> init.py
  Support seams: ``src/plugins/memory_state.py`` (memory-state),
  ``src/plugin_state/runtime_health_store.py`` (runtime-health-store).

Tests: ``tests/test_phase512_context_engine.py`` ports the vectors from
``context-engine.test.ts``, ``host-compat.test.ts``,
``runtime-settings.test.ts``, and ``quarantine-health.test.ts``.
"""
