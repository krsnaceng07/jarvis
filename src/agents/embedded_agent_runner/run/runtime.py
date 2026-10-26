"""jarvis.agents.embedded_agent_runner.run.runtime — prepare embedded run runtime wrapper.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/runtime.ts``.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from .runtime_preparation import prepare_embedded_run_runtime as _prepare_transport

_LOG = logging.getLogger("jarvis.agents.embedded_agent_runner.run.runtime")


class PreparedEmbeddedRuntime:
    """Prepared embedded run runtime container."""

    def __init__(self, initial_data: Dict[str, Any], run_params: Dict[str, Any]) -> None:
        self._data = dict(initial_data)
        self.run_params = run_params
        self.provider = initial_data.get("provider") or run_params.get("provider") or "default"
        self.model_id = initial_data.get("modelId") or run_params.get("model") or "default"
        self.requested_model_id = self.model_id
        self.model = initial_data.get("runtimeModel") or {}
        self.profile_candidates: list[Any] = []
        self.plugin_harness_owns_auth_bootstrap = False
        self.attempted_thinking: set[str] = set()
        self.attempt_auth_profile_store: Dict[str, Any] = {}
        self.profile_failure_store: Dict[str, Any] = {}
        self.admitted_run_context: Dict[str, Any] = run_params.get("admittedRunContext") or {}

    def snapshot(self) -> Dict[str, Any]:
        return {
            **self._data,
            "provider": self.provider,
            "modelId": self.model_id,
            "agentHarness": self._data.get("agentHarness") or {"id": "openclaw", "deliveryDefaults": None},
            "effectiveModel": self._data.get("runtimeModel") or {},
            "thinkLevel": self._data.get("initialThinkLevel") or "off",
            "outerContextTokenMeta": {},
            "lastProfileId": None,
            "pluginHarnessOwnsTransport": False,
            "providerRuntimeHandle": type("PluginHandle", (), {"plugin": "core"})(),
            "activePreparedAuthPlan": type("AuthPlan", (), {"credentialSource": None, "modelRoute": None, "deferredRouteSupport": None})(),
        }

    def get_api_key_info(self) -> Optional[Dict[str, Any]]:
        return None

    def advance_attempt_auth_profile(self) -> None:
        pass

    def stop_runtime_auth_refresh_timer(self) -> None:
        pass

    async def release_transport(self) -> None:
        self.stop_runtime_auth_refresh_timer()

    def set_think_level(self, level: str) -> None:
        self._data["initialThinkLevel"] = level


async def prepare_embedded_run_runtime(input_obj: Dict[str, Any]) -> PreparedEmbeddedRuntime:
    """Prepares the embedded run runtime.
    Mirrors prepareEmbeddedRunRuntime in OpenClaw run/runtime.ts.
    """
    initial = await _prepare_transport(input_obj)
    run_params = input_obj.get("runParams") or {}
    return PreparedEmbeddedRuntime(initial, run_params)


__all__ = [
    "PreparedEmbeddedRuntime",
    "prepare_embedded_run_runtime",
]
