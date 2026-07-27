"""jarvis.shared — process-local shared helpers.

OpenClaw parity: mirrors ``src/shared/`` (global-singleton.ts,
pid-alive.ts, plus the prompt-section normalizer that OpenClaw keeps in
``packages/ai/src/utils/prompt-cache-stability.ts``).
"""
from __future__ import annotations

from .global_singleton import resolve_global_map, resolve_global_singleton  # noqa: F401
from .pid_alive import (  # noqa: F401
    get_process_start_time,
    is_pid_alive,
    is_pid_definitely_dead,
)
from .structured_prompt_section import normalize_structured_prompt_section  # noqa: F401
