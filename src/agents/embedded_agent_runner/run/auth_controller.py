"""jarvis.agents.embedded_agent_runner.run.auth_controller — provider auth + profile rotation + runtime auth refresh.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/auth-controller.ts``.

Public surface (mirrors the OpenClaw source):

- :func:`resolve_embedded_auth_cooldown_probe_policy` — decide whether
  one automatic profile may bypass its current cooldown.
- :func:`create_embedded_run_auth_controller` — factory that returns
  an :class:`EmbeddedRunAuthController` instance with the
  ``applyAuthProfileCandidate`` / ``advanceAuthProfile`` /
  ``initializeAuthProfile`` / ``maybeRefreshRuntimeAuthForAuthError`` /
  ``stopRuntimeAuthRefreshTimer`` methods.

Phase 7.6b-1 — focused minimal port.

The OpenClaw source is ~25K and tightly coupled to the auth-profiles,
provider-runtime, fail-over, and runtime-secret layers. The Python
port keeps the public surface and delegates the heavy auth-prep,
profile-rotation, and refresh logic to installable hooks so the host
can plug in the real layers as they land.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


#: Auth-failover reason codes. Mirrors the OpenClaw source's
#: :data:`FailoverReason` (``auth-controller.ts`` re-exports from
#: ``embedded-agent-helpers.ts``).
FailoverReason = str


#: Auth profile store shape. Mirrors the OpenClaw source's
#: :class:`AuthProfileStore` (``auth-profiles.ts``). The Python port
#: keeps it as a dict alias because the runner only reads a few
#: well-known fields.
AuthProfileStore = Dict[str, Any]


#: Auth-controller state shape. Mirrors the OpenClaw source's
#: :class:`RuntimeApiKeySink` (``auth-controller.ts:49-51``).
RuntimeApiKeySink = Dict[str, Any]


#: Logger shape. Mirrors :class:`LogLike` (``auth-controller.ts:53-57``).
LogLike = Dict[str, Callable[[str], None]]


#: Runtime-auth state shape. Mirrors :class:`RuntimeAuthState` from
#: ``run/helpers.ts``.
RuntimeAuthState = Dict[str, Any]


#: Cooldown-probe policy. Mirrors the return shape of
#: :func:`resolveEmbeddedAuthCooldownProbePolicy`
#: (``auth-controller.ts:60-89``).
CooldownProbePolicy = Dict[str, Any]


#: Cooldown-probe policy result.
_DEFAULT_PROBE_POLICY: CooldownProbePolicy = {
    "allowProbe": False,
    "unavailableReason": None,
}


#: Unavailable reason when no auto-profile candidates are configured.
UNKNOWN_UNAVAILABLE_REASON: str = "unknown"


# ---------------------------------------------------------------------------
# Installable hooks
# ---------------------------------------------------------------------------


#: Hook for :func:`isProfileInCooldown` from ``auth-profiles.ts``.
_IS_PROFILE_IN_COOLDOWN: Callable[[Dict[str, Any], str, Any, str], bool] = (
    lambda store, profile_id, _unused, model_id: False
)


def set_is_profile_in_cooldown_hook(
    hook: Callable[[Dict[str, Any], str, Any, str], bool],
) -> None:
    """Install a custom isProfileInCooldown hook."""
    global _IS_PROFILE_IN_COOLDOWN
    _IS_PROFILE_IN_COOLDOWN = hook


#: Hook for :func:`resolveProfilesUnavailableReason` from
#: ``auth-profiles.ts``.
_RESOLVE_PROFILES_UNAVAILABLE_REASON: Callable[[Dict[str, Any]], Optional[str]] = (
    lambda params: None
)


def set_resolve_profiles_unavailable_reason_hook(
    hook: Callable[[Dict[str, Any]], Optional[str]],
) -> None:
    """Install a custom resolveProfilesUnavailableReason hook."""
    global _RESOLVE_PROFILES_UNAVAILABLE_REASON
    _RESOLVE_PROFILES_UNAVAILABLE_REASON = hook


#: Hook for :func:`shouldUseTransientCooldownProbeSlot` from
#: ``failover-policy.ts``.
_SHOULD_USE_TRANSIENT_COOLDOWN_PROBE: Callable[[Optional[str]], bool] = (
    lambda _reason: False
)


def set_should_use_transient_cooldown_probe_hook(
    hook: Callable[[Optional[str]], bool],
) -> None:
    """Install a custom shouldUseTransientCooldownProbeSlot hook."""
    global _SHOULD_USE_TRANSIENT_COOLDOWN_PROBE
    _SHOULD_USE_TRANSIENT_COOLDOWN_PROBE = hook


#: Hook for :func:`classifyFailoverReason` from
#: ``embedded-agent-helpers.ts``.
_CLASSIFY_FAILOVER_REASON: Callable[[str, Dict[str, Any]], Optional[str]] = (
    lambda _text, _context: None
)


def set_classify_failover_reason_hook(
    hook: Callable[[str, Dict[str, Any]], Optional[str]],
) -> None:
    """Install a custom classifyFailoverReason hook."""
    global _CLASSIFY_FAILOVER_REASON
    _CLASSIFY_FAILOVER_REASON = hook


#: Hook for :func:`isFailoverErrorMessage` from
#: ``embedded-agent-helpers.ts``.
_IS_FAILOVER_ERROR_MESSAGE: Callable[[str, Dict[str, Any]], bool] = (
    lambda _text, _context: False
)


def set_is_failover_error_message_hook(
    hook: Callable[[str, Dict[str, Any]], bool],
) -> None:
    """Install a custom isFailoverErrorMessage hook."""
    global _IS_FAILOVER_ERROR_MESSAGE
    _IS_FAILOVER_ERROR_MESSAGE = hook


#: Hook for :func:`formatAuthProfileFailureMessage` from
#: ``auth-profiles/failure-copy.ts``.
_FORMAT_AUTH_PROFILE_FAILURE_MESSAGE: Callable[[Dict[str, Any]], str] = (
    lambda _params: "auth profile failure"
)


def set_format_auth_profile_failure_message_hook(
    hook: Callable[[Dict[str, Any]], str],
) -> None:
    """Install a custom formatAuthProfileFailureMessage hook."""
    global _FORMAT_AUTH_PROFILE_FAILURE_MESSAGE
    _FORMAT_AUTH_PROFILE_FAILURE_MESSAGE = hook


#: Hook for :func:`prepareProviderRuntimeAuth` from
#: ``plugins/provider-runtime.ts``.
_PREPARE_PROVIDER_RUNTIME_AUTH: Callable[[Dict[str, Any]], Any] = (
    lambda params: None
)


def set_prepare_provider_runtime_auth_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom prepareProviderRuntimeAuth hook."""
    global _PREPARE_PROVIDER_RUNTIME_AUTH
    _PREPARE_PROVIDER_RUNTIME_AUTH = hook


#: Hook for :func:`getApiKeyForModel` from ``model-auth.ts``.
_GET_API_KEY_FOR_MODEL: Callable[[Dict[str, Any]], Any] = (
    lambda params: None
)


def set_get_api_key_for_model_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom getApiKeyForModel hook."""
    global _GET_API_KEY_FOR_MODEL
    _GET_API_KEY_FOR_MODEL = hook


#: Hook for runtime-auth refresh logic. The host installs the real
#: credential-refresh flow when the runtime-secret layer lands. The
#: default is a no-op that succeeds.
_REFRESH_RUNTIME_AUTH: Callable[[Dict[str, Any]], Any] = (
    lambda params: None
)


def set_refresh_runtime_auth_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom runtime-auth refresh hook."""
    global _REFRESH_RUNTIME_AUTH
    _REFRESH_RUNTIME_AUTH = hook


#: Hook for :func:`protectPreparedProviderRuntimeAuth` from
#: ``provider-secret-egress.ts``.
_PROTECT_PREPARED_PROVIDER_RUNTIME_AUTH: Callable[[Dict[str, Any]], Any] = (
    lambda params: None
)


def set_protect_prepared_provider_runtime_auth_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom protectPreparedProviderRuntimeAuth hook."""
    global _PROTECT_PREPARED_PROVIDER_RUNTIME_AUTH
    _PROTECT_PREPARED_PROVIDER_RUNTIME_AUTH = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_embedded_auth_cooldown_probe_policy(
    params: Dict[str, Any],
) -> CooldownProbePolicy:
    """Decide whether one automatic profile may bypass its cooldown.

    Mirrors :func:`resolveEmbeddedAuthCooldownProbePolicy`
    (``auth-controller.ts:60-89``).
    """
    auth_store = params.get("authStore") or {}
    profile_candidates = params.get("profileCandidates") or []
    locked_profile_id = params.get("lockedProfileId")
    model_id = params.get("modelId") or ""
    allow_transient = bool(params.get("allowTransientCooldownProbe", False))
    auto_profiles: List[str] = [
        candidate
        for candidate in profile_candidates
        if isinstance(candidate, str)
        and len(candidate) > 0
        and candidate != locked_profile_id
    ]
    if not auto_profiles:
        return dict(_DEFAULT_PROBE_POLICY)
    all_in_cooldown = all(
        _IS_PROFILE_IN_COOLDOWN(auth_store, candidate, None, model_id)
        for candidate in auto_profiles
    )
    unavailable_reason: Optional[str] = None
    if all_in_cooldown:
        unavailable_reason = (
            _RESOLVE_PROFILES_UNAVAILABLE_REASON(
                {"store": auth_store, "profileIds": auto_profiles}
            )
            or UNKNOWN_UNAVAILABLE_REASON
        )
    allow_probe = bool(
        allow_transient
        and all_in_cooldown
        and _SHOULD_USE_TRANSIENT_COOLDOWN_PROBE(unavailable_reason)
    )
    return {
        "allowProbe": allow_probe,
        "unavailableReason": unavailable_reason,
    }


def _read_profile_api_key(value: Any) -> Optional[str]:
    """Resolve an API key from a nested profile entry."""
    if value is None:
        return None
    if isinstance(value, str):
        trimmed = value.strip()
        return trimmed or None
    if isinstance(value, dict):
        for key in ("apiKey", "api_key", "key", "token", "accessToken", "refreshToken"):
            nested = value.get(key)
            extracted = _read_profile_api_key(nested)
            if extracted is not None:
                return extracted
        for key in ("credential", "credentials", "auth"):
            extracted = _read_profile_api_key(value.get(key))
            if extracted is not None:
                return extracted
    return None


def _profile_aliases(profile_id: Optional[str]) -> set[str]:
    """Return equivalent auth-profile aliases for canonical/legacy OpenAI IDs."""
    ids: set[str] = set()
    if not isinstance(profile_id, str):
        return ids

    normalized = profile_id.strip()
    if not normalized:
        return ids
    ids.add(normalized)

    if normalized.startswith("openai:"):
        suffix = normalized.split(":", 1)[1]
        ids.add(f"openai-codex:{suffix}")
    elif normalized.startswith("openai-codex:"):
        suffix = normalized.split(":", 1)[1]
        ids.add(f"openai:{suffix}")
    return ids


class EmbeddedRunAuthController:
    """Auth-controller handle returned by :func:`create_embedded_run_auth_controller`.

    Mirrors the object returned by
    :func:`createEmbeddedRunAuthController`
    (``auth-controller.ts:673-679``) with the public surface collapsed
    into a class for Python.

    Public methods:

    - :meth:`apply_auth_profile_candidate`
    - :meth:`advance_auth_profile`
    - :meth:`initialize_auth_profile`
    - :meth:`maybe_refresh_runtime_auth_for_auth_error`
    - :meth:`stop_runtime_auth_refresh_timer`
    """

    def __init__(self, params: Dict[str, Any]) -> None:
        self._params = dict(params or {})
        self._log = self._params.get("log") or {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _warn(self, message: str) -> None:
        warn = (self._log or {}).get("warn")
        if callable(warn):
            warn(message)

    def _info(self, message: str) -> None:
        info = (self._log or {}).get("info")
        if callable(info):
            info(message)

    def _debug(self, message: str) -> None:
        debug = (self._log or {}).get("debug")
        if callable(debug):
            debug(message)

    def _get_provider(self) -> str:
        get_provider = self._params.get("getProvider")
        if callable(get_provider):
            return str(get_provider() or "")
        return ""

    def _get_model_id(self) -> str:
        get_model_id = self._params.get("getModelId")
        if callable(get_model_id):
            return str(get_model_id() or "")
        return ""

    def _get_profile_index(self) -> int:
        get_profile_index = self._params.get("getProfileIndex")
        if callable(get_profile_index):
            return int(get_profile_index() or 0)
        return 0

    def _set_profile_index(self, value: int) -> None:
        set_profile_index = self._params.get("setProfileIndex")
        if callable(set_profile_index):
            set_profile_index(int(value))

    def _get_runtime_auth_state(self) -> Optional[RuntimeAuthState]:
        get_state = self._params.get("getRuntimeAuthState")
        if callable(get_state):
            return get_state()
        return None

    def _resolve_runtime_api_key_for_profile(self, profile_id: Optional[str]) -> str:
        """Resolve the runtime API key for a selected provider profile."""
        if not profile_id:
            return ""

        def _scan_store(store: Any) -> Optional[str]:
            if not isinstance(store, dict):
                return None
            profiles = store.get("profiles")
            if isinstance(profiles, dict):
                aliases = _profile_aliases(profile_id)
                for key in profiles:
                    if key in aliases and isinstance(profiles[key], dict):
                        api_key = _read_profile_api_key(profiles[key])
                        if api_key is not None:
                            return api_key
                profile = profiles.get(profile_id)
                if isinstance(profile, dict):
                    api_key = _read_profile_api_key(profile)
                    if api_key is not None:
                        return api_key
            return None

        for store_name in ("authStore", "authProfileStore", "profileStore", "store"):
            value = self._params.get(store_name)
            api_key = _scan_store(value)
            if api_key is not None:
                return api_key

        for value in self._params.values():
            if isinstance(value, dict):
                api_key = _scan_store(value)
                if api_key is not None:
                    return api_key

        auth_storage = self._params.get("authStorage")
        if hasattr(auth_storage, "data"):
            data = getattr(auth_storage, "data", None)
            if isinstance(data, dict):
                provider = self._get_provider()
                if provider:
                    credential = data.get(provider)
                    api_key = _read_profile_api_key(credential)
                    if api_key is not None:
                        return api_key

        return ""

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def apply_auth_profile_candidate(
        self,
        profile_id: Optional[str],
        attempt_index: Optional[int] = None,
    ) -> None:
        """Apply the auth profile and update the runtime API key.

        Mirrors :func:`applyAuthProfileCandidate`
        (``auth-controller.ts:...``).
        """
        if attempt_index is not None:
            self._set_profile_index(int(attempt_index))
        set_api_key = (self._params.get("authStorage") or {}).get("setRuntimeApiKey")
        set_last_profile_id = self._params.get("setLastProfileId")
        resolved_api_key = self._resolve_runtime_api_key_for_profile(profile_id)
        if callable(set_api_key):
            set_api_key(self._get_provider(), resolved_api_key)
        if callable(set_last_profile_id):
            set_last_profile_id(profile_id)

    def advance_auth_profile(self) -> bool:
        """Advance the profile index to the next candidate.

        Mirrors :func:`advanceAuthProfile`
        (``auth-controller.ts:...``).
        """
        profile_candidates = self._params.get("profileCandidates") or []
        if self._get_profile_index() + 1 >= len(profile_candidates):
            return False
        self._set_profile_index(self._get_profile_index() + 1)
        return True

    def initialize_auth_profile(self) -> None:
        """Initialize the auth profile state for the run.

        Mirrors :func:`initializeAuthProfile`
        (``auth-controller.ts:...``).
        """
        auth_store = self._params.get("authStore") or {}
        profile_candidates = self._params.get("profileCandidates") or []
        locked_profile_id = self._params.get("lockedProfileId")
        cooldown_probe_policy = resolve_embedded_auth_cooldown_probe_policy(
            {
                "authStore": auth_store,
                "profileCandidates": profile_candidates,
                "lockedProfileId": locked_profile_id,
                "modelId": self._get_model_id(),
                "allowTransientCooldownProbe": bool(
                    self._params.get("allowTransientCooldownProbe", False)
                ),
            }
        )
        provider = self._get_provider()
        model_id = self._get_model_id()
        if cooldown_probe_policy.get("allowProbe"):
            self._warn(
                f"probing cooldowned auth profile for {provider}/{model_id} "
                f"due to {cooldown_probe_policy.get('unavailableReason') or 'transient'} "
                f"unavailability"
            )
        while self._get_profile_index() < len(profile_candidates):
            candidate = profile_candidates[self._get_profile_index()]
            in_cooldown = bool(
                candidate
                and candidate != locked_profile_id
                and _IS_PROFILE_IN_COOLDOWN(auth_store, candidate, None, model_id)
            )
            if in_cooldown and not cooldown_probe_policy.get("allowProbe"):
                self._set_profile_index(self._get_profile_index() + 1)
                continue
            self.apply_auth_profile_candidate(
                profile_candidates[self._get_profile_index()],
                self._get_profile_index(),
            )
            break
        if self._get_profile_index() >= len(profile_candidates):
            self._warn(
                _FORMAT_AUTH_PROFILE_FAILURE_MESSAGE(
                    {
                        "allInCooldown": True,
                        "provider": provider,
                        "modelId": model_id,
                    }
                )
            )

    def maybe_refresh_runtime_auth_for_auth_error(
        self,
        error_text: str,
        retried: bool,
    ) -> bool:
        """Try to refresh runtime auth on an auth-error.

        Mirrors :func:`maybeRefreshRuntimeAuthForAuthError`
        (``auth-controller.ts:651-671``).
        """
        if not self._get_runtime_auth_state() or retried:
            return False
        provider = self._get_provider()
        if not _IS_FAILOVER_ERROR_MESSAGE(error_text, {"provider": provider}):
            return False
        if _CLASSIFY_FAILOVER_REASON(error_text, {"provider": provider}) != "auth":
            return False
        try:
            _REFRESH_RUNTIME_AUTH(
                {
                    "provider": provider,
                    "modelId": self._get_model_id(),
                    "reason": "auth-error",
                }
            )
            return True
        except Exception:
            return False

    def stop_runtime_auth_refresh_timer(self) -> None:
        """Stop the runtime-auth refresh timer.

        Mirrors :func:`stopRuntimeAuthRefreshTimer`
        (``auth-controller.ts:223-229``).
        """
        if not self._get_runtime_auth_state():
            return
        set_cancelled = self._params.get("setRuntimeAuthRefreshCancelled")
        if callable(set_cancelled):
            set_cancelled(True)


def create_embedded_run_auth_controller(
    params: Dict[str, Any],
) -> EmbeddedRunAuthController:
    """Build a :class:`EmbeddedRunAuthController` from the given params.

    Mirrors :func:`createEmbeddedRunAuthController`
    (``auth-controller.ts:96-679``).
    """
    return EmbeddedRunAuthController(params)


__all__ = [
    "AuthProfileStore",
    "CooldownProbePolicy",
    "EmbeddedRunAuthController",
    "FailoverReason",
    "LogLike",
    "RuntimeApiKeySink",
    "RuntimeAuthState",
    "UNKNOWN_UNAVAILABLE_REASON",
    "create_embedded_run_auth_controller",
    "resolve_embedded_auth_cooldown_probe_policy",
    "set_classify_failover_reason_hook",
    "set_format_auth_profile_failure_message_hook",
    "set_get_api_key_for_model_hook",
    "set_is_failover_error_message_hook",
    "set_is_profile_in_cooldown_hook",
    "set_prepare_provider_runtime_auth_hook",
    "set_protect_prepared_provider_runtime_auth_hook",
    "set_refresh_runtime_auth_hook",
    "set_resolve_profiles_unavailable_reason_hook",
    "set_should_use_transient_cooldown_probe_hook",
]
