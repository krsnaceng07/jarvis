"""jarvis_sdk.plugin_registry_state — plugin registry state factory.

OpenClaw parity: mirrors
``src/plugins/registry-state.ts`` (~100 LOC).
Creates the in-memory state object backing a plugin
registry. The state carries the empty ``PluginRegistry``
shape, the core-gateway method set, the hook-rollback
map, the side-effect-guard map, and the diagnostic
push helper.

Public API:
- ``PluginTypedHookPolicy`` — typed-hook policy shape.
- ``PluginSideEffectGuard`` — side-effect guard shape.
- ``PluginRegistrationCapabilities`` — decoded mode flags.
- ``resolve_plugin_registration_capabilities(mode)`` —
  decode the public mode once.
- ``resolve_typed_hook_timeout_ms(...)`` — normalize the
  typed-hook timeout using a layered fallback.
- ``create_plugin_registry_state(params)`` — build the
  state object.

Key port decisions:
- The ``createModelCatalogRegistrationHandlers`` dep
  (from OpenClaw's ``model-catalog-registration.ts``) is
  stubbed for now: the port provides a no-op
  ``registerModelCatalogProvider`` so the state factory
  has the same shape. A later phase will port the
  model-catalog registration logic in full.
- ``Object.keys`` → ``list(...)``.
- ``toSorted`` → ``sorted``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, TypedDict, TypeAlias, cast

from .plugin_registry_empty import create_empty_plugin_registry
from .plugin_registry_types import (
    PluginRegistry,
    PluginRegistryParams,
)

if TYPE_CHECKING:
    pass

# Mirrors OpenClaw's ``PluginRegistrationMode``.
# Possible values: ``"full"`` / ``"discovery"`` / ``"tool-discovery"`` /
# ``"setup-runtime"`` / ``"setup-only"``. The Python port uses
# ``Literal`` for clarity.
PluginRegistrationMode = Literal[
    "full", "discovery", "tool-discovery", "setup-runtime", "setup-only"
]


class PluginTypedHookPolicy(TypedDict, total=False):
    """Typed-hook policy shape. Mirrors OpenClaw's ``PluginTypedHookPolicy``."""

    allowPromptInjection: bool  # noqa: N815
    allowConversationAccess: bool  # noqa: N815
    timeoutMs: int  # noqa: N815
    timeouts: dict[str, int]  # { hook_name: ms }


class PluginSideEffectGuard(TypedDict, total=False):
    """Side-effect guard shape. Mirrors OpenClaw's ``PluginSideEffectGuard``."""

    active: bool


class PluginRegistrationCapabilities(TypedDict, total=False):
    """Decoded registration-mode flags.

    Mirrors OpenClaw's ``PluginRegistrationCapabilities``.
    """

    capabilityHandlers: bool  # noqa: N815
    setupRuntimeHandlers: bool  # noqa: N815
    runtimeChannel: bool  # noqa: N815


def resolve_plugin_registration_capabilities(
    mode: PluginRegistrationMode,
) -> PluginRegistrationCapabilities:
    """Decode ``mode`` once so domain registrars don't repeat string checks.

    Mirrors OpenClaw's ``resolvePluginRegistrationCapabilities``.
    """
    return {
        "capabilityHandlers": mode in ("full", "discovery", "tool-discovery"),
        "setupRuntimeHandlers": mode == "setup-runtime",
        "runtimeChannel": mode not in ("setup-only", "tool-discovery"),
    }


def _normalize_hook_timeout_ms(value: object) -> int | None:
    """Normalize a timeout value. Mirrors OpenClaw's ``normalizeHookTimeoutMs``.

    Returns ``None`` for non-positive / non-finite values.
    """
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    if value != value or value <= 0:  # NaN check + positivity
        return None
    if value == float("inf") or value == float("-inf"):
        return None
    return int(value)


def resolve_typed_hook_timeout_ms(
    *,
    hook_name: str,
    opts: dict[str, Any] | None = None,
    policy: PluginTypedHookPolicy | None = None,
) -> int | None:
    """Resolve the typed-hook timeout using a layered fallback.

    Mirrors OpenClaw's ``resolveTypedHookTimeoutMs``:
    1. ``policy.timeouts[hookName]``
    2. ``policy.timeoutMs``
    3. ``opts.timeoutMs``
    """
    if policy is not None:
        timeouts = policy.get("timeouts")
        if isinstance(timeouts, dict):
            ms = _normalize_hook_timeout_ms(timeouts.get(hook_name))
            if ms is not None:
                return ms
        ms = _normalize_hook_timeout_ms(policy.get("timeoutMs"))
        if ms is not None:
            return ms
    if opts is not None:
        ms = _normalize_hook_timeout_ms(opts.get("timeoutMs"))
        if ms is not None:
            return ms
    return None


def _create_stub_model_catalog_registration_handlers(
    registry: PluginRegistry,
    push_diagnostic: Any,
) -> dict[str, Any]:
    """Stub for the model-catalog registration handlers.

    A later phase will replace this with a full port of
    OpenClaw's ``model-catalog-registration.ts``. For now
    the stub provides a no-op ``registerModelCatalogProvider``
    so ``create_plugin_registry_state`` has the same shape.
    """
    def _register_model_catalog_provider(
        record: Any,
        provider: Any,
    ) -> None:
        # No-op stub: the real implementation will validate
        # the provider, push diagnostics on conflict, and
        # append to ``registry.modelCatalogProviders``.
        # This stub exists so the public surface compiles.
        _ = (registry, push_diagnostic, record, provider)

    def _register_synth_text(*_args: Any, **_kwargs: Any) -> None:
        return None

    def _register_synth_media(*_args: Any, **_kwargs: Any) -> None:
        return None

    def _register_synth_voice(*_args: Any, **_kwargs: Any) -> None:
        return None

    return {
        "registerModelCatalogProvider": _register_model_catalog_provider,
        "registerSynthesizedTextModelCatalogProvider": _register_synth_text,
        "registerSynthesizedMediaModelCatalogProvider": _register_synth_media,
        "registerSynthesizedVoiceModelCatalogProvider": _register_synth_voice,
    }


def create_plugin_registry_state(
    registry_params: PluginRegistryParams,
) -> dict[str, Any]:
    """Build the plugin-registry state object.

    Mirrors OpenClaw's ``createPluginRegistryState``.
    The returned dict has the same shape as the source's
    return value (so consumers can use ``.registry``,
    ``.pushDiagnostic``, ``.getHostCronService``, etc.).
    """
    registry = create_empty_plugin_registry()
    method_names: set[str] = set()
    core_gateway_method_names_raw = registry_params.get("coreGatewayMethodNames")
    if isinstance(core_gateway_method_names_raw, list):
        for name in core_gateway_method_names_raw:
            if isinstance(name, str):
                method_names.add(name)
    core_gateway_handlers_raw = registry_params.get("coreGatewayHandlers")
    if isinstance(core_gateway_handlers_raw, dict):
        for name in cast(dict[object, object], core_gateway_handlers_raw).keys():
            if isinstance(name, str):
                method_names.add(name)
    core_gateway_method_names = sorted(method_names)
    registry["coreGatewayMethodNames"] = core_gateway_method_names

    def push_diagnostic(diagnostic: dict[str, Any]) -> None:
        diagnostics = registry.get("diagnostics")
        if isinstance(diagnostics, list):
            diagnostics.append(diagnostic)

    model_catalog_registrars = _create_stub_model_catalog_registration_handlers(
        registry,
        push_diagnostic,
    )

    return {
        "registry": registry,
        "registryParams": registry_params,
        "coreGatewayMethods": set(core_gateway_method_names),
        "getHostCronService": lambda: (
            (registry_params.get("hostServices") or {}).get("cron")  # type: ignore[union-attr]
        ),
        "pluginHookRollback": {},
        "pluginsWithChannelRegistrationConflict": set(),
        "pluginSideEffectGuards": {},
        "pushDiagnostic": push_diagnostic,
        **model_catalog_registrars,
    }


PluginRegistryState: TypeAlias = dict[str, Any]


__all__ = [
    "PluginRegistrationMode",
    "PluginTypedHookPolicy",
    "PluginSideEffectGuard",
    "PluginRegistrationCapabilities",
    "resolve_plugin_registration_capabilities",
    "resolve_typed_hook_timeout_ms",
    "create_plugin_registry_state",
]
