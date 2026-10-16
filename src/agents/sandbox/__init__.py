"""jarvis.agents.sandbox — OpenClaw-parity sandbox subsystems."""

from src.config.sandbox_config import (
    BrowserSandboxConfig,
    DockerSandboxConfig,
    SandboxBackend,
    SandboxConfig,
    SandboxMode,
    SandboxScope,
    SandboxWorkspaceAccess,
    resolve_sandbox_config,
)
from .context import (
    SandboxContext,
    is_main_session_key,
    resolve_sandbox_context,
    sanitize_identifier_for_container,
)
from .docker_backend import (
    ensure_sandbox_container,
    exec_in_sandbox,
    is_container_engine_available,
    is_container_running,
    translate_path_to_sandbox,
)
from .elevated import evaluate_elevated_execution
from .environment import (
    is_sensitive_env_key,
    sanitize_execution_environment,
)
from .filesystem_guard import (
    guard_sandbox_tool_access,
    is_path_contained,
    resolve_deepest_existing_ancestor,
    validate_sandbox_path,
)
from .process_job import ProcessTreeContainment
from .tool_policy import (
    TOOL_GROUPS,
    evaluate_sandbox_tool_policy,
    expand_tool_policy_items,
)

__all__ = [
    "BrowserSandboxConfig",
    "DockerSandboxConfig",
    "ProcessTreeContainment",
    "SandboxBackend",
    "SandboxConfig",
    "SandboxContext",
    "SandboxMode",
    "SandboxScope",
    "SandboxWorkspaceAccess",
    "TOOL_GROUPS",
    "ensure_sandbox_container",
    "evaluate_elevated_execution",
    "evaluate_sandbox_tool_policy",
    "exec_in_sandbox",
    "expand_tool_policy_items",
    "guard_sandbox_tool_access",
    "is_container_engine_available",
    "is_container_running",
    "is_main_session_key",
    "is_path_contained",
    "is_sensitive_env_key",
    "resolve_deepest_existing_ancestor",
    "resolve_sandbox_config",
    "resolve_sandbox_context",
    "sanitize_execution_environment",
    "sanitize_identifier_for_container",
    "translate_path_to_sandbox",
    "validate_sandbox_path",
]
