"""legacy_codex — legacy Codex provider spellings + model-ref canonicalization.

OpenClaw parity: mirrors ``openclaw-main/src/config/legacy-codex-provider.ts``
plus ``toCanonicalOpenAIModelRef`` from
``openclaw-main/src/commands/doctor/shared/codex-route-model-ref.ts``.

Single home for the "is this provider id a legacy Codex spelling" question.
Provider spellings ``codex`` and ``openai-codex`` are accepted only by
legacy migration boundaries (``jarvis doctor --fix``); new config must use
``openai`` and let the harness runtime policy select Codex.

Scope warning: ``openai-codex:<profile>`` AUTH PROFILE ids (colon
separator) are a live, separate namespace owned by the auth paths — they
are not model refs and this module never touches them. Only
``provider/model`` refs (slash separator) with a legacy provider prefix
are canonicalized. Likewise ``codex/``-prefixed refs in image slots
(``imageModel``/``visionModel``) are an intentional bounded-turn routing
signal, not legacy — the doctor migration preserves them.
"""

from __future__ import annotations

from typing import Any

#: Provider ids accepted only by legacy migration boundaries. Mirrors
#: ``LEGACY_CODEX_PROVIDER_IDS``.
LEGACY_CODEX_PROVIDER_IDS: frozenset[str] = frozenset({"codex", "openai-codex"})

#: Canonical provider for rewritten refs. Mirrors the ``openai/`` target in
#: ``toCanonicalOpenAIModelRef``.
CANONICAL_CODEX_MODEL_PROVIDER = "openai"


def is_legacy_codex_provider_id(provider: Any) -> bool:
    """Return whether *provider* is a legacy Codex provider spelling.

    Mirrors ``isLegacyCodexProviderId`` (case-insensitive, blank-safe).
    """
    if not isinstance(provider, str):
        return False
    normalized = provider.strip().lower()
    return bool(normalized) and normalized in LEGACY_CODEX_PROVIDER_IDS


def to_canonical_openai_model_ref(model_ref: Any) -> str | None:
    """Rewrite a legacy Codex model ref to its canonical ``openai/`` form.

    Mirrors ``toCanonicalOpenAIModelRef``: ``openai-codex/<m>`` and
    ``codex/<m>`` become ``openai/<m>`` (model-id case preserved — model
    ids are case-sensitive). Returns ``None`` when *model_ref* is not a
    legacy Codex ref.
    """
    if not isinstance(model_ref, str):
        return None
    trimmed = model_ref.strip()
    slash = trimmed.find("/")
    if slash <= 0 or slash >= len(trimmed) - 1:
        return None
    if not is_legacy_codex_provider_id(trimmed[:slash]):
        return None
    model_id = trimmed[slash + 1 :].strip()
    if not model_id:
        return None
    return f"{CANONICAL_CODEX_MODEL_PROVIDER}/{model_id}"


__all__ = [
    "CANONICAL_CODEX_MODEL_PROVIDER",
    "LEGACY_CODEX_PROVIDER_IDS",
    "is_legacy_codex_provider_id",
    "to_canonical_openai_model_ref",
]
