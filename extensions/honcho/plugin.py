from typing import Any
from jarvis_sdk import ToolPlugin, ToolDecl, ToolParam
from jarvis_sdk import Result, Ok, Err
from .client import HonchoClient

HONCHO_CONTEXT_TOOL = ToolDecl(
    name="honcho_context", description="Full user representation across sessions.", parameters=[]
)

HONCHO_SEARCH_CONCLUSIONS_TOOL = ToolDecl(
    name="honcho_search_conclusions",
    description="Semantic search over stored conclusions.",
    parameters=[ToolParam(name="query", type="string", required=True, description="Search query.")],
)

HONCHO_SEARCH_MESSAGES_TOOL = ToolDecl(
    name="honcho_search_messages",
    description="Find messages across sessions (filter by sender, date).",
    parameters=[
        ToolParam(name="query", type="string", required=True, description="Search query."),
        ToolParam(name="sender", type="string", required=False, description="Filter by sender."),
        ToolParam(name="date", type="string", required=False, description="Filter by date."),
    ],
)

HONCHO_SESSION_TOOL = ToolDecl(
    name="honcho_session", description="Current session history and summary.", parameters=[]
)

HONCHO_ASK_TOOL = ToolDecl(
    name="honcho_ask",
    description="Ask about the user. depth='quick' for facts, 'thorough' for synthesis.",
    parameters=[
        ToolParam(
            name="question", type="string", required=True, description="The question to ask."
        ),
        ToolParam(name="depth", type="string", required=False, description="quick or thorough."),
    ],
)


class HonchoPlugin(ToolPlugin):
    """Honcho Plugin mapping to OpenClaw's honcho integration."""

    def __init__(self) -> None:
        self._tools = [
            HONCHO_CONTEXT_TOOL,
            HONCHO_SEARCH_CONCLUSIONS_TOOL,
            HONCHO_SEARCH_MESSAGES_TOOL,
            HONCHO_SESSION_TOOL,
            HONCHO_ASK_TOOL,
        ]
        self._client: HonchoClient | None = None

    def init(self, ctx: Any) -> None:
        """Lifecycle hook."""
        api = ctx
        # Setup config
        api_cfg = getattr(api, "config", None) or {}
        config = (
            api_cfg.get("plugins.entries.openclaw-honcho.config", {})
            if hasattr(api_cfg, "get")
            else {}
        )
        api_key = config.get("apiKey", "")
        workspace_id = config.get("workspaceId", "openclaw")
        base_url = config.get("baseUrl", "https://api.honcho.dev")

        self._client = HonchoClient(api_key, workspace_id, base_url)

        async def _before_prompt_build(event: Any) -> None:
            # Inject context into prompt
            if self._client:
                ctx = await self._client.get_context()
                if not ctx:
                    return
                if isinstance(event, dict):
                    prompt_val = event.get("prompt")
                    if isinstance(prompt_val, list):
                        prompt_val.append({"role": "system", "content": f"Honcho Context: {ctx}"})
                    elif isinstance(prompt_val, str):
                        event["prompt"] = f"{prompt_val}\n\nHoncho Context: {ctx}"
                    elif "messages" in event and isinstance(event["messages"], list):
                        event["messages"].append(
                            {"role": "system", "content": f"Honcho Context: {ctx}"}
                        )
                    if "appendContext" in event:
                        event["appendContext"] = (
                            f"{event.get('appendContext', '')}\nHoncho Context: {ctx}".strip()
                        )
                    elif "prependContext" in event:
                        event["prependContext"] = (
                            f"{event.get('prependContext', '')}\nHoncho Context: {ctx}".strip()
                        )

        async def _after_turn(event: Any) -> None:
            if self._client:
                # Observe turn
                await self._client.observe_turn(event)

        api.register_hook("before_prompt_build", _before_prompt_build, priority=15)
        api.register_hook("after_turn", _after_turn, priority=15)

    def register(self, api: Any) -> None:
        self.init(api)
        api.register_tool(self)

    @property
    def tools(self) -> list[ToolDecl]:
        return self._tools

    async def call(self, name: str, args: dict[str, Any]) -> Result[str]:
        if not self._client:
            return Err("Honcho client not initialized.", code="NOT_INITIALIZED")

        try:
            if name == "honcho_context":
                res = await self._client.get_context()
                return Ok(str(res))
            elif name == "honcho_search_conclusions":
                query = args.get("query", "")
                res = await self._client.search_conclusions(query)
                return Ok(str(res))
            elif name == "honcho_search_messages":
                query = args.get("query", "")
                sender = args.get("sender")
                date = args.get("date")
                res = await self._client.search_messages(query, sender, date)
                return Ok(str(res))
            elif name == "honcho_session":
                res = await self._client.get_session()
                return Ok(str(res))
            elif name == "honcho_ask":
                question = args.get("question", "")
                depth = args.get("depth", "quick")
                res = await self._client.ask(question, depth)
                return Ok(str(res))
            return Err(f"Unknown tool: {name}", code="UNKNOWN_TOOL")
        except Exception as e:
            return Err(f"Honcho tool failed: {e}", code="RUNTIME_ERROR")


honcho_plugin = HonchoPlugin()
entry = honcho_plugin

__all__ = ["HonchoPlugin", "honcho_plugin", "entry"]
