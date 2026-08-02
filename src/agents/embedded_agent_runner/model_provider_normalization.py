"""jarvis.agents.embedded_agent_runner.model_provider_normalization — apply provider compat normalization.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/model.provider-normalization.ts``.

Public surface (mirrors the OpenClaw source):

- :func:`normalize_resolved_provider_model` — apply the
  provider-compat normalization to a resolved model record.

Phase 7.3a — focused minimal port.

The OpenClaw source delegates to
:func:`normalizeModelCompat` from
``plugins/provider-model-compat.js``. The Python port delegates
to an installable hook so the host can plug in the real
provider-model-compat implementation when the compat layer
lands. The default no-op returns the model unchanged.
"""
from __future__ import annotations

from typing import Any, Callable, Dict


#: Model-compat normalizer. The host installs the real
#: :func:`normalizeModelCompat`` implementation when the
#: provider-compat layer lands. The Python port defaults to a
#: no-op (returns the model unchanged).
_MODEL_COMPAT_NORMALIZER: Callable[[Any], Any] = lambda model: model


def set_model_compat_normalizer(
    normalizer: Callable[[Any], Any],
) -> None:
    """Install a custom model-compat normalizer."""
    global _MODEL_COMPAT_NORMALIZER
    _MODEL_COMPAT_NORMALIZER = normalizer


def normalize_resolved_provider_model(
    *,
    provider: str,
    model: Any,
) -> Any:
    """Apply provider-compat normalization to a resolved model record.

    Mirrors :func:`normalizeResolvedProviderModel``
    (``model.provider-normalization.ts:10-12``).
    """
    return _MODEL_COMPAT_NORMALIZER(model)


__all__ = [
    "normalize_resolved_provider_model",
    "set_model_compat_normalizer",
]
