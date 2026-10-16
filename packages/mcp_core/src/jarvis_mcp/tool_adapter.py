"""Adapter for MCP tools to JARVIS AgentTools."""

from typing import Any, Optional

from mcp.types import Tool as McpTool


def adapt_mcp_tool(server_name: str, mcp_tool: McpTool, registry: Any) -> dict:
    """Wraps an MCP tool as a JARVIS ToolDefinition dictionary."""

    async def _execute(
        tool_call_id: str,
        params: dict,
        signal: Optional[Any] = None,
        on_update: Optional[Any] = None,
        ctx: Optional[Any] = None,
    ) -> Any:
        if signal and getattr(signal, "is_set", lambda: False)():
            raise RuntimeError("Aborted before execution")

        if on_update:
            from jarvis_agent.types import AgentToolProgress

            await on_update(AgentToolProgress(text=f"Calling MCP tool {mcp_tool.name}..."))

        response = await registry.call_tool(server_name, mcp_tool.name, params)

        if signal and getattr(signal, "is_set", lambda: False)():
            raise RuntimeError("Aborted during execution")

        is_error = getattr(response, "isError", getattr(response, "is_error", False))

        content_parts = []
        for c in response.content:
            if c.type == "text":
                content_parts.append(c.text)
            elif c.type == "resource":
                content_parts.append(f"[Resource {c.resource.uri}]")
            else:
                content_parts.append(f"[Media {c.type}]")

        final_content = "\n".join(content_parts)

        if is_error:
            raise RuntimeError(f"MCP Tool Error: {final_content}")

        from jarvis_agent.types import AgentToolResult
        from jarvis_llm.types import TextContent

        return AgentToolResult(
            content=[TextContent(text=final_content)],
            details={"mcp_response": [c.model_dump() for c in response.content]},
        )

    def _prepare(args: Any) -> dict:
        return args if isinstance(args, dict) else {}

    return {
        "name": f"mcp_{server_name}_{mcp_tool.name}",
        "label": f"MCP: {server_name}/{mcp_tool.name}",
        "description": mcp_tool.description or f"MCP tool from {server_name}",
        "parameters": getattr(
            mcp_tool,
            "inputSchema",
            getattr(mcp_tool, "input_schema", {"type": "object", "properties": {}}),
        ),
        "outputSchema": None,
        "prepareArguments": _prepare,
        "execute": _execute,
        "hideFromChannelProgress": False,
        "promptSnippet": "",
        "promptGuidelines": [],
    }
