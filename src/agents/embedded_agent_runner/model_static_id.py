"""jarvis.agents.embedded_agent_runner.model_static_id — static model id matching.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/model.static-id.ts``.

Public surface (mirrors the OpenClaw source):

- :func:`static_model_id_matches` — return True when a candidate
  static model id matches a target provider/model pair.

Phase 7.3a — focused minimal port.

The OpenClaw source uses
:func:`normalizeStaticProviderModelId` from
``model-ref-shared.js`` to canonicalize the candidate id and the
target id before comparison. The Python port delegates to an
installable normalizer so the host can plug in the real
catalog-canonical implementation when the model catalog lands.
"""
from __future__ import annotations

from typing import Callable, Optional


#: Provider id normalizer. The OpenClaw source uses
#: ``normalizeProviderId`` from
#: ``@openclaw/model-catalog-core/provider-id``. The Python port
#: defaults to a focused minimal trim+lowercase; the host can
#: override through :func:`set_provider_id_normalizer`.
_PROVIDER_ID_NORMALIZER: Callable[[str], str] = lambda value: (value or "").strip().lower()


def set_provider_id_normalizer(
    normalizer: Callable[[str], str],
) -> None:
    """Install a custom provider id normalizer."""
    global _PROVIDER_ID_NORMALIZER
    _PROVIDER_ID_NORMALIZER = normalizer


#: Static-provider-model-id normalizer. The OpenClaw source uses
#: ``normalizeStaticProviderModelId`` from ``model-ref-shared.js``.
_STATIC_PROVIDER_MODEL_ID_NORMALIZER: Callable[[str, str], str] = (
    lambda _provider, value: (value or "").strip().lower()
)


def set_static_provider_model_id_normalizer(
    normalizer: Callable[[str, str], str],
) -> None:
    """Install a custom static-provider-model-id normalizer."""
    global _STATIC_PROVIDER_MODEL_ID_NORMALIZER
    _STATIC_PROVIDER_MODEL_ID_NORMALIZER = normalizer


def static_model_id_matches(
    *,
    candidate_id: str,
    provider: str,
    model_id: str,
    row_provider: Optional[str] = None,
) -> bool:
    """Return True if ``candidate_id`` matches the target provider/model.

    Mirrors :func:`staticModelIdMatches``
    (``model.static-id.ts:4-18``).
    """
    normalized_provider = _PROVIDER_ID_NORMALIZER(provider or "")
    if row_provider and _PROVIDER_ID_NORMALIZER(row_provider) != normalized_provider:
        return False
    candidate_normalized = _STATIC_PROVIDER_MODEL_ID_NORMALIZER(
        normalized_provider, candidate_id
    ).strip().lower()
    target_normalized = _STATIC_PROVIDER_MODEL_ID_NORMALIZER(
        normalized_provider, model_id
    ).strip().lower()
    return candidate_normalized == target_normalized


__all__ = [
    "set_provider_id_normalizer",
    "set_static_provider_model_id_normalizer",
    "static_model_id_matches",
]
