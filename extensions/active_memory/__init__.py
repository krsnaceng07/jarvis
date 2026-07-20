"""active_memory — JARVIS active-memory plugin (Phase 4.2).

OpenClaw parity: mirrors ``extensions/active-memory/`` (18 source
files, ~180KB). The plugin's full surface is the auto-recall
router that picks ``memory-core`` vs ``memory-lancedb`` per
session and runs the recall sub-agent on every eligible
turn.

Phase 4.2 ships the plugin in three sub-phases:

- **Phase 4.2a** — foundation: ``types.py``, ``config.py``,
  ``recall_state.py``, ``session_policy.py``.
- **Phase 4.2b** — recall flow: ``recall.py`` +
  ``recall_run.py`` + ``query.py`` + ``prompt.py`` +
  ``session.py`` + ``transcript*.py``.
- **Phase 4.2c** — entry + slash command + doctor:
  ``index.py`` + ``doctor_contract_api.py``.

The 4.2c commit closes the active-memory port: with the
``register_active_memory`` callback wired to the host's
hook bus + slash-command router, the plugin is
feature-complete against OpenClaw's index.

Surface
-------
- **Tools:** none — active_memory is a *consumer* of the
  host's memory slot, not a producer.
- **Memory capability:** none — it reads via the host's
  memory plugin (``memory-core`` or ``memory-lancedb``).
- **Lifecycle hooks:** ``before_prompt_build`` (preflight
  + recall race).
- **Slash command:** ``/active-memory`` (status / on /
  off / help; ``--global`` for admin-gated operator
  config mutation).

OpenClaw parity
==============
Every constant, default, and config key in OpenClaw's
``types.ts`` and ``config.ts`` has a 1:1 Python counterpart.
Session policy helpers mirror OpenClaw's regexes,
fallback shapes, and admin-gating rules. The recall
orchestration + sub-agent dispatch are ported
``recall.ts`` + ``recall-run.ts`` line-for-line (with the
LLM run stubbed to a no-op that returns
``{ payloads: [] }``; the host overrides the stub to wire
in the real harness).
"""

from __future__ import annotations

import logging
from typing import Any

from jarvis_sdk import define_plugin_entry

from .doctor_contract_api import state_migrations as _state_migrations
from .index import register_active_memory

_log = logging.getLogger("extensions.active_memory")

# State migrations exposed to the host's doctor runner.
# Mirrors OpenClaw's `stateMigrations` export from
# doctor-contract-api.ts.
state_migrations = _state_migrations()


def _register(api: Any) -> None:
    """Register the active-memory plugin's surface with the host.

    Thin wrapper around ``register_active_memory`` so the
    plugin loader (which expects a ``register(api)`` callable
    in the entry module) can call us.
    """
    register_active_memory(api)


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


__all__ = ["entry", "state_migrations"]
