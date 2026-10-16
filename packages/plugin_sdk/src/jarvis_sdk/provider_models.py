"""Provider-owned model route facts (no credential precedence).

Mirrors OpenClaw's ``src/plugin-sdk/provider-model-types.ts``.
Route order expresses the provider default, never credential
precedence; authored ``agentRuntime`` policy stays authoritative
and route ``default_runtime_id`` values are advisory only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Union

#: Credential requirement for one concrete route (secret-free fact).
ProviderModelRouteAuthRequirement = Literal["api-key", "subscription"]

#: Secret-free summary of request behavior the runtime must reproduce.
ProviderRouteOverridePresence = Literal["none", "present"]


@dataclass(frozen=True, slots=True)
class ProviderModelRouteRuntimePolicy:
    """Agent runtime ids that reproduce this route without losing transport behavior."""

    compatible_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ProviderModelRouteCandidate:
    """One concrete provider route for a logical model."""

    api: str = ""
    base_url: str = ""
    auth_requirement: ProviderModelRouteAuthRequirement = "api-key"
    request_transport_overrides: ProviderRouteOverridePresence = "none"
    runtime_policy: ProviderModelRouteRuntimePolicy | None = None


@dataclass(frozen=True, slots=True)
class RoutesResolution:
    """One or more concrete routes, first entry is the provider default."""

    kind: Literal["routes"] = "routes"
    routes: tuple[ProviderModelRouteCandidate, ...] = field(default_factory=tuple)
    default_runtime_id: str | None = None

    def __post_init__(self) -> None:
        # TS type is a non-empty tuple; an empty `routes` kind is unresolvable.
        if not self.routes:
            raise ValueError("RoutesResolution requires at least one route")


@dataclass(frozen=True, slots=True)
class IndeterminateResolution:
    """Route facts absent; preserves the provider's implicit runtime."""

    kind: Literal["indeterminate"] = "indeterminate"
    default_runtime_id: str | None = None


@dataclass(frozen=True, slots=True)
class IncompatibleResolution:
    """No usable route; carries a closed code plus human message."""

    kind: Literal["incompatible"] = "incompatible"
    code: str = ""
    message: str = ""


#: Discriminated union over every route-resolution outcome.
ProviderModelRouteResolution = Union[
    RoutesResolution, IndeterminateResolution, IncompatibleResolution
]


@dataclass(frozen=True, slots=True)
class ProviderResolveModelRoutesContext:
    """Secret-free inputs for resolving one provider/model pair.

    Mirrors ``ProviderResolveModelRoutesContext``: the provider owns
    interpretation of ``env``; ``observedRoutes`` carries physical
    route facts whose input order is not preference.
    """

    provider: str = ""
    model_id: str | None = None
    request_transport_overrides: ProviderRouteOverridePresence = "none"
    configured_model: dict[str, Any] | None = None
    configured_provider: dict[str, Any] | None = None
    env: dict[str, str | None] | None = None
    observed_routes: tuple[dict[str, Any], ...] = field(default_factory=tuple)


__all__ = [
    "IncompatibleResolution",
    "IndeterminateResolution",
    "ProviderModelRouteAuthRequirement",
    "ProviderModelRouteCandidate",
    "ProviderModelRouteResolution",
    "ProviderModelRouteRuntimePolicy",
    "ProviderResolveModelRoutesContext",
    "ProviderRouteOverridePresence",
    "RoutesResolution",
]
