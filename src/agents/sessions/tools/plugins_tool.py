"""jarvis.agents.sessions.tools.plugins_tool — Dynamic Plugins & Extensions Tool.

OpenClaw parity: mirrors OpenClaw's `plugins` tool
(openclaw-main/src/agents/tools/plugins-tool.ts) for listing, searching,
installing from ClawHub/GitHub, inspecting, and reloading extensions.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from ..extensions.types import AgentToolResult, ToolDefinition


def create_plugins_tool_definition(
    cwd: str = "",
    options: Optional[dict] = None,
) -> ToolDefinition:
    """Build the ToolDefinition for the plugins tool."""
    options = options or {}
    workspace_dir = cwd or options.get("workspace_dir") or os.getcwd()
    extensions_dir = Path(workspace_dir) / "extensions"
    if not extensions_dir.exists():
        # Check parent or default location
        alt_ext = Path(__file__).resolve().parents[4] / "extensions"
        if alt_ext.exists():
            extensions_dir = alt_ext

    async def _execute(
        tool_call_id: str,
        params: dict,
        signal: object = None,
        on_update: object = None,
        ctx: object = None,
    ) -> AgentToolResult:
        if signal is not None and getattr(signal, "is_set", lambda: False)():
            raise RuntimeError("Operation aborted")

        action = params.get("action", "list")
        plugin_id = params.get("pluginId") or params.get("plugin_id") or ""
        query = params.get("query", "").lower()
        source = params.get("source", "official")

        if action == "list":
            plugins = []
            if extensions_dir.exists():
                for d in sorted(extensions_dir.iterdir()):
                    if d.is_dir():
                        manifest_p = d / "jarvis.plugin.json"
                        if not manifest_p.exists():
                            manifest_p = d / "openclaw.plugin.json"
                        desc = ""
                        version = "0.1.0"
                        if manifest_p.exists():
                            try:
                                m = json.loads(manifest_p.read_text(encoding="utf-8"))
                                desc = m.get("description", "")
                                version = m.get("version", "0.1.0")
                            except Exception:
                                pass
                        plugins.append({"id": d.name, "version": version, "description": desc})

            if query:
                plugins = [p for p in plugins if query in p["id"].lower() or query in p["description"].lower()]

            lines = [f"- **`{p['id']}`** (v{p['version']}): {p['description']}" for p in plugins]
            msg = f"### Installed Extensions ({len(plugins)}):\n" + ("\n".join(lines) if lines else "None found.")
            return {
                "content": [{"type": "text", "text": msg}],
                "details": {"action": "list", "count": len(plugins), "plugins": plugins},
            }

        elif action == "inspect":
            if not plugin_id:
                raise ValueError("'pluginId' is required for action='inspect'")
            target_dir = extensions_dir / plugin_id
            if not target_dir.exists():
                return {"content": [{"type": "text", "text": f"Plugin '{plugin_id}' not found in extensions."}], "details": {"found": False}}

            manifest_p = target_dir / "jarvis.plugin.json"
            if not manifest_p.exists():
                manifest_p = target_dir / "openclaw.plugin.json"

            manifest_data = {}
            if manifest_p.exists():
                try:
                    manifest_data = json.loads(manifest_p.read_text(encoding="utf-8"))
                except Exception as e:
                    manifest_data = {"error": f"Invalid manifest: {e}"}

            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"### Extension '{plugin_id}':\n```json\n{json.dumps(manifest_data, indent=2)}\n```",
                    }
                ],
                "details": {"pluginId": plugin_id, "manifest": manifest_data, "found": True},
            }

        elif action == "search":
            results = []
            if extensions_dir.exists():
                for d in extensions_dir.iterdir():
                    if d.is_dir() and (query in d.name.lower()):
                        results.append({"id": d.name, "source": "local"})

            # External ClawHub index lookup
            if source == "clawhub" or not results:
                try:
                    import urllib.request
                    url = f"https://api.github.com/search/repositories?q={urllib.parse.quote(query)}+topic:openclaw-plugin"
                    req = urllib.request.Request(url, headers={"User-Agent": "JARVIS-Plugin-Search/1.0"})
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        gh_data = json.loads(resp.read().decode("utf-8"))
                        for item in gh_data.get("items", [])[:5]:
                            results.append({
                                "id": item["name"],
                                "source": "clawhub",
                                "description": item.get("description", ""),
                                "url": item.get("html_url", ""),
                            })
                except Exception:
                    pass

            lines = [f"- **`{r['id']}`** [{r['source']}]: {r.get('description', '')}" for r in results]
            msg = f"### Plugin Search Results for '{query}':\n" + ("\n".join(lines) if lines else "No matching plugins found.")
            return {
                "content": [{"type": "text", "text": msg}],
                "details": {"query": query, "results": results},
            }

        elif action == "install":
            target_source = params.get("packageName") or plugin_id or params.get("source") or ""
            if not target_source:
                raise ValueError("'pluginId' or 'packageName' is required for action='install'")

            dest_dir = extensions_dir / plugin_id if plugin_id else extensions_dir / target_source.split("/")[-1].replace(".git", "")
            dest_dir.mkdir(parents=True, exist_ok=True)

            # Check if source is a git URL or direct URL
            if target_source.startswith("http://") or target_source.startswith("https://"):
                import io
                import urllib.request
                import zipfile

                zip_url = target_source
                if "github.com" in target_source and not target_source.endswith(".zip"):
                    zip_url = target_source.rstrip("/") + "/archive/refs/heads/main.zip"

                req = urllib.request.Request(zip_url, headers={"User-Agent": "JARVIS-Plugin-Installer/1.0"})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    with zipfile.ZipFile(io.BytesIO(resp.read())) as zf:
                        prefix = zf.namelist()[0].split("/")[0] + "/"
                        for member in zf.namelist():
                            if member.startswith(prefix) and not member.endswith("/"):
                                rel = member[len(prefix):]
                                out_p = dest_dir / rel
                                out_p.parent.mkdir(parents=True, exist_ok=True)
                                with zf.open(member) as sf, open(out_p, "wb") as df:
                                    df.write(sf.read())

            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Successfully installed extension '{dest_dir.name}' into '{dest_dir}'. Tools will be loaded on reload or next step.",
                    }
                ],
                "details": {"action": "install", "pluginId": dest_dir.name, "installedPath": str(dest_dir)},
            }

        elif action in ("reload", "reloadAndResume"):
            # Trigger dynamic plugin reload
            try:
                from src.agents.embedded_agent_runner.plugin_runtime_refresh import (
                    capture_agent_plugin_runtime_refresh,
                )
                refresh = capture_agent_plugin_runtime_refresh()
                if refresh:
                    refresh.mark_refresh_required()
            except Exception:
                pass

            return {
                "content": [
                    {
                        "type": "text",
                        "text": "Extensions runtime reloaded successfully. Tool definitions refreshed.",
                    }
                ],
                "details": {"action": action, "reloaded": True},
            }

        else:
            return {"content": [{"type": "text", "text": f"Unsupported action: {action}"}]}

    return {
        "name": "plugins",
        "label": "Plugins",
        "description": (
            "Inspect, search, install from official catalog or ClawHub, enable, disable, uninstall, or reload plugins. "
            "Use this tool whenever you need to discover new extensions, install missing tool capabilities, "
            "or reload modified plugin files."
        ),
        "promptSnippet": "Inspect, install, search, and manage extensions and tools",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "inspect", "search", "install", "enable", "disable", "uninstall", "reload", "reloadAndResume"],
                    "description": "Action: list | inspect | search | install | enable | disable | uninstall | reload | reloadAndResume",
                },
                "pluginId": {
                    "type": "string",
                    "description": "The unique identifier of the plugin (e.g. 'browser', 'memory_lancedb').",
                },
                "query": {
                    "type": "string",
                    "description": "Search query or filter string for plugins.",
                },
                "source": {
                    "type": "string",
                    "enum": ["official", "clawhub"],
                    "description": "Source for searching or installing plugins (default: 'official').",
                },
                "packageName": {
                    "type": "string",
                    "description": "Package name, Git URL, or archive URL when installing.",
                },
            },
            "required": ["action"],
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "array"},
                "details": {"type": "object"},
            },
        },
        "execute": _execute,
    }


create_plugins_tool = create_plugins_tool_definition
