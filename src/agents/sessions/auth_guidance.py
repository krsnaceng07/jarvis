"""jarvis.agents.sessions.auth_guidance — auth guidance message formatters.

OpenClaw parity: mirrors the ``formatNoApiKeyFoundMessage`` +
``formatNoModelSelectedMessage`` helpers
in
``openclaw-main/src/agents/sessions/auth-guidance.ts``.

Phase 6.12c — STUB. The OpenClaw source
builds a richer message (with hints
about the env var to set, the OAuth
flow to use, etc.). The Python port
returns a simple one-line string; the
full guidance lands in Phase 6.13.
"""
from __future__ import annotations


#: Sentinel for "no provider specified".
#: Mirrors the OpenClaw source's
#: ``UNKNOWN_PROVIDER`` constant.
UNKNOWN_PROVIDER = "unknown"


def format_no_api_key_found_message(provider: str) -> str:
    """Build the user-facing message when
    the model registry has no API key
    for ``provider``.

    Mirrors ``formatNoApiKeyFoundMessage``
    (``auth-guidance.ts``).

    The OpenClaw source special-cases the
    ``UNKNOWN_PROVIDER`` sentinel: when
    no provider is selected, the message
    says "the selected model" instead of
    naming a specific provider. The
    Python port preserves that shape so
    the user-facing text matches.
    """
    if provider == UNKNOWN_PROVIDER:
        return (
            "No API key found for the selected model. "
            "Run /login <provider> to configure credentials."
        )
    return (
        f"No API key found for provider {provider}. "
        f"Run /login {provider} to configure credentials."
    )


def format_no_model_selected_message() -> str:
    """Build the user-facing message when
    no model has been selected.

    Mirrors ``formatNoModelSelectedMessage``
    (``auth-guidance.ts``).
    """
    return (
        "No model selected. Use /model to pick one, "
        "or run /login to configure a provider."
    )


def format_no_models_available_message() -> str:
    """Build the user-facing message when
    the model registry has no models
    available for any provider.

    Mirrors the OpenClaw source's
    ``formatNoModelsAvailableMessage``
    (the full impl lands in 6.13).
    """
    return (
        "No models available. "
        "Run /login to configure a provider."
    )


def get_provider_login_help(provider: str = UNKNOWN_PROVIDER) -> str:
    """Build a provider-specific help
    string for the ``/login <provider>``
    command. Mirrors the OpenClaw
    source's ``getProviderLoginHelp``
    (the full impl lands in 6.13).

    The default ``UNKNOWN_PROVIDER``
    argument yields a generic help
    message that links to the
    ``providers.md`` + ``models.md``
    docs (the OpenClaw source's
    generic-help case).
    """
    if provider == UNKNOWN_PROVIDER:
        return (
            "Run /login <provider> to configure credentials. "
            "See providers.md and models.md for the supported list."
        )
    return (
        f"Run /login {provider} to configure credentials. "
        f"See providers.md and models.md for the supported list."
    )


__all__ = [
    "UNKNOWN_PROVIDER",
    "format_no_api_key_found_message",
    "format_no_model_selected_message",
    "format_no_models_available_message",
    "get_provider_login_help",
]
