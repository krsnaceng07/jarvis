from typing import Any, Callable, Dict, List, Optional

# We reuse the types defined in code_mode_worker.py
from .code_mode_worker import (
    CodeModeNamespaceDescriptor,
)


class CodeModeNamespaceRuntime:
    """Runtime dispatcher for invoking callable namespace paths."""

    def __init__(
        self, descriptors: List[CodeModeNamespaceDescriptor], dispatch_hooks: Dict[str, Any]
    ):
        self.descriptors = descriptors
        self.dispatch_hooks = dispatch_hooks

    async def invoke(
        self,
        namespace_id: str,
        path: List[str],
        args: List[Any],
        execute_tool: Callable[..., Any],
    ) -> Any:
        # In this Python port, we route namespace calls back to execute_tool.
        # A more complete port would resolve the namespace_id and path to the
        # actual registered CodeModeNamespaceScope function.
        # For parity, we forward it to the provided execute_tool.

        # Example logic mapping path to a tool name, based on dispatch_hooks
        tool_name = "_".join([namespace_id] + path)
        return await execute_tool(
            {
                "namespaceId": namespace_id,
                "path": path,
                "toolName": tool_name,
                "input": args,
            }
        )


def describe_code_mode_namespaces_for_prompt(runtime: CodeModeNamespaceRuntime) -> Optional[str]:
    """Return a markdown-formatted description of the available code mode namespaces."""
    if not runtime.descriptors:
        return None

    lines = []
    for desc in runtime.descriptors:
        lines.append(f"- `{desc['globalName']}`: {desc.get('description', '')}")
        # Note: could recursively format the scope if needed

    return "\n".join(lines)


def create_code_mode_namespace_runtime(ctx: Any) -> CodeModeNamespaceRuntime:
    """Build the runtime containing all registered namespaces available in this context."""
    # This is a stub that should gather from a global registry
    return CodeModeNamespaceRuntime([], {})
