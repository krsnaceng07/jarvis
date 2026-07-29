"""Session model override helpers normalize per-session provider model choices.

Mirrors OpenClaw's ``src/sessions/model-overrides.ts``:

- ``applyModelOverrideToSessionEntry`` — applies a model/auth-profile
  override to a session entry and clears stale runtime fields
- ``repairProviderWrappedModelOverride`` — repairs overrides where
  legacy provider/model fields were stored as ``provider/model``
  strings (OpenRouter-style)

The Python port preserves the public surface (function names, return
shapes, error codes) and the field-by-field mutation semantics; the
only Python adaptation is the session-entry shape: OpenClaw's
``SessionEntry`` is a deep TypeScript interface with hundreds of
fields, so we use ``dict`` (annotated ``SessionEntry`` for type
hints) — callers that want strict typing can substitute a TypedDict
when they import this module.

Python adaptations (documented in code):
- TS ``SessionEntry`` → Python ``dict`` (no per-field TypedDict is
  used here to keep the port focused on the override semantics;
  the helper functions only touch the small set of fields below)
- TS ``normalizeOptionalString`` → ``normalize_optional_string``
  (already ported in ``jarvis_normalization_core``)
- TS string-literal unions (``"auto" | "user"``) → Python
  ``Literal["auto", "user"]`` + ``frozenset`` for runtime checks
"""
from __future__ import annotations

from typing import Any, Literal, TypedDict

from jarvis_normalization_core.string_coerce import normalize_optional_string

# Literal unions mirror the TS string-literal types. The
# ``frozenset`` constants are runtime membership sets used by
# downstream code to validate input before applying it.
SelectionSource = Literal["auto", "user"]
ProfileOverrideSource = Literal["auto", "user"]
VALID_SELECTION_SOURCES: frozenset[str] = frozenset({"auto", "user"})
VALID_PROFILE_OVERRIDE_SOURCES: frozenset[str] = frozenset({"auto", "user"})

# Public error / message constants (mirrors TS exports).
MODEL_SELECTION_LOCKED_MESSAGE = "Model selection is locked for this session."
MODEL_SELECTION_LOCKED_RESET_MESSAGE = (
    "This session cannot be reset while model selection is locked."
)


class ModelSelectionLockedError(Exception):
    """Raised when a caller attempts to mutate a locked session model selection.

    Mirrors ``ModelSelectionLockedError`` in OpenClaw.
    """

    def __init__(self, message: str = MODEL_SELECTION_LOCKED_MESSAGE) -> None:
        super().__init__(message)
        self.name = "ModelSelectionLockedError"


# Lightweight TypedDict covering only the fields this module
# touches; the rest of ``SessionEntry`` is intentionally omitted.
# Callers that need the full type should layer their own TypedDict
# on top of this and pass it through.
class SessionEntryOverrideFields(TypedDict, total=False):
    sessionId: str
    updatedAt: int
    # Persistent override fields
    providerOverride: str
    modelOverride: str
    modelOverrideSource: SelectionSource
    modelOverrideFallbackOriginProvider: str
    modelOverrideFallbackOriginModel: str
    # Runtime model identity (cleared on override changes)
    model: str
    modelProvider: str
    # Context window state (derived from the active session model)
    contextTokens: int
    contextBudgetStatus: dict[str, Any]
    # Live-switch / fallback notices
    liveModelSwitchPending: bool
    fallbackNoticeSelectedModel: str
    fallbackNoticeActiveModel: str
    fallbackNoticeReason: str
    # Auth profile override
    authProfileOverride: str
    authProfileOverrideSource: ProfileOverrideSource
    authProfileOverrideCompactionCount: int
    # Selection lock
    modelSelectionLocked: bool


# Type alias for the entry; in practice this is a plain dict.
SessionEntry = dict[str, Any]


class ModelOverrideSelection(TypedDict, total=False):
    provider: str
    model: str
    isDefault: bool


def is_model_selection_locked(entry: SessionEntry | None) -> bool:
    """Return ``True`` when the entry has ``modelSelectionLocked`` set.

    Mirrors ``isModelSelectionLocked`` in OpenClaw.
    """
    if not entry:
        return False
    return entry.get("modelSelectionLocked") is True


def _assert_model_selection_unlocked(entry: SessionEntry) -> None:
    """Raise :class:`ModelSelectionLockedError` if the entry is locked.

    Mirrors the private ``assertModelSelectionUnlocked`` helper.
    """
    if is_model_selection_locked(entry):
        raise ModelSelectionLockedError()


def _clear_fallback_origin(entry: SessionEntry) -> bool:
    """Delete ``modelOverrideFallbackOrigin{Provider,Model}`` if present.

    Returns ``True`` if any field was deleted. Mirrors the private
    ``clearFallbackOrigin`` helper.
    """
    updated = False
    if "modelOverrideFallbackOriginProvider" in entry:
        del entry["modelOverrideFallbackOriginProvider"]
        updated = True
    if "modelOverrideFallbackOriginModel" in entry:
        del entry["modelOverrideFallbackOriginModel"]
        updated = True
    return updated


def apply_model_override_to_session_entry(
    *,
    entry: SessionEntry,
    selection: ModelOverrideSelection,
    profileOverride: str | None = None,
    profileOverrideSource: ProfileOverrideSource | None = None,
    preserveAuthProfileOverride: bool = False,
    selectionSource: SelectionSource | None = None,
    markLiveSwitchPending: bool = False,
) -> dict[str, bool]:
    """Apply a model/auth-profile override to a session entry and clear stale runtime fields.

    Mirrors ``applyModelOverrideToSessionEntry`` in OpenClaw. Returns
    ``{"updated": bool}`` indicating whether any field changed.
    """
    _assert_model_selection_unlocked(entry)
    profile_source = profileOverrideSource if profileOverrideSource in VALID_PROFILE_OVERRIDE_SOURCES else "user"
    sel_source = selectionSource if selectionSource in VALID_SELECTION_SOURCES else "user"
    updated = False
    selection_updated = False
    profile_updated = False

    is_default = bool(selection.get("isDefault"))
    if is_default:
        if "providerOverride" in entry:
            del entry["providerOverride"]
            updated = True
            selection_updated = True
        if "modelOverride" in entry:
            del entry["modelOverride"]
            updated = True
            selection_updated = True
        if "modelOverrideSource" in entry:
            del entry["modelOverrideSource"]
            updated = True
        updated = _clear_fallback_origin(entry) or updated
    else:
        new_provider = selection.get("provider", "")
        new_model = selection.get("model", "")
        if entry.get("providerOverride") != new_provider:
            entry["providerOverride"] = new_provider
            updated = True
            selection_updated = True
        if entry.get("modelOverride") != new_model:
            entry["modelOverride"] = new_model
            updated = True
            selection_updated = True
        if entry.get("modelOverrideSource") != sel_source:
            entry["modelOverrideSource"] = sel_source
            updated = True
        updated = _clear_fallback_origin(entry) or updated

    # Model overrides supersede previously recorded runtime model
    # identity. If runtime fields are stale (or the override changed),
    # clear them so status surfaces reflect the selected model
    # immediately.
    runtime_model = normalize_optional_string(entry.get("model")) or ""
    runtime_provider = normalize_optional_string(entry.get("modelProvider")) or ""
    runtime_present = bool(runtime_model) or bool(runtime_provider)
    runtime_aligned = runtime_model == selection.get("model", "") and (
        not runtime_provider or runtime_provider == selection.get("provider", "")
    )
    if runtime_present and (selection_updated or not runtime_aligned):
        if "model" in entry:
            del entry["model"]
            updated = True
        if "modelProvider" in entry:
            del entry["modelProvider"]
            updated = True

    # When switching back to the default model without override
    # fields to delete (e.g. model comes from steering/fallback
    # runtime fields), the ``is_default`` branch above won't set
    # ``selection_updated``. Mark it here so that
    # ``liveModelSwitchPending`` can still be set below when
    # runtime is misaligned.
    if is_default and runtime_present and not runtime_aligned:
        selection_updated = True

    # ``contextTokens`` are derived from the active session model.
    # When the selected model changes (or runtime model is already
    # stale), the cached window can pin the session to an
    # older/smaller limit until another run refreshes it.
    if "contextTokens" in entry and (selection_updated or (runtime_present and not runtime_aligned)):
        del entry["contextTokens"]
        updated = True
    if "contextBudgetStatus" in entry and (selection_updated or (runtime_present and not runtime_aligned)):
        del entry["contextBudgetStatus"]
        updated = True

    if profileOverride:
        if entry.get("authProfileOverride") != profileOverride:
            entry["authProfileOverride"] = profileOverride
            updated = True
            profile_updated = True
        if entry.get("authProfileOverrideSource") != profile_source:
            entry["authProfileOverrideSource"] = profile_source
            updated = True
            profile_updated = True
        if "authProfileOverrideCompactionCount" in entry:
            del entry["authProfileOverrideCompactionCount"]
            updated = True
    elif not preserveAuthProfileOverride:
        if "authProfileOverride" in entry:
            del entry["authProfileOverride"]
            updated = True
            profile_updated = True
        if "authProfileOverrideSource" in entry:
            del entry["authProfileOverrideSource"]
            updated = True
            profile_updated = True
        if "authProfileOverrideCompactionCount" in entry:
            del entry["authProfileOverrideCompactionCount"]
            updated = True

    # Clear stale fallback notice when the user explicitly switches
    # models. The "pending without modelOverride" encoding is the
    # deliberate switch-back-to-default signal: the default branch
    # above also clears the runtime model fields so live-switch
    # resolution lands on the default.
    if updated:
        if (selection_updated or profile_updated) and markLiveSwitchPending:
            entry["liveModelSwitchPending"] = True
        entry.pop("fallbackNoticeSelectedModel", None)
        entry.pop("fallbackNoticeActiveModel", None)
        entry.pop("fallbackNoticeReason", None)
        import time

        entry["updatedAt"] = int(time.time() * 1000)

    return {"updated": updated}


def _wrapped_override_model(provider: str, model: str) -> str:
    """Return ``"{provider}/{model}"``. Mirrors the private TS helper."""
    return f"{provider}/{model}"


def repair_provider_wrapped_model_override(
    *,
    entry: SessionEntry,
    defaultProvider: str,
    defaultModel: str | None = None,
) -> dict[str, bool]:
    """Repair overrides where legacy provider/model fields were stored as ``provider/model`` strings.

    Mirrors ``repairProviderWrappedModelOverride`` in OpenClaw.
    """
    _assert_model_selection_unlocked(entry)
    override_provider = normalize_optional_string(entry.get("providerOverride"))
    override_model = normalize_optional_string(entry.get("modelOverride"))
    if not override_provider or not override_model:
        return {"updated": False}

    wrapped_model = _wrapped_override_model(override_provider, override_model)
    runtime_provider = normalize_optional_string(entry.get("modelProvider"))
    runtime_model = normalize_optional_string(entry.get("model"))
    if (
        runtime_provider
        and runtime_model == wrapped_model
        and runtime_provider != override_provider
    ):
        return apply_model_override_to_session_entry(
            entry=entry,
            selection={
                "provider": runtime_provider,
                "model": runtime_model or "",
                "isDefault": (
                    runtime_provider == defaultProvider
                    and bool(defaultModel)
                    and runtime_model == defaultModel
                ),
            },
            selectionSource="auto" if entry.get("modelOverrideSource") == "auto" else "user",
        )

    if (
        defaultProvider != override_provider
        and defaultModel is not None
        and defaultModel == wrapped_model
    ):
        return apply_model_override_to_session_entry(
            entry=entry,
            selection={
                "provider": defaultProvider,
                "model": defaultModel,
                "isDefault": True,
            },
        )

    return {"updated": False}


__all__ = [
    "MODEL_SELECTION_LOCKED_MESSAGE",
    "MODEL_SELECTION_LOCKED_RESET_MESSAGE",
    "ModelOverrideSelection",
    "ModelSelectionLockedError",
    "ProfileOverrideSource",
    "SelectionSource",
    "SessionEntry",
    "SessionEntryOverrideFields",
    "VALID_PROFILE_OVERRIDE_SOURCES",
    "VALID_SELECTION_SOURCES",
    "apply_model_override_to_session_entry",
    "is_model_selection_locked",
    "repair_provider_wrapped_model_override",
]
