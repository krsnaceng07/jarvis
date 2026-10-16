"""Native Codex plugin discovery tool.

OpenClaw parity: mirrors `extensions/codex/src/native-plugin-tool.ts`.

Exposes the `codex_plugins` tool that lets owners discover which native
Codex plugins are available in the connected Codex app-server without
installing or enabling them. The tool queries the app-server plugin inventory
and returns a curated, safe-to-display list.
"""

from __future__ import annotations

from typing import Any, Callable


async def _list_codex_plugins(
    request: Callable[[str, Any], Any],
    get_plugin_config: Callable[[], Any],
) -> dict[str, Any]:
    """Query the app-server for available native plugins."""
    try:
        result = await request("plugin/list", {"installed": False})
    except Exception as exc:
        return {"error": str(exc), "plugins": []}

    raw_plugins = result.get("plugins", []) if isinstance(result, dict) else []
    plugins: list[dict[str, Any]] = []
    for item in raw_plugins:
        if not isinstance(item, dict):
            continue
        entry: dict[str, Any] = {}
        for key in ("name", "marketplace", "version", "description", "enabled", "installed"):
            if key in item:
                entry[key] = item[key]
        if entry.get("name"):
            plugins.append(entry)
    return {"plugins": plugins}


def create_codex_plugins_tool(
    *,
    get_plugin_config: Callable[[], Any],
    context: Any = None,
) -> dict[str, Any]:
    """Return the `codex_plugins` tool descriptor.

    OpenClaw parity: mirrors `createCodexPluginsTool`
    (`native-plugin-tool.ts`). The tool is registered unconditionally
    (owner gating happens at the `api.register_tool` call site in
    `plugin.py`).
    """
    return {
        "name": "codex_plugins",
        "description": (
            "Discover available Codex plugins without installing or enabling them. "
            "Lists plugins from the connected Codex app-server marketplace inventory."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        "_handler": lambda req, params: _list_codex_plugins(req, get_plugin_config),
    }


__all__ = ["create_codex_plugins_tool"]
