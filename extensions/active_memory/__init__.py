"""active_memory — JARVIS active-memory plugin (Phase 4.2).

OpenClaw parity: mirrors ``extensions/active-memory/`` (18 source
files, ~180KB). The plugin's full surface is the auto-recall
router that picks ``memory-core`` vs ``memory-lancedb`` per
session and runs the recall sub-agent on every eligible
turn.

Phase 4.2 ships the plugin in three sub-phases:

- **Phase 4.2a** (this commit) — foundation:
  - ``types.py`` — constants, defaults, type aliases.
  - ``config.py`` — operator-facing config schema
    (25+ keys) + the CLI-runtime timeout bump.
  - ``recall_state.py`` — TTL cache + per-agent/model
    circuit breaker + log helpers.
  - ``session_policy.py`` — eligibility checks
    (chat type, allow/deny lists, harness skip,
    session toggle store) + the ``/active-memory``
    slash command's eligibility/permission helpers.
- **Phase 4.2b** (next) — recall flow:
  ``recall.ts`` + ``recall-run.ts`` + ``query.ts`` +
  ``prompt.ts`` + ``session.ts`` + ``transcript*.ts``.
- **Phase 4.2c** (after that) — entry + slash command
  + doctor: ``index.ts`` + ``doctor-contract-api.ts``.

The 4.2a commit is shippable on its own — the
eligibility, harness-skip, and config-parse primitives
are exactly the building blocks the recall flow and
the slash command will need.

Surface
-------
- **Tools:** none in 4.2a (4.2c wires the slash command).
- **Memory capability:** none — active_memory is a
  *consumer* of the host's memory slot, not a producer.
  It reads via ``api.runtime.memory_plugin.get_memory_search_manager()``
  (Phase 4.2b).
- **Lifecycle hooks:** none registered in 4.2a (4.2c
  registers ``before_prompt_build``).

OpenClaw parity
==============
Every constant, default, and config key in OpenClaw's
``types.ts`` and ``config.ts`` has a 1:1 Python counterpart.
Session policy helpers mirror OpenClaw's regexes,
fallback shapes, and admin-gating rules.
"""

from __future__ import annotations

import logging
from typing import Any

from jarvis_sdk import define_plugin_entry

_log = logging.getLogger("extensions.active_memory")


def _register(api: Any) -> None:
    """Register the active-memory plugin's surface with the host.

    Phase 4.2a registers no tools, hooks, or commands — the
    entry point exists only so the plugin loader discovers
    the module. Phase 4.2c wires:

    - The ``/active-memory`` slash command (uses
      ``is_session_active_memory_disabled`` +
      ``set_session_active_memory_disabled`` +
      ``format_active_memory_command_help`` from
      ``session_policy``).
    - The ``before_prompt_build`` hook (uses
      ``is_eligible_interactive_session`` +
      ``is_allowed_chat_type`` + ``is_allowed_chat_id`` +
      ``should_skip_active_memory_for_harness_session`` from
      ``session_policy``).

    The eligibility primitives are ready and unit-tested in
    4.2a; wiring them into the host's hook bus is 4.2c.
    """
    logger = getattr(api, "logger", None)
    if logger is not None:
        info = getattr(logger, "info", None)
        if callable(info):
            info(
                "active-memory: foundation loaded (types + config + "
                "recall_state + session_policy); recall flow wires in 4.2b/c"
            )


# ── Plugin entry (mirrors OpenClaw's `definePluginEntry`) ───────────
entry = define_plugin_entry(
    id="active_memory",
    kind="memory",
    name="Active Memory",
    description=(
        "Runs bounded pre-reply memory retrieval and implements "
        "per-agent Remember across conversations for eligible "
        "private conversations. Phase 4.2 OpenClaw parity."
    ),
    register=_register,
    version="0.1.0",
    activation="on_startup",
    permissions=["fs:read:memory", "fs:write:memory"],
)


__all__ = ["entry"]
