"""src.agents.subagents — Canonical OpenClaw-parity multi-agent and subagent runtime.

Exports:
- Types & Enums: SubagentRole, SubagentStatus, SubagentSpawnContextMode, SubagentRunRecord, SpawnSubagentParams, SpawnSubagentResult
- Registry: SubagentRegistry
- Capabilities: resolve_subagent_role, can_spawn_subagents, can_control_children, filter_tools_for_subagent, DEFAULT_SUBAGENT_MAX_SPAWN_DEPTH
- Spawner: SubagentSpawner
- Runner: SubagentRunner
- Completion: SubagentCompletionHandler, build_child_completion_findings, wrap_prompt_data_block
- Orchestrator: MultiAgentOrchestrator, OrchestrationMode, SubtaskDefinition
- Control: SubagentController
"""

from .capabilities import (
    DEFAULT_LEAF_ALLOWED_TOOLS,
    DEFAULT_SUBAGENT_MAX_SPAWN_DEPTH,
    LEAF_DENIED_TOOLS,
    SUBAGENT_DELEGATION_TOOLS,
    can_control_children,
    can_spawn_subagents,
    filter_tools_for_subagent,
    resolve_subagent_role,
)
from .completion import (
    SubagentCompletionHandler,
    build_child_completion_findings,
    describe_subagent_outcome,
    wrap_prompt_data_block,
)
from .control import SubagentController
from .orchestrator import (
    MultiAgentOrchestrator,
    OrchestrationMode,
    SubtaskDefinition,
)
from .registry import SubagentRegistry
from .spawner import SubagentSpawner, normalize_task_name
from .runner import SubagentRunner
from .types import (
    SpawnSubagentParams,
    SpawnSubagentResult,
    SubagentRole,
    SubagentRunRecord,
    SubagentSpawnContextMode,
    SubagentStatus,
)

__all__ = [
    "DEFAULT_LEAF_ALLOWED_TOOLS",
    "DEFAULT_SUBAGENT_MAX_SPAWN_DEPTH",
    "LEAF_DENIED_TOOLS",
    "SUBAGENT_DELEGATION_TOOLS",
    "MultiAgentOrchestrator",
    "OrchestrationMode",
    "SpawnSubagentParams",
    "SpawnSubagentResult",
    "SubagentCompletionHandler",
    "SubagentController",
    "SubagentRegistry",
    "SubagentRole",
    "SubagentRunRecord",
    "SubagentRunner",
    "SubagentSpawner",
    "SubagentSpawnContextMode",
    "SubagentStatus",
    "SubtaskDefinition",
    "build_child_completion_findings",
    "can_control_children",
    "can_spawn_subagents",
    "describe_subagent_outcome",
    "filter_tools_for_subagent",
    "normalize_task_name",
    "resolve_subagent_role",
    "wrap_prompt_data_block",
]
