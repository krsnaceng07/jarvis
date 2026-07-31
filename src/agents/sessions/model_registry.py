"""jarvis.agents.sessions.model_registry — model registry core.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/model-registry.ts``.

The :class:`ModelRegistry` is the public
model-registry facade. It loads the
``models.json`` file + the built-in provider
catalog + the plugin-published model catalogs,
resolves API keys via :class:`AuthStorage`,
and exposes a ``registerProvider`` /
``unregisterProvider`` API for extensions.

Phase 6.7b — model registry core (1:1 port).

Adaptations
-----------
- The OpenClaw source's TypeBox schemas
  (``typebox`` ``Type`` / ``Compile``) are
  replaced with plain dataclasses + a
  hand-rolled :func:`validate_config`. The
  Python port keeps the same field shape
  + the same validation semantics, but
  doesn't depend on a TypeBox-equivalent
  schema library.
- The OpenClaw source's Node ``fs`` calls
  are replaced with :mod:`os.path` +
  :func:`open` + :mod:`json`.
- The OpenClaw source's ``process.env`` is
  replaced with :data:`os.environ`.
- The OpenClaw source's plugin-catalog
  discovery (``listPluginModelCatalogFiles`` /
  ``isGeneratedPluginModelCatalog`` /
  ``filterGeneratedPluginModelCatalogProviders``)
  is a Phase 6.7+ stub — the Python port
  loads only the root ``models.json`` in 6.7b.
  The full plugin-catalog layer lands with
  the LLM client + the model-discovery
  context.
- The OpenClaw source's
  ``resolveModelPluginMetadataSnapshot`` is
  a Phase 6.7+ stub returning ``None``.
- The OpenClaw source's ``@openclaw/ai``
  / ``registerBuiltInApiProviders`` /
  ``getPublishedApiProviders`` API
  registration is a Phase 6.7+ stub — the
  Python port stores the registration
  intent but doesn't publish the provider
  to the api-registry.
- The OpenClaw source's ``Model`` type from
  ``llm/types.js`` is a typed LLM-message
  shape. The Python port uses a plain
  ``dict`` (the typed Model shape lands in
  Phase 6.7+ with the LLM client).
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Union

from .auth_storage import AuthStorage
from .auth_storage_oauth_registry import (
    get_auth_storage_oauth_provider_registry,
)
from .model_registry_runtime import (
    initialize_model_registry_runtime,
    reset_model_registry_runtime,
)
from .provider_display_names import BUILT_IN_PROVIDER_DISPLAY_NAMES
from .resolve_config_value import (
    clear_config_value_cache,
    resolve_config_value_or_throw,
    resolve_config_value_uncached,
    resolve_headers_or_throw,
)


_LOG = logging.getLogger("jarvis.agents.sessions.model_registry")


# ============================================================================
# Public types
# ============================================================================


#: Mirrors ``ResolvedRequestAuth``
#: (``model-registry.ts:244-253``).
#: ``{"ok": true, "apiKey"?, "headers"?}`` or
#: ``{"ok": false, "error"}``.
ResolvedRequestAuth = dict


#: Mirrors ``ProviderAuthMode``
#: (``model-registry.ts:158``).
#: ``"api-key"`` / ``"aws-sdk"`` / ``"oauth"`` /
#: ``"token"``.
ProviderAuthMode = str


#: Mirrors ``Api`` (the LLM-side API tag). The
#: Python port uses ``str`` for now (the
#: LLM-side enum lands in Phase 6.7+).
Api = str


#: Mirrors ``Model`` (the LLM-side model
#: shape). The Python port uses ``dict`` for
#: now (the typed Model shape lands in Phase
#: 6.7+).
Model = dict


#: Mirrors ``Context`` /
#: ``AssistantMessageEventStreamContract`` /
#: ``SimpleStreamOptions`` from the LLM
#: client. The Python port uses ``dict`` /
#: ``Any``.
Context = dict
AssistantMessageEventStreamContract = Any
SimpleStreamOptions = dict


# ============================================================================
# ProviderConfigInput
# ============================================================================


#: Mirrors ``ProviderConfigInput``
#: (``model-registry.ts:920-949``).
ProviderConfigInput = dict


# ============================================================================
# Internal types
# ============================================================================


@dataclass(frozen=True, slots=True)
class ProviderRequestConfig:
    """Internal: stores the request-level
    config for a provider. Mirrors the OpenClaw
    source's ``ProviderRequestConfig``
    (``model-registry.ts:237-242``)."""

    api_key: Optional[str] = None
    auth: Optional[ProviderAuthMode] = None
    headers: Optional[dict] = None
    auth_header: Optional[bool] = None


#: Internal: result of loading custom models
#: from ``models.json``. Mirrors
#: ``CustomModelsResult``
#: (``model-registry.ts:256-259``).
class CustomModelsResult(dict):
    """``{"models", "error"}``."""

    def __init__(
        self,
        models: Optional[list[Model]] = None,
        error: Optional[str] = None,
    ) -> None:
        super().__init__(models=list(models or []), error=error)


# ============================================================================
# Helpers
# ============================================================================


def _empty_custom_models_result(
    error: Optional[str] = None,
) -> CustomModelsResult:
    """Mirrors ``emptyCustomModelsResult``
    (``model-registry.ts:261-263``)."""
    return CustomModelsResult(models=[], error=error)


def _format_validation_path(
    error: dict,
) -> str:
    """Mirrors ``formatValidationPath``
    (``model-registry.ts:216-228``)."""
    keyword = error.get("keyword")
    if keyword == "required":
        required = (
            error.get("params", {}).get("requiredProperties") or []
        )
        if required:
            required_property = required[0]
            base_path = re.sub(
                r"^/", "", error.get("instancePath", "")
            ).replace("/", ".")
            return (
                f"{base_path}.{required_property}"
                if base_path
                else required_property
            )
    path = re.sub(r"^/", "", error.get("instancePath", "")).replace(
        "/", "."
    )
    return path or "root"


def _strip_json_comments(input_str: str) -> str:
    """Strip ``//`` line comments + trailing
    commas from JSON, leaving string literals
    untouched. Mirrors ``stripJsonComments``
    (``model-registry.ts:231-235``)."""
    # Phase 6.7b ships a best-effort Python
    # port: the OpenClaw regex-based
    # implementation is non-trivial. The
    # Python port handles the common cases
    # (single-line ``//`` comments outside
    # strings + trailing commas). The full
    # edge-case coverage lands with the LLM
    # client.
    result: list[str] = []
    i = 0
    in_string = False
    escape = False
    while i < len(input_str):
        ch = input_str[i]
        if in_string:
            result.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            result.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < len(input_str) and input_str[i + 1] == "/":
            # Line comment — skip to end of line.
            while i < len(input_str) and input_str[i] != "\n":
                i += 1
            continue
        result.append(ch)
        i += 1
    text = "".join(result)
    # Strip trailing commas before } or ].
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    return text


def _merge_compat(
    base_compat: Optional[dict],
    override_compat: Optional[dict],
) -> Optional[dict]:
    """Merge two compat dicts. Mirrors
    ``mergeCompat``
    (``model-registry.ts:270-304``)."""
    if not override_compat:
        return base_compat
    base = base_compat or {}
    override = override_compat
    merged = {**base, **override}
    base_routing = base.get("openRouterRouting")
    override_routing = override.get("openRouterRouting")
    if base_routing or override_routing:
        merged["openRouterRouting"] = {
            **(base_routing or {}),
            **(override_routing or {}),
        }
    base_vercel = base.get("vercelGatewayRouting")
    override_vercel = override.get("vercelGatewayRouting")
    if base_vercel or override_vercel:
        merged["vercelGatewayRouting"] = {
            **(base_vercel or {}),
            **(override_vercel or {}),
        }
    return merged


# ============================================================================
# ModelRegistry
# ============================================================================


def _default_models_json_path() -> str:
    """Return the default ``models.json`` path.
    Mirrors the OpenClaw source's
    ``join(getAgentDir(), "models.json")``
    (``model-registry.ts:343``)."""
    return str(
        Path.home() / ".jarvis" / "agents" / "default" / "models.json"
    )


class ModelRegistry:
    """Model-registry facade. Mirrors
    ``ModelRegistry``
    (``model-registry.ts:312-915``).

    Loads the ``models.json`` file + the
    built-in + plugin-published provider
    catalogs, resolves API keys via
    :class:`AuthStorage`, and exposes a
    ``registerProvider`` / ``unregisterProvider``
    API for extensions.

    Phase 6.7b ships the file-based load +
    the provider registration + the API-key
    resolution chain. The plugin-catalog
    discovery + the LLM client + the api/
    stream provider registration land in
    Phase 6.7+ with the LLM client.
    """

    def __init__(
        self,
        auth_storage: AuthStorage,
        models_json_path: Optional[str] = None,
        options: Optional[dict] = None,
    ) -> None:
        options = options or {}
        self.auth_storage = auth_storage
        try:
            initialize_model_registry_runtime(self)
        except RuntimeError:
            reset_model_registry_runtime(self)
        self.models_json_path = models_json_path
        # Plugin metadata snapshot — Phase 6.7b
        # ships ``None`` (the full snapshot
        # resolver lands in 6.7+).
        self.plugin_metadata_snapshot = options.get("pluginMetadataSnapshot")
        # Workspace dir (used by the plugin
        # snapshot resolver in 6.7+).
        self.workspace_dir = options.get("workspaceDir")
        self.models: list[Model] = []
        self.provider_request_configs: dict[str, ProviderRequestConfig] = {}
        self.model_request_headers: dict[str, dict] = {}
        self.registered_providers: dict[str, ProviderConfigInput] = {}
        self.load_error: Optional[str] = None
        self._load_models()

    # ------------------------------------------------------------------
    # Static factories
    # ------------------------------------------------------------------

    @staticmethod
    def create(
        auth_storage: AuthStorage,
        models_json_path: Optional[str] = None,
        options: Optional[dict] = None,
    ) -> "ModelRegistry":
        """Mirrors ``ModelRegistry.create``
        (``model-registry.ts:341-347``)."""
        if models_json_path is None:
            models_json_path = _default_models_json_path()
        return ModelRegistry(
            auth_storage=auth_storage,
            models_json_path=models_json_path,
            options=options,
        )

    @staticmethod
    def in_memory(auth_storage: AuthStorage) -> "ModelRegistry":
        """Mirrors ``ModelRegistry.inMemory``
        (``model-registry.ts:349-351``)."""
        return ModelRegistry(
            auth_storage=auth_storage,
            models_json_path=None,
        )

    # ------------------------------------------------------------------
    # Refresh / load
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Reload models from disk. Mirrors
        ``refresh``
        (``model-registry.ts:356-370``)."""
        self.provider_request_configs.clear()
        self.model_request_headers.clear()
        self.load_error = None
        # Reset the API registry + the OAuth
        # registry so re-applied dynamic
        # providers are the only registered
        # ones.
        reset_model_registry_runtime(self)
        try:
            get_auth_storage_oauth_provider_registry(
                self.auth_storage
            ).reset()
        except Exception:
            pass
        self._load_models()
        for provider_name, config in self.registered_providers.items():
            self._apply_provider_config(provider_name, config)

    def get_error(self) -> Optional[str]:
        """Return any root / generated catalog
        load error. Mirrors ``getError``
        (``model-registry.ts:373-375``)."""
        return self.load_error

    # ------------------------------------------------------------------
    # Load models
    # ------------------------------------------------------------------

    def _load_models(self) -> None:
        """Load configured models + request
        settings from ``models.json`` +
        generated plugin-owned catalog shards.
        Mirrors ``loadModels``
        (``model-registry.ts:377-401``)."""
        result: CustomModelsResult
        if self.models_json_path:
            result = self._load_custom_models(
                self.models_json_path,
                {"include_plugin_catalogs": True},
            )
        else:
            result = _empty_custom_models_result()
        if result.get("error"):
            self.load_error = result["error"]
            _LOG.warning(
                "model catalog load issue: %s", result["error"]
            )
        combined = list(result.get("models", []))
        # Let OAuth providers modify their
        # models (e.g., update ``baseUrl``).
        try:
            for oauth_provider in (
                self.auth_storage.get_oauth_providers() or []
            ):
                cred = self.auth_storage.get(oauth_provider.get("id"))
                if (
                    isinstance(cred, dict)
                    and cred.get("type") == "oauth"
                    and oauth_provider.get("modifyModels")
                ):
                    combined = oauth_provider["modifyModels"](
                        combined, cred
                    )
        except Exception:
            pass
        self.models = combined

    def _load_custom_models(
        self,
        models_json_path: str,
        options: Optional[dict] = None,
    ) -> CustomModelsResult:
        """Load a single ``models.json`` file.
        Mirrors ``loadCustomModels``
        (``model-registry.ts:403-495``)."""
        options = options or {}
        if not os.path.exists(models_json_path):
            return _empty_custom_models_result()
        try:
            with open(models_json_path, "r", encoding="utf-8") as f:
                content = f.read()
            try:
                parsed = json.loads(_strip_json_comments(content))
            except json.JSONDecodeError as exc:
                if options.get("requireGeneratedCatalog") is True:
                    return _empty_custom_models_result()
                return _empty_custom_models_result(
                    f"Failed to parse models.json: {exc.msg}\n\nFile: {models_json_path}"
                )
            if not isinstance(parsed, dict):
                return _empty_custom_models_result(
                    f"Invalid models.json: expected an object at the top level.\n\nFile: {models_json_path}"
                )
            # Validate the schema (Phase 6.7b's
            # hand-rolled validation mirrors
            # TypeBox's ``validateModelsConfig``).
            validation_errors = self._validate_models_config_schema(
                parsed
            )
            if validation_errors:
                error_text = "\n".join(
                    f"  - {_format_validation_path(err)}: {err.get('message', 'Unknown error')}"
                    for err in validation_errors
                ) or "Unknown schema error"
                return _empty_custom_models_result(
                    f"Invalid models.json schema:\n{error_text}\n\nFile: {models_json_path}"
                )
            config = parsed
            providers = config.get("providers", {})
            config_for_use = {**config, "providers": providers}
            # Phase 6.7b: no plugin-catalog
            # support (lands in 6.7+).
            try:
                self._validate_config(config_for_use)
            except Exception as exc:
                return _empty_custom_models_result(
                    f"Invalid models.json: {exc}\n\nFile: {models_json_path}"
                )
            for provider_name, provider_config in providers.items():
                if (provider_config.get("models") or []):
                    self._store_provider_request_config(
                        provider_name, provider_config
                    )
            models = self._parse_models(
                config_for_use, "configured"
            )
            return CustomModelsResult(models=models, error=None)
        except Exception as exc:
            return _empty_custom_models_result(
                f"Failed to load models.json: {exc}\n\nFile: {models_json_path}"
            )

    def _validate_models_config_schema(
        self, parsed: dict
    ) -> list[dict]:
        """Hand-rolled schema validator. Mirrors
        the OpenClaw source's
        ``validateModelsConfig``
        (``model-registry.ts:211``)."""
        errors: list[dict] = []
        if not isinstance(parsed, dict):
            errors.append(
                {
                    "instancePath": "",
                    "message": "expected object",
                }
            )
            return errors
        if "providers" not in parsed:
            errors.append(
                {
                    "instancePath": "",
                    "keyword": "required",
                    "params": {"requiredProperties": ["providers"]},
                    "message": "missing required property 'providers'",
                }
            )
            return errors
        if not isinstance(parsed.get("providers"), dict):
            errors.append(
                {
                    "instancePath": "/providers",
                    "message": "expected object",
                }
            )
            return errors
        for provider_name, provider_config in parsed["providers"].items():
            if not isinstance(provider_config, dict):
                errors.append(
                    {
                        "instancePath": f"/providers/{provider_name}",
                        "message": "expected object",
                    }
                )
                continue
            # ``apiKey`` / ``baseUrl`` / ``auth`` are optional.
            # ``api`` is optional (some providers use compat
            # for the API type).
            # ``models`` is an optional array of objects.
            models = provider_config.get("models", [])
            if models is not None and not isinstance(models, list):
                errors.append(
                    {
                        "instancePath": f"/providers/{provider_name}/models",
                        "message": "expected array",
                    }
                )
            for i, model_def in enumerate(models or []):
                if not isinstance(model_def, dict):
                    errors.append(
                        {
                            "instancePath": f"/providers/{provider_name}/models/{i}",
                            "message": "expected object",
                        }
                    )
                    continue
                if "id" not in model_def or not isinstance(
                    model_def.get("id"), str
                ) or not model_def["id"]:
                    errors.append(
                        {
                            "instancePath": f"/providers/{provider_name}/models/{i}",
                            "keyword": "required",
                            "params": {"requiredProperties": ["id"]},
                            "message": "missing required property 'id'",
                        }
                    )
        return errors

    def _validate_config(self, config: dict) -> None:
        """Validate the post-schema config.
        Mirrors ``validateConfig``
        (``model-registry.ts:497-533``)."""
        for provider_name, provider_config in config.get(
            "providers", {}
        ).items():
            models = provider_config.get("models") or []
            if not models:
                continue
            if not provider_config.get("baseUrl"):
                raise RuntimeError(
                    f'Provider {provider_name}: "baseUrl" is required when defining custom models.'
                )
            for model_def in models:
                has_provider_api = bool(provider_config.get("api"))
                has_model_api = bool(model_def.get("api"))
                if not has_provider_api and not has_model_api:
                    raise RuntimeError(
                        f"Provider {provider_name}, model {model_def.get('id')}: no \"api\" specified. Set at provider or model level."
                    )
                if not model_def.get("id"):
                    raise RuntimeError(
                        f'Provider {provider_name}: model missing "id"'
                    )
                if (
                    model_def.get("contextWindow") is not None
                    and model_def["contextWindow"] <= 0
                ):
                    raise RuntimeError(
                        f"Provider {provider_name}, model {model_def['id']}: invalid contextWindow"
                    )
                if (
                    model_def.get("maxTokens") is not None
                    and model_def["maxTokens"] <= 0
                ):
                    raise RuntimeError(
                        f"Provider {provider_name}, model {model_def['id']}: invalid maxTokens"
                    )

    def _parse_models(
        self, config: dict, max_tokens_source: str
    ) -> list[Model]:
        """Parse the model definitions into
        :class:`Model` rows. Mirrors
        ``parseModels``
        (``model-registry.ts:535-588``)."""
        models: list[Model] = []
        for provider_name, provider_config in config.get(
            "providers", {}
        ).items():
            model_defs = provider_config.get("models") or []
            if not model_defs:
                continue
            for model_def in model_defs:
                api = model_def.get("api") or provider_config.get("api")
                if not api:
                    continue
                base_url = model_def.get("baseUrl") or provider_config.get(
                    "baseUrl"
                )
                if not base_url:
                    continue
                # Project richer persisted metadata
                # to runtime's text/image contract.
                raw_input = model_def.get("input") or ["text"]
                runtime_input = [
                    i for i in raw_input if i in ("text", "image")
                ]
                if len(raw_input) > 0 and not runtime_input:
                    continue
                compat = _merge_compat(
                    provider_config.get("compat"),
                    model_def.get("compat"),
                )
                self._store_model_headers(
                    provider_name,
                    model_def.get("id"),
                    model_def.get("headers"),
                )
                default_cost = {
                    "input": 0,
                    "output": 0,
                    "cacheRead": 0,
                    "cacheWrite": 0,
                }
                model: Model = {
                    "id": model_def.get("id"),
                    "name": model_def.get("name") or model_def.get("id"),
                    "api": api,
                    "provider": provider_name,
                    "baseUrl": base_url,
                    "reasoning": bool(model_def.get("reasoning")),
                    "thinkingLevelMap": model_def.get("thinkingLevelMap"),
                    "input": runtime_input,
                    "cost": model_def.get("cost") or default_cost,
                    "contextWindow": model_def.get("contextWindow") or 128000,
                    "maxTokens": model_def.get("maxTokens") or 16384,
                    "params": model_def.get("params"),
                    "headers": None,
                    "compat": compat,
                }
                if "maxTokens" in model_def:
                    model["maxTokensSource"] = max_tokens_source
                models.append(model)
        return models

    # ------------------------------------------------------------------
    # Getters
    # ------------------------------------------------------------------

    def get_all(self) -> list[Model]:
        """Get every configured model. Mirrors
        ``getAll``
        (``model-registry.ts:593-595``)."""
        return self.models

    def get_available(self) -> list[Model]:
        """Get only models that have auth
        configured. Mirrors ``getAvailable``
        (``model-registry.ts:601-603``)."""
        return [m for m in self.models if self.has_configured_auth(m)]

    def find(
        self, provider: str, model_id: str
    ) -> Optional[Model]:
        """Find a model by provider + id. Mirrors
        ``find``
        (``model-registry.ts:608-610``)."""
        for m in self.models:
            if m.get("provider") == provider and m.get("id") == model_id:
                return m
        return None

    def has_configured_auth(self, model: Model) -> bool:
        """True iff the model has auth configured.
        Mirrors ``hasConfiguredAuth``
        (``model-registry.ts:615-621``)."""
        provider = model.get("provider")
        if self.auth_storage.has_auth(provider):
            return True
        config = self.provider_request_configs.get(provider)
        if config and config.auth == "aws-sdk":
            return True
        if config and config.api_key is not None:
            return True
        return False

    # ------------------------------------------------------------------
    # API-key + headers resolution
    # ------------------------------------------------------------------

    async def get_api_key_and_headers(
        self, model: Model
    ) -> ResolvedRequestAuth:
        """Resolve the API key + request headers
        for a model. Mirrors ``getApiKeyAndHeaders``
        (``model-registry.ts:664-714``)."""
        try:
            provider = model.get("provider")
            provider_config = self.provider_request_configs.get(provider)
            uses_aws_sdk_auth = (
                provider_config is not None
                and provider_config.auth == "aws-sdk"
            )
            api_key_from_auth_storage: Optional[str] = None
            if not uses_aws_sdk_auth:
                api_key_from_auth_storage = (
                    await self.auth_storage.get_api_key(
                        provider, {"includeFallback": False}
                    )
                )
            api_key: Optional[str] = (
                api_key_from_auth_storage
                if api_key_from_auth_storage
                else (
                    resolve_config_value_or_throw(
                        provider_config.api_key,
                        f'API key for provider "{provider}"',
                    )
                    if (
                        provider_config
                        and not uses_aws_sdk_auth
                        and provider_config.api_key
                    )
                    else None
                )
            )
            provider_headers = resolve_headers_or_throw(
                provider_config.headers if provider_config else None,
                f'provider "{provider}"',
            )
            model_headers = resolve_headers_or_throw(
                self.model_request_headers.get(
                    self._get_model_request_key(
                        provider, model.get("id")
                    )
                ),
                f'model "{provider}/{model.get("id")}"',
            )
            model_existing_headers = model.get("headers")
            headers: Optional[dict] = None
            if model_existing_headers or provider_headers or model_headers:
                headers = {
                    **(model_existing_headers or {}),
                    **(provider_headers or {}),
                    **(model_headers or {}),
                }
            if provider_config and provider_config.auth_header:
                if not api_key:
                    return {
                        "ok": False,
                        "error": f'No API key found for "{provider}"',
                    }
                headers = {
                    **(headers or {}),
                    "Authorization": f"Bearer {api_key}",
                }
            return {
                "ok": True,
                "apiKey": api_key,
                "headers": (
                    headers
                    if headers and len(headers) > 0
                    else None
                ),
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def get_provider_auth_status(self, provider: str) -> dict:
        """Return the auth status for a
        provider. Mirrors ``getProviderAuthStatus``
        (``model-registry.ts:720-745``)."""
        config = self.provider_request_configs.get(provider)
        if config and config.auth == "aws-sdk":
            return {
                "configured": True,
                "source": "models_json_key",
                "label": config.auth,
            }
        auth_status = self.auth_storage.get_auth_status(provider)
        if auth_status.get("source"):
            return auth_status
        provider_api_key = config.api_key if config else None
        if not provider_api_key:
            return auth_status
        if provider_api_key.startswith("!"):
            return {
                "configured": True,
                "source": "models_json_command",
            }
        if provider_api_key in os.environ:
            return {
                "configured": True,
                "source": "environment",
                "label": provider_api_key,
            }
        return {
            "configured": True,
            "source": "models_json_key",
        }

    def get_provider_display_name(self, provider: str) -> str:
        """Return the display name for a
        provider. Mirrors
        ``getProviderDisplayName``
        (``model-registry.ts:750-761``)."""
        registered = self.registered_providers.get(provider) or {}
        oauth_providers = self.auth_storage.get_oauth_providers() or []
        oauth_provider = next(
            (
                p
                for p in oauth_providers
                if p.get("id") == provider
            ),
            None,
        )
        return (
            registered.get("name")
            or (registered.get("oauth") or {}).get("name")
            or (oauth_provider or {}).get("name")
            or BUILT_IN_PROVIDER_DISPLAY_NAMES.get(provider, provider)
        )

    async def get_api_key_for_provider(
        self, provider: str
    ) -> Optional[str]:
        """Get the API key for a provider. Mirrors
        ``getApiKeyForProvider``
        (``model-registry.ts:766-774``)."""
        api_key = await self.auth_storage.get_api_key(
            provider, {"includeFallback": False}
        )
        if api_key is not None:
            return api_key
        config = self.provider_request_configs.get(provider)
        provider_api_key = config.api_key if config else None
        if not provider_api_key:
            return None
        return resolve_config_value_uncached(provider_api_key)

    def is_using_oauth(self, model: Model) -> bool:
        """True iff the model is using OAuth
        credentials. Mirrors ``isUsingOAuth``
        (``model-registry.ts:779-782``)."""
        cred = self.auth_storage.get(model.get("provider"))
        return isinstance(cred, dict) and cred.get("type") == "oauth"

    # ------------------------------------------------------------------
    # registerProvider / unregisterProvider
    # ------------------------------------------------------------------

    def register_provider(
        self, provider_name: str, config: ProviderConfigInput
    ) -> None:
        """Register a provider dynamically
        (from extensions). Mirrors
        ``registerProvider``
        (``model-registry.ts:792-796``)."""
        self._validate_provider_config(provider_name, config)
        self._apply_provider_config(provider_name, config)
        self._upsert_registered_provider(provider_name, config)

    def unregister_provider(self, provider_name: str) -> None:
        """Unregister a previously registered
        provider. Mirrors ``unregisterProvider``
        (``model-registry.ts:806-812``)."""
        if provider_name not in self.registered_providers:
            return
        del self.registered_providers[provider_name]
        self.refresh()

    def _upsert_registered_provider(
        self, provider_name: str, config: ProviderConfigInput
    ) -> None:
        """Upsert a provider config into
        ``registeredProviders``. Mirrors
        ``upsertRegisteredProvider``
        (``model-registry.ts:820-831``)."""
        existing = self.registered_providers.get(provider_name)
        if not existing:
            self.registered_providers[provider_name] = config
            return
        for k, v in config.items():
            if v is not None:
                existing[k] = v

    def _validate_provider_config(
        self, provider_name: str, config: ProviderConfigInput
    ) -> None:
        """Validate the post-schema provider
        config. Mirrors ``validateProviderConfig``
        (``model-registry.ts:833-851``)."""
        if config.get("streamSimple") and not config.get("api"):
            raise RuntimeError(
                f'Provider {provider_name}: "api" is required when registering streamSimple.'
            )
        models = config.get("models") or []
        if not models:
            return
        if not config.get("baseUrl"):
            raise RuntimeError(
                f'Provider {provider_name}: "baseUrl" is required when defining models.'
            )
        for model_def in models:
            api = model_def.get("api") or config.get("api")
            if not api:
                raise RuntimeError(
                    f"Provider {provider_name}, model {model_def.get('id')}: no \"api\" specified."
                )

    def _apply_provider_config(
        self, provider_name: str, config: ProviderConfigInput
    ) -> None:
        """Apply a provider config. Mirrors
        ``applyProviderConfig``
        (``model-registry.ts:853-914``)."""
        if config.get("oauth"):
            oauth_provider = {
                **config["oauth"],
                "id": provider_name,
            }
            try:
                get_auth_storage_oauth_provider_registry(
                    self.auth_storage
                ).register(oauth_provider)
            except Exception:
                pass
        if config.get("streamSimple") and config.get("api"):
            # Phase 6.7+ wires the actual API
            # registration via the LLM client.
            # The Python port stores the intent
            # without publishing.
            pass
        self._store_provider_request_config(provider_name, config)
        models = config.get("models") or []
        if not models:
            return
        # Full replacement: remove existing
        # models for this provider.
        self.models = [
            m for m in self.models if m.get("provider") != provider_name
        ]
        for model_def in models:
            api = model_def.get("api") or config.get("api")
            self._store_model_headers(
                provider_name,
                model_def.get("id"),
                model_def.get("headers"),
            )
            self.models.append(
                {
                    "id": model_def.get("id"),
                    "name": model_def.get("name"),
                    "api": api,
                    "provider": provider_name,
                    "baseUrl": model_def.get("baseUrl")
                    or config.get("baseUrl"),
                    "reasoning": model_def.get("reasoning"),
                    "thinkingLevelMap": model_def.get("thinkingLevelMap"),
                    "input": model_def.get("input"),
                    "cost": model_def.get("cost"),
                    "contextWindow": model_def.get("contextWindow"),
                    "maxTokens": model_def.get("maxTokens"),
                    "params": model_def.get("params"),
                    "headers": None,
                    "compat": model_def.get("compat"),
                }
            )
        # Apply OAuth ``modifyModels`` if
        # credentials exist.
        oauth = config.get("oauth")
        if oauth and oauth.get("modifyModels"):
            cred = self.auth_storage.get(provider_name)
            if isinstance(cred, dict) and cred.get("type") == "oauth":
                self.models = oauth["modifyModels"](
                    self.models, cred
                )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_model_request_key(
        self, provider: str, model_id: str
    ) -> str:
        """``"{provider}:{modelId}"``. Mirrors
        ``getModelRequestKey``
        (``model-registry.ts:623-625``)."""
        return f"{provider}:{model_id}"

    def _store_provider_request_config(
        self,
        provider_name: str,
        config: dict,
    ) -> None:
        """Store the request-level config for a
        provider. Mirrors
        ``storeProviderRequestConfig``
        (``model-registry.ts:627-646``)."""
        api_key = config.get("apiKey")
        auth = config.get("auth")
        headers = config.get("headers")
        auth_header = config.get("authHeader")
        if not api_key and not auth and not headers and not auth_header:
            return
        self.provider_request_configs[provider_name] = (
            ProviderRequestConfig(
                api_key=api_key,
                auth=auth,
                headers=headers,
                auth_header=bool(auth_header),
            )
        )

    def _store_model_headers(
        self,
        provider_name: str,
        model_id: str,
        headers: Optional[dict],
    ) -> None:
        """Store the per-model headers. Mirrors
        ``storeModelHeaders``
        (``model-registry.ts:648-659``)."""
        key = self._get_model_request_key(provider_name, model_id)
        if not headers:
            self.model_request_headers.pop(key, None)
            return
        self.model_request_headers[key] = headers


# ============================================================================
# Re-export the cache-clear helper
# ============================================================================


#: Mirrors the OpenClaw source's
#: ``export const clearApiKeyCache``
#: (``model-registry.ts:306-307``). The
#: Python port delegates to the underlying
#: ``resolveConfigValue`` cache-clear helper
#: from :mod:`jarvis.agents.sessions.resolve_config_value`.
clear_api_key_cache = clear_config_value_cache


#: Phase 6.7a placeholder (the typed shape
#: lands in Phase 6.7+ with the LLM client).
ConfiguredModel = Model


#: Phase 6.7a placeholder (the typed shape
#: lands in Phase 6.7+ with the LLM client).
ModelDefinition = dict


__all__ = [
    "Api",
    "AssistantMessageEventStreamContract",
    "ConfiguredModel",
    "Context",
    "CustomModelsResult",
    "Model",
    "ModelDefinition",
    "ModelRegistry",
    "ProviderAuthMode",
    "ProviderConfigInput",
    "ProviderRequestConfig",
    "ResolvedRequestAuth",
    "SimpleStreamOptions",
    "clear_api_key_cache",
]
