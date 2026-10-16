"""jarvis.agents.embedded_agent_runner.compaction_harness_model_provider — harness model provider.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/compaction-harness-model-provider.ts``.

Public surface (mirrors the OpenClaw
source):

- :func:`build_compaction_harness_model_provider` —
  build the harness-prepared model
  provider for compaction.

Phase 7.2a — focused minimal port.
The full integration with the
agent-harness selection helpers
lands in 7.2b+ (when
:mod:`agent_harness.support` is
ported)."""
from __future__ import annotations

from typing import Optional


def build_compaction_harness_model_provider(
    model: Optional[dict] = None,
    plan: Optional[dict] = None,
    attempt: Optional[dict] = None,
) -> dict:
    """Build the harness-prepared
    model provider for compaction.
    Mirrors
    :func:`buildCompactionHarnessModelProvider`
    (``compaction-harness-model-provider.ts:10-28`).

    Phase 7.2a — focused minimal
    port: the OpenClaw source's
    ``resolveAgentHarnessPreparedRouteSupport``
    +
    ``resolveAgentHarnessPreparedAuthSupport``
    helpers land in 7.2b+.

    Returns a dict with:
    - ``api``: the API identifier
      (from the model route or
      model).
    - ``baseUrl``: the base URL
      (from the model route or
      model).
    - ``preparedAuth``: the
      prepared auth (only when a
      ``plan`` is provided).
    """
    route = (plan or {}).get("modelRoute") if isinstance(
        plan, dict
    ) else None
    if not isinstance(route, dict):
        route = {}
    model_dict = (
        model if isinstance(model, dict) else {}
    )
    result: dict = {}
    api = route.get("api")
    if api is None:
        api = model_dict.get("api")
    if api is not None:
        result["api"] = api
    base_url = route.get("baseUrl")
    if base_url is None:
        base_url = model_dict.get("baseUrl")
    if base_url is not None:
        result["baseUrl"] = base_url
    if isinstance(plan, dict):
        # Phase 7.2a — STUB. The
        # ``resolveAgentHarnessPreparedAuthSupport``
        # helper lands in 7.2b+ (the
        # auth support module
        # depends on the agent
        # harness selection).
        attempt_kind = (
            attempt.get("kind") if isinstance(attempt, dict) else None
        )
        result["preparedAuth"] = {
            "source": (
                None
                if attempt_kind == "implicit"
                else attempt_kind
            ),
        }
    return result


__all__ = ["build_compaction_harness_model_provider"]
