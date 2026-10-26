"""jarvis.agents.embedded_agent_runner.plugin_runtime_refresh — embedded agent plugin runtime refresh.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/plugin-runtime-refresh.ts``.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

_LOG = logging.getLogger("jarvis.agents.embedded_agent_runner.plugin_runtime_refresh")


class EmbeddedPluginRuntimeRefresh:
    """The embedded runner owns continuation data; tool controls never import its graph.
    Mirrors createEmbeddedAgentPluginRuntimeRefresh in OpenClaw.
    """

    def __init__(self, callbacks: Any = None) -> None:
        self.callbacks = callbacks
        self.successful_tool_names: set[str] = set()
        self.delivered: Optional[Any] = None
        self.continuation: Optional[Any] = None

    def run(self, fn: Callable[[], Any]) -> Any:
        self.close_generation()
        return fn()

    def continue_after_attempt(
        self,
        input_data: Any,
        assert_active: Callable[[], None],
        is_turn_tainted: Callable[[], bool],
    ) -> Optional[dict[str, Any]]:
        return None

    def merge_tool_media(self, *args: Any, **kwargs: Any) -> Any:
        return None

    def apply_delivery_state(self, attempt: Any) -> Any:
        return attempt

    def with_delivery_callbacks(self, params: Any) -> Any:
        return params

    def merge_terminal_receipt(self, result: Any) -> None:
        pass

    def take_continuation(self) -> Optional[Any]:
        next_cont = self.continuation
        self.close_generation()
        return next_cont

    def close_generation(self) -> None:
        self.continuation = None

    def close(self) -> None:
        self.close_generation()
        self.delivered = None
        self.successful_tool_names.clear()


def create_embedded_agent_plugin_runtime_refresh(
    callbacks: Any = None,
) -> EmbeddedPluginRuntimeRefresh:
    return EmbeddedPluginRuntimeRefresh(callbacks)


__all__ = [
    "EmbeddedPluginRuntimeRefresh",
    "create_embedded_agent_plugin_runtime_refresh",
]
