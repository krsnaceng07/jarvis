"""Context-engine public types define the pluggable context-management lifecycle.

OpenClaw parity: ``src/context-engine/types.ts``. Engines exchange
camelCase dicts at the data level (the wire shape third-party engines
see); the module-level helpers keep the same names and semantics as the
host. ``ContextEngine`` itself is a duck-typed protocol: any object with
``info`` plus ``ingest``/``assemble``/``compact`` callables satisfies the
registry contract (mirroring the TS structural interface).
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = [
    "ContextEngine",
    "ContextEngineRuntimeSettingsUnavailableError",
    "ContextEngineRuntimeSettingsUnsupportedError",
    "resolve_compaction_successor_transcript",
]

# Result and params shapes are camelCase dicts on the wire, matching the TS
# object literals one-to-one:
#
#   AssembleResult          {messages, estimatedTokens, promptAuthority?,
#                            systemPromptAddition?, contextProjection?}
#   CompactResult           {ok, compacted, reason?, result?{summary?,
#                            firstKeptEntryId?, tokensBefore, tokensAfter?,
#                            details?, sessionId?, sessionTarget?, sessionFile?}}
#   IngestResult            {ingested}
#   IngestBatchResult       {ingestedCount}
#   BootstrapResult         {bootstrapped, importedMessages?, reason?}
#   MaintenanceResult       {changed, bytesFreed, rewrittenEntries, reason?}
#   ContextEngineInfo       {id, name, version?, ownsCompaction?,
#                            turnMaintenanceMode?, hostRequirements?}
#   SessionTarget           {agentId?, sessionId?, sessionKey?, storePath?,
#                            threadId?}


class ContextEngineRuntimeSettingsUnavailableError(Exception):
    """Raised when runtime settings cannot be produced for this run."""

    code = "context_engine_runtime_settings_unavailable"
    name = "ContextEngineRuntimeSettingsUnavailableError"


class ContextEngineRuntimeSettingsUnsupportedError(Exception):
    """Raised when the host does not support runtime settings at all."""

    code = "context_engine_runtime_settings_unsupported"
    name = "ContextEngineRuntimeSettingsUnsupportedError"


@runtime_checkable
class ContextEngine(Protocol):
    """Pluggable contract for context management (structural, like TS).

    Required: ``info`` metadata plus async ``ingest``/``assemble``/
    ``compact``. Optional lifecycle hooks (``bootstrap``, ``maintain``,
    ``ingestBatch``, ``afterTurn``, ``prepareSubagentSpawn``,
    ``onSubagentEnded``, ``dispose``) are duck-typed at call sites, so
    implementations simply omit what they do not support.
    """

    @property
    def info(self) -> dict[str, Any]: ...

    async def ingest(self, params: dict[str, Any]) -> dict[str, Any]: ...

    async def assemble(self, params: dict[str, Any]) -> dict[str, Any]: ...

    async def compact(self, params: dict[str, Any]) -> dict[str, Any]: ...


def resolve_compaction_successor_transcript(result: dict[str, Any]) -> dict[str, Any]:
    """Resolve the post-compaction live transcript identity from a compact result.

    Prefers the typed ``sessionTarget``. Reading the raw fields is the
    named compat path for shipped third-party engines that predate
    ``sessionTarget``; it is removed together with the deprecated
    ``sessionFile`` result field.
    """
    inner = result.get("result") or {}
    target = inner.get("sessionTarget") or {}
    return {
        "sessionId": target.get("sessionId", inner.get("sessionId")),
        # Storage-neutral targets carry no raw locator; the deprecated raw
        # field on the result remains the only file-era locator shipped
        # engines report.
        "sessionFile": inner.get("sessionFile"),
    }
