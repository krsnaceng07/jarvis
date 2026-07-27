"""jarvis.plugin_state — host-side plugin-state store mechanics.

OpenClaw parity: mirrors ``src/plugin-state/``.
"""
from __future__ import annotations

from .runtime_health_store import (  # noqa: F401
    RuntimeHealthRecordEnvelope,
    RuntimeHealthStore,
    RuntimeHealthStoreOptions,
    create_runtime_health_record_envelope,
    create_runtime_health_store,
    current_process_token,
)
