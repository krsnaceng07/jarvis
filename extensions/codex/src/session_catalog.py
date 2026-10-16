"""Codex session catalog — native thread discovery and sidebar registration.

OpenClaw parity: mirrors `extensions/codex/src/session-catalog.ts` and the
catalog registration block in `extensions/codex/index.ts:178-210`.

The session catalog discovers non-archived Codex threads from the operator's
native Codex home (or explicitly configured additional homes) and surfaces
them in the JARVIS sidebar.  It is opt-in and enabled by default when the
`codex` plugin is active; operators can disable it with
`sessionCatalog.enabled: false` without disabling the full Codex harness.

Architecture (matching OpenClaw):
- `create_codex_session_catalog_control` builds a stateful control factory
  that knows how to list, archive, and continue Codex sessions.
- `codex_session_catalog_runtime_register` calls `api.register_catalog` (or
  the equivalent JARVIS seam) to wire the control into the sidebar.
- `create_codex_session_catalog_node_host_commands` and
  `create_codex_session_catalog_node_invoke_policies` emit the node host
  commands and invoke policies needed for paired-node session discovery.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable


# ---------------------------------------------------------------------------
# Catalog control types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CodexSessionCatalogEntry:
    """A single Codex thread row in the session catalog."""

    thread_id: str
    name: str | None = None
    status: str = "unknown"
    cwd: str | None = None
    source: str | None = None
    updated_at: int | None = None
    human_attached: bool = False
    node_id: str | None = None  # set for paired-node rows


@dataclass
class CodexSessionCatalogControl:
    """Stateful control for the Codex session catalog.

    OpenClaw parity: mirrors the `CodexSessionCatalogControlFactory` shape.
    Lifecycle: created once during `register()`, shared across turns.
    """

    _resolve_runtime_options: Callable[..., Any]
    _binding_store: Any
    _get_plugin_config: Callable[[], Any]
    _get_runtime_config: Callable[[], Any]

    async def list_sessions(
        self,
        *,
        include_archived: bool = False,
        limit: int = 100,
    ) -> list[CodexSessionCatalogEntry]:
        """List Codex threads visible to the catalog."""
        plugin_config = self._get_plugin_config()
        catalog_config = getattr(plugin_config, "session_catalog", None)
        if catalog_config is not None and not getattr(catalog_config, "enabled", True):
            return []
        # Delegate to the binding store's catalog snapshot when available.
        if hasattr(self._binding_store, "list_catalog_sessions"):
            try:
                raw = await self._binding_store.list_catalog_sessions(
                    include_archived=include_archived,
                    limit=limit,
                )
                return [_normalize_entry(r) for r in raw if isinstance(r, dict)]
            except Exception:
                pass
        return []

    async def archive_session(self, thread_id: str, *, confirmed: bool = False) -> dict[str, Any]:
        """Archive a stored or idle Codex session.

        OpenClaw parity: active sessions cannot be archived; explicit
        confirmation is required (mirrors the `noOtherRunner` guard).
        """
        if not confirmed:
            return {"error": "explicit confirmation required to archive a Codex session"}
        if hasattr(self._binding_store, "archive_session"):
            try:
                return await self._binding_store.archive_session(thread_id)
            except Exception as exc:
                return {"error": str(exc)}
        return {"error": "archive not supported by binding store"}

    async def continue_session(
        self,
        thread_id: str,
        *,
        context: Any = None,
    ) -> dict[str, Any]:
        """Fork or continue a stored/idle session into the current OpenClaw session.

        OpenClaw parity: mirrors the catalog-level continuation path that calls
        `session-catalog-adoption.ts`. The fork attaches to the current
        JARVIS session and remains readable by thread ID from other native Codex
        clients.
        """
        if hasattr(self._binding_store, "adopt_session"):
            try:
                return await self._binding_store.adopt_session(
                    thread_id,
                    context=context,
                )
            except Exception as exc:
                return {"error": str(exc)}
        # Fallback: store the thread id as a pending binding so the next harness
        # turn picks it up via inbound_claim resolution.
        session_id = _resolve_session_id(context)
        if session_id and hasattr(self._binding_store, "update_binding"):
            try:
                self._binding_store.update_binding(session_id, {"threadId": thread_id})
                return {"adopted": True, "threadId": thread_id}
            except Exception as exc:
                return {"error": str(exc)}
        return {"error": "binding store does not support session adoption"}


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_codex_session_catalog_control(
    *,
    resolve_runtime_options: Callable[..., Any],
    binding_store: Any,
    get_plugin_config: Callable[[], Any],
    get_runtime_config: Callable[[], Any],
    config: Any = None,
) -> CodexSessionCatalogControl:
    """Create the session catalog control instance.

    OpenClaw parity: mirrors `createCodexSessionCatalogControl`
    (`session-catalog.ts`). Called once during plugin registration;
    the returned object is shared across all catalog operations.
    """
    return CodexSessionCatalogControl(
        _resolve_runtime_options=resolve_runtime_options,
        _binding_store=binding_store,
        _get_plugin_config=get_plugin_config,
        _get_runtime_config=get_runtime_config,
    )


# ---------------------------------------------------------------------------
# Runtime registration
# ---------------------------------------------------------------------------


def codex_session_catalog_runtime_register(
    api: Any,
    *,
    resolve_runtime_options: Callable[..., Any],
    binding_store: Any,
    control: CodexSessionCatalogControl,
    get_plugin_config: Callable[[], Any],
    get_runtime_config: Callable[[], Any],
) -> None:
    """Register the Codex session catalog as a JARVIS sidebar catalog.

    OpenClaw parity: mirrors `codexSessionCatalogRuntime.register`
    (`session-catalog.ts`). Calls `api.register_catalog` when available;
    silently skips if the SDK does not yet expose that seam.
    """
    if not hasattr(api, "register_catalog"):
        # SDK does not yet expose catalog registration; skip gracefully.
        return
    api.register_catalog(
        {
            "id": "codex-sessions",
            "label": "Codex Sessions",
            "description": "Native Codex threads in the operator's Codex home.",
            "control": control,
        }
    )


# ---------------------------------------------------------------------------
# Node host commands (paired-node session listing / continuation)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _NodeHostCommand:
    id: str
    label: str
    handler: Callable[..., Any]


def create_codex_session_catalog_node_host_commands(
    control: CodexSessionCatalogControl,
    params: dict[str, Any],
    binding_store: Any,
) -> Iterable[dict[str, Any]]:
    """Yield node host commands for catalog operations on paired nodes.

    OpenClaw parity: mirrors `createCodexSessionCatalogNodeHostCommands`
    (`session-catalog.ts`). These commands let Gateway-paired nodes expose
    their local Codex thread catalogs to the central gateway.
    """
    yield {
        "id": "codex_session_catalog_list",
        "label": "List Codex sessions on this node",
        "handler": lambda ctx: control.list_sessions(include_archived=False, limit=100),
    }
    yield {
        "id": "codex_session_catalog_continue",
        "label": "Continue a Codex session from this node",
        "handler": lambda ctx: control.continue_session(
            ctx.get("threadId") or ctx.get("thread_id", ""),
            context=ctx,
        ),
    }


def create_codex_session_catalog_node_invoke_policies() -> Iterable[dict[str, Any]]:
    """Yield invoke policies that restrict paired-node catalog commands.

    OpenClaw parity: mirrors `createCodexSessionCatalogNodeInvokePolicies`
    (`session-catalog.ts`). Returns a minimal owner-only policy.
    """
    yield {
        "id": "codex_session_catalog",
        "commands": ["codex_session_catalog_list", "codex_session_catalog_continue"],
        "requireOwner": True,
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _normalize_entry(row: dict[str, Any]) -> CodexSessionCatalogEntry:
    return CodexSessionCatalogEntry(
        thread_id=str(row.get("threadId") or row.get("id") or ""),
        name=row.get("name"),
        status=str(row.get("status", "unknown")),
        cwd=row.get("cwd"),
        source=row.get("source"),
        updated_at=int(row["updatedAt"])
        if isinstance(row.get("updatedAt"), (int, float))
        else None,
        human_attached=bool(row.get("humanAttached", False)),
        node_id=row.get("nodeId"),
    )


def _resolve_session_id(context: Any) -> str | None:
    if isinstance(context, dict):
        val = context.get("sessionId") or context.get("session_id")
    else:
        val = getattr(context, "session_id", None) or getattr(context, "sessionId", None)
    return str(val).strip() if isinstance(val, str) and val.strip() else None


__all__ = [
    "CodexSessionCatalogControl",
    "CodexSessionCatalogEntry",
    "codex_session_catalog_runtime_register",
    "create_codex_session_catalog_control",
    "create_codex_session_catalog_node_host_commands",
    "create_codex_session_catalog_node_invoke_policies",
]
