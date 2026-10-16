import logging
from typing import Any
from pathlib import Path
import glob

_log = logging.getLogger("jarvis.hooks.bootstrap_extra_files")

def handle(event: Any) -> None:
    """Injects additional bootstrap files configured via hook config."""
    if event.type != "agent" or event.action != "bootstrap":
        return

    # event.context contains: bootstrapFiles (list), agentId (str), cfg (dict)
    context = event.context
    if "bootstrapFiles" not in context:
        return

    # Fetch config for this hook
    cfg = context.get("cfg", {})
    hook_cfg = cfg.get("hooks", {}).get("internal", {}).get("entries", {}).get("bootstrap-extra-files", {})
    
    paths = hook_cfg.get("paths") or hook_cfg.get("patterns") or hook_cfg.get("files") or []
    if not paths:
        return

    workspace_dir_str = context.get("workspaceDir")
    if not workspace_dir_str:
        return
        
    workspace_dir = Path(workspace_dir_str)
    
    allowed_basenames = {"AGENTS.md", "SOUL.md", "IDENTITY.md", "USER.md", "BOOTSTRAP.md", "MEMORY.md"}
    
    # OpenClaw explicitly ignores TOOLS.md now via doctor --fix, but we ignore it on load too
    ignored_basenames = {"TOOLS.md"}

    injected: list[str] = []
    for pattern in paths:
        try:
            # Safe globbing inside workspace
            search_path = workspace_dir / pattern
            matches = glob.glob(str(search_path), recursive=True)
            for match in matches:
                p = Path(match)
                if not p.is_file():
                    continue
                if p.name in ignored_basenames:
                    continue
                if p.name in allowed_basenames:
                    if str(p) not in context["bootstrapFiles"]:
                        context["bootstrapFiles"].append(str(p))
                        injected.append(str(p))
        except Exception as e:
            _log.warning("failed to resolve pattern %r: %s", pattern, e)

    if injected:
        _log.debug("injected %d extra bootstrap files", len(injected))
