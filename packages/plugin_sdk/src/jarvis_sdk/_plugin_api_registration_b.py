"""PluginApi registration helpers for the internal SDK implementation."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, cast

if TYPE_CHECKING:
    from .types import MediaUnderstandingProvider
    from .api import PluginControlUiDescriptor
    from .cron import CronDecl
    from .skill import SkillDecl

JSON = dict[str, Any]


class PluginApiRegistrationsB:
    def register_runtime_lifecycle(self, lifecycle: dict[str, Any] | Any) -> None:
        """Register a runtime lifecycle hook. Mirrors OpenClaw's host API surface."""
        if isinstance(lifecycle, dict):
            lifecycle_dict = cast(dict[str, Any], lifecycle)
            lifecycle_id = lifecycle_dict.get("id")
            start = lifecycle_dict.get("start")
            if not lifecycle_id or not isinstance(lifecycle_id, str):
                raise ValueError("runtime lifecycle requires a non-empty 'id'")
            if start is not None and not callable(start):
                raise ValueError("runtime lifecycle 'start' must be callable when provided")
            payload: dict[str, Any] = dict(lifecycle_dict)
        else:
            lifecycle_id = getattr(lifecycle, "id", None)
            start = getattr(lifecycle, "start", None)
            if not lifecycle_id or not isinstance(lifecycle_id, str):
                raise ValueError("runtime lifecycle requires a non-empty 'id'")
            if start is not None and not callable(start):
                raise ValueError("runtime lifecycle 'start' must be callable when provided")
            payload: dict[str, Any] = {"id": lifecycle_id, "start": start}
        payload["_owner_id"] = self._ctx.plugin_id
        self._runtime_lifecycles.append(payload)

    def register_control_ui_descriptor(
        self,
        descriptor: Any,
    ) -> None:
        """Register a control UI descriptor through the root PluginApi contract."""
        descriptor_obj = descriptor
        if isinstance(descriptor, dict):
            descriptor_dict = cast(dict[str, Any], descriptor)
            raw_required: list[object] = cast(
                list[object],
                descriptor_dict.get("requiredScopes")
                or descriptor_dict.get("required_scopes")
                or [],
            )
            if not isinstance(raw_required, list):
                raw_required = []
            required_scopes: list[str] = [x for x in raw_required if isinstance(x, str)]
            from .api import PluginControlUiDescriptor

            descriptor_obj = PluginControlUiDescriptor(
                surface=str(descriptor_dict.get("surface", "tab")),
                id=str(descriptor_dict.get("id", "")),
                label=str(descriptor_dict.get("label", "")),
                description=str(descriptor_dict.get("description", "")),
                icon=str(descriptor_dict.get("icon", "")),
                group=str(descriptor_dict.get("group", "control")),
                required_scopes=required_scopes,
            )
        if not getattr(descriptor_obj, "id", None):
            raise ValueError("control-ui descriptor must have a non-empty 'id'")
        payload: dict[str, Any] = {
            "surface": getattr(descriptor_obj, "surface", "tab"),
            "id": descriptor_obj.id,
            "label": getattr(descriptor_obj, "label", ""),
            "description": getattr(descriptor_obj, "description", ""),
            "icon": getattr(descriptor_obj, "icon", ""),
            "group": getattr(descriptor_obj, "group", "control"),
            "requiredScopes": list(getattr(descriptor_obj, "required_scopes", [])),
            "_owner_id": self._ctx.plugin_id,
        }
        self._control_ui_descriptors.append(payload)
        self.session.controls.register_control_ui_descriptor(descriptor_obj)

    def register_tool_metadata(self, metadata: dict[str, Any] | Any) -> None:
        """Register plugin tool metadata. Mirrors OpenClaw's capability surface."""
        if isinstance(metadata, dict):
            metadata_dict = cast(dict[str, Any], metadata)
            metadata_id = metadata_dict.get("id")
            if not metadata_id or not isinstance(metadata_id, str):
                raise ValueError("tool metadata requires a non-empty 'id'")
            payload: dict[str, Any] = dict(metadata_dict)
        else:
            metadata_id = getattr(metadata, "id", None)
            if not metadata_id or not isinstance(metadata_id, str):
                raise ValueError("tool metadata requires a non-empty 'id'")
            payload: dict[str, Any] = {"id": metadata_id, "metadata": getattr(metadata, "metadata", None) or {}}
        payload["_owner_id"] = self._ctx.plugin_id
        self._tool_metadata.append(payload)

    def register_trusted_tool_policy(self, policy: dict[str, Any] | Any) -> None:
        """Register a trusted-tool policy. Mirrors OpenClaw's capability surface."""
        if isinstance(policy, dict):
            policy_dict = cast(dict[str, Any], policy)
            policy_id = policy_dict.get("id")
            if not policy_id or not isinstance(policy_id, str):
                raise ValueError("trusted tool policy requires a non-empty 'id'")
            payload: dict[str, Any] = dict(policy_dict)
        else:
            policy_id = getattr(policy, "id", None)
            if not policy_id or not isinstance(policy_id, str):
                raise ValueError("trusted tool policy requires a non-empty 'id'")
            payload: dict[str, Any] = {"id": policy_id, "policy": getattr(policy, "policy", None) or {}}
        payload["_owner_id"] = self._ctx.plugin_id
        self._trusted_tool_policies.append(payload)

    def register_session_scheduler_job(self, job: dict[str, Any] | Any) -> None:
        """Register a session-scheduler job through the public API surface."""
        if isinstance(job, dict):
            job_dict = cast(dict[str, Any], job)
            job_id = job_dict.get("id")
            run = job_dict.get("run") or job_dict.get("handler")
            if not job_id or not isinstance(job_id, str):
                raise ValueError("session scheduler job requires a non-empty 'id'")
            if run is not None and not callable(run):
                raise ValueError("session scheduler job 'run' must be callable when provided")
            payload: dict[str, Any] = dict(job_dict)
        else:
            job_id = getattr(job, "id", None)
            run = getattr(job, "run", None) or getattr(job, "handler", None)
            if not job_id or not isinstance(job_id, str):
                raise ValueError("session scheduler job requires a non-empty 'id'")
            if run is not None and not callable(run):
                raise ValueError("session scheduler job 'run' must be callable when provided")
            payload: dict[str, Any] = {"id": job_id, "run": run}
        payload["_owner_id"] = self._ctx.plugin_id
        self._session_scheduler_jobs.append(payload)

    def register_session_action(self, action: dict[str, Any] | Any) -> None:
        """Register a session action through the host API contract."""
        if isinstance(action, dict):
            action_dict = cast(dict[str, Any], action)
            action_id = action_dict.get("id")
            run = action_dict.get("run") or action_dict.get("handler")
            if not action_id or not isinstance(action_id, str):
                raise ValueError("session action requires a non-empty 'id'")
            if run is not None and not callable(run):
                raise ValueError("session action 'run' must be callable when provided")
            payload: dict[str, Any] = dict(action_dict)
        else:
            action_id = getattr(action, "id", None)
            run = getattr(action, "run", None) or getattr(action, "handler", None)
            if not action_id or not isinstance(action_id, str):
                raise ValueError("session action requires a non-empty 'id'")
            if run is not None and not callable(run):
                raise ValueError("session action 'run' must be callable when provided")
            payload: dict[str, Any] = {"id": action_id, "run": run}
        payload["_owner_id"] = self._ctx.plugin_id
        self._session_actions.append(payload)

    def register_agent_event_subscription(self, subscription: dict[str, Any] | Any) -> None:
        """Register an agent-event subscription for runtime observation."""
        if isinstance(subscription, dict):
            subscription_dict = cast(dict[str, Any], subscription)
            subscription_id = subscription_dict.get("id")
            run = subscription_dict.get("run") or subscription_dict.get("handler")
            if not subscription_id or not isinstance(subscription_id, str):
                raise ValueError("agent event subscription requires a non-empty 'id'")
            if run is not None and not callable(run):
                raise ValueError("agent event subscription 'run' must be callable when provided")
            payload: dict[str, Any] = dict(subscription_dict)
        else:
            subscription_id = getattr(subscription, "id", None)
            run = getattr(subscription, "run", None) or getattr(subscription, "handler", None)
            if not subscription_id or not isinstance(subscription_id, str):
                raise ValueError("agent event subscription requires a non-empty 'id'")
            if run is not None and not callable(run):
                raise ValueError("agent event subscription 'run' must be callable when provided")
            payload: dict[str, Any] = {"id": subscription_id, "run": run}
        payload["_owner_id"] = self._ctx.plugin_id
        self._agent_event_subscriptions.append(payload)

    def register_memory_embedding_provider(self, provider: dict[str, Any] | Any) -> None:
        """Register a memory embedding-provider adapter at the API boundary."""
        if isinstance(provider, dict):
            provider_dict = cast(dict[str, Any], provider)
            provider_id = provider_dict.get("id")
            adapter = provider_dict.get("provider")
            if not provider_id or not isinstance(provider_id, str):
                raise ValueError("memory embedding provider requires a non-empty 'id'")
            payload: dict[str, Any] = dict(provider_dict)
        else:
            provider_id = getattr(provider, "id", None)
            adapter = getattr(provider, "provider", None)
            if not provider_id or not isinstance(provider_id, str):
                raise ValueError("memory embedding provider requires a non-empty 'id'")
            payload: dict[str, Any] = {"id": provider_id, "provider": adapter}
        payload["_owner_id"] = self._ctx.plugin_id
        self._memory_embedding_providers.append(payload)

    def register_conversation_binding_resolved_handler(self, handler: dict[str, Any] | Any) -> None:
        """Register a conversation-binding resolved handler through the OpenClaw API contract."""
        if isinstance(handler, dict):
            handler_dict = cast(dict[str, Any], handler)
            handler_id = handler_dict.get("id")
            cb = handler_dict.get("handler")
            if not handler_id or not isinstance(handler_id, str):
                raise ValueError("conversation binding resolved handler requires a non-empty 'id'")
            if cb is not None and not callable(cb):
                raise ValueError("conversation binding resolved handler 'handler' must be callable when provided")
            payload: dict[str, Any] = dict(handler_dict)
        else:
            handler_id = getattr(handler, "id", None)
            cb = getattr(handler, "handler", None)
            if not handler_id or not isinstance(handler_id, str):
                raise ValueError("conversation binding resolved handler requires a non-empty 'id'")
            if cb is not None and not callable(cb):
                raise ValueError("conversation binding resolved handler 'handler' must be callable when provided")
            payload: dict[str, Any] = {"id": handler_id, "handler": cb}
        payload["_owner_id"] = self._ctx.plugin_id
        self._conversation_binding_resolved_handlers.append(payload)

    def register_doctor_contract(self, contract: dict[str, Any]) -> None:
        """Register a doctor / migration contract."""
        contract["_owner_id"] = self._ctx.plugin_id
        self._doctor_contracts.append(contract)

    def register_http_handler(self, handler: dict[str, Any] | Any) -> None:
        """Register an HTTP handler for the gateway's admin surface."""
        if isinstance(handler, dict):
            handler_dict = cast(dict[str, Any], handler)
            if "path" not in handler_dict or "handler" not in handler_dict:
                raise ValueError(f"http route missing required keys (path, handler): {handler!r}")
            payload: dict[str, Any] = dict(handler_dict)
            payload["_owner_id"] = self._ctx.plugin_id
            self._http_handlers.append(payload)
        else:
            path = getattr(handler, "path", None)
            cb = getattr(handler, "handler", None)
            if not path or not callable(cb):
                raise ValueError(f"http route missing path/handler: {handler!r}")
            self._http_handlers.append(
                {
                    "path": path,
                    "handler": cb,
                    "auth": getattr(handler, "auth", "gateway"),
                    "match": getattr(handler, "match", "exact"),
                    "_owner_id": self._ctx.plugin_id,
                }
            )

    def register_http_route(self, route: dict[str, Any] | Any) -> None:
        """Alias for ``register_http_handler`` for OpenClaw compatibility."""
        self.register_http_handler(route)

    def register_text_transforms(self, transform: dict[str, Any] | Any) -> None:
        """Alias for ``register_text_transform`` for OpenClaw compatibility."""
        self.register_text_transform(transform)

    def register_typed_hook(
        self,
        name_or_descriptor: str | dict[str, Any],
        handler: Callable[..., Any] | None = None,
        *,
        priority: int = 0,
        timeout_ms: int | None = None,
    ) -> None:
        """Compatibility alias for OpenClaw's ``registerTypedHook``."""
        if isinstance(name_or_descriptor, dict):
            name_or_descriptor_dict = cast(dict[str, Any], name_or_descriptor)
            descriptor = name_or_descriptor_dict
            name = descriptor.get("name")
            handler = descriptor.get("handler")
            priority = descriptor.get("priority", priority)
            timeout_ms = descriptor.get("timeoutMs", descriptor.get("timeout_ms", timeout_ms))
        else:
            name = name_or_descriptor
        if not isinstance(name, str) or not name:
            raise ValueError("typed hook must include a non-empty 'name'")
        if handler is None or not callable(handler):
            raise ValueError("typed hook must include a callable 'handler'")
        self.register_hook(name, handler, priority=priority, timeout_ms=timeout_ms)

    def register_model_catalog_provider(self, record: Any, provider: Any) -> None:
        """Register a model catalog provider for OpenClaw compatibility."""
        payload: dict[str, Any] = {
            "record": record,
            "provider": provider,
            "_owner_id": self._ctx.plugin_id,
        }
        self._model_catalog_providers.append(payload)

    def register_agent_tool_result_middleware(self, middleware: dict[str, Any] | Any) -> None:
        """Register agent tool result middleware for OpenClaw compatibility."""
        if isinstance(middleware, dict):
            middleware_dict = cast(dict[str, Any], middleware)
            middleware_id = middleware_dict.get("id")
            handler = middleware_dict.get("handler") or middleware_dict.get("run")
            if not middleware_id or not isinstance(middleware_id, str):
                raise ValueError("agent tool result middleware requires a non-empty 'id'")
        else:
            middleware_id = getattr(middleware, "id", None)
            handler = getattr(middleware, "handler", None) or getattr(middleware, "run", None)
            if not middleware_id or not isinstance(middleware_id, str):
                raise ValueError("agent tool result middleware requires a non-empty 'id'")
        if handler is not None and not callable(handler):
            raise ValueError("agent tool result middleware 'handler' must be callable when provided")
        payload: dict[str, Any] = {
            "id": middleware_id,
            "handler": handler,
            "_owner_id": self._ctx.plugin_id,
        }
        self._agent_tool_result_middlewares.append(payload)

    def register_skill(self, skill: SkillDecl) -> None:
        """Register a declarative skill (markdown frontmatter + body)."""
        if not skill.name or not skill.description:
            raise ValueError(
                f"SkillDecl must have non-empty name and description; "
                f"got name={skill.name!r}, description={skill.description!r}"
            )
        self._skills.append(skill)

    def register_hook(
        self,
        name: str,
        handler: Callable[..., Any],
        *,
        priority: int = 0,
        timeout_ms: int | None = None,
    ) -> None:
        """Register a hook handler for the named event."""
        if not callable(handler):
            raise TypeError(
                f"Hook handler for {name!r} must be callable; " f"got {type(handler).__name__}"
            )
        from .hook import HookRegistration

        self._hooks.append(
            HookRegistration(
                name=name,
                handler=handler,
                priority=priority,
                timeout_ms=timeout_ms,
            )
        )

    def register_cron(self, job: CronDecl) -> None:
        """Register a scheduled job (cron expression or one-shot)."""
        if not job.id or not job.schedule or not callable(job.handler):
            raise ValueError(
                f"CronDecl must have id, schedule, and callable handler; "
                f"got id={job.id!r}, schedule={job.schedule!r}"
            )
        self._cron_jobs.append(job)

    def register_gateway_discovery_service(self, service: dict[str, Any]) -> None:
        """Register a gateway discovery service (mDNS / Bonjour / etc.)."""
        if not isinstance(service, dict):
            raise TypeError(
                f"gateway discovery service must be a dict; got {type(service).__name__}"
            )
        if "id" not in service or not service["id"]:
            raise ValueError("gateway discovery service must have a non-empty 'id'")
        if "advertise" not in service or not callable(service["advertise"]):
            raise ValueError(
                "gateway discovery service must have a callable 'advertise' "
                "(async function taking ctx and returning a stop handle)"
            )
        if self._gateway_discovery_service is not None:
            raise RuntimeError(
                f"Plugin {self._ctx.plugin_id!r} tried to register a gateway "
                f"discovery service but {self._gateway_discovery_service.get('id')!r} "
                f"is already registered. Only one discovery backend is supported."
            )
        service["_owner_id"] = self._ctx.plugin_id
        self._gateway_discovery_service = service

    def register_media_understanding_provider(
        self, provider: MediaUnderstandingProvider | dict[str, Any]
    ) -> None:
        """Register a media-understanding provider (audio/image/video)."""
        if isinstance(provider, dict):
            provider_dict = cast(dict[str, Any], provider)
            provider_dict = cast(dict[str, Any], provider)
            provider_dict = cast(dict[str, Any], provider)
            provider_id = provider_dict.get("id")
            capabilities = provider_dict.get("capabilities", [])
            if not provider_id:
                raise ValueError("media understanding provider must have a non-empty 'id'")
            provider_obj: dict[str, Any] = {
                "id": provider_id,
                "capabilities": list(capabilities),
                "default_models": dict(provider_dict.get("default_models", {})),
                "auto_priority": dict(provider_dict.get("auto_priority", {})),
                "transcribe_audio": provider_dict.get("transcribe_audio"),
                "metadata": dict(provider_dict.get("metadata", {})),
            }
        else:
            provider_value = cast(Any, provider)
            provider_id = getattr(provider_value, "id", None)
            if not provider_id:
                raise ValueError("media understanding provider must have a non-empty 'id'")
            provider_obj = {
                "id": provider_id,
                "capabilities": list(getattr(provider_value, "capabilities", [])),
                "default_models": dict(getattr(provider_value, "default_models", {})),
                "auto_priority": dict(getattr(provider_value, "auto_priority", {})),
                "transcribe_audio": getattr(provider_value, "transcribe_audio", None),
                "metadata": dict(getattr(provider_value, "metadata", {})),
            }
        for existing in self._media_understanding_providers:
            if existing["id"] == provider_id:
                raise RuntimeError(
                    f"Plugin {self._ctx.plugin_id!r} tried to register media "
                    f"understanding provider {provider_id!r} but it's already "
                    f"registered by {existing.get('_owner_id')!r}."
                )
        provider_obj["_owner_id"] = self._ctx.plugin_id
        self._media_understanding_providers.append(provider_obj)

