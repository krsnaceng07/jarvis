"""jarvis.agents.openai_model_routes — provider-owned OpenAI route facts (cold).

OpenClaw parity: mirrors ``openclaw-main/src/agents/openai-model-routes.ts``.

Thin core adapter over the owner-side policy
(``extensions/openai/route_policy.py``). Route ownership stays in the
provider artifact; this module only shapes the call. The owner import is
lazy so runtime selection never pays provider-runtime import cost.
"""

from __future__ import annotations

from typing import Any


def _normalize_provider_id(provider: Any) -> str:
    return provider.strip().lower() if isinstance(provider, str) else ""


def _split_auth_profile(model_id: Any) -> Any:
    """Strip a trailing ``:auth-profile`` suffix. Mirrors splitTrailingAuthProfile."""
    if not isinstance(model_id, str):
        return model_id
    # Auth profiles attach after the last colon only when a non-empty
    # profile follows; model ids themselves never contain colons.
    head, sep, tail = model_id.rpartition(":")
    if sep and head.strip() and tail.strip() and "/" not in tail:
        return head
    return model_id


def create_openai_model_routes_resolver(params: dict[str, Any]) -> Any:
    """Build a reusable OpenAI route resolver over one authored config view.

    Mirrors ``createOpenAIModelRoutesResolver``.
    """
    from extensions.openai.route_policy import create_model_routes_resolver  # noqa: PLC0415

    resolve_routes = create_model_routes_resolver(
        {
            "provider": "openai",
            "config": params.get("config"),
            "env": params.get("env"),
            "requestTransportOverrides": params.get("requestTransportOverrides"),
        }
    )

    def _resolve(observed: dict[str, Any] | None = None) -> dict[str, Any] | None:
        observed = observed or {}
        api = observed.get("api")
        base_url = observed.get("baseUrl")
        return resolve_routes(
            {
                **(
                    {"modelId": _split_auth_profile(observed.get("modelId"))}
                    if observed.get("modelId")
                    else {}
                ),
                **(
                    {"observedRoutes": [{"api": api, "baseUrl": base_url}]}
                    if api is not None or base_url is not None
                    else {}
                ),
            }
        )

    return _resolve


def resolve_openai_model_routes(params: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve provider-owned OpenAI route state without provider runtime.

    Mirrors ``resolveOpenAIModelRoutes``. Returns ``None`` for non-OpenAI
    providers.
    """
    if _normalize_provider_id(params.get("provider") or "") != "openai":
        return None
    resolve_routes = create_openai_model_routes_resolver(
        {
            "config": params.get("config"),
            "env": params.get("env"),
            "requestTransportOverrides": params.get("requestTransportOverrides"),
        }
    )
    api = params.get("api")
    base_url = params.get("baseUrl")
    return resolve_routes(
        {
            **({"modelId": params.get("modelId")} if params.get("modelId") else {}),
            **(
                {"observedRoutes": [{"api": api, "baseUrl": base_url}]}
                if api is not None or base_url is not None
                else {}
            ),
        }
    )


__all__ = ["create_openai_model_routes_resolver", "resolve_openai_model_routes"]
