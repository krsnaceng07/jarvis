"""jarvis.agents.embedded_agent_runner.run.execution_context — prepared-run input.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/execution-context.ts``.

Public surface (mirrors the OpenClaw
source):

- :data:`PreparedEmbeddedRunInput` —
  the input shape for
  :func:`run_prepared_embedded_loop`
  (the orchestrator prepares this
  before invoking the loop).

Phase 7.1 — focused minimal port.
The OpenClaw source uses ``ReturnType<...>``
for several fields (the loop stage
tracker, the lane controller, the
hook context, etc.); the Python
port uses plain :class:`dict` /
:class:`Any` for the same fields
(the typed shapes land in 7.2+)."""
from __future__ import annotations

from typing import Any, Optional

from .internal_params import RunEmbeddedAgentParamsWithSessionFile


#: The input shape for the
#: prepared-embedded-run loop.
#: Mirrors :class:`PreparedEmbeddedRunInput`
#: (``execution-context.ts:11-32``).
class PreparedEmbeddedRunInput:
    """The orchestrator prepares this
    object before invoking the
    loop. Mirrors
    :class:`PreparedEmbeddedRunInput`
    in :mod:`execution-context.ts`.
    """

    def __init__(
        self,
        run_params: RunEmbeddedAgentParamsWithSessionFile,
        provider: str,
        model_id: str,
        agent_dir: str,
        workspace_dir: str,
        is_canonical_workspace: bool = False,
        global_lane: str = "main",
        hook_context: Optional[Any] = None,
        fallback_configured: bool = False,
        is_probe_session: bool = False,
        resolved_session_key: str = "",
        resolved_tool_result_format: str = "markdown",
        started_at_ms: int = 0,
        lifecycle_generation: int = 0,
    ) -> None:
        self.run_params = run_params
        self.provider = provider
        self.model_id = model_id
        self.agent_dir = agent_dir
        # workspaceResolution is a
        # structured result from
        # ``resolveRunWorkspaceDir``
        # — we use a dict placeholder
        # for the focused minimal
        # port.
        self.workspace_resolution: dict = {}
        self.workspace_dir = workspace_dir
        self.is_canonical_workspace = is_canonical_workspace
        self.global_lane = global_lane
        # hookRunner is the result of
        # ``getGlobalHookRunner()`` —
        # we use ``None`` for the
        # focused minimal port.
        self.hook_runner: Any = None
        self.hook_context = hook_context
        self.fallback_configured = fallback_configured
        self.is_probe_session = is_probe_session
        self.resolved_session_key = resolved_session_key
        self.resolved_tool_result_format = (
            resolved_tool_result_format
        )
        self.started_at_ms = started_at_ms
        # startupStages is the result
        # of ``createEmbeddedRunStageTracker()``
        # — we use ``None`` for the
        # focused minimal port.
        self.startup_stages: Any = None
        # emitStartupStageSummary is a
        # callback that emits the
        # stage summary on completion
        # — we use ``None`` for the
        # focused minimal port.
        self.emit_startup_stage_summary: Optional[Any] = None
        # progressController is the
        # result of
        # ``createEmbeddedRunProgressController()``
        # — we use ``None`` for the
        # focused minimal port.
        self.progress_controller: Any = None
        # laneController is the result
        # of
        # ``createEmbeddedRunLaneController()``
        # — we use ``None`` for the
        # focused minimal port.
        self.lane_controller: Any = None
        self.lifecycle_generation = lifecycle_generation
        # suspendForFailure is a
        # callback that suspends the
        # session on a final failure
        # — we use ``None`` for the
        # focused minimal port.
        self.suspend_for_failure: Optional[Any] = None

    def to_dict(self) -> dict:
        """Serialize the input as a
        dict (for compatibility with
        the OpenClaw source's
        ``PreparedEmbeddedRunInput``
        type)."""
        return {
            "runParams": self.run_params,
            "provider": self.provider,
            "modelId": self.model_id,
            "agentDir": self.agent_dir,
            "workspaceResolution": self.workspace_resolution,
            "workspaceDir": self.workspace_dir,
            "isCanonicalWorkspace": self.is_canonical_workspace,
            "globalLane": self.global_lane,
            "hookRunner": self.hook_runner,
            "hookContext": self.hook_context,
            "fallbackConfigured": self.fallback_configured,
            "isProbeSession": self.is_probe_session,
            "resolvedSessionKey": self.resolved_session_key,
            "resolvedToolResultFormat": (
                self.resolved_tool_result_format
            ),
            "startedAtMs": self.started_at_ms,
            "startupStages": self.startup_stages,
            "emitStartupStageSummary": (
                self.emit_startup_stage_summary
            ),
            "progressController": self.progress_controller,
            "laneController": self.lane_controller,
            "lifecycleGeneration": self.lifecycle_generation,
            "suspendForFailure": self.suspend_for_failure,
        }


__all__ = ["PreparedEmbeddedRunInput"]
