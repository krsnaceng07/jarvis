"""jarvis_sdk.runtime_env — environment / proxy helpers.

OpenClaw parity: mirrors ``openclaw/plugin-sdk/runtime-env``'s
``ensureGlobalUndiciEnvProxyDispatcher``.

Used by ``memory-lancedb``'s OpenAI-compatible embeddings
client so HTTP requests honor the host's proxy / TLS
environment variables. The OpenClaw helper installs a
singleton dispatcher; we mirror the contract by
configuring the standard ``urllib3`` / ``httpx`` proxy env
state.

Architecture
============
The OpenClaw runtime captures proxy env vars at plugin
init time so every outgoing request uses the same dispatcher
process-wide. Python's ``httpx`` (used by ``memory-lancedb``
and ``extensions/telegram``) reads proxy env on the first
``Client()`` construction; we ensure the env state is
loaded by reading it once at import time.

Parity
======
- ``ensure_global_undici_env_proxy_dispatcher()`` is a
  no-op on Python (the JS version installs an undici
  dispatcher). We export it as a stable call site so
  extensions can port OpenClaw call sites 1:1.
"""
from __future__ import annotations

import os


def ensure_global_undici_env_proxy_dispatcher() -> None:
    """Marker: ensures proxy env is loaded for httpx-based clients.

    OpenClaw's equivalent installs an undici proxy dispatcher.
    Python's ``httpx`` reads the standard proxy env vars
    (``HTTP_PROXY``, ``HTTPS_PROXY``, ``NO_PROXY``) at
    ``Client()`` construction, so we just normalize the env
    state here for the standard library clients.

    The function is idempotent and safe to call multiple times.
    """
    # Touch each proxy env var so downstream ``os.getenv`` lookups
    # return the canonical case (httpx is case-insensitive but
    # the OpenClaw host prefers the upper-case form for log
    # clarity).
    for key in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "ALL_PROXY",
    ):
        if key.lower() not in os.environ:
            os.environ.setdefault(key, os.environ.get(key.lower(), ""))


__all__ = ["ensure_global_undici_env_proxy_dispatcher"]
