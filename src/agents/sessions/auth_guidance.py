"""jarvis.agents.sessions.auth_guidance — user-facing auth guidance.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/auth-guidance.ts``.

Uses docs paths instead of provider-specific
instructions so guidance stays correct across
OAuth / API-key providers.

Parity
======
- ``format_no_models_available_message() -> str``
  (``auth-guidance.ts:21-23``).
- ``format_no_model_selected_message() -> str``
  (``auth-guidance.ts:26-28``).
- ``format_no_api_key_found_message(provider) -> str``
  (``auth-guidance.ts:31-34``) — special-cases the
  ``"unknown"`` provider to use the phrase
  ``"the selected model"`` (matches the OpenClaw
  constant).
- ``get_provider_login_help()`` — the shared helper
  that returns the standard login help block
  (``auth-guidance.ts:12-18``).

Phase 6.0 — scaffolding + helpers + small types.

Adaptations
-----------
- The OpenClaw source uses ``getDocsPath()`` from
  ``../config.js`` to build the docs URLs. The
  Python port introduces a ``_get_docs_path()``
  helper that returns the JARVIS docs root
  (``<workspace>/docs/``). Later phases can swap
  the helper for the real OpenClaw-style config
  resolver.
- The env override for the docs path is
  ``OPENCLAW_DOCS_PATH`` (matches the OpenClaw
  convention).
"""
from __future__ import annotations

import os
from pathlib import Path

#: Sentinel provider name that means "no provider
#: selected yet". Mirrors ``UNKNOWN_PROVIDER``
#: (``auth-guidance.ts:9``).
UNKNOWN_PROVIDER = "unknown"


def _get_docs_path() -> Path:
    """Return the docs directory used for help URLs.

    Mirrors ``getDocsPath`` from
    ``openclaw-main/src/agents/config.js`` (Phase 6.x
    — the JARVIS port introduces this helper in
    Phase 6.0 so the messages are correct even before
    the full settings manager lands).

    Override with the ``OPENCLAW_DOCS_PATH`` env var
    (CI / packaged launcher control). Default: the
    ``docs/`` directory under the workspace root.
    """
    override = os.environ.get("OPENCLAW_DOCS_PATH")
    if override:
        return Path(override)
    # The OpenClaw source uses a config-driven path;
    # the JARVIS port defaults to the workspace docs
    # dir (matches ``docs/`` in this repo).
    # ``Path.cwd()`` is the workspace root when the
    # host is invoked from the JARVIS CLI / desktop.
    return Path.cwd() / "docs"


def get_provider_login_help() -> str:
    """Return the standard provider login help block.

    Mirrors ``getProviderLoginHelp``
    (``auth-guidance.ts:12-18``). The two doc links
    use ``os.path.join`` (Python's ``str(Path /)``)
    to build a platform-correct path — the same as
    ``node:path.join`` in OpenClaw.
    """
    docs = _get_docs_path()
    return (
        "Use /login to log into a provider via OAuth or API key. See:\n"
        f"  {docs / 'providers.md'}\n"
        f"  {docs / 'models.md'}"
    )


def format_no_models_available_message() -> str:
    """Format the message shown when no configured
    model can be used.

    Mirrors ``formatNoModelsAvailableMessage``
    (``auth-guidance.ts:21-23``).
    """
    return f"No models available. {get_provider_login_help()}"


def format_no_model_selected_message() -> str:
    """Format the message shown before a model is
    selected.

    Mirrors ``formatNoModelSelectedMessage``
    (``auth-guidance.ts:26-28``).
    """
    return (
        f"No model selected.\n\n"
        f"{get_provider_login_help()}\n\n"
        f"Then use /model to select a model."
    )


def format_no_api_key_found_message(provider: str) -> str:
    """Format the missing API key guidance for a
    provider (or the ``"unknown"`` sentinel).

    Mirrors ``formatNoApiKeyFoundMessage``
    (``auth-guidance.ts:31-34``). When the provider is
    the ``"unknown"`` sentinel, the displayed name is
    ``"the selected model"`` (matches OpenClaw).
    """
    provider_display = (
        "the selected model" if provider == UNKNOWN_PROVIDER else provider
    )
    return (
        f"No API key found for {provider_display}.\n\n"
        f"{get_provider_login_help()}"
    )


__all__ = [
    "UNKNOWN_PROVIDER",
    "format_no_api_key_found_message",
    "format_no_model_selected_message",
    "format_no_models_available_message",
    "get_provider_login_help",
]
