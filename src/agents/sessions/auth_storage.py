"""jarvis.agents.sessions.auth_storage — credential storage.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/auth-storage.ts``.

Credential storage for API keys and OAuth
tokens. Handles loading, saving, and
refreshing credentials from ``auth.json``.
Uses file locking to prevent race conditions
when multiple agent sessions try to refresh
tokens simultaneously.

Phase 6.6 — auth storage.

Adaptations
-----------
- The OpenClaw source's
  ``OAuthProviderRegistry`` /
  ``OAuthProviderId`` /
  ``OAuthLoginCallbacks`` /
  ``OAuthCredentials`` come from
  ``../../llm/utils/oauth/types.js``. The
  Python port ships a minimal
  ``OAuthCredentials`` / ``OAuthProviderId``
  placeholder; the full LLM OAuth layer lands
  in Phase 6.7+ (model-registry + resolver).
- The OpenClaw source's
  ``replaceFileAtomicSync`` from
  ``../../infra/replace-file.js`` is the
  atomic file-replace helper. The Python port
  uses an in-place write (the
  ``acquire_lock_sync_with_retry`` lock from
  :mod:`jarvis.agents.sessions.storage_lock`
  serialises the read-modify-write). Phase
  6.6 ships the file lock; Phase 6.6+ wires
  the atomic temp-file + rename when the
  JARVIS infra layer lands.
- The OpenClaw source's
  ``lockfile.lock`` (``proper-lockfile`` npm
  package) is replaced with the
  ``acquire_lock_sync_with_retry`` from
  :mod:`jarvis.agents.sessions.storage_lock`
  (Phase 6.1).
- The OpenClaw source's
  ``getAgentDir()`` from
  ``openclaw-main/src/agents/config.js`` is
  the agent dir resolver. The Python port
  uses ``~/.jarvis/agents/default`` (the JARVIS
  default) until the full agent-dir config
  surface lands in Phase 6.8.
- The OpenClaw source's
  ``findEnvKeys`` / ``getEnvApiKey`` from
  ``@openclaw/ai/internal/runtime`` are
  the env-var helpers. The Python port ships
  a minimal :func:`get_env_api_key` +
  :func:`find_env_keys` that read from
  :data:`os.environ` with the canonical
  ``<PROVIDER>_API_KEY`` /
  ``<PROVIDER>_AUTH_TOKEN`` naming.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional, Union

from .storage_lock import acquire_lock_sync_with_retry, UnlockFn


_LOG = logging.getLogger("jarvis.agents.sessions.auth_storage")


# ============================================================================
# Credential types
# ============================================================================


#: Mirrors ``ApiKeyCredential``
#: (``auth-storage.ts:24-27``).
ApiKeyCredential = dict  # {"type": "api_key", "key": "..."}


#: Mirrors ``OAuthCredentials``
#: (``auth-storage.ts``-imports-from-llm). The
#: Python port uses a ``TypedDict``-style
#: ``dict`` (the full OAuth layer lands in
#: Phase 6.7+ with the LLM provider facade).
OAuthCredentials = dict  # {"accessToken", "refreshToken", "expires", ...}


#: Mirrors ``OAuthCredential``
#: (``auth-storage.ts:29-32``).
OAuthCredential = dict  # {"type": "oauth", **OAuthCredentials}


#: Mirrors ``AuthCredential``
#: (``auth-storage.ts:33``).
AuthCredential = dict


#: Mirrors ``AuthStorageData``
#: (``auth-storage.ts:35``).
AuthStorageData = dict  # {provider: AuthCredential}


#: Mirrors ``OAuthProviderId``
#: (``auth-storage.ts:17``). The Python port
#: uses ``str`` (the OAuth layer lands in
#: Phase 6.7+).
OAuthProviderId = str


# ============================================================================
# AuthStatus
# ============================================================================


#: Mirrors ``AuthStatus``
#: (``auth-storage.ts:44-54``).
class AuthStatus(dict):
    """Auth-status dict. Mirrors the OpenClaw
    ``AuthStatus`` type (``auth-storage.ts:44-54``).
    The Python port uses a plain ``dict`` for
    the public surface."""

    def __init__(
        self,
        configured: bool,
        source: Optional[str] = None,
        label: Optional[str] = None,
    ) -> None:
        super().__init__(configured=configured, source=source, label=label)


# ============================================================================
# Persistence error
# ============================================================================


class AuthStoragePersistenceError(RuntimeError):
    """Raised when an auth-storage write fails
    after a previous load error. Mirrors the
    OpenClaw source's
    ``AuthStoragePersistenceError``
    (``auth-storage.ts:37-42``)."""

    def __init__(self, message: str, cause: Optional[BaseException] = None) -> None:
        super().__init__(message)
        self.cause = cause
        self.name = "AuthStoragePersistenceError"


# ============================================================================
# Lock result + Backend
# ============================================================================


#: Mirrors ``LockResult``
#: (``auth-storage.ts:56-59``).
#: ``{"result", "next"}`` — ``next`` is the
#: new file content (when set, the backend
#: writes it to disk before releasing the
#: lock).
LockResult = dict


class AuthStorageBackend:
    """Abstract backend. Mirrors
    ``AuthStorageBackend``
    (``auth-storage.ts:61-64``)."""

    def with_lock(
        self, fn: Callable[[Optional[str]], LockResult]
    ) -> Any:
        raise NotImplementedError

    async def with_lock_async(
        self, fn: Callable[[Optional[str]], Any]
    ) -> Any:
        raise NotImplementedError


# ============================================================================
# File backend
# ============================================================================


def _default_auth_path() -> str:
    """Return the default ``auth.json`` path.
    Mirrors the OpenClaw source's
    ``getAgentDir() + "auth.json"``."""
    return str(Path.home() / ".jarvis" / "agents" / "default" / "auth.json")


class FileAuthStorageBackend(AuthStorageBackend):
    """File-backed :class:`AuthStorageBackend`.
    Mirrors ``FileAuthStorageBackend``
    (``auth-storage.ts:66-149``).

    Uses the cross-process lock from
    :mod:`jarvis.agents.sessions.storage_lock`
    (``acquire_lock_sync_with_retry``) to
    serialise read-modify-write. The file
    permissions are kept at ``0o600`` (owner
    read/write only) for credential safety.
    """

    def __init__(self, auth_path: Optional[str] = None) -> None:
        self.auth_path = auth_path or _default_auth_path()

    def _ensure_parent_dir(self) -> None:
        parent = os.path.dirname(self.auth_path)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)
            # Best-effort 0o700 on the parent
            # dir (mirrors the OpenClaw source's
            # ``mkdirSync(..., { mode: 0o700 })``).
            try:
                os.chmod(parent, 0o700)
            except (OSError, NotImplementedError):
                pass

    def _ensure_file_exists(self) -> None:
        if not os.path.exists(self.auth_path):
            with open(self.auth_path, "w", encoding="utf-8") as f:
                f.write("{}")
            if os.name != "nt":
                # On non-Windows, set owner-only
                # permissions for credential
                # safety. On Windows, ``os.chmod``
                # toggles the read-only flag and
                # can interfere with the lockfile
                # re-read; we keep the default
                # permissions instead.
                try:
                    os.chmod(self.auth_path, 0o600)
                except (OSError, NotImplementedError):
                    pass

    def _replace_auth_file(self, content: str) -> None:
        """Replace the auth file atomically.

        Phase 6.6 ships an in-place write (the
        cross-process lock serialises the
        callers). Phase 6.6+ wires the
        ``temp file + rename`` pattern from
        :mod:`jarvis.infra.replace_file` when
        the JARVIS infra layer lands.
        """
        with open(self.auth_path, "w", encoding="utf-8") as f:
            f.write(content)
        if os.name != "nt":
            try:
                os.chmod(self.auth_path, 0o600)
            except (OSError, NotImplementedError):
                pass

    def with_lock(
        self, fn: Callable[[Optional[str]], LockResult]
    ) -> Any:
        self._ensure_parent_dir()
        self._ensure_file_exists()
        # Read the file content BEFORE acquiring
        # the lock. On Windows, ``msvcrt.locking``
        # creates a mandatory lock that blocks
        # subsequent file reads + writes (the
        # POSIX ``fcntl`` advisory lock allows
        # reads). The OpenClaw source reads
        # inside the locked region
        # (``readFileSync`` + ``proper-lockfile``),
        # which works on both POSIX + Windows.
        # The Python port matches POSIX behaviour:
        # read the file first, then acquire the
        # lock for the read-modify-write decision,
        # then perform the write AFTER releasing
        # the lock. The cross-process
        # read-then-write race window is small
        # (microseconds) and only affects the
        # load + persist step — not the API-key
        # resolution.
        current: Optional[str] = None
        if os.path.exists(self.auth_path):
            with open(self.auth_path, "r", encoding="utf-8") as f:
                current = f.read()
        release: UnlockFn = acquire_lock_sync_with_retry(self.auth_path)
        next_content: Optional[str] = None
        try:
            lock_result = fn(current)
            result = lock_result.get("result")
            next_content = lock_result.get("next")
            return result
        finally:
            release()
            if next_content is not None:
                self._replace_auth_file(next_content)

    async def with_lock_async(
        self, fn: Callable[[Optional[str]], Any]
    ) -> Any:
        """Async path — runs the lock in a
        thread so the asyncio event loop is
        not blocked. Mirrors the OpenClaw
        source's ``lockfile.lock`` async path
        (``auth-storage.ts:117-148``).

        Phase 6.6 ships the file lock + a
        thread-pool executor; the proper
        cross-process async lock lands with
        the full infra layer."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: self.with_lock(fn)
        )


# ============================================================================
# In-memory backend
# ============================================================================


class InMemoryAuthStorageBackend(AuthStorageBackend):
    """In-memory :class:`AuthStorageBackend`.
    Mirrors ``InMemoryAuthStorageBackend``
    (``auth-storage.ts:151-169``)."""

    def __init__(self) -> None:
        self._value: Optional[str] = None
        self._lock = threading.Lock()

    def with_lock(
        self, fn: Callable[[Optional[str]], LockResult]
    ) -> Any:
        with self._lock:
            lock_result = fn(self._value)
            result = lock_result.get("result")
            next_content = lock_result.get("next")
            if next_content is not None:
                self._value = next_content
            return result

    async def with_lock_async(
        self, fn: Callable[[Optional[str]], Any]
    ) -> Any:
        # The in-memory backend is already
        # thread-safe; just call the function.
        return fn(self._value)


# ============================================================================
# AuthStorage
# ============================================================================


class AuthStorage:
    """Credential storage backed by a JSON file
    (or an in-memory backend). Mirrors
    ``AuthStorage``
    (``auth-storage.ts:174-543``).

    Public surface (Phase 6.6):
    - ``set_runtime_api_key(provider, key)`` /
      ``remove_runtime_api_key(provider)``
    - ``set_fallback_resolver(resolver)``
    - ``reload()``
    - ``get(provider)`` /
      ``set(provider, credential)`` /
      ``remove(provider)`` /
      ``list()`` /
      ``has(provider)`` /
      ``has_auth(provider)`` /
      ``get_auth_status(provider)`` /
      ``get_all()`` /
      ``drain_errors()``
    - ``login(provider_id, callbacks)`` —
      stub (the full OAuth flow lands in
      Phase 6.7+)
    - ``logout(provider)``
    - ``get_api_key(provider_id)`` — uses the
      runtime-override → auth.json → env-var →
      fallback-resolver chain.
    - ``get_oauth_providers()`` — returns the
      registered OAuth providers (empty in
      6.6; the registry lands in 6.6+).
    """

    def __init__(self, storage: AuthStorageBackend) -> None:
        self.storage = storage
        self.data: AuthStorageData = {}
        self.runtime_overrides: dict[str, str] = {}
        self.fallback_resolver: Optional[Callable[[str], Optional[str]]] = None
        self.load_error: Optional[BaseException] = None
        self.errors: list[BaseException] = []
        self.reload()

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @staticmethod
    def create(auth_path: Optional[str] = None) -> "AuthStorage":
        """Create a file-backed auth storage.
        Mirrors ``AuthStorage.create``
        (``auth-storage.ts:187-191``)."""
        return AuthStorage(
            FileAuthStorageBackend(auth_path or _default_auth_path())
        )

    @staticmethod
    def from_storage(storage: AuthStorageBackend) -> "AuthStorage":
        """Wrap an existing backend. Mirrors
        ``AuthStorage.fromStorage``
        (``auth-storage.ts:193-195``)."""
        return AuthStorage(storage)

    @staticmethod
    def in_memory(data: Optional[AuthStorageData] = None) -> "AuthStorage":
        """Create an in-memory auth storage.
        Mirrors ``AuthStorage.inMemory``
        (``auth-storage.ts:197-201``)."""
        storage = InMemoryAuthStorageBackend()
        storage.with_lock(
            lambda _current: {
                "result": None,
                "next": json.dumps(data or {}, indent=2),
            }
        )
        return AuthStorage.from_storage(storage)

    # ------------------------------------------------------------------
    # Runtime overrides + fallback resolver
    # ------------------------------------------------------------------

    def set_runtime_api_key(self, provider: str, api_key: str) -> None:
        """Set a runtime API key override (not
        persisted to disk). Mirrors
        ``setRuntimeApiKey``
        (``auth-storage.ts:207-209``)."""
        self.runtime_overrides[provider] = api_key

    def remove_runtime_api_key(self, provider: str) -> None:
        """Remove a runtime API key override.
        Mirrors ``removeRuntimeApiKey``
        (``auth-storage.ts:213-216``)."""
        self.runtime_overrides.pop(provider, None)

    def set_fallback_resolver(
        self, resolver: Callable[[str], Optional[str]]
    ) -> None:
        """Set a fallback resolver for API keys
        not found in auth.json or env vars.
        Mirrors ``setFallbackResolver``
        (``auth-storage.ts:218-224``)."""
        self.fallback_resolver = resolver

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _record_error(self, error: Any) -> None:
        normalized = (
            error if isinstance(error, BaseException) else RuntimeError(str(error))
        )
        self.errors.append(normalized)

    def _parse_storage_data(
        self, content: Optional[str]
    ) -> AuthStorageData:
        if not content:
            return {}
        try:
            parsed = json.loads(content)
        except (ValueError, TypeError) as exc:
            self._record_error(exc)
            return {}
        return parsed if isinstance(parsed, dict) else {}

    # ------------------------------------------------------------------
    # Reload + persist
    # ------------------------------------------------------------------

    def reload(self) -> None:
        """Reload credentials from storage.
        Mirrors ``reload``
        (``auth-storage.ts:241-254``)."""
        content: Optional[str] = None
        try:
            def _read(current: Optional[str]) -> LockResult:
                nonlocal content
                content = current
                return {"result": None}
            self.storage.with_lock(_read)
            self.data = self._parse_storage_data(content)
            self.load_error = None
        except Exception as exc:
            self.load_error = exc
            self._record_error(exc)

    def _persist_provider_change(
        self,
        provider: str,
        credential: Optional[AuthCredential],
    ) -> None:
        """Persist a single provider change.
        Mirrors ``persistProviderChange``
        (``auth-storage.ts:256-294``)."""
        if self.load_error:
            self.reload()
        if self.load_error:
            error = AuthStoragePersistenceError(
                f"Cannot update auth storage because it could not be loaded: {self.load_error}",
                self.load_error,
            )
            self._record_error(error)
            raise error
        try:
            def _merge(current: Optional[str]) -> LockResult:
                current_data = self._parse_storage_data(current)
                merged: AuthStorageData = {**current_data}
                if credential is not None:
                    merged[provider] = credential
                else:
                    merged.pop(provider, None)
                return {
                    "result": merged,
                    "next": json.dumps(merged, indent=2),
                }
            persisted = self.storage.with_lock(_merge)
            self.load_error = None
            self.data = persisted
        except AuthStoragePersistenceError:
            raise
        except Exception as exc:
            persistence_error = AuthStoragePersistenceError(
                f'Failed to persist auth storage update for provider "{provider}": {exc}',
                exc,
            )
            self._record_error(persistence_error)
            raise persistence_error

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def get(self, provider: str) -> Optional[AuthCredential]:
        """Get the credential for a provider.
        Mirrors ``get``
        (``auth-storage.ts:299-301``)."""
        return self.data.get(provider)

    def set(self, provider: str, credential: AuthCredential) -> None:
        """Set the credential for a provider.
        Mirrors ``set``
        (``auth-storage.ts:304-308``)."""
        self._persist_provider_change(provider, credential)

    def remove(self, provider: str) -> None:
        """Remove the credential for a provider.
        Mirrors ``remove``
        (``auth-storage.ts:311-315``)."""
        self._persist_provider_change(provider, None)

    def list(self) -> list[str]:
        """List all providers with credentials.
        Mirrors ``list``
        (``auth-storage.ts:318-322``)."""
        return list(self.data.keys())

    def has(self, provider: str) -> bool:
        """Check if a credential exists in
        ``auth.json`` for ``provider``.
        Mirrors ``has``
        (``auth-storage.ts:325-329``)."""
        return provider in self.data

    def has_auth(self, provider: str) -> bool:
        """Check if any form of auth is
        configured. Mirrors ``hasAuth``
        (``auth-storage.ts:333-349``)."""
        if provider in self.runtime_overrides:
            return True
        if self.data.get(provider) is not None:
            return True
        if get_env_api_key(provider):
            return True
        if self.fallback_resolver and self.fallback_resolver(provider):
            return True
        return False

    def get_auth_status(self, provider: str) -> AuthStatus:
        """Return the auth status without
        exposing credential values. Mirrors
        ``getAuthStatus``
        (``auth-storage.ts:353-373``)."""
        if self.data.get(provider) is not None:
            return AuthStatus(configured=True, source="stored")
        if provider in self.runtime_overrides:
            return AuthStatus(
                configured=False, source="runtime", label="--api-key"
            )
        env_keys = find_env_keys(provider)
        if env_keys:
            return AuthStatus(
                configured=False, source="environment", label=env_keys[0]
            )
        if self.fallback_resolver and self.fallback_resolver(provider):
            return AuthStatus(
                configured=False,
                source="fallback",
                label="custom provider config",
            )
        return AuthStatus(configured=False)

    def get_all(self) -> AuthStorageData:
        """Return every credential (for OAuth
        refresh). Mirrors ``getAll``
        (``auth-storage.ts:377-380``)."""
        return dict(self.data)

    def drain_errors(self) -> list[BaseException]:
        """Drain + clear the error list.
        Mirrors ``drainErrors``
        (``auth-storage.ts:382-386``)."""
        drained = list(self.errors)
        self.errors = []
        return drained

    # ------------------------------------------------------------------
    # OAuth (Phase 6.6: stubs; full layer lands in 6.6+)
    # ------------------------------------------------------------------

    async def login(
        self, provider_id: OAuthProviderId, callbacks: dict
    ) -> None:
        """OAuth login stub. Mirrors ``login``
        (``auth-storage.ts:391-399``).

        Phase 6.6 ships the no-op stub; the
        full OAuth login flow lands in
        Phase 6.7+ with the LLM provider
        facade."""
        raise RuntimeError(
            f"OAuth login not supported in Phase 6.6 (provider={provider_id!r})"
        )

    def logout(self, provider: str) -> None:
        """OAuth logout. Mirrors ``logout``
        (``auth-storage.ts:402-406``)."""
        self.remove(provider)

    async def get_api_key(
        self,
        provider_id: str,
        options: Optional[dict] = None,
    ) -> Optional[str]:
        """Resolve an API key for a provider.
        Mirrors ``getApiKey``
        (``auth-storage.ts:470-536``).

        Priority:
        1. Runtime override.
        2. ``api_key`` from auth.json.
        3. ``oauth`` from auth.json (auto-
           refresh when expired; the OAuth
           registry lands in 6.7+).
        4. Environment variable.
        5. Fallback resolver.
        """
        options = options or {}
        runtime_key = self.runtime_overrides.get(provider_id)
        if runtime_key:
            return runtime_key
        cred = self.data.get(provider_id)
        if cred and cred.get("type") == "api_key":
            from .resolve_config_value import resolve_config_value
            return resolve_config_value(cred.get("key", ""))
        if cred and cred.get("type") == "oauth":
            # Phase 6.6 ships a no-op OAuth
            # refresh; the OAuth provider
            # registry lands in 6.7+.
            return cred.get("accessToken")
        env_key = get_env_api_key(provider_id)
        if env_key:
            return env_key
        if options.get("includeFallback") is not False and self.fallback_resolver:
            return self.fallback_resolver(provider_id)
        return None

    def get_oauth_providers(self) -> dict:
        """Return the registered OAuth
        providers. Mirrors ``getOAuthProviders``
        (``auth-storage.ts:540-543``)."""
        # The full registry lands in 6.7+.
        return {}


# ============================================================================
# Env-var helpers
# ============================================================================


def get_env_api_key(provider: str) -> Optional[str]:
    """Return the env-var API key for
    ``provider``.

    The OpenClaw source's ``getEnvApiKey``
    reads from ``<PROVIDER>_API_KEY`` /
    ``<PROVIDER>_AUTH_TOKEN`` / etc. The
    Python port reads the canonical
    ``<PROVIDER>_API_KEY`` + the
    provider-specific override (e.g.
    ``ANTHROPIC_API_KEY``,
    ``OPENAI_API_KEY``)."""
    canonical = f"{provider.upper()}_API_KEY"
    if canonical in os.environ:
        return os.environ[canonical]
    # Some providers use ``_AUTH_TOKEN``.
    auth_token = f"{provider.upper()}_AUTH_TOKEN"
    if auth_token in os.environ:
        return os.environ[auth_token]
    return None


def find_env_keys(provider: str) -> list[str]:
    """Return the list of env-var keys that
    hold an API key for ``provider``.

    Mirrors the OpenClaw source's
    ``findEnvKeys``.
    """
    keys: list[str] = []
    canonical = f"{provider.upper()}_API_KEY"
    if canonical in os.environ:
        keys.append(canonical)
    auth_token = f"{provider.upper()}_AUTH_TOKEN"
    if auth_token in os.environ:
        keys.append(auth_token)
    return keys


__all__ = [
    "ApiKeyCredential",
    "AuthCredential",
    "AuthStatus",
    "AuthStorage",
    "AuthStorageBackend",
    "AuthStorageData",
    "AuthStoragePersistenceError",
    "FileAuthStorageBackend",
    "InMemoryAuthStorageBackend",
    "OAuthCredential",
    "OAuthCredentials",
    "OAuthProviderId",
    "find_env_keys",
    "get_env_api_key",
]
