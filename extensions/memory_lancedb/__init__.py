"""memory_lancedb — JARVIS LanceDB-backed long-term memory (Phase 4.1).

Mirrors OpenClaw's ``extensions/memory-lancedb/`` plugin (13
source files in the source; we ship the Python port as a
focused subset that meets the SDK contract).

Surface
-------
  - **Tools** (OpenClaw tool names):
      - ``memory_recall`` — vector search over the agent's
        memory. Returns ranked hits with category and score.
      - ``memory_store`` — append a long-term memory. Refuses
        prompt-injection payloads.
      - ``memory_forget`` — delete by exact id (GDPR) or by
        search.
  - **Memory capability:** registered via
    ``api.register_memory_capability`` with
    ``prompt_builder`` + ``flush_plan_resolver`` + ``runtime``
    + ``public_artifacts``. Matches OpenClaw's
    ``MemoryPluginCapability`` shape.
  - **CLI:** ``jarvis ltm list|search|query|stats`` via the
    slash command ``/ltm``.
  - **Lifecycle hooks:**
      - ``before_prompt_build`` — auto-recall; injects
        top-K relevant memories as ``prependContext``.
      - ``agent_end`` — auto-capture; sanitizes user
        messages, gates them through ``should_capture``,
        embeds them, and stores in the agent's memory.
      - ``session_end`` — clears per-session auto-capture
        cursor.
  - **Doctor contract:** legacy ``memory.json`` migration +
    LanceDB per-agent-isolation migration.

Backends
--------
The plugin transparently supports two backends:

  1. **LanceDB** (preferred) — uses the lazily-loaded
     ``lancedb`` package. The native dep is heavy and may
     not be installable on every platform, so the plugin
     detects availability with ``is_lancedb_available()``.
  2. **In-memory numpy fallback** — same public interface,
     no on-disk state, used in tests and on unsupported
     platforms.

Both backends implement the same ``MemoryStore`` protocol
and both observe the same agent scoping rules.

OpenClaw parity
==============
- Tool names match OpenClaw's
  ``memory_recall``/``memory_store``/``memory_forget``
  exactly. The host's dispatch map is keyed on these names.
- The LanceDB table name, agent column, and SQL predicate
  follow OpenClaw's ``lancedb-schema.ts``.
- The auto-recall ``prependContext`` payload format is
  identical to OpenClaw's
  ``formatRelevantMemoriesContext``.
- The auto-capture gate is the same
  ``should_capture`` + ``detect_category`` pair.

Phase 4.1 vs Phase 4.0
=====================
Phase 4.0 ships ``extensions/memory_core`` (SQLite key/value
+ substring search). Phase 4.1 adds ``memory_lancedb``
(OpenAI embeddings + vector search) as a parallel
extension. The host picks one per process — Phase 4.0's
``memory_core`` stays the default; ``memory_lancedb`` is
opt-in via the operator's config.

Phase 4.2 (active_memory) will introduce a single-active-
slot router so only one of the two is wired into the host
at a time.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from jarvis_sdk import (
    PluginApi,
    define_plugin_entry,
)

from . import doctor as doctor_module, plugin_globals
from .config import MemoryConfig, parse_config, vector_dims_for_model
from .embeddings import create_embeddings
from .plugin import (
    MEMORY_LANCEDB_CLI_HANDLER,
    MemoryLancedbPlugin,
    build_capability,
)
from .runtime import MemoryDB

_log = logging.getLogger("extensions.memory_lancedb")


# ── Registration ────────────────────────────────────────────────


def _resolve_db_path(plugin_config: dict[str, Any], data_dir: Path) -> str:
    """Resolve the db path from the plugin config + host data dir.

    Mirrors OpenClaw's ``api.resolvePath(dbPath)`` behavior:
    relative paths are anchored at the plugin's data dir.
    Cloud URIs (``s3://``, ``gs://``) are passed through
    unchanged.
    """
    raw = plugin_config.get("dbPath")
    if isinstance(raw, str) and raw:
        if "://" in raw:
            return raw
        if raw.startswith("~"):
            return str(Path(raw).expanduser())
        if Path(raw).is_absolute():
            return raw
        return str(data_dir / "memory" / "lancedb")
    return str(data_dir / "memory" / "lancedb")


def _resolve_dims(cfg: MemoryConfig) -> int:
    """Return the vector dimension for the active model.

    Mirrors OpenClaw's ``vectorDim = dimensions ?? vectorDimsForModel(model)``.
    """
    if cfg.embedding_dimensions is not None:
        return cfg.embedding_dimensions
    return vector_dims_for_model(cfg.embedding_model)


# ruff: noqa: PLR0915  # _register is intentionally long (parity with OpenClaw's index.ts)
def _register(api: PluginApi) -> None:
    """Register the memory_lancedb plugin's surface with the host's PluginApi."""
    plugin = MemoryLancedbPlugin()

    # ── Config parsing ──────────────────────────────────────────
    # The JARVIS host doesn't yet pass per-plugin config in the
    # ``api`` (Phase 4.2 wires this). For now we read from
    # ``api.ctx.config`` if the host set it, and fall back to an
    # empty dict (which uses the in-memory store + a stub
    # embeddings client — see ``config.parse_config``).
    raw_config: dict[str, Any] = {}
    ctx_config = getattr(api.ctx, "config", None)
    if isinstance(ctx_config, Mapping):
        plugin_cfg = ctx_config.get("memory_lancedb")  # type: ignore[index]
        if isinstance(plugin_cfg, Mapping):
            raw_config = dict(plugin_cfg)  # type: ignore[arg-type]
    try:
        cfg = parse_config(raw_config)
    except ValueError as exc:
        api.logger.warn(f"memory-lancedb: disabled until configured ({exc})")
        return

    db_path = _resolve_db_path(raw_config, api.ctx.data_dir)
    Path(db_path).mkdir(parents=True, exist_ok=True)
    vector_dim = _resolve_dims(cfg)

    try:
        db = MemoryDB(
            db_path=db_path,
            vector_dim=vector_dim,
            storage_options=cfg.storage_options,
        )
    except Exception as exc:
        api.logger.warn(f"memory-lancedb: failed to open store at {db_path}: {exc}")
        return

    # The provider-adapter path needs host config. The direct
    # OpenAI path is selected automatically when no adapter is
    # wired.
    from jarvis_sdk.memory_embeddings import get_memory_embedding_provider

    embeddings = create_embeddings(
        cfg,
        config_provider=lambda: (getattr(api.ctx, "config", None) or {}),
        get_provider=getattr(api, "get_memory_embedding_provider", None) or get_memory_embedding_provider,
    )
    plugin.configure(cfg, db, embeddings)

    # ── Active-slot globals (used by the CLI handlers) ─────────
    plugin_globals.set_active_db(db)
    plugin_globals.set_active_embeddings(embeddings)

    # ── Tools (memory_recall, memory_store, memory_forget) ──────
    api.register_tool(
        plugin,
        {"names": ["memory_recall", "memory_store", "memory_forget"]},
    )

    # ── Memory capability (single-active-slot) ─────────────────
    _capability = build_capability(plugin)
    _public_artifacts = _capability.public_artifacts
    if _public_artifacts is None:  # pragma: no cover - build_capability always sets one
        raise RuntimeError("memory_lancedb capability missing public_artifacts")
    api.register_memory_capability(
        {
            "prompt_builder": _capability.prompt_builder,
            "flush_plan_resolver": _capability.flush_plan_resolver,
            "runtime": _capability.runtime,
            "public_artifacts": {"list_artifacts": _public_artifacts.list_artifacts},
        }
    )

    # ── Slash command: /ltm ─────────────────────────────────────
    api.register_command(
        {
            "name": "ltm",
            "description": ("LanceDB memory plugin commands: list, search, query, stats."),
            "accepts_args": True,
            "expose_sender_is_owner": True,
            "handler": MEMORY_LANCEDB_CLI_HANDLER,
        }
    )

    # ── Lifecycle hooks ─────────────────────────────────────────

    async def _before_prompt_build(event: Any) -> None:
        """Auto-recall hook. Mutates ``event`` to set
        ``prependContext`` if any memories survive.

        Mirrors OpenClaw's ``before_prompt_build`` hook. The
        JARVIS host currently doesn't fire this hook; the
        plugin's hook will be picked up by Phase 4.2's
        active-memory router.
        """
        # Accept either OpenClaw shape (event.prompt, event.messages)
        # or JARVIS current shape (event.input, event.output).
        if isinstance(event, dict):
            prompt = event.get("prompt") or event.get("input") or ""
            messages = event.get("messages")
            agent_id = event.get("agentId") or event.get("agent_id")
            session_key = event.get("sessionKey") or event.get("session_key")
        else:
            prompt = getattr(event, "prompt", "") or ""
            messages = getattr(event, "messages", None)
            agent_id = getattr(event, "agentId", None)
            session_key = getattr(event, "sessionKey", None)
        if not prompt:
            return
        prepend = await plugin.auto_recall(
            prompt=prompt,
            messages=messages,
            agent_id=agent_id,
        )
        if prepend is None:
            return
        if isinstance(event, dict):
            event["prependContext"] = prepend
        else:
            event.prependContext = prepend
        _ = session_key  # currently unused; reserved for Phase 4.2

    async def _agent_end(event: Any) -> None:
        """Auto-capture hook. Sanitizes + stores memory-worthy turns.

        Mirrors OpenClaw's ``agent_end`` hook. Accepts either
        OpenClaw shape (event.messages, event.success) or the
        JARVIS current shape (event.input, event.output).
        """
        if isinstance(event, dict):
            messages = event.get("messages")
            if not messages:
                # JARVIS current shape: derive a single user
                # message from input.
                input_text = event.get("input")
                if input_text:
                    messages = [{"role": "user", "content": str(input_text)}]
            agent_id = event.get("agentId") or event.get("agent_id")
            session_key = (
                event.get("sessionKey")
                or event.get("session_key")
                or event.get("sessionId")
                or event.get("session_id")
            )
            success = event.get("success", True)
        else:
            messages = getattr(event, "messages", None)
            agent_id = getattr(event, "agentId", None)
            session_key = getattr(event, "sessionKey", None)
            success = getattr(event, "success", True)
        if not success or not messages:
            return
        await plugin.auto_capture(
            messages=messages,
            agent_id=agent_id,
            session_key=session_key,
        )

    def _session_end(event: Any) -> None:
        """Clear per-session auto-capture cursor.

        Mirrors OpenClaw's ``session_end`` hook. The hook
        runs synchronously (the cursor is in-memory).
        """
        if isinstance(event, dict):
            agent_id = event.get("agentId") or event.get("agent_id")
            session_key = (
                event.get("sessionKey")
                or event.get("session_key")
                or event.get("sessionId")
                or event.get("session_id")
            )
        else:
            agent_id = getattr(event, "agentId", None)
            session_key = getattr(event, "sessionKey", None)
        plugin.clear_session_cursor(agent_id=agent_id, session_key=session_key)

    api.register_hook("before_prompt_build", _before_prompt_build, priority=10)
    api.register_hook("agent_end", _agent_end, priority=0, timeout_ms=30_000)
    api.register_hook("session_end", _session_end, priority=0)

    # ── Doctor contract ─────────────────────────────────────────
    api.register_doctor_contract(
        {
            "id": "memory_lancedb.legacy_jarvis",
            "version": 1,
            "detect_label": "Memory LanceDB legacy per-agent isolation",
            "detect_path": "memory/lancedb",
            "detect": lambda state_dir, config: [
                {
                    "id": f.id,
                    "label": f.label,
                    "preview": list(f.preview),
                }
                for f in doctor_module.detect_legacy(state_dir, config)
            ],
            "apply": lambda state_dir, config: {
                "changes": list(doctor_module.apply_migration(state_dir, config).changes),
                "warnings": list(doctor_module.apply_migration(state_dir, config).warnings),
            },
        }
    )

    # ── Service registration ────────────────────────────────────
    # The SDK doesn't yet have ``register_service`` (the host's
    # service-lifecycle machinery is Phase 4.2). We log the
    # start message here and rely on Python's normal process
    # shutdown (and Phase 4.2's hook) to clean up. ``db.close()``
    # is idempotent so a redundant call is safe.
    _log.info(
        "memory-lancedb: initialized (db: %s, model: %s)",
        db_path,
        cfg.embedding_model,
    )


# ── Plugin entry (mirrors OpenClaw's `definePluginEntry`) ───────────
entry = define_plugin_entry(
    id="memory_lancedb",
    kind="memory",
    name="Memory (LanceDB)",
    description=(
        "LanceDB-backed long-term memory with auto-recall, auto-capture, "
        "and vector search. OpenAI-compatible embeddings. Phase 4.1 "
        "OpenClaw parity."
    ),
    register=_register,
    version="0.1.0",
    activation="on_commands",
    permissions=["fs:read:memory", "fs:write:memory", "net:https:api.openai.com"],
)


__all__ = ["entry"]
