"""jarvis.agents.embedded_agent_runner.run.attempt_transcript_policy — resolve the attempt-transcript policy.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt.transcript-policy.ts``.

Public surface:

- :func:`resolve_attempt_transcript_policy`

Phase 7.6d-1 — focused minimal port.

The OpenClaw source is small (~1.8K) and tight to the provider
runtime-model contract. The Python port keeps the public surface
and delegates the heavy work to installable hooks.
"""
from __future__ import annotations

from typing import Any, Callable, Dict


#: Attempt-transcript policy shape.
AttemptTranscriptPolicy = Dict[str, Any]


#: Provider runtime model shape.
ProviderRuntimeModel = Dict[str, Any]


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


#: Hook for the asProviderRuntimeModel step.
_AS_PROVIDER_RUNTIME_MODEL: Callable[[Any], Any] = lambda _m: _m


def set_as_provider_runtime_model_hook(
    hook: Callable[[Any], Any],
) -> None:
    """Install a custom asProviderRuntimeModel hook."""
    global _AS_PROVIDER_RUNTIME_MODEL
    _AS_PROVIDER_RUNTIME_MODEL = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_attempt_transcript_policy(
    params: Dict[str, Any],
) -> AttemptTranscriptPolicy:
    """Resolve the attempt-transcript policy.

    Mirrors :func:`resolveAttemptTranscriptPolicy`
    (``attempt.transcript-policy.ts``).
    """
    runtime_model = params.get("runtimeModel")
    provider_runtime_model = (
        _AS_PROVIDER_RUNTIME_MODEL(runtime_model)
        if runtime_model is not None
        else None
    )
    return {
        "runtimeModel": provider_runtime_model,
        "transcriptRetention": params.get("transcriptRetention"),
        "extraParams": params.get("extraParams") or {},
    }


__all__ = [
    "AttemptTranscriptPolicy",
    "ProviderRuntimeModel",
    "resolve_attempt_transcript_policy",
    "set_as_provider_runtime_model_hook",
]
