from dataclasses import dataclass, field
from typing import Any
from jarvis_sdk import Plugin
from .tool import register_diffs_tool
from .store import DiffArtifactStore
import os

DIFFS_AGENT_GUIDANCE = """
# `diffs` tool usage
You can generate visual diffs using the `diffs` tool. This tool will return a URL where the diff can be viewed.
You can optionally render a PNG or PDF of the diff.
When you output a file path, users can use the `message` tool to upload it to the conversation.
"""


@dataclass(frozen=True, slots=True)
class DiffsPlugin(Plugin):
    id: str = "diffs"
    name: str = "Diffs Viewer"
    kind: str = "tool"
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        pass

    def register(self, api: Any) -> None:
        # Create store
        # In OpenClaw, it stores artifacts in tmp dir. We'll use a fixed path or from api.
        root_dir = os.path.join(os.path.expanduser("~"), ".jarvis", "tmp", "openclaw-diffs")
        os.makedirs(root_dir, exist_ok=True)
        store = DiffArtifactStore(root_dir=root_dir)

        # Register tool
        register_diffs_tool(api, store)

        # Register HTTP Route (Stub for viewer)
        # Note: Depending on jarvis_sdk api, we map the HTTP handler here.
        # Currently, if Jarvis API has register_http_route we call it.
        if hasattr(api, "register_http_route"):

            def http_handler(request: Any) -> Any:
                # Basic viewer handler stub
                # A complete HTTP handler would serve the viewer HTML from `store.read_authorized_viewer`
                pass

            api.register_http_route(
                path="/plugins/diffs", auth="plugin", match="prefix", handler=http_handler
            )

        # Hook for prompt guidance
        if hasattr(api, "on"):
            api.on("before_prompt_build", lambda: {"prependSystemContext": DIFFS_AGENT_GUIDANCE})


diffs_plugin = DiffsPlugin()
entry = diffs_plugin
