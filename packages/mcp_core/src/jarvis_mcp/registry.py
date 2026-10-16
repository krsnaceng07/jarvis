"""MCP Registry for JARVIS.

Manages connections to MCP servers defined in configuration.
"""

import logging
from typing import Any, Dict, List, Optional
import fnmatch

from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.sse import sse_client
from jarvis_config_core import JarvisConfig, McpServerConfig

logger = logging.getLogger("jarvis.mcp_core.registry")


class McpServerConnection:
    """A managed connection to an MCP server."""

    def __init__(self, name: str, config: McpServerConfig):
        self.name = name
        self.config = config
        self._session: Optional[ClientSession] = None
        self._exit_stack = None

    async def connect(self):
        """Establish the connection to the MCP server."""
        if self._session:
            return

        from contextlib import AsyncExitStack

        self._exit_stack = AsyncExitStack()

        if self.config.transport == "stdio":
            if not self.config.command:
                raise ValueError(f"Server {self.name} missing 'command' for stdio transport")

            server_params = StdioServerParameters(
                command=self.config.command,
                args=self.config.args or [],
                env=self.config.env or None,
            )
            # Use enter_async_context instead of yielding
            read, write = await self._exit_stack.enter_async_context(stdio_client(server_params))

        elif self.config.transport in ("sse", "streamable-http"):
            if not self.config.url:
                raise ValueError(
                    f"Server {self.name} missing 'url' for {self.config.transport} transport"
                )
            read, write = await self._exit_stack.enter_async_context(sse_client(self.config.url))
        else:
            raise ValueError(f"Unknown transport {self.config.transport} for {self.name}")

        self._session = await self._exit_stack.enter_async_context(ClientSession(read, write))
        assert self._session is not None
        await self._session.initialize()
        logger.info(f"Connected to MCP server {self.name}")

    async def get_tools(self) -> List[Any]:
        """Fetch tools from the connected MCP server, applying filters."""
        if not self._session:
            await self.connect()

        if not self._session:
            return []

        response = await self._session.list_tools()
        tools = response.tools

        filtered = []
        for tool in tools:
            # apply include/exclude
            if _matches_filter(tool.name, self.config.toolFilter):
                filtered.append(tool)
        return filtered

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        if not self._session:
            await self.connect()
        if not self._session:
            raise RuntimeError(f"Server {self.name} not connected")

        return await self._session.call_tool(tool_name, arguments)

    async def close(self):
        if self._exit_stack:
            await self._exit_stack.aclose()
            self._session = None
            self._exit_stack = None


def _matches_filter(tool_name: str, tool_filter) -> bool:
    """Matches tool name against include/exclude patterns."""
    if not tool_filter:
        return True

    if tool_filter.exclude:
        for ex in tool_filter.exclude:
            if fnmatch.fnmatch(tool_name, ex):
                return False

    if tool_filter.include:
        matched = False
        for inc in tool_filter.include:
            if fnmatch.fnmatch(tool_name, inc):
                matched = True
                break
        if not matched:
            return False

    return True


class McpRegistry:
    """Registry holding all MCP servers."""

    def __init__(self, config: JarvisConfig):
        self.config = config
        self.servers: Dict[str, McpServerConnection] = {}
        self._init_servers()

    def _init_servers(self):
        mcp_config = self.config.mcp
        if not mcp_config or not mcp_config.servers:
            return

        for name, srv_config in mcp_config.servers.items():
            if srv_config.enabled:
                if srv_config.transport == "stdio" and not srv_config.command:
                    logger.warning(f"MCP server {name} is enabled but missing 'command'; skipping")
                    continue
                self.servers[name] = McpServerConnection(name, srv_config)

    async def get_all_tools(self) -> List[tuple[str, Any]]:
        """Returns a list of (server_name, tool) tuples across all servers."""
        all_tools = []
        # In a real environment, we might do this concurrently
        for name, conn in self.servers.items():
            try:
                tools = await conn.get_tools()
                for t in tools:
                    all_tools.append((name, t))
            except Exception as e:
                logger.warning(f"Failed to fetch tools from MCP server {name}: {e}")

        return all_tools

    async def call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> Any:
        conn = self.servers.get(server_name)
        if not conn:
            raise ValueError(f"MCP server {server_name} not found")

        return await conn.call_tool(tool_name, arguments)

    async def close_all(self):
        for conn in self.servers.values():
            try:
                await conn.close()
            except Exception as e:
                logger.error(f"Error closing {conn.name}: {e}")
