"""Context-engine registry owns engine registration, resolution, compatibility, and quarantine.

OpenClaw parity: ``src/context-engine/registry.ts``. The two TS ``Proxy``
wrappers become ``__getattr__``-delegating wrapper classes with identical
retry/quarantine semantics; the two ``WeakMap`` side tables become
``WeakKeyDictionary`` instances; the ``Symbol.for`` registry singleton
becomes a process-global keyed singleton (same chunk-isolation guarantee,
one module system apart). Engine method names stay camelCase because they
are the wire contract third-party engines implement.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import os
import re
import sys
import time
import weakref
from datetime import datetime
from typing import Any, Awaitable, Callable, Iterable, Iterator

from src.infra.abort_signal import create_abort_error
from src.plugins.slots import default_slot_id_for_key
from src.shared.global_singleton import resolve_global_singleton
from src.terminal_core.ansi import sanitize_for_log
from src.utils.string_readers import is_string_option

from .quarantine_health import (
    clear_persisted_context_engine_quarantine_for_process,
    list_persisted_context_engine_quarantines,
    record_persisted_context_engine_quarantine,
)

__all__ = [
    "clear_context_engines_for_owner",
    "get_context_engine_registration",
    "list_context_engine_quarantines",
    "register_context_engine",
    "register_context_engine_for_owner",
    "resolve_context_engine",
    "resolve_context_engine_owner_plugin_id",
]

# ---------------------------------------------------------------------------
# Session-key legacy compatibility
# ---------------------------------------------------------------------------

_LEGACY_SESSION_KEY_COMPAT_MARKER = "_openclaw_context_engine_session_key_compat"

SESSION_KEY_COMPAT_METHODS = (
    "bootstrap",
    "maintain",
    "ingest",
    "ingestBatch",
    "afterTurn",
    "assemble",
    "compact",
)
LEGACY_COMPAT_PARAMS = (
    "sessionKey",
    "prompt",
    "runtimeSettings",
    "sessionTarget",
    "runtimeContext",
)
LEGACY_COMPAT_METHOD_KEYS: dict[str, tuple[str, ...]] = {
    "bootstrap": ("sessionKey", "runtimeSettings", "sessionTarget", "runtimeContext"),
    "maintain": ("sessionKey", "runtimeSettings", "sessionTarget", "runtimeContext"),
    "ingest": ("sessionKey",),
    "ingestBatch": ("sessionKey",),
    "afterTurn": ("sessionKey", "runtimeSettings", "sessionTarget", "runtimeContext"),
    "assemble": ("sessionKey", "prompt", "runtimeSettings"),
    "compact": ("sessionKey", "runtimeSettings", "sessionTarget", "runtimeContext"),
}


def _is_session_key_compat_method_name(value: str) -> bool:
    return is_string_option(value, SESSION_KEY_COMPAT_METHODS)


def _has_own_legacy_compat_key(params: Any, key: str) -> bool:
    return isinstance(params, dict) and key in params


def _without_legacy_compat_keys(params: dict[str, Any], keys: Iterable[str]) -> dict[str, Any]:
    legacy_params = dict(params)
    for key in keys:
        legacy_params.pop(key, None)
    return legacy_params


def _legacy_unknown_field_patterns(key: str) -> tuple[re.Pattern[str], ...]:
    quoted = f"['\"`]{key}['\"`]"
    return (
        re.compile(
            r"\bunrecognized key(?:\(s\)|s)? in object:.*" + quoted,
            re.IGNORECASE,
        ),
        re.compile(r"\badditional propert(?:y|ies)\b.*" + quoted, re.IGNORECASE),
        re.compile(
            r"\bmust not have additional propert(?:y|ies)\b.*" + quoted,
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(?:unexpected|extraneous)\s+(?:property|properties|field|fields|key|keys)\b.*"
            + quoted,
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(?:unknown|invalid)\s+(?:property|properties|field|fields|key|keys)\b.*"
            + quoted,
            re.IGNORECASE,
        ),
        re.compile(quoted + r".*\b(?:was|is)\s+not allowed\b", re.IGNORECASE),
        re.compile(
            r'"code"\s*:\s*"unrecognized_keys"[\s\S]*"' + key + '"',
            re.IGNORECASE,
        ),
    )


LEGACY_UNKNOWN_FIELD_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    key: _legacy_unknown_field_patterns(key) for key in LEGACY_COMPAT_PARAMS
}


def _is_legacy_compat_unknown_field_validation_message(message: str, key: str) -> bool:
    return any(pattern.search(message) for pattern in LEGACY_UNKNOWN_FIELD_PATTERNS[key])


def _field(candidate: Any, name: str) -> Any:
    if isinstance(candidate, dict):
        return candidate.get(name)
    return getattr(candidate, name, None)


def _issue_rejects_legacy_compat_key_strictly(issue: Any, key: str) -> bool:
    if issue is None or not isinstance(issue, (dict, object)) or isinstance(issue, (str, int, float, bool)):
        return False
    code = _field(issue, "code")
    keys = _field(issue, "keys")
    if code == "unrecognized_keys" and isinstance(keys, (list, tuple)) and any(
        issue_key == key for issue_key in keys
    ):
        return True
    return _is_legacy_compat_error_for_key(_field(issue, "message"), key)


def _iterate_error_chain(error: Any) -> Iterator[Any]:
    current = error
    seen: list[Any] = []
    while current is not None and not any(current is entry for entry in seen):
        yield current
        seen.append(current)
        if isinstance(current, (str, int, float, bool)):
            break
        next_cause = _field(current, "cause")
        if next_cause is None and isinstance(current, BaseException):
            next_cause = current.__cause__
        current = next_cause


def _is_legacy_compat_error_for_key(error: Any, key: str) -> bool:
    # Some external engines validate params with zod/JSON-schema-style
    # validators and reject legacy host keys. Walk common error shapes
    # without depending on a specific validator package.
    for candidate in _iterate_error_chain(error):
        if isinstance(candidate, (list, tuple)):
            if any(
                _issue_rejects_legacy_compat_key_strictly(entry, key)
                for entry in candidate
            ):
                return True
            continue

        if isinstance(candidate, str):
            if _is_legacy_compat_unknown_field_validation_message(candidate, key):
                return True
            continue

        if isinstance(candidate, (int, float, bool)) or candidate is None:
            continue

        issues = _field(candidate, "issues")
        if isinstance(issues, (list, tuple)) and any(
            _issue_rejects_legacy_compat_key_strictly(issue, key) for issue in issues
        ):
            return True

        errors = _field(candidate, "errors")
        if isinstance(errors, (list, tuple)) and any(
            _issue_rejects_legacy_compat_key_strictly(issue, key) for issue in errors
        ):
            return True

        message = _field(candidate, "message")
        if message is None and isinstance(candidate, BaseException):
            message = str(candidate)
        if isinstance(message, str) and _is_legacy_compat_unknown_field_validation_message(
            message, key
        ):
            return True

    return False


def _detect_rejected_legacy_compat_keys(error: Any, allowed_keys: Iterable[str]) -> set[str]:
    rejected_keys: set[str] = set()
    for key in allowed_keys:
        if _is_legacy_compat_error_for_key(error, key):
            rejected_keys.add(key)
    return rejected_keys


async def _call_engine_method(method: Callable[..., Any], params: Any) -> Any:
    result = method(params)
    if inspect.isawaitable(result):
        return await result
    return result


async def invoke_with_legacy_compat(
    method: Callable[..., Any],
    params: Any,
    allowed_keys: tuple[str, ...],
    *,
    on_legacy_keys_detected: Callable[[set[str]], None] | None = None,
    rejected_keys: set[str] | None = None,
) -> Any:
    active_rejected_keys = set(rejected_keys or ())
    available_keys = [key for key in allowed_keys if _has_own_legacy_compat_key(params, key)]
    if not available_keys:
        return await _call_engine_method(method, params)

    current_params = (
        _without_legacy_compat_keys(params, active_rejected_keys)
        if active_rejected_keys
        else params
    )

    try:
        return await _call_engine_method(method, current_params)
    except Exception as error:  # noqa: BLE001 — compat detection walks arbitrary errors
        current_error: BaseException = error
        while True:
            newly_rejected = _detect_rejected_legacy_compat_keys(
                current_error, available_keys
            )
            learned_new_key = False
            for key in newly_rejected:
                if key not in active_rejected_keys:
                    active_rejected_keys.add(key)
                    learned_new_key = True

            if not learned_new_key:
                raise current_error

            # Once an engine proves it rejects a legacy key, retry without it
            # and remember that choice.
            if on_legacy_keys_detected is not None:
                on_legacy_keys_detected(newly_rejected)
            current_params = _without_legacy_compat_keys(params, active_rejected_keys)

            try:
                return await _call_engine_method(method, current_params)
            except Exception as retry_error:  # noqa: BLE001
                current_error = retry_error


class _SessionKeyCompatContextEngine:
    """Strips legacy host params engines reject, memoizing per-engine choices."""

    _openclaw_context_engine_session_key_compat = True

    def __init__(self, engine: Any) -> None:
        self._target = engine
        self._rejected_keys: set[str] = set()

    def __getattr__(self, name: str) -> Any:
        value = getattr(self._target, name)
        if not callable(value):
            return value
        if not _is_session_key_compat_method_name(name):
            return value

        allowed_keys = LEGACY_COMPAT_METHOD_KEYS[name]
        rejected_keys = self._rejected_keys

        def on_legacy_keys_detected(keys: set[str]) -> None:
            rejected_keys.update(keys)

        async def compat_invoke(params: Any) -> Any:
            return await invoke_with_legacy_compat(
                value,
                params,
                allowed_keys,
                on_legacy_keys_detected=on_legacy_keys_detected,
                rejected_keys=rejected_keys,
            )

        return compat_invoke


def wrap_context_engine_with_session_key_compat(engine: Any) -> Any:
    if getattr(engine, _LEGACY_SESSION_KEY_COMPAT_MARKER, False):
        return engine
    return _SessionKeyCompatContextEngine(engine)


# ---------------------------------------------------------------------------
# Registry (module-level singleton)
# ---------------------------------------------------------------------------

CONTEXT_ENGINE_REGISTRY_STATE = "openclaw.contextEngineRegistryState"
CORE_CONTEXT_ENGINE_OWNER = "core"
PUBLIC_CONTEXT_ENGINE_OWNER = "public-sdk"

# Metadata side tables: TS WeakMaps keyed by engine object identity.
_RESOLVED_CONTEXT_ENGINE_METADATA: "weakref.WeakKeyDictionary[Any, dict[str, Any]]" = (
    weakref.WeakKeyDictionary()
)
_RUNTIME_QUARANTINE_PROXY_STATE: "weakref.WeakKeyDictionary[Any, dict[str, Any]]" = (
    weakref.WeakKeyDictionary()
)


def _get_context_engine_registry_state() -> dict[str, Any]:
    # Keep context-engine registrations process-global so duplicated module
    # copies still share one registry map at runtime.
    return resolve_global_singleton(
        CONTEXT_ENGINE_REGISTRY_STATE,
        lambda: {"engines": {}, "quarantinedEngines": {}},
    )


def _require_context_engine_owner(owner: str) -> str:
    normalized_owner = owner.strip() if isinstance(owner, str) else ""
    if not normalized_owner:
        raise ValueError(
            "registerContextEngineForOwner: owner must be a non-empty string, "
            f"got {json.dumps(owner)}"
        )
    return normalized_owner


def _format_context_engine_error(error: Any) -> str:
    if isinstance(error, BaseException):
        return str(error)
    return str(error)


def _record_context_engine_quarantine(
    *,
    engine_id: str,
    operation: str,
    error: Any,
    default_engine_id: str,
    owner: str | None = None,
) -> dict[str, Any]:
    registry_state = _get_context_engine_registry_state()
    existing = registry_state["quarantinedEngines"].get(engine_id)
    if existing:
        # First failure wins so logs and diagnostics point at the root cause,
        # not follow-on fallback use.
        return existing

    quarantine: dict[str, Any] = {
        "engineId": engine_id,
        "operation": operation,
        "reason": _format_context_engine_error(error),
        "failedAt": datetime.now(),
    }
    if owner:
        quarantine["owner"] = owner
    registry_state["quarantinedEngines"][engine_id] = quarantine
    try:
        record_persisted_context_engine_quarantine(
            {
                "engineId": engine_id,
                "operation": operation,
                "reason": quarantine["reason"],
                "failedAtMs": quarantine["failedAt"].timestamp() * 1000,
                **({"owner": owner} if owner else {}),
            }
        )
    except Exception:  # noqa: BLE001
        # Quarantine behavior must not depend on the best-effort health mirror.
        pass
    owner_suffix = f" owner={sanitize_for_log(owner)}" if owner else ""
    print(
        f'[context-engine] Context engine "{sanitize_for_log(engine_id)}"{owner_suffix} '
        f"failed during {sanitize_for_log(operation)}: "
        f"{sanitize_for_log(quarantine['reason'])}; quarantining it for this process "
        f'and falling back to default engine "{default_engine_id}".',
        file=sys.stderr,
    )
    return quarantine


def _get_context_engine_quarantine(engine_id: str) -> dict[str, Any] | None:
    return _get_context_engine_registry_state()["quarantinedEngines"].get(engine_id)


def list_context_engine_quarantines() -> list[dict[str, Any]]:
    quarantines: list[dict[str, Any]] = []
    for entry in _get_context_engine_registry_state()["quarantinedEngines"].values():
        quarantine: dict[str, Any] = {
            "engineId": entry["engineId"],
            "operation": entry["operation"],
            "reason": entry["reason"],
            "failedAt": entry["failedAt"],
        }
        if entry.get("owner"):
            quarantine["owner"] = entry["owner"]
        quarantines.append(quarantine)
    seen_engine_ids = {entry["engineId"] for entry in quarantines}
    for persisted in list_persisted_context_engine_quarantines():
        if persisted["engineId"] in seen_engine_ids:
            continue
        entry = {
            "engineId": persisted["engineId"],
            "operation": persisted["operation"],
            "reason": persisted["reason"],
            "failedAt": datetime.fromtimestamp(persisted["failedAtMs"] / 1000),
        }
        if persisted.get("owner"):
            entry["owner"] = persisted["owner"]
        quarantines.append(entry)
        seen_engine_ids.add(persisted["engineId"])
    return quarantines


def clear_context_engine_runtime_quarantine(engine_id: str | None = None) -> None:
    quarantined_engines = _get_context_engine_registry_state()["quarantinedEngines"]
    if engine_id is None:
        quarantined_engines.clear()
        clear_persisted_context_engine_quarantine_for_process(None, os.getpid())
        return
    quarantined_engines.pop(engine_id, None)
    clear_persisted_context_engine_quarantine_for_process(engine_id, os.getpid())


def register_context_engine_for_owner(
    engine_id: str,
    factory: Callable[..., Any],
    owner: str,
    *,
    allow_same_owner_refresh: bool = False,
    lifecycle: str = "runtime",
) -> dict[str, Any]:
    """Register a context engine implementation under an explicit trusted owner."""
    normalized_owner = _require_context_engine_owner(owner)
    registry = _get_context_engine_registry_state()["engines"]
    existing = registry.get(engine_id)
    if (
        engine_id == default_slot_id_for_key("contextEngine")
        and normalized_owner != CORE_CONTEXT_ENGINE_OWNER
    ):
        # The default fallback id is core-owned; plugins can select other ids
        # through slots.
        return {"ok": False, "existingOwner": CORE_CONTEXT_ENGINE_OWNER}
    if existing and existing["owner"] != normalized_owner:
        return {"ok": False, "existingOwner": existing["owner"]}
    if existing and existing["lifecycle"] == "runtime" and lifecycle == "readOnlyDiscovery":
        # Read-only discovery may re-run after live activation. It can collect
        # metadata, but it must not replace the runtime-safe factory with a
        # closure that captured a read-only plugin mode.
        return {"ok": True}
    if existing and allow_same_owner_refresh is not True:
        return {"ok": False, "existingOwner": existing["owner"]}
    registry[engine_id] = {
        "factory": factory,
        "owner": normalized_owner,
        "lifecycle": lifecycle,
    }
    if lifecycle == "runtime":
        clear_context_engine_runtime_quarantine(engine_id)
    return {"ok": True}


def register_context_engine(engine_id: str, factory: Callable[..., Any]) -> dict[str, Any]:
    """Public SDK entry point for third-party registrations.

    This path is intentionally unprivileged: it cannot claim core-owned ids
    and it cannot safely refresh an existing registration because the
    caller's identity is not authenticated.
    """
    return register_context_engine_for_owner(engine_id, factory, PUBLIC_CONTEXT_ENGINE_OWNER)


def get_context_engine_registration(engine_id: str) -> dict[str, Any] | None:
    """Registration metadata so callers can distinguish discovery snapshots from runtime entries."""
    return _get_context_engine_registry_state()["engines"].get(engine_id)


def _list_context_engine_ids() -> list[str]:
    return list(_get_context_engine_registry_state()["engines"].keys())


def clear_context_engines_for_owner(owner: str) -> None:
    normalized_owner = _require_context_engine_owner(owner)
    registry = _get_context_engine_registry_state()["engines"]
    for engine_id, entry in list(registry.items()):
        if entry["owner"] == normalized_owner:
            del registry[engine_id]
            clear_context_engine_runtime_quarantine(engine_id)


def resolve_context_engine_owner_plugin_id(engine: Any) -> str | None:
    """Return the trusted plugin id that registered a resolved context engine."""
    if engine is None:
        return None
    metadata = _resolve_effective_context_engine_metadata(engine)
    owner = metadata.get("owner") if metadata else None
    if not owner or not owner.startswith("plugin:"):
        return None
    plugin_id = owner[len("plugin:") :].strip()
    return plugin_id or None


def _resolve_effective_context_engine_metadata(engine: Any) -> dict[str, Any] | None:
    quarantine_state = _RUNTIME_QUARANTINE_PROXY_STATE.get(engine)
    if quarantine_state and _get_context_engine_quarantine(quarantine_state["engineId"]):
        # After quarantine, metadata follows the resolved fallback so
        # plugin-scoped operations do not keep attributing work to a
        # disabled engine.
        fallback_engine = quarantine_state["getResolvedFallbackEngine"]()
        fallback_metadata = (
            _RESOLVED_CONTEXT_ENGINE_METADATA.get(fallback_engine)
            if fallback_engine is not None
            else None
        )
        return fallback_metadata or {"owner": CORE_CONTEXT_ENGINE_OWNER}
    return _RESOLVED_CONTEXT_ENGINE_METADATA.get(engine)


def _json_stringify(value: Any) -> str:
    # JSON.stringify parity: undefined -> "undefined"; BigInt raises (mirrored
    # by Python values json cannot encode raising TypeError to the caller).
    if value is None:
        return "null"
    return json.dumps(value)


def describe_resolved_context_engine_contract_error(
    engine_id: str, engine: Any
) -> str | None:
    is_object = engine is not None and not isinstance(engine, (str, int, float, bool))
    if not is_object:
        return (
            f'Context engine "{engine_id}" factory returned {_json_stringify(engine)} '
            "instead of a ContextEngine object."
        )

    issues: list[str] = []
    info = _field(engine, "info")
    if not info or not isinstance(info, dict):
        issues.append("missing info")
    else:
        # Engines own their internal info.id; it is metadata, not a handle
        # into the registry. The registered id (plugin slot id) and the
        # engine's own id are allowed to differ, so we only require that
        # info.id is a non-empty string for display/logging purposes and do
        # not enforce equality with engine_id.
        info_id = info.get("id").strip() if isinstance(info.get("id"), str) else ""
        if not info_id:
            issues.append("missing info.id")
        info_name = info.get("name")
        if not isinstance(info_name, str) or not info_name.strip():
            issues.append("missing info.name")

    if not callable(_field(engine, "ingest")):
        issues.append("missing ingest()")
    if not callable(_field(engine, "assemble")):
        issues.append("missing assemble()")
    if not callable(_field(engine, "compact")):
        issues.append("missing compact()")

    if not issues:
        return None

    return (
        f'Context engine "{engine_id}" factory returned an invalid ContextEngine: '
        f"{', '.join(issues)}."
    )


# ---------------------------------------------------------------------------
# Runtime quarantine wrapper
# ---------------------------------------------------------------------------

GUARDED_CONTEXT_ENGINE_METHODS = frozenset(
    (
        "bootstrap",
        "maintain",
        "ingest",
        "ingestBatch",
        "afterTurn",
        "assemble",
        "compact",
        "prepareSubagentSpawn",
        "onSubagentEnded",
    )
)


def context_engine_fallback_result(method_name: str) -> Any:
    if method_name == "bootstrap":
        return {
            "bootstrapped": False,
            "reason": "context engine downgraded to legacy",
        }
    if method_name == "maintain":
        return {
            "changed": False,
            "bytesFreed": 0,
            "rewrittenEntries": 0,
            "reason": "context engine downgraded to legacy",
        }
    if method_name == "ingest":
        return {"ingested": False}
    if method_name == "ingestBatch":
        return {"ingestedCount": 0}
    if method_name in ("afterTurn", "prepareSubagentSpawn", "onSubagentEnded"):
        return None
    raise RuntimeError(f"No legacy fallback result for {method_name}")


def _context_engine_abort_signal(method_params: Any) -> Any:
    if not isinstance(method_params, dict):
        return None
    signal = method_params.get("abortSignal")
    if signal is not None and hasattr(signal, "aborted"):
        return signal
    return None


def _context_engine_abort_error(method_params: Any) -> BaseException | None:
    signal = _context_engine_abort_signal(method_params)
    if signal is None or not signal.aborted:
        return None
    reason = getattr(signal, "reason", None)
    if isinstance(reason, BaseException):
        return reason
    return create_abort_error(
        reason if isinstance(reason, str) and reason else "Context engine operation aborted."
    )


def _is_context_engine_abort_rejection(error: Any, method_params: Any) -> bool:
    signal = _context_engine_abort_signal(method_params)
    if signal is None or not signal.aborted:
        return False
    if error is getattr(signal, "reason", None):
        return True
    if isinstance(error, BaseException):
        message = str(error).lower()
        return (
            getattr(error, "name", None) == "AbortError"
            or "abort" in message
            or "cancelled" in message
            or "canceled" in message
        )
    return isinstance(error, str) and bool(
        re.search(r"abort|cancelled|canceled", error, re.IGNORECASE)
    )


async def _invoke_fallback_context_engine_method(
    *,
    get_fallback_engine: Callable[[], Awaitable[Any]],
    method_name: str,
    method_params: Any,
) -> Any:
    fallback_engine = await get_fallback_engine()
    fallback_method = getattr(fallback_engine, method_name, None)
    if callable(fallback_method):
        return await _call_engine_method(fallback_method, method_params)
    return context_engine_fallback_result(method_name)


class _RuntimeQuarantineContextEngine:
    """Downgrades a failing non-default engine to the default for this process."""

    def __init__(
        self,
        *,
        engine: Any,
        engine_id: str,
        owner: str,
        default_engine_id: str,
        factory_ctx: dict[str, Any],
    ) -> None:
        self._target = engine
        self._engine_id = engine_id
        self._owner = owner
        self._default_engine_id = default_engine_id
        self._factory_ctx = factory_ctx
        self._fallback_engine: Any = None
        self._fallback_lock = asyncio.Lock()

    async def _get_fallback_engine(self) -> Any:
        async with self._fallback_lock:
            if self._fallback_engine is None:
                self._fallback_engine = await resolve_default_context_engine(
                    self._default_engine_id, self._factory_ctx
                )
        return self._fallback_engine

    def _resolved_fallback_engine(self) -> Any:
        return self._fallback_engine

    def _fallback_info(self) -> dict[str, Any]:
        if self._fallback_engine is not None:
            return self._fallback_engine.info
        return {
            "id": self._default_engine_id,
            "name": (
                "Legacy Context Engine"
                if self._default_engine_id == "legacy"
                else f"{self._default_engine_id} Context Engine"
            ),
        }

    def _is_quarantined(self) -> bool:
        return _get_context_engine_quarantine(self._engine_id) is not None

    @property
    def info(self) -> dict[str, Any]:
        if self._is_quarantined():
            return self._fallback_info()
        return self._target.info

    def __getattr__(self, name: str) -> Any:
        value = getattr(self._target, name)
        if not callable(value) or name not in GUARDED_CONTEXT_ENGINE_METHODS:
            return value

        method_name = name

        async def guarded(method_params: Any) -> Any:
            aborted = _context_engine_abort_error(method_params)
            if aborted is not None:
                raise aborted
            if self._is_quarantined():
                # Runtime failures downgrade future guarded calls for this process.
                return await _invoke_fallback_context_engine_method(
                    get_fallback_engine=self._get_fallback_engine,
                    method_name=method_name,
                    method_params=method_params,
                )

            try:
                return await _call_engine_method(value, method_params)
            except Exception as error:  # noqa: BLE001 — quarantine guards all engine failures
                if _is_context_engine_abort_rejection(error, method_params):
                    # Abort is caller intent, not engine instability; never
                    # quarantine for it.
                    raise
                _record_context_engine_quarantine(
                    engine_id=self._engine_id,
                    owner=self._owner,
                    operation=method_name,
                    error=error,
                    default_engine_id=self._default_engine_id,
                )
                if method_name in ("compact", "prepareSubagentSpawn"):
                    raise
                try:
                    return await _invoke_fallback_context_engine_method(
                        get_fallback_engine=self._get_fallback_engine,
                        method_name=method_name,
                        method_params=method_params,
                    )
                except Exception:  # noqa: BLE001
                    raise error from None

        return guarded


def wrap_context_engine_with_runtime_quarantine(
    *,
    engine: Any,
    engine_id: str,
    owner: str,
    default_engine_id: str,
    factory_ctx: dict[str, Any],
) -> Any:
    proxy = _RuntimeQuarantineContextEngine(
        engine=engine,
        engine_id=engine_id,
        owner=owner,
        default_engine_id=default_engine_id,
        factory_ctx=factory_ctx,
    )
    _RUNTIME_QUARANTINE_PROXY_STATE[proxy] = {
        "engineId": engine_id,
        "getResolvedFallbackEngine": proxy._resolved_fallback_engine,
    }
    return proxy


def _wrap_resolved_context_engine(engine: Any, metadata: dict[str, Any]) -> Any:
    compat_wrapped = wrap_context_engine_with_session_key_compat(engine)
    if (
        metadata.get("defaultEngineId")
        and metadata.get("factoryCtx") is not None
        and metadata["engineId"] != metadata["defaultEngineId"]
    ):
        wrapped = wrap_context_engine_with_runtime_quarantine(
            engine=compat_wrapped,
            engine_id=metadata["engineId"],
            owner=metadata["owner"],
            default_engine_id=metadata["defaultEngineId"],
            factory_ctx=metadata["factoryCtx"],
        )
    else:
        wrapped = compat_wrapped
    _RESOLVED_CONTEXT_ENGINE_METADATA[wrapped] = metadata
    return wrapped


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


async def _call_factory(factory: Callable[..., Any], factory_ctx: dict[str, Any]) -> Any:
    # Existing no-arg factories continue to work, mirroring the TS call-site
    # tolerance for extra arguments.
    try:
        signature = inspect.signature(factory)
        accepts_ctx = len(signature.parameters) > 0
    except (TypeError, ValueError):
        accepts_ctx = True
    result = factory(factory_ctx) if accepts_ctx else factory()
    if inspect.isawaitable(result):
        return await result
    return result


async def resolve_context_engine(
    config: dict[str, Any] | None = None,
    options: dict[str, Any] | None = None,
) -> Any:
    """Resolve which ContextEngine to use based on plugin slot configuration.

    Resolution order: (1) ``config["plugins"]["slots"]["contextEngine"]``
    explicit slot override, (2) default slot value ("legacy"). Non-default
    engines that fail (unregistered, factory throw, or contract violation)
    are logged and silently replaced by the default engine. Throws only
    when the default engine itself cannot be resolved.
    """
    slot_value = ((config or {}).get("plugins") or {}).get("slots", {}).get("contextEngine")
    engine_id = (
        slot_value.strip()
        if isinstance(slot_value, str) and slot_value.strip()
        else default_slot_id_for_key("contextEngine")
    )

    default_engine_id = default_slot_id_for_key("contextEngine")
    is_default_engine = engine_id == default_engine_id

    factory_ctx: dict[str, Any] = {
        "config": config,
        "agentDir": (options or {}).get("agentDir"),
        "workspaceDir": (options or {}).get("workspaceDir"),
    }

    quarantine = None if is_default_engine else _get_context_engine_quarantine(engine_id)
    if quarantine:
        # Previously failed custom engines stay downgraded until explicit
        # quarantine clear/restart.
        return await resolve_default_context_engine(default_engine_id, factory_ctx)

    entry = _get_context_engine_registry_state()["engines"].get(engine_id)
    if not entry:
        if is_default_engine:
            raise RuntimeError(
                f'Context engine "{engine_id}" is not registered. '
                f"Available engines: {', '.join(_list_context_engine_ids()) or '(none)'}"
            )
        _record_context_engine_quarantine(
            engine_id=engine_id,
            operation="resolve",
            error="not registered",
            default_engine_id=default_engine_id,
        )
        return await resolve_default_context_engine(default_engine_id, factory_ctx)

    if not is_default_engine and entry["lifecycle"] == "readOnlyDiscovery":
        print(
            f'[context-engine] Context engine "{engine_id}" owner={entry["owner"]} is '
            "registered for read-only discovery only; falling back to default engine "
            f'"{default_engine_id}" without quarantine until runtime activation '
            "registers it.",
            file=sys.stderr,
        )
        return await resolve_default_context_engine(default_engine_id, factory_ctx)

    try:
        engine = await _call_factory(entry["factory"], factory_ctx)
    except Exception as factory_error:  # noqa: BLE001
        if is_default_engine:
            raise
        _record_context_engine_quarantine(
            engine_id=engine_id,
            owner=entry["owner"],
            operation="factory",
            error=factory_error,
            default_engine_id=default_engine_id,
        )
        return await resolve_default_context_engine(default_engine_id, factory_ctx)

    try:
        contract_error = describe_resolved_context_engine_contract_error(engine_id, engine)
    except Exception as validation_error:  # noqa: BLE001
        if is_default_engine:
            raise
        _record_context_engine_quarantine(
            engine_id=engine_id,
            owner=entry["owner"],
            operation="contract-validation",
            error=validation_error,
            default_engine_id=default_engine_id,
        )
        return await resolve_default_context_engine(default_engine_id, factory_ctx)
    if contract_error:
        if is_default_engine:
            raise RuntimeError(contract_error)
        _record_context_engine_quarantine(
            engine_id=engine_id,
            owner=entry["owner"],
            operation="contract-validation",
            error=contract_error,
            default_engine_id=default_engine_id,
        )
        return await resolve_default_context_engine(default_engine_id, factory_ctx)

    return _wrap_resolved_context_engine(
        engine,
        {
            "owner": entry["owner"],
            "engineId": engine_id,
            "defaultEngineId": default_engine_id,
            "factoryCtx": factory_ctx,
        },
    )


async def resolve_default_context_engine(
    default_engine_id: str, factory_ctx: dict[str, Any]
) -> Any:
    """Resolve the default context engine as a last-resort fallback.

    This helper is intentionally strict: if the default engine itself
    fails, there is no further fallback and the error must propagate.
    """
    default_entry = _get_context_engine_registry_state()["engines"].get(default_engine_id)
    if not default_entry:
        raise RuntimeError(
            f'[context-engine] fallback failed: default engine "{default_engine_id}" '
            "is not registered. "
            f"Available engines: {', '.join(_list_context_engine_ids()) or '(none)'}"
        )
    engine = await _call_factory(default_entry["factory"], factory_ctx)
    contract_error = describe_resolved_context_engine_contract_error(
        default_engine_id, engine
    )
    if contract_error:
        raise RuntimeError(f"[context-engine] {contract_error}")
    return _wrap_resolved_context_engine(
        engine,
        {"owner": default_entry["owner"], "engineId": default_engine_id},
    )
