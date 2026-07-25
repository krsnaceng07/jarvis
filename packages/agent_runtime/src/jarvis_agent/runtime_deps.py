"""jarvis_agent.runtime_deps — injected provider functions.

OpenClaw parity: ``packages/agent-core/src/runtime-deps.ts``.

This is how agent-core stays provider-agnostic: it never imports a
provider, it receives the two functions it needs. The agent loop calls
``stream_simple``; summarization helpers call ``complete_simple``.
"""

from __future__ import annotations

from dataclasses import dataclass

from jarvis_llm.stream import CompleteSimpleFn, StreamFn


@dataclass(frozen=True, slots=True)
class AgentCoreRuntimeDeps:
    """Runtime functions injected by host packages.

    Parity: the ``AgentCoreRuntimeDeps`` interface. Both fields are
    optional here because the TS type is satisfied structurally by the
    ``Pick<>`` subsets below — a caller that only ever streams need not
    construct a completion function it will never use.

    Anything assigned to ``stream_simple`` must satisfy the never-throw
    contract in :mod:`jarvis_llm.stream`. Wrap raw providers in
    ``guard_stream_fn`` before injecting them; the loop above has no way
    to recover from a provider that raises.
    """

    #: Streaming completion used for normal agent turns.
    stream_simple: StreamFn | None = None
    #: Non-streaming completion used by summarization helpers.
    complete_simple: CompleteSimpleFn | None = None


#: Parity: ``AgentCoreStreamRuntimeDeps`` — the streaming-only subset.
#: TypeScript expresses this as ``Pick<>``; Python reuses the one dataclass
#: with optional fields, and the two aliases document intent at call sites.
AgentCoreStreamRuntimeDeps = AgentCoreRuntimeDeps

#: Parity: ``AgentCoreCompletionRuntimeDeps`` — the summarization subset.
AgentCoreCompletionRuntimeDeps = AgentCoreRuntimeDeps


def _missing_runtime_dep(name: str) -> RuntimeError:
    """Parity: ``missingRuntimeDep``. Message text kept verbatim.

    The package name in the text is left as ``@openclaw/agent-core`` on
    purpose during the port so a mismatch between this and the TS is
    visible in logs; Phase 5.19 rewrites these strings once the old brain
    is gone and there is only one implementation to name.
    """
    return RuntimeError(
        f'@openclaw/agent-core runtime dependency "{name}" is not configured. '
        "Pass an AgentCoreRuntimeDeps instance or a streamFn explicitly."
    )


def resolve_agent_core_stream_fn(
    runtime: AgentCoreRuntimeDeps | None,
    stream_fn: StreamFn | None = None,
) -> StreamFn:
    """Resolve the stream function, explicit override winning.

    Parity: ``resolveAgentCoreStreamFn``. Raises when neither is available
    — a misconfiguration to fix, not a runtime failure to encode in a
    stream, and there is no stream yet at this point anyway.
    """
    if stream_fn is not None:
        return stream_fn
    if runtime is not None and runtime.stream_simple is not None:
        return runtime.stream_simple
    raise _missing_runtime_dep("streamSimple")


def resolve_agent_core_complete_fn(
    runtime: AgentCoreRuntimeDeps | None,
) -> CompleteSimpleFn:
    """Resolve the completion function. Parity: ``resolveAgentCoreCompleteFn``."""
    if runtime is not None and runtime.complete_simple is not None:
        return runtime.complete_simple
    raise _missing_runtime_dep("completeSimple")


__all__ = [
    "AgentCoreCompletionRuntimeDeps",
    "AgentCoreRuntimeDeps",
    "AgentCoreStreamRuntimeDeps",
    "resolve_agent_core_complete_fn",
    "resolve_agent_core_stream_fn",
]
